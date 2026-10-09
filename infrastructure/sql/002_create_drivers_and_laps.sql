BEGIN;

CREATE TABLE IF NOT EXISTS analytics.drivers (
    session_key BIGINT NOT NULL,
    driver_number INTEGER NOT NULL,
    full_name TEXT,
    name_acronym TEXT,
    team_name TEXT,
    team_colour TEXT,
    loaded_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (session_key, driver_number),

    FOREIGN KEY (session_key)
        REFERENCES analytics.sessions (session_key),

    CHECK (driver_number > 0)
);

CREATE TABLE IF NOT EXISTS analytics.laps (
    session_key BIGINT NOT NULL,
    driver_number INTEGER NOT NULL,
    lap_number INTEGER NOT NULL,

    lap_started_at_utc TIMESTAMPTZ,
    lap_duration_seconds DOUBLE PRECISION,
    sector_1_seconds DOUBLE PRECISION,
    sector_2_seconds DOUBLE PRECISION,
    sector_3_seconds DOUBLE PRECISION,

    is_pit_out_lap BOOLEAN,
    lap_time_status TEXT NOT NULL,
    is_eligible_for_timed_stats BOOLEAN NOT NULL,

    delta_to_previous_lap_seconds DOUBLE PRECISION,
    rolling_5_lap_average_seconds DOUBLE PRECISION,
    rolling_5_lap_sample_count INTEGER NOT NULL,

    source_run_id TEXT NOT NULL,
    source_retrieved_at_utc TIMESTAMPTZ NOT NULL,
    loaded_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (session_key, driver_number, lap_number),

    FOREIGN KEY (session_key, driver_number)
        REFERENCES analytics.drivers (session_key, driver_number),

    CHECK (lap_number > 0),

    CHECK (
        lap_time_status IN ('available', 'missing', 'invalid')
    ),

    CHECK (
        rolling_5_lap_sample_count BETWEEN 0 AND 5
    ),

    CHECK (
        NOT is_eligible_for_timed_stats
        OR (
            lap_time_status = 'available'
            AND lap_duration_seconds IS NOT NULL
            AND lap_duration_seconds > 0
            AND lap_duration_seconds < 'Infinity'::DOUBLE PRECISION
            AND is_pit_out_lap IS FALSE
        )
    )
);

COMMIT;
