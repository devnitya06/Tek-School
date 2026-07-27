from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
import time


SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def retry_db_operation(operation, retries=3, delay=1):
    last_exception = None
    for attempt in range(retries):
        try:
            return operation()
        except OperationalError as exc:
            last_exception = exc
            engine.dispose()
            time.sleep(delay)
    raise last_exception or RuntimeError("DB operation failed after retries")


def inspect_engine():
    return retry_db_operation(lambda: inspect(engine))

# Import all models to ensure they're registered with Base
from app.models.users import *
from app.models.school import *
from app.models.teachers import *
from app.models.students import *
from app.models.assignments.assignment import (
    Assignment,
    StudentAssignmentProgress,
    AssignmentKeyPoint,
    AssignmentQuestion,
    AssignmentImage,
    AssignmentPDF,
    AssignmentVideoLink,
    AssignmentMediaBanner,
    PublishConfiguration,
    StudentAssignmentAttempt,
    ChapterFeedback,
    TeacherRating,
    AssignmentView,
    AssignmentDoubt,
    DoubtReply,
    AssignmentReport,
    FavoriteTeacher,
)
from app.models.user_session import UserSession
from app.models.admin import *
from app.models.staff import *
from app.models.progress_reports import *
from app.models.academic_results import *
from app.models.tuition import *

def create_tables():
    """Create all tables that don't exist yet"""
    Base.metadata.create_all(bind=engine)

def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    inspector = inspect_engine()
    if not inspector.has_table(table_name):
        return False
    columns = inspector.get_columns(table_name)
    return any(column['name'] == column_name for column in columns)

def add_missing_columns():
    """Add missing columns to existing tables"""
    inspector = inspect_engine()
    
    for table_name in Base.metadata.tables.keys():
        if inspector.has_table(table_name):
            table = Base.metadata.tables[table_name]
            existing_columns = [col['name'] for col in inspector.get_columns(table_name)]
            
            for column in table.columns:
                if column.name not in existing_columns:
                    # Add the column to the table
                    column_type = column.type.compile(engine.dialect)
                    
                    with engine.begin() as conn:
                        alter_stmt = f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {column_type}'
                        
                        # Add NULL/NOT NULL constraint
                        if not column.nullable:
                            alter_stmt += " NOT NULL"
                        
                        # Add default value if specified
                        if column.default is not None:
                            if callable(column.default.arg):
                                default_value = column.default.arg()
                            else:
                                default_value = column.default.arg
                            # Handle enum default values
                            if hasattr(default_value, 'value'):
                                default_value = default_value.value
                            alter_stmt += f" DEFAULT '{default_value}'"
                        
                        conn.execute(text(alter_stmt))
def drop_extra_columns():
    inspector = inspect_engine()
    
    for table_name in Base.metadata.tables.keys():
        if inspector.has_table(table_name):
            model_columns = {c.name for c in Base.metadata.tables[table_name].columns}
            db_columns = {col['name'] for col in inspector.get_columns(table_name)}
            
            extra_columns = db_columns - model_columns
            for column in extra_columns:
                with engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE "{table_name}" DROP COLUMN "{column}"'))


def ensure_attendance_qr_token_columns():
    """Ensure school attendance QR token columns exist (persisted tokens; old QR invalid after regenerate)."""
    for col, ddl_sqlite in (
        ("attendance_qr_mark_in_token", "VARCHAR(64)"),
        ("attendance_qr_mark_out_token", "VARCHAR(64)"),
    ):
        if column_exists("schools", col):
            continue
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE schools ADD COLUMN "{col}" {ddl_sqlite}'))


def ensure_staff_school_id_nullable():
    """Allow platform staff (admin/superadmin) with no school."""
    inspector = inspect_engine()
    if not inspector.has_table("staff"):
        return
    for col in inspector.get_columns("staff"):
        if col["name"] == "school_id" and col.get("nullable") is False:
            with engine.begin() as conn:
                conn.execute(text('ALTER TABLE staff ALTER COLUMN school_id DROP NOT NULL'))
            break


