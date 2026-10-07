# Databricks notebook source
dbutils.widgets.text("session_key", "9558", "Session key")

SESSION_KEY = int(dbutils.widgets.get("session_key"))

if SESSION_KEY <= 0:
    raise ValueError("session_key must be positive")

spark.sql("SET TIME ZONE 'UTC'")

print(f"Building gold tables for session {SESSION_KEY}")


# COMMAND ----------

from pyspark.sql import functions as F

source_laps = (
    spark.table("apex.apex_silver.laps")
    .filter(F.col("session_key") == SESSION_KEY)
)

if source_laps.count() == 0:
    raise ValueError(
        f"No silver laps found for session {SESSION_KEY}"
    )

print(f"Source laps: {source_laps.count()}")


# COMMAND ----------



spark.sql("CREATE SCHEMA IF NOT EXISTS apex.apex_gold")

driver_summary = spark.sql(f"""
    WITH lap_stats AS (
        SELECT
            session_key,
            driver_number,

            COUNT(*) AS recorded_laps,

            SUM(
                CASE
                    WHEN is_eligible_for_timed_stats THEN 1
                    ELSE 0
                END
            ) AS timed_laps,

            SUM(
                CASE
                    WHEN lap_time_status = 'missing' THEN 1
                    ELSE 0
                END
            ) AS missing_duration_laps,

            MIN(
                CASE
                    WHEN is_eligible_for_timed_stats
                    THEN lap_duration_seconds
                END
            ) AS fastest_lap_seconds,

            AVG(
                CASE
                    WHEN is_eligible_for_timed_stats
                    THEN lap_duration_seconds
                END
            ) AS average_lap_seconds

        FROM apex.apex_silver.laps
        WHERE session_key = {SESSION_KEY}
        GROUP BY session_key, driver_number
    ),

    ranked_stats AS (
        SELECT
            *,
            CASE
                WHEN fastest_lap_seconds IS NOT NULL
                THEN DENSE_RANK() OVER (
                    PARTITION BY session_key
                    ORDER BY fastest_lap_seconds ASC NULLS LAST
                )
            END AS fastest_lap_rank
        FROM lap_stats
    )

    SELECT
        stats.*,
        drivers.full_name,
        drivers.name_acronym,
        drivers.team_name,
        drivers.team_colour,
        sessions.session_name,
        sessions.session_type,
        sessions.circuit_short_name,
        sessions.country_name,
        sessions.session_started_at_utc,
        CURRENT_TIMESTAMP() AS gold_updated_at_utc

    FROM ranked_stats AS stats

    INNER JOIN apex.apex_silver.drivers AS drivers
        ON stats.session_key = drivers.session_key
        AND stats.driver_number = drivers.driver_number

    INNER JOIN apex.apex_silver.sessions AS sessions
        ON stats.session_key = sessions.session_key
""")

display(
    driver_summary.orderBy(
        "fastest_lap_rank",
        "driver_number",
    )
)


# COMMAND ----------

from pyspark.sql import functions as F

source_laps = (
    spark.table("apex.apex_silver.laps")
    .filter(F.col("session_key") == SESSION_KEY)
)

expected_driver_count = (
    source_laps
    .select("session_key", "driver_number")
    .distinct()
    .count()
)

summary_count = driver_summary.count()

duplicate_groups = (
    driver_summary
    .groupBy("session_key", "driver_number")
    .count()
    .filter(F.col("count") > 1)
    .count()
)

totals = driver_summary.agg(
    F.sum("recorded_laps").alias("recorded_laps"),
    F.sum("timed_laps").alias("timed_laps"),
    F.sum("missing_duration_laps").alias("missing_duration_laps"),
).first()

expected_timed_laps = source_laps.filter(
    F.col("is_eligible_for_timed_stats")
).count()

assert summary_count == expected_driver_count, (
    "Driver count mismatch: check joins"
)
assert duplicate_groups == 0, "Duplicate summary keys"
assert totals["recorded_laps"] == source_laps.count()
assert totals["timed_laps"] == expected_timed_laps
expected_missing_durations = source_laps.filter(
    F.col("lap_time_status") == "missing"
).count()

assert totals["missing_duration_laps"] == expected_missing_durations


print(f"Passed: {summary_count} driver summaries")
print(f"Recorded laps: {totals['recorded_laps']}")
print(f"Eligible timed laps: {totals['timed_laps']}")
print(f"Missing durations: {totals['missing_duration_laps']}")


# COMMAND ----------

TABLE_NAME = "apex.apex_gold.driver_session_summary"

if not spark.catalog.tableExists(TABLE_NAME):
    (
        driver_summary.write
        .format("delta")
        .mode("append")
        .saveAsTable(TABLE_NAME)
    )
else:
    (
        driver_summary.write
        .format("delta")
        .mode("overwrite")
        .option("replaceWhere", f"session_key = {SESSION_KEY}")
        .saveAsTable(TABLE_NAME)
    )

saved_summary = (
    spark.table(TABLE_NAME)
    .filter(F.col("session_key") == SESSION_KEY)
)

assert saved_summary.count() == expected_driver_count

display(
    saved_summary.orderBy(
        F.col("fastest_lap_rank").asc_nulls_last(),
        "driver_number",
    )
)

print(f"Saved {TABLE_NAME}")


# COMMAND ----------



