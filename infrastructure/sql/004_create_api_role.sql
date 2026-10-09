BEGIN;

CREATE ROLE apex_api LOGIN;

GRANT CONNECT ON DATABASE apex TO apex_api;
GRANT USAGE ON SCHEMA analytics TO apex_api;

GRANT SELECT ON
    analytics.sessions,
    analytics.drivers,
    analytics.laps
TO apex_api;

COMMIT;