def ensure_staff_compensation_tables():
    """
    Ensure staff compensation tables exist even when RUN_SCHEMA_SYNC is disabled.
    These are required by staff designation-compensation endpoints.
    """
    EmployeeCompensation.__table__.create(bind=engine, checkfirst=True)
    DesignationCompensationTemplate.__table__.create(bind=engine, checkfirst=True)

def ensure_academic_results_tables():
    """Ensure academic results tables exist."""
    from app.models.academic_results import AcademicResultDefinition, AcademicStudentResult, academic_result_sections
    AcademicResultDefinition.__table__.create(bind=engine, checkfirst=True)
    academic_result_sections.create(bind=engine, checkfirst=True)
    AcademicStudentResult.__table__.create(bind=engine, checkfirst=True)

def ensure_progress_report_tables():
    """Ensure progress report tables exist."""
    from app.models.progress_reports import ProgressReport
    ProgressReport.__table__.create(bind=engine, checkfirst=True)


def ensure_attendance_verified_at_column():
    """Teacher/staff attendance approval timestamp (set when is_verified becomes true)."""
    if column_exists("attendances", "verified_at"):
        return
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE attendances ADD COLUMN verified_at TIMESTAMP NULL'))


def ensure_attendance_qr_source_columns():
    """Whether mark-in/out was recorded via QR (vs manual attendance API)."""
    for col in ("mark_in_via_qr", "mark_out_via_qr"):
        if column_exists("attendances", col):
            continue
        with engine.begin() as conn:
            conn.execute(
                text(f'ALTER TABLE attendances ADD COLUMN "{col}" BOOLEAN NULL')
            )


def ensure_attendance_mark_columns():
    """
    Ensure attendance mark-in/out columns exist for runtime compatibility.
    This is a targeted, safe patch for existing databases.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE attendances
                ADD COLUMN IF NOT EXISTS mark_in_at TIMESTAMP NULL
                """
            )
        )
        conn.execute(
            text(
                """
                ALTER TABLE attendances
                ADD COLUMN IF NOT EXISTS mark_out_at TIMESTAMP NULL
                """
            )
        )


def ensure_tuition_teaching_setup_schema():
    """Ensure the tuition teaching setup table and its columns exist for the current model."""
    from app.models.tuition.teaching_setup import TuitionTeachingSetup

    table_name = TuitionTeachingSetup.__tablename__
    inspector = inspect_engine()
    if not inspector.has_table(table_name):
        TuitionTeachingSetup.__table__.create(bind=engine, checkfirst=True)
        return

    existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
    for column in TuitionTeachingSetup.__table__.columns:
        if column.name in existing_columns:
            continue
        column_type = column.type.compile(dialect=engine.dialect)
        alter_stmt = f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {column_type}'
        if not column.nullable:
            alter_stmt += " NOT NULL"
        if column.default is not None:
            default_value = column.default.arg
            if callable(default_value):
                default_value = default_value()
            if hasattr(default_value, "value"):
                default_value = default_value.value
            alter_stmt += f" DEFAULT '{default_value}'"
        with engine.begin() as conn:
            conn.execute(text(alter_stmt))


