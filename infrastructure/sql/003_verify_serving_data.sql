SELECT 'sessions' AS dataset, COUNT(*) AS row_count
FROM analytics.sessions
WHERE session_key = 9558

UNION ALL

SELECT 'drivers', COUNT(*)
FROM analytics.drivers
WHERE session_key = 9558

UNION ALL

SELECT 'laps', COUNT(*)
FROM analytics.laps
WHERE session_key = 9558;

SELECT
    driver_number,
    lap_number,
    lap_duration_seconds,
    lap_time_status,
    is_eligible_for_timed_stats
FROM analytics.laps
WHERE session_key = 9558
  AND lap_time_status = 'missing'
ORDER BY driver_number, lap_number;

WITH driver_stats AS (
    SELECT
        session_key,
        driver_number,
        COUNT(*) AS recorded_laps,
        COUNT(*) FILTER (
            WHERE is_eligible_for_timed_stats
        ) AS timed_laps,
        MIN(lap_duration_seconds) FILTER (
            WHERE is_eligible_for_timed_stats
        ) AS fastest_lap_seconds,
        AVG(lap_duration_seconds) FILTER (
            WHERE is_eligible_for_timed_stats
        ) AS average_lap_seconds
    FROM analytics.laps
    WHERE session_key = 9558
    GROUP BY session_key, driver_number
)
SELECT
    drivers.full_name,
    drivers.team_name,
    stats.recorded_laps,
    stats.timed_laps,
    ROUND(stats.fastest_lap_seconds::NUMERIC, 3) AS fastest_lap_seconds,
    ROUND(stats.average_lap_seconds::NUMERIC, 3) AS average_lap_seconds
FROM driver_stats AS stats
JOIN analytics.drivers AS drivers
    ON stats.session_key = drivers.session_key
   AND stats.driver_number = drivers.driver_number
ORDER BY stats.fastest_lap_seconds ASC NULLS LAST;
