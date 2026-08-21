-- =============================================================================
-- Tek School -- Missing Performance Indexes
-- Safe to run multiple times (IF NOT EXISTS on all statements)
-- Run: docker exec -i postgres-db psql -U postgres -d tek_school < scripts/add_indexes.sql
-- =============================================================================

-- schools: most APIs filter/JOIN on these
CREATE INDEX IF NOT EXISTS idx_schools_user_id          ON schools (user_id);
CREATE INDEX IF NOT EXISTS idx_schools_followup_enabled ON schools (followup_enabled) WHERE followup_enabled = TRUE;
CREATE INDEX IF NOT EXISTS idx_schools_followup_status  ON schools (followup_status);
CREATE INDEX IF NOT EXISTS idx_schools_claim_status     ON schools (claim_status);

-- students: renewal task + school-scoped list queries
CREATE INDEX IF NOT EXISTS idx_students_school_status
    ON students (school_id, status)
    WHERE status != 'INACTIVE';

CREATE INDEX IF NOT EXISTS idx_students_expiry_status
    ON students (status_expiry_date, status)
    WHERE status_expiry_date IS NOT NULL;

-- self_signed_students: same renewal task patterns
CREATE INDEX IF NOT EXISTS idx_self_signed_students_status
    ON self_signed_students (status)
    WHERE status != 'INACTIVE';

CREATE INDEX IF NOT EXISTS idx_self_signed_students_expiry
    ON self_signed_students (status_expiry_date, status)
    WHERE status_expiry_date IS NOT NULL;

-- excellent_students: new filter fields (ILIKE needs lower() for case-insensitive)
CREATE INDEX IF NOT EXISTS idx_excellent_students_school_id
    ON excellent_students (school_id);

CREATE INDEX IF NOT EXISTS idx_excellent_students_student_name
    ON excellent_students (lower(student_name));

CREATE INDEX IF NOT EXISTS idx_excellent_students_grade
    ON excellent_students (lower(grade));

CREATE INDEX IF NOT EXISTS idx_excellent_students_class_name
    ON excellent_students (lower(class_name));

CREATE INDEX IF NOT EXISTS idx_excellent_students_gender
    ON excellent_students (lower(gender));

CREATE INDEX IF NOT EXISTS idx_excellent_students_batch
    ON excellent_students (lower(batch_of_student));

-- teachers / staff
CREATE INDEX IF NOT EXISTS idx_teachers_school_id  ON teachers (school_id);
CREATE INDEX IF NOT EXISTS idx_teachers_user_id    ON teachers (user_id);
CREATE INDEX IF NOT EXISTS idx_staff_school_id     ON staff (school_id);

-- attendances: reports always filter by school + date
CREATE INDEX IF NOT EXISTS idx_attendances_school_date ON attendances (school_id, date);

-- payments
CREATE INDEX IF NOT EXISTS idx_student_payments_student_id ON student_payments (student_id);
CREATE INDEX IF NOT EXISTS idx_student_payments_school_id  ON student_payments (school_id);
CREATE INDEX IF NOT EXISTS idx_payment_records_school_id   ON payment_records (school_id);

-- news
CREATE INDEX IF NOT EXISTS idx_news_school_id ON news (school_id);

SELECT 'All indexes created successfully.' AS result;