def ensure_staff_teacher_boss_columns():
    """
    Ensure both legacy/current boss column spellings exist and stay mirrored.
    Some databases have `immediate_boss`, others have `immidiate_boss`.
    """
    with engine.begin() as conn:
        # staff table
        conn.execute(text('ALTER TABLE staff ADD COLUMN IF NOT EXISTS "immidiate_boss" VARCHAR NULL'))
        conn.execute(text('ALTER TABLE staff ADD COLUMN IF NOT EXISTS "immediate_boss" VARCHAR NULL'))
        conn.execute(text('ALTER TABLE staff ADD COLUMN IF NOT EXISTS "super_boss" VARCHAR NULL'))
        conn.execute(text('ALTER TABLE staff ADD COLUMN IF NOT EXISTS "mark_in_time" TIME NULL'))
        conn.execute(text('ALTER TABLE staff ADD COLUMN IF NOT EXISTS "mark_out_time" TIME NULL'))
        conn.execute(text('ALTER TABLE staff ADD COLUMN IF NOT EXISTS "employee_grade" VARCHAR(100) NULL'))
        conn.execute(text('ALTER TABLE staff ADD COLUMN IF NOT EXISTS "is_active_hr_service" BOOLEAN NULL'))
        conn.execute(text('ALTER TABLE staff ADD COLUMN IF NOT EXISTS "hiring_for_board" VARCHAR(255) NULL'))
        conn.execute(text('ALTER TABLE staff ADD COLUMN IF NOT EXISTS "teaching_language" JSON NULL'))
        conn.execute(text('ALTER TABLE staff ADD COLUMN IF NOT EXISTS "subjects" VARCHAR NULL'))
        conn.execute(text('ALTER TABLE staff ADD COLUMN IF NOT EXISTS "assigned_class" VARCHAR(255) NULL'))
        conn.execute(text('ALTER TABLE staff ADD COLUMN IF NOT EXISTS "assigned_subjects" JSON NULL'))
        conn.execute(
            text(
                """
                UPDATE staff
                SET immidiate_boss = COALESCE(immidiate_boss, immediate_boss),
                    immediate_boss = COALESCE(immediate_boss, immidiate_boss)
                """
            )
        )

        # teachers table
        conn.execute(text('ALTER TABLE teachers ADD COLUMN IF NOT EXISTS "immidiate_boss" VARCHAR NULL'))
        conn.execute(text('ALTER TABLE teachers ADD COLUMN IF NOT EXISTS "immediate_boss" VARCHAR NULL'))
        conn.execute(text('ALTER TABLE teachers ADD COLUMN IF NOT EXISTS "super_boss" VARCHAR NULL'))
        conn.execute(text('ALTER TABLE teachers ADD COLUMN IF NOT EXISTS "designation" VARCHAR NULL'))
        conn.execute(text('ALTER TABLE teachers ADD COLUMN IF NOT EXISTS "mark_in_time" TIME NULL'))
        conn.execute(text('ALTER TABLE teachers ADD COLUMN IF NOT EXISTS "mark_out_time" TIME NULL'))
        conn.execute(text('ALTER TABLE teachers ADD COLUMN IF NOT EXISTS "employee_grade" VARCHAR(100) NULL'))
        conn.execute(text('ALTER TABLE teachers ADD COLUMN IF NOT EXISTS "is_active_hr_service" BOOLEAN NULL'))
        conn.execute(text('ALTER TABLE teachers ADD COLUMN IF NOT EXISTS "avg_rating" FLOAT DEFAULT 0.0'))
        conn.execute(text('ALTER TABLE teachers ADD COLUMN IF NOT EXISTS "rating_count" INTEGER DEFAULT 0'))
        conn.execute(
            text(
                """
                UPDATE teachers
                SET immidiate_boss = COALESCE(immidiate_boss, immediate_boss),
                    immediate_boss = COALESCE(immediate_boss, immidiate_boss)
                """
            )
        )


def ensure_school_settlement_schema():
    """
    Ledger for school settlements (per bank account or cash offline) + default channel on schools.
    """
    from app.models.school import SchoolSettlementTransaction, CashDepositTransaction

    SchoolSettlementTransaction.__table__.create(bind=engine, checkfirst=True)
    CashDepositTransaction.__table__.create(bind=engine, checkfirst=True)
    if column_exists("schools", "default_settlement_channel"):
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE schools ADD COLUMN IF NOT EXISTS default_settlement_channel "
                "VARCHAR(32) NOT NULL DEFAULT 'cash_offline'"
            )
        )


def ensure_self_signed_student_teacher_id_column():
    """Ensure the nullable foreign key column exists for self-signed student teacher links."""
    if column_exists("self_signed_students", "self_signed_teacher_id"):
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                'ALTER TABLE self_signed_students '
                'ADD COLUMN IF NOT EXISTS "self_signed_teacher_id" INTEGER NULL'
            )
        )


