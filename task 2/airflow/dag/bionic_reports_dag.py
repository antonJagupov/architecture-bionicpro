from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
import clickhouse_connect
import pandas as pd
import requests
import json
from io import StringIO

default_args = {
    'owner': 'bionic',
    'depends_on_past': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
    'start_date': datetime(2025, 1, 1),
}

dag = DAG(
    'bionic_daily_report_etl',
    default_args=default_args,
    description='ETL for user reports from CRM and telemetry',
    schedule_interval='0 2 * * *',
    catchup=False,
    tags=['bionic', 'reports'],
)

def extract_crm(**context):
    """Извлечение данных из CRM (Битрикс24) через REST API"""
    # Заглушка: в реальности используйте OAuth и пагинацию
    # Здесь имитируем получение данных
    # Пример ответа от CRM:
    crm_data = [
        {"ID": 1, "NAME": "User", "LAST_NAME": "One", "UF_PROSTHESIS_SN": "PR-001"},
        {"ID": 2, "NAME": "User", "LAST_NAME": "Two", "UF_PROSTHESIS_SN": "PR-002"},
    ]
    users_df = pd.DataFrame(crm_data)
    context['ti'].xcom_push(key='crm_users', value=users_df.to_json())
    return 'CRM extracted'

def extract_telemetry(**context):
    """Извлечение телеметрии из PostgreSQL за вчерашний день"""
    pg_hook = PostgresHook(postgres_conn_id='bionic_postgres')
    yesterday = (datetime.now() - timedelta(days=0)).strftime('%Y-%m-%d')
    sql = f"""
        SELECT user_id, timestamp, movement_type, response_time_ms, battery_voltage
        FROM telemetry
        WHERE DATE(timestamp) = '{yesterday}'
    """
    df = pg_hook.get_pandas_df(sql)
    context['ti'].xcom_push(key='telemetry_df', value=df.to_json())
    return 'Telemetry extracted'

def transform_and_load(**context):
    """Трансформация и загрузка в ClickHouse"""
    ti = context['ti']
    users_json = ti.xcom_pull(key='crm_users', task_ids='extract_crm')
    tele_json = ti.xcom_pull(key='telemetry_df', task_ids='extract_telemetry')

    users_df = pd.read_json(users_json)
    tele_df = pd.read_json(tele_json)

    if tele_df.empty:
        print("No telemetry data for yesterday, skipping load.")
        return "No data"

    # Агрегация телеметрии по пользователю и дате
    tele_df['timestamp'] = pd.to_datetime(tele_df['timestamp'])
    tele_df['report_date'] = tele_df['timestamp'].dt.date
    tele_df['user_id'] = tele_df['user_id'].astype(str)
    
    agg = tele_df.groupby(['user_id', 'report_date']).agg(
        total_movements=('movement_type', 'count'),
        avg_response_ms=('response_time_ms', 'mean'),
        battery_drain_pct=('battery_voltage', lambda x: (x.max() - x.min()) / x.max() * 100 if x.max() != 0 else 0),
        session_count=('timestamp', lambda x: x.diff().gt(pd.Timedelta(minutes=5)).cumsum().nunique())
    ).reset_index()

    # Добавляем версию прошивки (для примера)
    agg['firmware_version'] = 'v2.1'
    agg['user_id'] = agg['user_id'].astype(str)

    # Подключение к ClickHouse
    ch_client = clickhouse_connect.get_client(
        host='clickhouse',
        port=8123,
        username='default',
        password=''
    )
    # Создаём базу данных и таблицу, если не существуют
    ch_client.command("CREATE DATABASE IF NOT EXISTS bionic")
    ch_client.command("""
        CREATE TABLE IF NOT EXISTS bionic.user_daily_report (
            user_id          String,
            report_date      Date,
            total_movements  UInt32,
            avg_response_ms  Float32,
            battery_drain_pct Float32,
            session_count    UInt32,
            firmware_version String
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(report_date)
        ORDER BY (user_id, report_date)
    """)

    # Удаляем данные за этот день (чтобы избежать дублирования)
    report_date = agg['report_date'].iloc[0]
    ch_client.command(f"ALTER TABLE bionic.user_daily_report DELETE WHERE report_date = '{report_date}'")

    # Вставка данных
    ch_client.insert_df(table='bionic.user_daily_report', dataframe=agg)

    return 'Load completed'

with dag:
    t1 = PythonOperator(task_id='extract_crm', python_callable=extract_crm)
    t2 = PythonOperator(task_id='extract_telemetry', python_callable=extract_telemetry)
    t3 = PythonOperator(task_id='transform_and_load', python_callable=transform_and_load)

    [t1, t2] >> t3