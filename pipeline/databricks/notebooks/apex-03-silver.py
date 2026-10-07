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

spark.sql("SET TIME ZONE 'UTC'")

print(f"Processing session {SESSION_KEY}, ingestion run {RUN_ID}")


# COMMAND ----------

import json
from pyspark.sql import functions as F

CATALOG = "apex"
RUN_ID = "20261007T125516Z_5762b047"

for endpoint in ["sessions", "drivers", "laps"]:
    bronze = (
        spark.table(f"{CATALOG}.apex_bronze.{endpoint}")
        .filter(F.col("run_id") == RUN_ID)
    )

    first_record = (
        bronze.orderBy("record_index")
        .select("payload_json")
        .first()
    )

    if first_record is None:
        raise ValueError(f"No bronze records found for {endpoint}")

    print(f"\n--- {endpoint.upper()} ---")
    print(json.dumps(json.loads(first_record["payload_json"]), indent=2))


# COMMAND ----------

bronze_laps = (
    spark.table("apex.apex_bronze.laps")
    .filter(
        (F.col("run_id") == RUN_ID)
        & (F.col("session_key") == SESSION_KEY)
    )
)

if bronze_laps.count() == 0:
    raise ValueError("No bronze laps found for the requested session and run")


# Extract as strings first, so we can inspect source values
# before deciding on casting and validation rules.
lap_inspection = bronze_laps.select(
    "record_index",
    F.get_json_object("payload_json", "$.session_key").alias("session_key"),
    F.get_json_object("payload_json", "$.driver_number").alias("driver_number"),
    F.get_json_object("payload_json", "$.lap_number").alias("lap_number"),
    F.get_json_object("payload_json", "$.lap_duration").alias("lap_duration"),
    F.get_json_object("payload_json", "$.is_pit_out_lap").alias("is_pit_out_lap"),
    "payload_json",
)

display(lap_inspection.orderBy("record_index").limit(20))


# COMMAND ----------

display(
    lap_inspection.agg(
        F.count("*").alias("total_records"),
        F.sum(
            F.col("session_key").isNull().cast("int")
        ).alias("missing_session_keys"),
        F.sum(
            F.col("driver_number").isNull().cast("int")
        ).alias("missing_driver_numbers"),
        F.sum(
            F.col("lap_number").isNull().cast("int")
        ).alias("missing_lap_numbers"),
        F.sum(
            F.col("lap_duration").isNull().cast("int")
        ).alias("missing_lap_durations"),
    )
)

duplicate_keys = (
    lap_inspection
    .groupBy("session_key", "driver_number", "lap_number")
    .count()
    .filter(F.col("count") > 1)
)

display(duplicate_keys)


# COMMAND ----------

# Show the three records with missing lap durations.
display(
    lap_inspection
    .filter(F.col("lap_duration").isNull())
    .select(
        "session_key",
        "driver_number",
        "lap_number",
        "lap_duration",
        "is_pit_out_lap",
        "payload_json",
    )
)


# COMMAND ----------

# Count groups sharing the proposed session/driver/lap key.
duplicate_key_count = duplicate_keys.count()

print(f"Duplicate key groups: {duplicate_key_count}")

if duplicate_key_count > 0:
    display(duplicate_keys)


# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.types import (
    BooleanType,
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
)

lap_schema = StructType([
    StructField("meeting_key", LongType()),
    StructField("session_key", LongType()),
    StructField("driver_number", IntegerType()),
    StructField("lap_number", IntegerType()),
    StructField("date_start", StringType()),
    StructField("lap_duration", DoubleType()),
    StructField("is_pit_out_lap", BooleanType()),
    StructField("duration_sector_1", DoubleType()),
    StructField("duration_sector_2", DoubleType()),
    StructField("duration_sector_3", DoubleType()),
])

bronze_laps = (
    spark.table("apex.apex_bronze.laps")
    .filter(
        (F.col("run_id") == RUN_ID)
        & (F.col("session_key") == SESSION_KEY)
    )
)