def ensure_self_signed_teacher_teaching_configuration_table():
    """Ensure the self-signed teacher teaching configuration table exists."""
    from app.models.teachers import SelfSignedTeacherTeachingConfiguration

    SelfSignedTeacherTeachingConfiguration.__table__.create(bind=engine, checkfirst=True)


def ensure_self_signed_student_additional_columns():
    """Ensure new self-signed student profile columns exist in the database."""
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE self_signed_students ADD COLUMN IF NOT EXISTS "gender" VARCHAR(20) NULL'))
        conn.execute(text('ALTER TABLE self_signed_students ADD COLUMN IF NOT EXISTS "dob" DATE NULL'))
        conn.execute(text('ALTER TABLE self_signed_students ADD COLUMN IF NOT EXISTS "student_type" VARCHAR(20) NULL'))
        conn.execute(text('ALTER TABLE self_signed_students ADD COLUMN IF NOT EXISTS "roll_number" VARCHAR(50) NULL'))
        conn.execute(text('ALTER TABLE self_signed_students ADD COLUMN IF NOT EXISTS "previous_school_name" VARCHAR(255) NULL'))
        conn.execute(text('ALTER TABLE self_signed_students ADD COLUMN IF NOT EXISTS "previous_class_marks_obtained" INTEGER NULL'))
        conn.execute(text('ALTER TABLE self_signed_students ADD COLUMN IF NOT EXISTS "previous_class_overall_percentage" FLOAT NULL'))
        conn.execute(text('ALTER TABLE self_signed_students ADD COLUMN IF NOT EXISTS "previous_class_final_grade" VARCHAR(20) NULL'))


def ensure_assignment_activity_tables():
    """Ensure assignment activity tables exist even when RUN_SCHEMA_SYNC is disabled."""
    # assignment_activity models merged into assignments module; no-op maintained for compatibility.
    return


