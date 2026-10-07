# Databricks notebook source
dbutils.widgets.text("session_key", "9558", "Session key")

SESSION_KEY = int(dbutils.widgets.get("session_key"))

if SESSION_KEY <= 0:
    raise ValueError("session_key must be positive")

print(f"Ingesting session {SESSION_KEY}")


# COMMAND ----------


CATALOG = "apex"

SCHEMA = "apex-raw"
VOLUME = "source_files"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{CATALOG}`.`{SCHEMA}`")

spark.sql(
    f"CREATE VOLUME IF NOT EXISTS "
    f"`{CATALOG}`.`{SCHEMA}`.`{VOLUME}`"
)

RAW_ROOT = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"

print(f"Raw storage location: {RAW_ROOT}")


# COMMAND ----------

import json
from datetime import datetime, timezone
from pathlib import Path

check_folder = Path(RAW_ROOT) / "_checks"
check_folder.mkdir(parents=True, exist_ok=True)

check_file = check_folder / "storage_check.json"

metadata = {
    "project": "apex",
    "purpose": "storage-connectivity-check",
    "checked_at_utc": datetime.now(timezone.utc).isoformat(),
}

check_file.write_text(
    json.dumps(metadata, indent=2),
    encoding="utf-8",
)

print(f"Created: {check_file}")
print(check_file.read_text(encoding="utf-8"))


# COMMAND ----------

import json
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://api.openf1.org/v1"

RAW_ROOT = "/Volumes/apex/apex-raw/source_files"


def fetch_json(endpoint, params):
    url = f"{BASE_URL}/{endpoint}?{urlencode(params)}"

    # Retry temporary server errors and rate-limit responses.
    for attempt in range(3):
        try:
            request = Request(
                url,
                headers={"Accept": "application/json"},
            )

            with urlopen(request, timeout=60) as response:
                raw_bytes = response.read()

            records = json.loads(raw_bytes)

            if not isinstance(records, list):
                raise ValueError(f"Expected a list from {endpoint}")

            return url, raw_bytes, records

        except HTTPError as error:
            retryable = error.code == 429 or 500 <= error.code < 600

            if not retryable or attempt == 2:
                raise

            time.sleep(2 ** (attempt + 1))


_, _, sessions = fetch_json(
    "sessions",
    {"session_key": SESSION_KEY},
)

if len(sessions) != 1:
    raise ValueError(
        f"Expected one session for {SESSION_KEY}, "
        f"found {len(sessions)}"
    )

session = sessions[0]

if session.get("session_key") != SESSION_KEY:
    raise ValueError("Returned session does not match the requested session")

print(json.dumps(session, indent=2))

print(f"Selected session: {SESSION_KEY}")


# COMMAND ----------

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

started_at = datetime.now(timezone.utc)
run_id = f"{started_at.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"

run_folder = (
    Path(RAW_ROOT)
    / "openf1"
    / f"session_key={SESSION_KEY}"
    / f"run_id={run_id}"
)

run_folder.mkdir(parents=True, exist_ok=False)

manifest = {
    "source": "openf1",
    "session_key": SESSION_KEY,
    "run_id": run_id,
    "started_at_utc": started_at.isoformat(),
    "files": [],
}

for endpoint in ["sessions", "drivers", "laps"]:
    url, raw_bytes, records = fetch_json(
        endpoint,
        {"session_key": SESSION_KEY},
    )

    if not records:
        raise ValueError(f"No records returned from {endpoint}")

    filename = f"{endpoint}.json"
    output_file = run_folder / filename

    # Preserve the response body without cleaning or restructuring it.
    output_file.write_bytes(raw_bytes)

    manifest["files"].append({
        "endpoint": endpoint,
        "request_url": url,
        "filename": filename,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "byte_count": len(raw_bytes),
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
    })

    print(f"Saved {filename}: {len(records)} records")

    # Space requests rather than sending a burst.
    time.sleep(1)

manifest["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
manifest["status"] = "complete"

(run_folder / "manifest.json").write_text(
    json.dumps(manifest, indent=2),
    encoding="utf-8",
)

print(f"\nCompleted ingestion: {run_folder}")


# COMMAND ----------

dbutils.jobs.taskValues.set(
    key="session_key",
    value=SESSION_KEY,
)

dbutils.jobs.taskValues.set(
    key="run_id",
    value=run_id,
)

print(f"Completed session: {SESSION_KEY}")
print(f"Completed ingestion run: {run_id}")
print(f"Raw folder: {run_folder}")