if bronze_laps.count() == 0:
    raise ValueError("No bronze laps found for the requested session and run")


parsed_laps = bronze_laps.withColumn(
    "parsed",
    F.from_json("payload_json", lap_schema),
)

silver_laps = parsed_laps.select(
    F.col("parsed.meeting_key").alias("meeting_key"),
    F.col("parsed.session_key").alias("session_key"),
    F.col("parsed.driver_number").alias("driver_number"),
    F.col("parsed.lap_number").alias("lap_number"),
    F.expr("try_cast(parsed.date_start AS TIMESTAMP)").alias(
        "lap_started_at_utc"
    ),
    F.col("parsed.lap_duration").alias("lap_duration_seconds"),
    F.col("parsed.is_pit_out_lap").alias("is_pit_out_lap"),
    F.col("parsed.duration_sector_1").alias("sector_1_seconds"),
    F.col("parsed.duration_sector_2").alias("sector_2_seconds"),
    F.col("parsed.duration_sector_3").alias("sector_3_seconds"),
    "source",
    "run_id",
    "source_file",
    "retrieved_at_utc",
)


# COMMAND ----------

duration = F.col("lap_duration_seconds")

silver_laps = (
    silver_laps
    .withColumn(
        "lap_time_status",
        F.when(duration.isNull(), F.lit("missing"))
        .when(
            F.isnan(duration)
            | (F.abs(duration) == F.lit(float("inf")))
            | (duration <= 0),
            F.lit("invalid"),
        )
        .otherwise(F.lit("available")),
    )
    .withColumn(
        "is_eligible_for_timed_stats",
        (F.col("lap_time_status") == "available")
        & F.coalesce(
            F.col("is_pit_out_lap") == F.lit(False),
            F.lit(False),
        ),
    )
    .withColumn("silver_updated_at_utc", F.current_timestamp())
)

display(
    silver_laps
    .groupBy("lap_time_status", "is_eligible_for_timed_stats")
    .count()
)


# COMMAND ----------

invalid_keys = silver_laps.filter(
    F.col("session_key").isNull()
    | F.col("driver_number").isNull()
    | F.col("lap_number").isNull()
    | (F.col("session_key") <= 0)
    | (F.col("driver_number") <= 0)
    | (F.col("lap_number") <= 0)
)

duplicate_keys = (
    silver_laps
    .groupBy("session_key", "driver_number", "lap_number")
    .count()
    .filter(F.col("count") > 1)
)

# Also ensure parsing preserved the source session identifier.
session_mismatches = parsed_laps.filter(
    ~F.col("parsed.session_key").eqNullSafe(F.col("session_key"))
)

if invalid_keys.count() > 0:
    raise ValueError("Invalid lap identifiers: investigate before loading")

if duplicate_keys.count() > 0:
    raise ValueError("Duplicate lap keys: investigate before loading")

if session_mismatches.count() > 0:
    raise ValueError("Payload session does not match bronze metadata")

assert silver_laps.count() == bronze_laps.count(), "Records were lost"

print("Quality checks passed")


# COMMAND ----------

from delta.tables import DeltaTable

spark.sql("CREATE SCHEMA IF NOT EXISTS apex.apex_silver")

TABLE_NAME = "apex.apex_silver.laps"

if not spark.catalog.tableExists(TABLE_NAME):
    (
        silver_laps.write
        .format("delta")
        .mode("append")
        .saveAsTable(TABLE_NAME)
    )
else:
    (
        DeltaTable.forName(spark, TABLE_NAME)
        .alias("target")
        .merge(
            silver_laps.alias("incoming"),
            """
            target.session_key = incoming.session_key
            AND target.driver_number = incoming.driver_number
            AND target.lap_number = incoming.lap_number
            """,
        )
        .whenMatchedUpdateAll(
            condition="""
            incoming.retrieved_at_utc > target.retrieved_at_utc
            """
        )
        .whenNotMatchedInsertAll()
        .execute()
    )

print(f"Loaded {TABLE_NAME}")


# COMMAND ----------