def ensure_assignment_tables():
    """Ensure core assignment module tables exist even when RUN_SCHEMA_SYNC is disabled."""
    from app.models.assignments.assignment import (
        Assignment,
        StudentAssignmentProgress,
        AssignmentKeyPoint,
        AssignmentQuestion,
        AssignmentImage,
        AssignmentPDF,
        AssignmentVideoLink,
        AssignmentMediaBanner,
        PublishConfiguration,
        StudentAssignmentAttempt,
        ChapterFeedback,
        TeacherRating,
        AssignmentView,
        AssignmentDoubt,
        DoubtReply,
        AssignmentReport,
    )

    Assignment.__table__.create(bind=engine, checkfirst=True)
    FavoriteTeacher.__table__.create(bind=engine, checkfirst=True)

    inspector = inspect(engine)
    if inspector.has_table("assignments"):
        if not column_exists("assignments", "created_by_teacher_id"):
            with engine.begin() as conn:
                conn.execute(text('ALTER TABLE assignments ADD COLUMN IF NOT EXISTS created_by_teacher_id VARCHAR NULL'))
        if not column_exists("assignments", "created_by_self_signed_teacher_id"):
            with engine.begin() as conn:
                conn.execute(text('ALTER TABLE assignments ADD COLUMN IF NOT EXISTS created_by_self_signed_teacher_id INTEGER NULL'))
        if not column_exists("assignments", "activity_type"):
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE assignments ADD COLUMN IF NOT EXISTS activity_type VARCHAR(255) NOT NULL DEFAULT 'Academic'"))
        for col_name, col_type in [
            ("class_id", "INTEGER"),
            ("subject_id", "INTEGER"),
            ("chapter_id", "INTEGER"),
            ("chapter_ids", "INTEGER[]"),
            ("title", "VARCHAR(255)"),
            ("chapter_name", "VARCHAR(255)"),
            ("chapter_description", "TEXT"),
            ("chapter_tagline", "VARCHAR(255)"),
            ("sub_chapter", "VARCHAR(255)"),
            ("topic_title", "VARCHAR(255)"),
            ("sub_chapters", "JSON"),
            ("tuition_setup_id", "VARCHAR(255)"),
            ("tuition_date", "DATE"),
            ("total_file_size_bytes", "BIGINT"),
            ("total_file_count", "INTEGER"),
        ]:
            if not column_exists("assignments", col_name):
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE assignments ADD COLUMN IF NOT EXISTS {col_name} {col_type} NULL"))

        # Ensure nullable columns aren't accidentally NOT NULL from old migrations
        nullable_cols = ["title", "chapter_tagline", "sub_chapter", "topic_title",
                         "chapter_name", "chapter_description", "sub_chapters",
                         "tuition_setup_id", "tuition_date", "total_file_size_bytes", "total_file_count"]
        with engine.begin() as conn:
            for col in nullable_cols:
                try:
                    conn.execute(text(f"ALTER TABLE assignments ALTER COLUMN {col} DROP NOT NULL"))
                except Exception:
                    pass  # Already nullable or column doesn't exist — safe to ignore

        # Ensure key point image_url column exists when table already present
        if inspector.has_table("assignment_key_points"):
            if not column_exists("assignment_key_points", "image_url"):
                with engine.begin() as conn:
                    conn.execute(text('ALTER TABLE assignment_key_points ADD COLUMN IF NOT EXISTS image_url VARCHAR NULL'))

        # Ensure assignment_images and assignment_pdfs have all file metadata columns
        _file_meta_cols = [
            ("file_name",        "VARCHAR(255)"),
            ("file_type",        "VARCHAR(50)"),
            ("usage",            "VARCHAR(100)"),
            ("sub_chapter_name", "VARCHAR(255)"),
            ("step_number",      "INTEGER"),
            ("file_size_bytes",  "BIGINT"),
            ("s3_key",           "VARCHAR(500)"),
        ]
        for _tbl in ("assignment_images", "assignment_pdfs"):
            if inspector.has_table(_tbl):
                for _col, _typ in _file_meta_cols:
                    if not column_exists(_tbl, _col):
                        with engine.begin() as conn:
                            conn.execute(text(f"ALTER TABLE {_tbl} ADD COLUMN IF NOT EXISTS {_col} {_typ} NULL"))

        # Ensure merged assignment doubt table columns exist for existing databases
        if inspector.has_table("assignment_doubts"):
            for col_name, col_type in [
                ("self_signed_student_id", "INTEGER"),
                ("question_id", "INTEGER"),
                ("doubt_summary", "VARCHAR(500)"),
                ("status", "VARCHAR(50)"),
                ("created_at", "TIMESTAMP"),
                ("resolved_at", "TIMESTAMP"),
                ("number_of_attempts", "INTEGER"),
                ("last_attempt_date", "TIMESTAMP"),
            ]:
                if not column_exists("assignment_doubts", col_name):
                    with engine.begin() as conn:
                        conn.execute(text(f'ALTER TABLE assignment_doubts ADD COLUMN IF NOT EXISTS "{col_name}" {col_type} NULL'))

        if inspector.has_table("doubt_replies"):
            for col_name, col_type in [
                ("teacher_user_id", "INTEGER"),
                ("self_signed_teacher_id", "INTEGER"),
                ("student_user_id", "INTEGER"),
                ("self_signed_student_id", "INTEGER"),
                ("reply_text", "TEXT"),
                ("file_url", "VARCHAR(255)"),
                ("step_solutions", "TEXT"),
                ("created_at", "TIMESTAMP"),
            ]:
                if not column_exists("doubt_replies", col_name):
                    with engine.begin() as conn:
                        conn.execute(text(f'ALTER TABLE doubt_replies ADD COLUMN IF NOT EXISTS "{col_name}" {col_type} NULL'))

            # Ensure existing copies of the table allow nullable teacher_user_id for self-signed teacher replies
            if column_exists("doubt_replies", "teacher_user_id"):
                current_cols = inspector.get_columns("doubt_replies")
                teacher_col = next((col for col in current_cols if col["name"] == "teacher_user_id"), None)
                if teacher_col is not None and teacher_col.get("nullable") is False:
                    with engine.begin() as conn:
                        conn.execute(text('ALTER TABLE doubt_replies ALTER COLUMN "teacher_user_id" DROP NOT NULL'))

    # Create assignment-related tables used by the app
    StudentAssignmentProgress.__table__.create(bind=engine, checkfirst=True)
    AssignmentKeyPoint.__table__.create(bind=engine, checkfirst=True)
    AssignmentQuestion.__table__.create(bind=engine, checkfirst=True)
    AssignmentImage.__table__.create(bind=engine, checkfirst=True)
    AssignmentPDF.__table__.create(bind=engine, checkfirst=True)
    AssignmentVideoLink.__table__.create(bind=engine, checkfirst=True)
    AssignmentMediaBanner.__table__.create(bind=engine, checkfirst=True)
    PublishConfiguration.__table__.create(bind=engine, checkfirst=True)
    StudentAssignmentAttempt.__table__.create(bind=engine, checkfirst=True)
    ChapterFeedback.__table__.create(bind=engine, checkfirst=True)
    TeacherRating.__table__.create(bind=engine, checkfirst=True)
    AssignmentView.__table__.create(bind=engine, checkfirst=True)
    AssignmentDoubt.__table__.create(bind=engine, checkfirst=True)
    DoubtReply.__table__.create(bind=engine, checkfirst=True)
    AssignmentReport.__table__.create(bind=engine, checkfirst=True)


