from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
import jwt
from jwt import PyJWKClient
import clickhouse_connect
import os
from datetime import date, datetime

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# Конфигурация Keycloak
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8080")
REALM = os.getenv("KEYCLOAK_REALM", "reports-realm")
JWKS_URL = f"http://keycloak:8080/realms/{REALM}/protocol/openid-connect/certs"

# Клиент для получения JWKS (публичных ключей)
jwks_client = PyJWKClient(JWKS_URL)

# Подключение к ClickHouse
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", 8123))
ch_client = clickhouse_connect.get_client(host=CLICKHOUSE_HOST, port=CLICKHOUSE_PORT, database="bionic")

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        # Получаем signing key из JWKS
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        # Декодируем и проверяем подпись, audience, issuer
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience="reports-frontend",   # clientId вашего фронтенда
            options={"verify_aud": False}
        )
        # Проверяем issuer
        expected_issuer = f"{KEYCLOAK_URL}/realms/{REALM}"
        if payload.get("iss") != expected_issuer:
            raise jwt.InvalidIssuerError("Invalid issuer")
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing subject")
        # Можно попробовать преобразовать в int, но sub обычно строка (UUID)
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Could not validate credentials: {str(e)}")

@app.get("/reports")
def get_report(
    current_user: str  = Depends(get_current_user),
    start_date: date = Query(..., description="Начальная дата отчёта (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Конечная дата отчёта (YYYY-MM-DD)")
):
    # Проверяем, что запрошенный период не превышает последнюю обработанную дату
    max_date_query = "SELECT max(report_date) FROM bionic.user_daily_report"
    last_processed = ch_client.query(max_date_query).first_row[0]
    if last_processed is None:
        raise HTTPException(status_code=404, detail="No data available yet")
    if end_date > last_processed:
        raise HTTPException(status_code=400, detail=f"Report data only up to {last_processed}. Please choose earlier end_date.")

    # Запрос витрины только для текущего пользователя
    query = """
        SELECT report_date, total_movements, avg_response_ms, battery_drain_pct, session_count, firmware_version
        FROM bionic.user_daily_report
        WHERE user_id = %(user_id)s AND report_date BETWEEN %(start)s AND %(end)s
        ORDER BY report_date
    """
    params = {"user_id": current_user, "start": start_date, "end": end_date}
    result = ch_client.query_df(query, parameters=params)
    if result.empty:
        raise HTTPException(status_code=404, detail="No reports found for this user and period")
    
    # Формируем JSON-отчёт
    report = {
        "user_id": current_user,
        "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
        "daily_stats": result.to_dict(orient="records"),
        "summary": {
            "total_movements": int(result["total_movements"].sum()),
            "avg_response_ms": round(result["avg_response_ms"].mean(), 2),
            "total_days": len(result)
        }
    }
    return report