saved_laps = (
    spark.table("apex.apex_silver.laps")
    .filter(F.col("session_key") == SESSION_KEY)
)

# Verify that every incoming lap key exists in silver.
lap_keys = ["session_key", "driver_number", "lap_number"]

missing_keys = (
    silver_laps.select(*lap_keys)
    .join(
        saved_laps.select(*lap_keys),
        on=lap_keys,
        how="left_anti",
    )
)

duplicate_groups = (
    saved_laps.groupBy(*lap_keys)
    .count()
    .filter(F.col("count") > 1)
)

incorrectly_eligible = saved_laps.filter(
    (F.col("lap_time_status") == "missing")
    & F.col("is_eligible_for_timed_stats")
)

assert missing_keys.count() == 0, "Incoming lap keys are missing from silver"
assert duplicate_groups.count() == 0, "Duplicate silver lap keys"
assert incorrectly_eligible.count() == 0, (
    "Missing-duration laps must not be eligible for timed statistics"
)

print(f"Incoming laps: {silver_laps.count()}")
print(f"Current silver laps for session: {saved_laps.count()}")
print("Passed: incoming keys present, unique keys, valid missing-time handling")


# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.types import (
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
)
from delta.tables import DeltaTable

RUN_ID = "20261007T125516Z_5762b047"

driver_schema = StructType([
    StructField("session_key", LongType()),
    StructField("meeting_key", LongType()),
    StructField("driver_number", IntegerType()),
    StructField("full_name", StringType()),
    StructField("name_acronym", StringType()),
    StructField("team_name", StringType()),
    StructField("team_colour", StringType()),
    StructField("country_code", StringType()),
])

session_schema = StructType([
    StructField("session_key", LongType()),
    StructField("meeting_key", LongType()),
    StructField("session_name", StringType()),
    StructField("session_type", StringType()),
    StructField("date_start", StringType()),
    StructField("date_end", StringType()),
    StructField("year", IntegerType()),
    StructField("country_name", StringType()),
    StructField("country_code", StringType()),
    StructField("circuit_key", LongType()),
    StructField("circuit_short_name", StringType()),
    StructField("location", StringType()),
])


# COMMAND ----------

def parse_bronze(endpoint, schema, key_columns):
    bronze = (
    spark.table(f"apex.apex_bronze.{endpoint}")
    .filter(
        (F.col("run_id") == RUN_ID)
        & (F.col("session_key") == SESSION_KEY)
    )
)


    if bronze.count() == 0:
        raise ValueError(f"No bronze records found for {endpoint}")

    parsed = bronze.withColumn(
        "parsed",
        F.from_json("payload_json", schema),
    )

    # Verify the source session matches the ingestion metadata.
    mismatches = parsed.filter(
        ~F.col("parsed.session_key").eqNullSafe(F.col("session_key"))
    )

    if mismatches.count() > 0:
        raise ValueError(f"Session mismatch in {endpoint}")

    result = parsed.select(
        "parsed.*",
        "source",
        "run_id",
        "source_file",
        "retrieved_at_utc",
    )

    invalid_key = F.lit(False)

    for column in key_columns:
        invalid_key = (
            invalid_key
            | F.col(column).isNull()
            | (F.col(column) <= 0)
        )

    if result.filter(invalid_key).count() > 0:
        raise ValueError(f"Missing or invalid keys in {endpoint}")

    duplicates = (
        result.groupBy(*key_columns)
        .count()
        .filter(F.col("count") > 1)
    )

    if duplicates.count() > 0:
        display(duplicates)
        raise ValueError(f"Duplicate keys in {endpoint}")

    return result.withColumn(
        "silver_updated_at_utc",
        F.current_timestamp(),
    )


silver_drivers = parse_bronze(
    "drivers",
    driver_schema,
    ["session_key", "driver_number"],
)

silver_sessions = parse_bronze(
    "sessions",
    session_schema,
    ["session_key"],
)


# COMMAND ----------

# Make timestamp display and interpretation consistent.
spark.sql("SET TIME ZONE 'UTC'")