def ensure_assignment_activity_chapter_ids_column():
    """Ensure assignment activities can store multiple chapter/topic IDs."""
    # Ensure assignments table has chapter_ids column (merged from assignment_activities)
    if not inspect(engine).has_table("assignments"):
        return

    if column_exists("assignments", "chapter_ids"):
        return

    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE assignments ADD COLUMN IF NOT EXISTS chapter_ids INTEGER[] NULL'))


def ensure_worker_payment_settlement_columns():
    """
    Worker payments must track bank/cash source for settlement ledger alignment.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE payment_records
                ADD COLUMN IF NOT EXISTS settlement_channel VARCHAR(32) NOT NULL DEFAULT 'cash_offline'
                """
            )
        )
        conn.execute(
            text(
                """
                ALTER TABLE payment_records
                ADD COLUMN IF NOT EXISTS bank_account_id INTEGER NULL
                """
            )
        )


def ensure_studentstatus_pending_enum_value():
    """Ensure studentstatus enum in PostgreSQL has the 'PENDING' value."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT e.enumlabel
                FROM pg_type t
                JOIN pg_enum e ON t.oid = e.enumtypid
                WHERE t.typname = 'studentstatus'
            """)).fetchall()
            labels = [r[0] for r in result]
            
        if 'PENDING' not in labels:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.execute(text("ALTER TYPE studentstatus ADD VALUE 'PENDING'"))
    except Exception as e:
        print(f"Skipping or failed to alter studentstatus enum (likely not PostgreSQL): {e}")


def ensure_assignmentstatus_enum_values():
    """Ensure the PostgreSQL enum `assignmentstatus` contains the values we use in code.

    Adds any missing lowercase labels (e.g. 'draft','published','unpublished','in_progress','completed').
    Safe-noop on non-Postgres backends or when the type doesn't exist.
    """
    required = [
        'draft',
        'published',
        'unpublished',
        'in_progress',
        'completed',
    ]
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT e.enumlabel FROM pg_type t JOIN pg_enum e ON t.oid = e.enumtypid WHERE t.typname = 'assignmentstatus'"))
            labels = [r[0] for r in result.fetchall()]

        missing = [v for v in required if v not in labels]
        if not missing:
            return

        # ALTER TYPE ... ADD VALUE must run in its own transaction/autocommit
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            for v in missing:
                try:
                    conn.execute(text(f"ALTER TYPE assignmentstatus ADD VALUE '{v}'"))
                except Exception:
                    # If adding a value fails (concurrent change or missing type), ignore and continue
                    pass
    except Exception as e:
        # Non-Postgres or other error; log and continue
        print(f"Skipping or failed to ensure assignmentstatus enum values: {e}")


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()