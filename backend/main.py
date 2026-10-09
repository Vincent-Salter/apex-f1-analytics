from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import logging
from datetime import datetime
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from fastapi import HTTPException
from psycopg.rows import dict_row
from fastapi import Query


logger = logging.getLogger(__name__)

BACKEND_FOLDER = Path(__file__).resolve().parent
db_config = dotenv_values(BACKEND_FOLDER / ".env")


def get_database_connection():
    required_settings = [
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
    ]

    missing = [
        setting
        for setting in required_settings
        if not db_config.get(setting)
    ]

    if missing:
        raise RuntimeError(
            f"Missing database settings: {', '.join(missing)}"
        )

    return psycopg.connect(
        host=db_config["DB_HOST"],
        port=int(db_config["DB_PORT"]),
        dbname=db_config["DB_NAME"],
        user=db_config["DB_USER"],
        password=db_config["DB_PASSWORD"],
        connect_timeout=10,
        row_factory=dict_row,
        options="-c timezone=UTC -c statement_timeout=5000",
    )


app = FastAPI(
    title="Apex Analytics API",
    description="Backend for the Apex F1 analytics dashboard.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=[],
)

class DemoLap(BaseModel):
    lap: int
    lavender: float
    mint: float
    peach: float


class DemoLapsResponse(BaseModel):
    source: str
    laps: list[DemoLap]

class DriverResponse(BaseModel):
    session_key: int
    driver_number: int
    full_name: str | None
    name_acronym: str | None
    team_name: str | None
    team_colour: str | None

class SessionResponse(BaseModel):
    session_key: int
    meeting_key: int | None
    session_name: str | None
    session_type: str | None
    circuit_short_name: str | None
    country_name: str | None
    session_started_at_utc: datetime | None

class LapResponse(BaseModel):
    session_key: int
    driver_number: int
    lap_number: int
    lap_started_at_utc: datetime | None
    lap_duration_seconds: float | None
    is_pit_out_lap: bool | None
    lap_time_status: str
    is_eligible_for_timed_stats: bool
    delta_to_previous_lap_seconds: float | None
    rolling_5_lap_average_seconds: float | None
    rolling_5_lap_sample_count: int



@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "apex-api",
    }

@app.get("/api/demo/laps", response_model=DemoLapsResponse)
def get_demo_laps() -> DemoLapsResponse:
    return DemoLapsResponse(
        source="fictional-demo",
        laps=[
            DemoLap(lap=1, lavender=88.2, mint=88.9, peach=89.4),
            DemoLap(lap=2, lavender=87.1, mint=87.6, peach=88.3),
            DemoLap(lap=3, lavender=86.4, mint=87.0, peach=87.8),
            DemoLap(lap=4, lavender=86.9, mint=86.5, peach=87.1),
            DemoLap(lap=5, lavender=85.8, mint=86.2, peach=86.6),
            DemoLap(lap=6, lavender=86.2, mint=86.8, peach=87.0),
        ],
    )



@app.get("/api/sessions", response_model=list[SessionResponse])
def get_sessions():
    try:
        with get_database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        session_key,
                        meeting_key,
                        session_name,
                        session_type,
                        circuit_short_name,
                        country_name,
                        session_started_at_utc
                    FROM analytics.sessions
                    ORDER BY
                        session_started_at_utc DESC NULLS LAST,
                        session_key DESC
                    """
                )

                return cursor.fetchall()

    except (psycopg.Error, RuntimeError):
        logger.exception("Failed to retrieve sessions")

        raise HTTPException(
            status_code=503,
            detail="Session data is temporarily unavailable",
        ) from None



@app.get(
    "/api/sessions/{session_key}/drivers",
    response_model=list[DriverResponse],
)
def get_session_drivers(session_key: int):
    if session_key <= 0:
        raise HTTPException(
            status_code=422,
            detail="session_key must be positive",
        )

    try:
        with get_database_connection() as connection:
            with connection.cursor() as cursor:
                # Distinguish an unknown session from an empty driver list.
                cursor.execute(
                    """
                    SELECT session_key
                    FROM analytics.sessions
                    WHERE session_key = %s
                    """,
                    (session_key,),
                )

                if cursor.fetchone() is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Session not found",
                    )

                cursor.execute(
                    """
                    SELECT
                        session_key,
                        driver_number,
                        full_name,
                        name_acronym,
                        team_name,
                        team_colour
                    FROM analytics.drivers
                    WHERE session_key = %s
                    ORDER BY driver_number
                    """,
                    (session_key,),
                )

                return cursor.fetchall()

    except (psycopg.Error, RuntimeError):
        logger.exception("Failed to retrieve session drivers")

        raise HTTPException(
            status_code=503,
            detail="Driver data is temporarily unavailable",
        ) from None

@app.get(
    "/api/sessions/{session_key}/laps",
    response_model=list[LapResponse],
)
def get_session_laps(
    session_key: int,
    driver_number: int = Query(..., gt=0),
    start_lap: int = Query(1, ge=1),
    end_lap: int | None = Query(None, ge=1),
):
    if session_key <= 0:
        raise HTTPException(
            status_code=422,
            detail="session_key must be positive",
        )

    if end_lap is not None and end_lap < start_lap:
        raise HTTPException(
            status_code=422,
            detail="end_lap must be greater than or equal to start_lap",
        )

    try:
        with get_database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT session_key
                    FROM analytics.sessions
                    WHERE session_key = %s
                    """,
                    (session_key,),
                )

                if cursor.fetchone() is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Session not found",
                    )

                cursor.execute(
                    """
                    SELECT driver_number
                    FROM analytics.drivers
                    WHERE session_key = %s
                      AND driver_number = %s
                    """,
                    (session_key, driver_number),
                )

                if cursor.fetchone() is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Driver not found in this session",
                    )

                query = """
                    SELECT
                        session_key,
                        driver_number,
                        lap_number,
                        lap_started_at_utc,
                        lap_duration_seconds,
                        is_pit_out_lap,
                        lap_time_status,
                        is_eligible_for_timed_stats,
                        delta_to_previous_lap_seconds,
                        rolling_5_lap_average_seconds,
                        rolling_5_lap_sample_count
                    FROM analytics.laps
                    WHERE session_key = %s
                      AND driver_number = %s
                      AND lap_number >= %s
                """

                parameters = [
                    session_key,
                    driver_number,
                    start_lap,
                ]

                if end_lap is not None:
                    query += " AND lap_number <= %s"
                    parameters.append(end_lap)

                query += " ORDER BY lap_number"

                cursor.execute(query, parameters)
                return cursor.fetchall()

    except (psycopg.Error, RuntimeError):
        logger.exception("Failed to retrieve session laps")

        raise HTTPException(
            status_code=503,
            detail="Lap data is temporarily unavailable",
        ) from None
