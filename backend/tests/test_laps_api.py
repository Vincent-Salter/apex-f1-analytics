from unittest.mock import MagicMock

import psycopg
import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def api():
    with TestClient(main.app) as client:
        yield client


@pytest.fixture
def mock_database(monkeypatch):
    connection = MagicMock()
    cursor = MagicMock()

    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(main, "get_database_connection", connect)

    return connect, cursor


def test_returns_filtered_laps(api, mock_database):
    connect, cursor = mock_database

    # The endpoint first checks the session, then the driver.
    cursor.fetchone.side_effect = [
        {"session_key": 9558},
        {"driver_number": 11},
    ]

    cursor.fetchall.return_value = [
        {
            "session_key": 9558,
            "driver_number": 11,
            "lap_number": lap_number,
            "lap_started_at_utc": None,
            "lap_duration_seconds": 90.0,
            "is_pit_out_lap": False,
            "lap_time_status": "available",
            "is_eligible_for_timed_stats": True,
        }
        for lap_number in [3, 4, 5]
    ]

    response = api.get(
        "/api/sessions/9558/laps",
        params={
            "driver_number": 11,
            "start_lap": 3,
            "end_lap": 5,
        },
    )

    assert response.status_code == 200
    assert [lap["lap_number"] for lap in response.json()] == [3, 4, 5]

    # Check that the endpoint passes the filters to the SQL query.
    query, parameters = cursor.execute.call_args.args

    assert "lap_number >= %s" in query
    assert "lap_number <= %s" in query
    assert parameters == [9558, 11, 3, 5]
    connect.assert_called_once()


def test_rejects_reversed_range(api, mock_database):
    connect, _ = mock_database

    response = api.get(
        "/api/sessions/9558/laps",
        params={
            "driver_number": 11,
            "start_lap": 5,
            "end_lap": 3,
        },
    )

    assert response.status_code == 422
    connect.assert_not_called()


def test_requires_driver_number(api, mock_database):
    connect, _ = mock_database

    response = api.get("/api/sessions/9558/laps")

    assert response.status_code == 422
    connect.assert_not_called()


def test_unknown_session_returns_404(api, mock_database):
    _, cursor = mock_database
    cursor.fetchone.return_value = None

    response = api.get(
        "/api/sessions/999999999/laps",
        params={"driver_number": 11},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"


def test_unknown_driver_returns_404(api, mock_database):
    _, cursor = mock_database
    cursor.fetchone.side_effect = [
        {"session_key": 9558},
        None,
    ]

    response = api.get(
        "/api/sessions/9558/laps",
        params={"driver_number": 999},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Driver not found in this session"


def test_empty_range_returns_empty_list(api, mock_database):
    _, cursor = mock_database
    cursor.fetchone.side_effect = [
        {"session_key": 9558},
        {"driver_number": 11},
    ]
    cursor.fetchall.return_value = []

    response = api.get(
        "/api/sessions/9558/laps",
        params={
            "driver_number": 11,
            "start_lap": 999,
            "end_lap": 1000,
        },
    )

    assert response.status_code == 200
    assert response.json() == []


def test_database_failure_returns_safe_error(api, mock_database):
    connect, _ = mock_database
    connect.side_effect = psycopg.OperationalError(
        "Internal database failure"
    )

    response = api.get(
        "/api/sessions/9558/laps",
        params={"driver_number": 11},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Lap data is temporarily unavailable"
    )
    assert "Internal database failure" not in response.text
