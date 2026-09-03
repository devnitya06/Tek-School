-- Inspect non-idle PostgreSQL sessions and currently running queries.
-- Run:
--   docker exec -it postgres-db psql -U postgres -d tek_school -f scripts/inspect_active_queries.sql

SELECT
    pid,
    usename,
    application_name,
    client_addr,
    age(clock_timestamp(), query_start) AS query_age,
    state,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE state IS DISTINCT FROM 'idle'
ORDER BY query_start NULLS LAST;