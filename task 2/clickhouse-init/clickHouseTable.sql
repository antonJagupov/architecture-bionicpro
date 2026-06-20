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
ORDER BY (user_id, report_date);

INSERT INTO bionic.user_daily_report VALUES
('cd009cf2-8c0d-41a2-87dc-8a1a272c4328', '2026-05-07', 120, 85.2, 12.5, 8, 'v2.1'),
('cd009cf2-8c0d-41a2-87dc-8a1a272c4328', '2026-05-08', 135, 79.8, 11.2, 9, 'v2.1');