silver_sessions = (
    silver_sessions
    .withColumn(
        "session_started_at_utc",
        F.expr("try_cast(date_start AS TIMESTAMP)"),
    )
    .withColumn(
        "session_ended_at_utc",
        F.expr("try_cast(date_end AS TIMESTAMP)"),
    )
)

invalid_timestamps = silver_sessions.filter(
    (
        F.col("date_start").isNotNull()
        & F.col("session_started_at_utc").isNull()
    )
    | (
        F.col("date_end").isNotNull()
        & F.col("session_ended_at_utc").isNull()
    )
    | (
        F.col("session_ended_at_utc")
        < F.col("session_started_at_utc")
    )
)

if invalid_timestamps.count() > 0:
    display(invalid_timestamps)
    raise ValueError("Invalid session timestamps")

silver_sessions = silver_sessions.drop("date_start", "date_end")

display(silver_drivers.orderBy("driver_number"))
display(silver_sessions)


# COMMAND ----------

def load_silver_table(dataframe, table_name, key_columns):
    if not spark.catalog.tableExists(table_name):
        (
            dataframe.write
            .format("delta")
            .mode("append")
            .saveAsTable(table_name)
        )
    else:
        match_condition = " AND ".join(
            f"target.`{column}` = incoming.`{column}`"
            for column in key_columns
        )

        (
            DeltaTable.forName(spark, table_name)
            .alias("target")
            .merge(
                dataframe.alias("incoming"),
                match_condition,
            )
            .whenMatchedUpdateAll(
                condition="""
                incoming.retrieved_at_utc > target.retrieved_at_utc
                """
            )
            .whenNotMatchedInsertAll()
            .execute()
        )

    print(f"Loaded {table_name}")


spark.sql("CREATE SCHEMA IF NOT EXISTS apex.apex_silver")

load_silver_table(
    silver_sessions,
    "apex.apex_silver.sessions",
    ["session_key"],
)

load_silver_table(
    silver_drivers,
    "apex.apex_silver.drivers",
    ["session_key", "driver_number"],
)


# COMMAND ----------

from pyspark.sql import functions as F

laps = (
    spark.table("apex.apex_silver.laps")
    .filter(F.col("session_key") == SESSION_KEY)
)

drivers = (
    spark.table("apex.apex_silver.drivers")
    .filter(F.col("session_key") == SESSION_KEY)
)

sessions = (
    spark.table("apex.apex_silver.sessions")
    .filter(F.col("session_key") == SESSION_KEY)
)

# A left-anti join returns records without a matching reference.
unmatched_drivers = laps.join(
    drivers.select("session_key", "driver_number"),
    on=["session_key", "driver_number"],
    how="left_anti",
)

unmatched_sessions = laps.join(
    sessions.select("session_key"),
    on="session_key",
    how="left_anti",
)

assert unmatched_drivers.count() == 0, "Laps reference unknown drivers"
assert unmatched_sessions.count() == 0, "Laps reference unknown sessions"

for name, table, expected_df, keys in [
    (
        "drivers",
        drivers,
        silver_drivers,
        ["session_key", "driver_number"],
    ),
    (
        "sessions",
        sessions,
        silver_sessions,
        ["session_key"],
    ),
]:
    actual_count = table.count()
    expected_count = expected_df.count()

    missing_reference_keys = (
        expected_df.select(*keys)
        .join(
            table.select(*keys),
            on=keys,
            how="left_anti",
        )
    )

    assert missing_reference_keys.count() == 0, (
        f"{name}: incoming reference keys are missing from silver"
    )

    duplicate_count = (
        table.groupBy(*keys)
        .count()
        .filter(F.col("count") > 1)
        .count()
    )

    assert duplicate_count == 0, f"{name}: duplicate keys"

    print(
        f"{name}: {actual_count} current silver rows, "
        f"{expected_count} incoming rows — checks passed"
    )

print(f"laps: {laps.count()} rows")
print("Passed: every lap references a known driver and session")


# COMMAND ----------

