"""Load one Databricks serving export into local PostgreSQL.

SETUP
1. Save this file as apex/pipeline/load_serving_export.py.
2. Keep sessions.json, drivers.json, laps.json and manifest.json together
   under apex/data/serving_exports/<export_id>/.
3. From apex/backend, activate the existing Python environment:
       source .venv/bin/activate
4. Run, replacing YOUR_EXPORT_ID with the actual export folder name:
       python ../pipeline/load_serving_export.py ../data/serving_exports/YOUR_EXPORT_ID

Dependencies: psycopg[binary], python-dotenv (already installed in backend).
Database password: read from apex/infrastructure/.env; never printed.

Behaviour: validate the export, stage all three datasets, then replace
one session's serving data in one transaction. Failure rolls back everything.
This is a manual development loader, not an automated Databricks connection.
Run one loader at a time. Only load the intended latest completed export:
this loader does not reject older snapshots automatically.
"""

import argparse
import hashlib
import json
from pathlib import Path

import psycopg
from psycopg import sql
from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]

COLUMNS = {
    "sessions": [
        "session_key", "meeting_key", "session_name", "session_type",
        "circuit_short_name", "country_name", "session_started_at_utc",
    ],
    "drivers": [
        "session_key", "driver_number", "full_name", "name_acronym",
        "team_name", "team_colour",
    ],
    "laps": [
        "session_key", "driver_number", "lap_number", "lap_started_at_utc",
        "lap_duration_seconds", "sector_1_seconds", "sector_2_seconds",
        "sector_3_seconds", "is_pit_out_lap", "lap_time_status",
        "is_eligible_for_timed_stats", "delta_to_previous_lap_seconds",
        "rolling_5_lap_average_seconds", "rolling_5_lap_sample_count",
        "source_run_id", "source_retrieved_at_utc",
    ],
}

KEYS = {
    "sessions": ["session_key"],
    "drivers": ["session_key", "driver_number"],
    "laps": ["session_key", "driver_number", "lap_number"],
}


def validate_export(folder):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))

    if manifest.get("status") != "complete":
        raise ValueError("Export manifest is not complete")
    if manifest.get("contract_version") != 1:
        raise ValueError("Unsupported export contract version")

    session_key = manifest.get("session_key")
    if type(session_key) is not int or session_key <= 0:
        raise ValueError("Manifest session_key must be a positive integer")

    entries = manifest.get("files")
    if not isinstance(entries, list) or len(entries) != len(COLUMNS):
        raise ValueError("Expected exactly three export files")
    if {entry["dataset"] for entry in entries} != set(COLUMNS):
        raise ValueError("Expected sessions, drivers and laps datasets")

    datasets = {}
    for entry in entries:
        name = entry["dataset"]
        filename = f"{name}.json"
        if entry["filename"] != filename:
            raise ValueError(f"Unexpected filename for {name}")

        content = (folder / filename).read_bytes()
        if hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise ValueError(f"Checksum mismatch: {filename}")

        records = json.loads(content)
        if not isinstance(records, list) or not records:
            raise ValueError(f"Empty or invalid dataset: {name}")
        if len(records) != entry["record_count"]:
            raise ValueError(f"Record-count mismatch: {name}")

        seen_keys = set()
        for record in records:
            if not isinstance(record, dict) or set(record) != set(COLUMNS[name]):
                raise ValueError(f"Column contract mismatch in {name}")
            if record["session_key"] != session_key:
                raise ValueError(f"Unexpected session in {name}")

            key = tuple(record[column] for column in KEYS[name])
            if any(type(value) is not int or value <= 0 for value in key):
                raise ValueError(f"Invalid key in {name}: {key}")
            if key in seen_keys:
                raise ValueError(f"Duplicate key in {name}: {key}")
            seen_keys.add(key)

        datasets[name] = records
        print(f"Validated {name}: {len(records)} records")

    if len(datasets["sessions"]) != 1:
        raise ValueError("Expected exactly one session")

    driver_keys = {
        (row["session_key"], row["driver_number"])
        for row in datasets["drivers"]
    }
    for lap in datasets["laps"]:
        if (lap["session_key"], lap["driver_number"]) not in driver_keys:
            raise ValueError("Export contains a lap without a matching driver")

    return session_key, datasets


def load_export(session_key, datasets):
    config = dotenv_values(PROJECT_ROOT / "infrastructure" / ".env")
    password = config.get("POSTGRES_PASSWORD")
    if not password:
        raise ValueError("POSTGRES_PASSWORD missing from infrastructure/.env")

    # The connection context commits on success and rolls back on exception.
    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="apex",
        user="apex_app",
        password=password,
        connect_timeout=10,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'UTC'")

            # Stage and type-check everything before replacing serving data.
            for name, columns in COLUMNS.items():
                stage = f"stage_{name}"
                cursor.execute(
                    sql.SQL(
                        "CREATE TEMP TABLE {} "
                        "(LIKE {} INCLUDING DEFAULTS INCLUDING CONSTRAINTS) "
                        "ON COMMIT DROP"
                    ).format(
                        sql.Identifier(stage),
                        sql.Identifier("analytics", name),
                    )
                )

                copy_statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
                    sql.Identifier(stage),
                    sql.SQL(", ").join(map(sql.Identifier, columns)),
                )
                with cursor.copy(copy_statement) as copy:
                    for record in datasets[name]:
                        copy.write_row(tuple(record[column] for column in columns))

                print(f"Staged {name}")

            # Delete child rows before parent rows to respect foreign keys.
            for name in ["laps", "drivers", "sessions"]:
                cursor.execute(
                    sql.SQL("DELETE FROM {} WHERE session_key = %s").format(
                        sql.Identifier("analytics", name)
                    ),
                    (session_key,),
                )

            # Insert parents before children. Target foreign keys also validate.
            for name, columns in COLUMNS.items():
                column_list = sql.SQL(", ").join(map(sql.Identifier, columns))
                cursor.execute(
                    sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {}").format(
                        sql.Identifier("analytics", name),
                        column_list,
                        column_list,
                        sql.Identifier(f"stage_{name}"),
                    )
                )

                cursor.execute(
                    sql.SQL(
                        "SELECT COUNT(*) FROM {} WHERE session_key = %s"
                    ).format(sql.Identifier("analytics", name)),
                    (session_key,),
                )
                actual = cursor.fetchone()[0]
                expected = len(datasets[name])
                if actual != expected:
                    raise ValueError(f"Loaded count mismatch for {name}")
                print(f"Reconciled {name}: {actual} rows")

    print(f"Committed serving data for session {session_key}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export_folder", type=Path)
    args = parser.parse_args()

    # File validation happens before any database changes.
    session_key, datasets = validate_export(args.export_folder.resolve())
    load_export(session_key, datasets)


if __name__ == "__main__":
    main()
