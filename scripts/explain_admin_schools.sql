-- Query plans for /admin/schools/.
-- Run after applying scripts/add_indexes.sql:
--   docker exec -i postgres-db psql -U postgres -d tek_school < scripts/explain_admin_schools.sql
--
-- Replace LIMIT/OFFSET and add the same filters used in the request when
-- investigating a specific slow call. EXPLAIN ANALYZE executes the queries.

-- Default list query: ORDER BY + pagination
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT s.*
FROM schools AS s
ORDER BY s.created_at DESC, s.id ASC
LIMIT 20 OFFSET 0;

-- Count query and a representative filtered list query
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT count(*)
FROM schools AS s
WHERE lower(s.district) = 'khordha'
  AND lower(s.school_board::text) = 'cbse';

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT s.*
FROM schools AS s
WHERE lower(s.district) = 'khordha'
  AND lower(s.school_board::text) = 'cbse'
ORDER BY s.created_at DESC, s.id ASC
LIMIT 20 OFFSET 0;