lap_analytics = spark.sql(f"""
    WITH lap_history AS (
        SELECT
            laps.*,

            LAG(lap_number) OVER (
                PARTITION BY session_key, driver_number
                ORDER BY lap_number
            ) AS previous_lap_number,

            LAG(
                CASE
                    WHEN is_eligible_for_timed_stats
                    THEN lap_duration_seconds
                END
            ) OVER (
                PARTITION BY session_key, driver_number
                ORDER BY lap_number
            ) AS previous_eligible_lap_seconds,

            AVG(
                CASE
                    WHEN is_eligible_for_timed_stats
                    THEN lap_duration_seconds
                END
            ) OVER (
                PARTITION BY session_key, driver_number
                ORDER BY lap_number
                RANGE BETWEEN 4 PRECEDING AND CURRENT ROW
            ) AS rolling_5_lap_average_seconds,

            COUNT(
                CASE
                    WHEN is_eligible_for_timed_stats
                    THEN lap_duration_seconds
                END
            ) OVER (
                PARTITION BY session_key, driver_number
                ORDER BY lap_number
                RANGE BETWEEN 4 PRECEDING AND CURRENT ROW
            ) AS rolling_5_lap_sample_count

        FROM apex.apex_silver.laps AS laps
        WHERE session_key = {SESSION_KEY}
    )

    SELECT
        history.session_key,
        history.meeting_key,
        history.driver_number,
        history.lap_number,
        history.lap_started_at_utc,
        history.lap_duration_seconds,
        history.sector_1_seconds,
        history.sector_2_seconds,
        history.sector_3_seconds,
        history.is_pit_out_lap,
        history.lap_time_status,
        history.is_eligible_for_timed_stats,

        CASE
            WHEN history.is_eligible_for_timed_stats
                 AND history.previous_lap_number = history.lap_number - 1
                 AND history.previous_eligible_lap_seconds IS NOT NULL
            THEN history.lap_duration_seconds
                 - history.previous_eligible_lap_seconds
        END AS delta_to_previous_lap_seconds,

        history.rolling_5_lap_average_seconds,
        history.rolling_5_lap_sample_count,

        drivers.full_name,
        drivers.name_acronym,
        drivers.team_name,
        drivers.team_colour,

        sessions.session_name,
        sessions.session_type,
        sessions.circuit_short_name,
        sessions.country_name,
        sessions.session_started_at_utc,

        history.run_id AS source_run_id,
        history.retrieved_at_utc AS source_retrieved_at_utc,
        CURRENT_TIMESTAMP() AS gold_updated_at_utc

    FROM lap_history AS history

    INNER JOIN apex.apex_silver.drivers AS drivers
        ON history.session_key = drivers.session_key
        AND history.driver_number = drivers.driver_number

    INNER JOIN apex.apex_silver.sessions AS sessions
        ON history.session_key = sessions.session_key
""")

display(
    lap_analytics
    .orderBy("driver_number", "lap_number")
    .limit(30)
)


# COMMAND ----------

from pyspark.sql import functions as F

source_laps = (
    spark.table("apex.apex_silver.laps")
    .filter(F.col("session_key") == SESSION_KEY)
)

duplicate_count = (
    lap_analytics
    .groupBy("session_key", "driver_number", "lap_number")
    .count()
    .filter(F.col("count") > 1)
    .count()
)

invalid_sample_counts = lap_analytics.filter(
    (F.col("rolling_5_lap_sample_count") < 0)
    | (F.col("rolling_5_lap_sample_count") > 5)
).count()

ineligible_with_delta = lap_analytics.filter(
    (~F.col("is_eligible_for_timed_stats"))
    & F.col("delta_to_previous_lap_seconds").isNotNull()
).count()

assert lap_analytics.count() == source_laps.count(), (
    "Gold lap count does not match silver"
)

assert duplicate_count == 0, "Duplicate analytical lap keys"
assert invalid_sample_counts == 0, "Invalid rolling sample counts"
assert ineligible_with_delta == 0, "Ineligible lap has a comparison delta"

print(
    f"Passed: {lap_analytics.count()} analytical laps, "
    "unique keys, valid window checks"
)



# COMMAND ----------

TABLE_NAME = "apex.apex_gold.lap_analytics"

if not spark.catalog.tableExists(TABLE_NAME):
    (
        lap_analytics.write
        .format("delta")
        .mode("append")
        .saveAsTable(TABLE_NAME)
    )
else:
    (
        lap_analytics.write
        .format("delta")
        .mode("overwrite")
        .option("replaceWhere", f"session_key = {SESSION_KEY}")
        .saveAsTable(TABLE_NAME)
    )

saved_laps = (
    spark.table(TABLE_NAME)
    .filter(F.col("session_key") == SESSION_KEY)
)

assert saved_laps.count() == source_laps.count(), (
    "Saved gold lap count does not match silver"
)

print(
    f"Saved {TABLE_NAME}: {saved_laps.count()} rows "
    f"for session {SESSION_KEY}"
)





# COMMAND ----------

display(
    saved_laps
    .filter(F.col("driver_number") == 11)
    .orderBy("lap_number")
    .select(
        "lap_number",
        "lap_duration_seconds",
        "is_eligible_for_timed_stats",
        "delta_to_previous_lap_seconds",
        "rolling_5_lap_average_seconds",
        "rolling_5_lap_sample_count",
    )
    .limit(15)
)


# COMMAND ----------

