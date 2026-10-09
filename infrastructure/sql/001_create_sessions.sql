BEGIN;

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS analytics.sessions (
    session_key BIGINT PRIMARY KEY,
    meeting_key BIGINT,
    session_name TEXT,
    session_type TEXT,
    circuit_short_name TEXT,
    country_name TEXT,
    session_started_at_utc TIMESTAMPTZ,
    loaded_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMIT;