-- =============================================================================
-- Performance Index Migration
-- Purpose: Fix PostgreSQL 98% CPU caused by sequential scans on nightly tasks.
-- Run with: psql -U postgres -d tek_school -f scripts/add_performance_indexes.sql
--
-- All indexes use CONCURRENTLY so they do NOT lock the tables.
-- Safe to run on a live production database.
-- =============================================================================

-- ── students table ────────────────────────────────────────────────────────────
-- Used by nightly check_student_renewals() Celery task
-- Filter: status != 'INACTIVE' AND status_expiry_date < NOW()
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_students_status
    ON students(status);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_students_status_expiry_date
    ON students(status_expiry_date)
    WHERE status_expiry_date IS NOT NULL;

-- Used by all school-scoped student queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_students_school_id
    ON students(school_id)
    WHERE school_id IS NOT NULL;

-- ── self_signed_students table ────────────────────────────────────────────────
-- Used by nightly check_student_renewals() Celery task
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_self_signed_students_status
    ON self_signed_students(status);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_self_signed_students_status_expiry_date
    ON self_signed_students(status_expiry_date)
    WHERE status_expiry_date IS NOT NULL;

-- ── schools table ─────────────────────────────────────────────────────────────
-- Used by nightly send_monthly_followup_emails() Celery task
-- Filter: followup_enabled = TRUE AND followup_status = 'pending'
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_schools_followup_enabled
    ON schools(followup_enabled)
    WHERE followup_enabled = TRUE;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_schools_followup_status
    ON schools(followup_status);

-- Composite: satisfies both filters in one index scan (most efficient)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_schools_followup_composite
    ON schools(followup_enabled, followup_status)
    WHERE followup_enabled = TRUE;

-- ── attendance table (common query filter) ────────────────────────────────────
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_attendances_school_id
    ON attendances(school_id)
    WHERE school_id IS NOT NULL;

-- =============================================================================
-- Verify: run after applying to confirm indexes were created
-- SELECT indexname, tablename FROM pg_indexes
-- WHERE indexname LIKE 'idx_%'
-- ORDER BY tablename, indexname;
-- =============================================================================
