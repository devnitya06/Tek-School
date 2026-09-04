-- =============================================================================
-- Tek School -- Performance Indexes
-- Safe to run multiple times (IF NOT EXISTS on all statements)
-- Run: docker exec -i postgres-db psql -U postgres -d tek_school < scripts/add_indexes.sql
-- =============================================================================

-- schools: most APIs filter/JOIN on these
CREATE INDEX IF NOT EXISTS idx_schools_user_id          ON schools (user_id);
-- Stable ordering for /admin/schools/ ORDER BY created_at DESC OFFSET/LIMIT
CREATE INDEX IF NOT EXISTS idx_schools_pagination       ON schools (created_at DESC, id);
CREATE INDEX IF NOT EXISTS idx_schools_district_lower   ON schools (lower(district));
CREATE INDEX IF NOT EXISTS idx_schools_board_lower      ON schools (lower(school_board::text));
CREATE INDEX IF NOT EXISTS idx_schools_medium_lower     ON schools (lower(school_medium::text));
CREATE INDEX IF NOT EXISTS idx_schools_institution_categories_gin
    ON schools USING GIN (institution_categories);
CREATE INDEX IF NOT EXISTS idx_schools_hostel_gin
    ON schools USING GIN (hostel);
CREATE INDEX IF NOT EXISTS idx_schools_available_classes_gin
    ON schools USING GIN (available_classes);
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

-- excellent_students: filter fields (ILIKE needs lower() for case-insensitive)
CREATE INDEX IF NOT EXISTS idx_excellent_students_school_id   ON excellent_students (school_id);
CREATE INDEX IF NOT EXISTS idx_excellent_students_student_name ON excellent_students (lower(student_name));
CREATE INDEX IF NOT EXISTS idx_excellent_students_grade        ON excellent_students (lower(grade));
CREATE INDEX IF NOT EXISTS idx_excellent_students_class_name   ON excellent_students (lower(class_name));
CREATE INDEX IF NOT EXISTS idx_excellent_students_gender       ON excellent_students (lower(gender));
CREATE INDEX IF NOT EXISTS idx_excellent_students_batch        ON excellent_students (lower(batch_of_student));

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

-- ─── NEW INDEXES ─────────────────────────────────────────────────────────────

-- achievements: school-scoped list queries (school profile page)
CREATE INDEX IF NOT EXISTS ix_achievements_school_id ON achievements (school_id);

-- school_team_members: school-scoped list queries
CREATE INDEX IF NOT EXISTS ix_school_team_members_school_id ON school_team_members (school_id);

-- school_ratings: used in /admin/schools/ to batch-fetch ratings per school page
CREATE INDEX IF NOT EXISTS ix_school_ratings_school_id ON school_ratings (school_id);

-- subjects: school-scoped subject listing
CREATE INDEX IF NOT EXISTS ix_subjects_school_id ON subjects (school_id);

-- classes: school-scoped class listing (JOIN in student queries)
CREATE INDEX IF NOT EXISTS ix_classes_school_id ON classes (school_id);

-- sections: used in timetable and attendance queries
CREATE INDEX IF NOT EXISTS ix_sections_school_id ON sections (school_id);

-- exams: school-scoped exam listing
CREATE INDEX IF NOT EXISTS ix_exams_school_id ON exams (school_id);

-- transports: school-scoped transport listing
CREATE INDEX IF NOT EXISTS ix_transports_school_id ON transports (school_id);

-- leave_requests: school-scoped leave management
CREATE INDEX IF NOT EXISTS ix_leave_requests_school_id ON leave_requests (school_id);

-- workers (staff payroll): school-scoped
CREATE INDEX IF NOT EXISTS ix_workers_school_id ON workers (school_id);

-- communication_sections: school-scoped
CREATE INDEX IF NOT EXISTS ix_communication_sections_school_id ON communication_sections (school_id);

-- listed_school_students: school-scoped public listing
CREATE INDEX IF NOT EXISTS ix_listed_school_students_school_id ON listed_school_students (school_id);

-- ─── ANALYZE (update planner statistics for ALL indexed tables) ───────────────
-- Without ANALYZE, PostgreSQL cannot see new indexes and falls back to seq scans.
-- Run this block every time you add/drop indexes or import a large data batch.
ANALYZE schools;
ANALYZE teachers;
ANALYZE students;
ANALYZE self_signed_students;
ANALYZE staff;
ANALYZE attendances;
ANALYZE achievements;
ANALYZE school_team_members;
ANALYZE school_ratings;
ANALYZE subjects;
ANALYZE classes;
ANALYZE sections;
ANALYZE exams;
ANALYZE transports;
ANALYZE leave_requests;
ANALYZE workers;
ANALYZE communication_sections;
ANALYZE listed_school_students;
ANALYZE student_payments;
ANALYZE payment_records;
ANALYZE news;

SELECT 'All indexes created and statistics updated successfully.' AS result;
