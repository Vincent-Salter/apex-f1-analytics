# Databricks notebook source
dbutils.widgets.text("session_key", "9558", "Session key")
dbutils.widgets.text(
    "run_id",
    "20261007T125516Z_5762b047",
    "Ingestion run ID",
)

SESSION_KEY = int(dbutils.widgets.get("session_key"))
RUN_ID = dbutils.widgets.get("run_id").strip()

if SESSION_KEY <= 0:
    raise ValueError("session_key must be positive")

if not RUN_ID or any(character in RUN_ID for character in ["/", "\\", ".."]):
    raise ValueError("Invalid ingestion run ID")

print(f"Processing session {SESSION_KEY}, ingestion run {RUN_ID}")


# COMMAND ----------

import hashlib
import json
from pathlib import Path

CATALOG = "apex"
BRONZE_SCHEMA = "apex_bronze"

RUN_FOLDER = (
    Path("/Volumes/apex/apex-raw/source_files/openf1")
    / f"session_key={SESSION_KEY}"
    / f"run_id={RUN_ID}"
)


manifest = json.loads(
    (RUN_FOLDER / "manifest.json").read_text(encoding="utf-8")
)

if manifest.get("status") != "complete":
    raise ValueError("This ingestion run is not complete")

if manifest.get("session_key") != SESSION_KEY:
    raise ValueError("Manifest session does not match the requested session")

if manifest.get("run_id") != RUN_ID:
    raise ValueError("Manifest run ID does not match the requested run")

if manifest.get("source") != "openf1":
    raise ValueError("Unexpected source in manifest")


expected_endpoints = {"sessions", "drivers", "laps"}
actual_endpoints = [entry["endpoint"] for entry in manifest["files"]]

if (
    set(actual_endpoints) != expected_endpoints
    or len(actual_endpoints) != len(expected_endpoints)
):
    raise ValueError("Expected exactly one file per endpoint")

# Validate every file before writing any tables.
validated_records = {}

for entry in manifest["files"]:
    raw_bytes = (RUN_FOLDER / entry["filename"]).read_bytes()

    if hashlib.sha256(raw_bytes).hexdigest() != entry["sha256"]:
        raise ValueError(f"Checksum mismatch: {entry['filename']}")

    records = json.loads(raw_bytes)

    if not isinstance(records, list):
        raise ValueError(f"Expected a JSON array: {entry['filename']}")

    if len(records) != entry["record_count"]:
        raise ValueError(f"Record-count mismatch: {entry['filename']}")

    validated_records[entry["endpoint"]] = records

    print(f"Validated {entry['filename']}: {len(records)} records")


# COMMAND ----------

from delta.tables import DeltaTable
from pyspark.sql import functions as F
from pyspark.sql.types import (
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
)

spark.sql(
    f"CREATE SCHEMA IF NOT EXISTS `{CATALOG}`.`{BRONZE_SCHEMA}`"
)

bronze_record_schema = StructType([
    StructField("source", StringType(), False),
    StructField("session_key", LongType(), False),
    StructField("run_id", StringType(), False),
    StructField("record_index", IntegerType(), False),
    StructField("source_file", StringType(), False),
    StructField("retrieved_at_utc", StringType(), False),
    StructField("payload_json", StringType(), False),
])

for entry in manifest["files"]:
    endpoint = entry["endpoint"]
    records = validated_records[endpoint]

    rows = [
        (
            manifest["source"],
            manifest["session_key"],
            manifest["run_id"],
            index,
            str(RUN_FOLDER / entry["filename"]),
            entry["retrieved_at_utc"],
            json.dumps(record, separators=(",", ":"), ensure_ascii=False),
        )
        for index, record in enumerate(records)
    ]

    bronze_df = (
        spark.createDataFrame(rows, schema=bronze_record_schema)
        .withColumn(
            "retrieved_at_utc",
            F.to_timestamp("retrieved_at_utc"),
        )
        .withColumn("bronze_loaded_at_utc", F.current_timestamp())
    )

    table_name = f"{CATALOG}.{BRONZE_SCHEMA}.{endpoint}"

    if not spark.catalog.tableExists(table_name):
        bronze_df.write.format("delta").mode("append").saveAsTable(
            table_name
        )
    else:
        (
            DeltaTable.forName(spark, table_name)
            .alias("target")
            .merge(
                bronze_df.alias("incoming"),
                """
                target.source = incoming.source
                AND target.session_key = incoming.session_key
                AND target.run_id = incoming.run_id
                AND target.record_index = incoming.record_index
                """,
            )
            .whenNotMatchedInsertAll()
            .execute()
        )

    print(f"Loaded {table_name}")


# COMMAND ----------

bronze_laps = spark.table("apex.apex_bronze.laps")

display(
    bronze_laps
    .filter(F.col("run_id") == manifest["run_id"])
    .orderBy("record_index")
    .select(
        "session_key",
        "run_id",
        "record_index",
        "payload_json",
        "retrieved_at_utc",
    )
    .limit(10)
)


# COMMAND ----------

for endpoint in ["sessions", "drivers", "laps"]:
    count = (
        spark.table(f"apex.apex_bronze.{endpoint}")
        .filter(F.col("run_id") == manifest["run_id"])
        .count()
    )

    expected = len(validated_records[endpoint])
    assert count == expected, f"Count mismatch for {endpoint}"

    print(f"{endpoint}: {count} rows — matches raw input")
