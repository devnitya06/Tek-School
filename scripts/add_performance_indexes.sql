-- =============================================================================
-- Performance Index Migration
-- Purpose: Fix PostgreSQL high CPU caused by sequential scans on nightly tasks.
-- Run with: docker exec -i postgres-db psql -U postgres -d tek_school < scripts/add_performance_indexes.sql
--
-- NOTE: CONCURRENTLY removed — it cannot run inside a psql pipe transaction.
-- IF NOT EXISTS makes all statements safe to re-run.
-- =============================================================================

-- ── students table ────────────────────────────────────────────────────────────
-- Used by nightly check_student_renewals() Celery task
-- Filter: status != 'INACTIVE' AND status_expiry_date < NOW()
CREATE INDEX IF NOT EXISTS idx_students_status
    ON students(status);

CREATE INDEX IF NOT EXISTS idx_students_status_expiry_date
    ON students(status_expiry_date)
    WHERE status_expiry_date IS NOT NULL;

-- Used by all school-scoped student queries
CREATE INDEX IF NOT EXISTS idx_students_school_id
    ON students(school_id)
    WHERE school_id IS NOT NULL;

-- ── self_signed_students table ────────────────────────────────────────────────
-- Used by nightly check_student_renewals() Celery task
CREATE INDEX IF NOT EXISTS idx_self_signed_students_status
    ON self_signed_students(status);

CREATE INDEX IF NOT EXISTS idx_self_signed_students_status_expiry_date
    ON self_signed_students(status_expiry_date)
    WHERE status_expiry_date IS NOT NULL;

-- ── schools table ─────────────────────────────────────────────────────────────
-- Used by nightly send_monthly_followup_emails() Celery task
-- Filter: followup_enabled = TRUE AND followup_status = 'pending'
CREATE INDEX IF NOT EXISTS idx_schools_followup_enabled
    ON schools(followup_enabled)
    WHERE followup_enabled = TRUE;

CREATE INDEX IF NOT EXISTS idx_schools_followup_status
    ON schools(followup_status);

-- Composite: satisfies both filters in one index scan (most efficient)
CREATE INDEX IF NOT EXISTS idx_schools_followup_composite
    ON schools(followup_enabled, followup_status)
    WHERE followup_enabled = TRUE;

-- ── attendances table ─────────────────────────────────────────────────────────
-- Wrapped: attendances.school_id may not exist on all deployments
DO $$ BEGIN
    CREATE INDEX IF NOT EXISTS idx_attendances_school_id
        ON attendances(school_id)
        WHERE school_id IS NOT NULL;
EXCEPTION WHEN undefined_column THEN
    RAISE NOTICE 'Skipping idx_attendances_school_id — school_id column not found.';
END $$;

-- =============================================================================
-- Verify: run after applying to confirm indexes were created
-- SELECT indexname, tablename FROM pg_indexes
-- WHERE indexname LIKE 'idx_%'
-- ORDER BY tablename, indexname;
-- =============================================================================
