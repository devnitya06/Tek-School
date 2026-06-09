from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings


SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Import all models to ensure they're registered with Base
from app.models.users import *
from app.models.school import *
from app.models.teachers import *
from app.models.students import *
from app.models.admin import *
from app.models.staff import *
from app.models.progress_reports import *
from app.models.academic_results import *

def create_tables():
    """Create all tables that don't exist yet"""
    Base.metadata.create_all(bind=engine)

def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        return False
    columns = inspector.get_columns(table_name)
    return any(column['name'] == column_name for column in columns)

def add_missing_columns():
    """Add missing columns to existing tables"""
    inspector = inspect(engine)
    
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
    inspector = inspect(engine)
    
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
    inspector = inspect(engine)
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


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()