"""
Migration script to add self-signed teacher schema and related DB columns.
Run this script against your database once after the self-signed teacher feature is deployed.
"""

import sys
from sqlalchemy import text
from app.db.session import SessionLocal


def add_self_signed_teacher_schema():
    db = SessionLocal()
    try:
        print("🚀 Starting self-signed teacher database migration...")

        # Add users columns if missing
        for column_name, column_sql in (
            ("verification_status", "VARCHAR(50) NOT NULL DEFAULT 'pending'"),
            ("profile_completed", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ):
            result = db.execute(text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'users'
                AND column_name = :column_name
                """), {"column_name": column_name})
            if result.first():
                print(f"ℹ️  users.{column_name} already exists")
            else:
                print(f"➕ Adding users.{column_name}...")
                db.execute(text(
                    f'ALTER TABLE users ADD COLUMN {column_name} {column_sql}'
                ))
                print(f"✅ Added users.{column_name}")

        # Ensure Postgres userrole enum includes the new self_signed_teacher value
        enum_exists = db.execute(text(
            """
            SELECT 1
            FROM pg_type t
            JOIN pg_enum e ON t.oid = e.enumtypid
            WHERE t.typname = 'userrole'
              AND e.enumlabel = 'self_signed_teacher'
            """
        )).first()
        if enum_exists:
            print("ℹ️  userrole enum already includes self_signed_teacher")
        else:
            print("➕ Adding self_signed_teacher to userrole enum...")
            db.execute(text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_type t
                        JOIN pg_enum e ON t.oid = e.enumtypid
                        WHERE t.typname = 'userrole'
                          AND e.enumlabel = 'self_signed_teacher'
                    ) THEN
                        ALTER TYPE userrole ADD VALUE 'self_signed_teacher';
                    END IF;
                END$$;
                """
            ))
            print("✅ Added self_signed_teacher enum value")

        # Add students.self_signed_teacher_id if missing
        result = db.execute(text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'students'
            AND column_name = 'self_signed_teacher_id'
            """
        ))
        if result.first():
            print("ℹ️  students.self_signed_teacher_id already exists")
        else:
            print("➕ Adding students.self_signed_teacher_id...")
            db.execute(text(
                "ALTER TABLE students ADD COLUMN self_signed_teacher_id INTEGER"
            ))
            print("✅ Added students.self_signed_teacher_id")

        # Add self_signed_teachers table if missing
        result = db.execute(text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'self_signed_teachers'
            """
        ))
        if result.first():
            print("ℹ️  Table self_signed_teachers already exists")
        else:
            print("➕ Creating self_signed_teachers table...")
            db.execute(text(
                """
                CREATE TABLE self_signed_teachers (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE,
                    first_name VARCHAR(100) NOT NULL,
                    last_name VARCHAR(100) NOT NULL,
                    gender VARCHAR(20) NOT NULL,
                    dob DATE NOT NULL,
                    profile_image VARCHAR NULL,
                    phone VARCHAR(20) NOT NULL,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    bio VARCHAR(500) NULL,
                    qualification VARCHAR(255) NULL,
                    university VARCHAR(255) NULL,
                    institution_name VARCHAR(255) NULL,
                    designation VARCHAR(255) NULL,
                    institution_pin_code VARCHAR(20) NULL,
                    division VARCHAR(100) NULL,
                    district VARCHAR(100) NULL,
                    state VARCHAR(100) NULL,
                    landmark VARCHAR(255) NULL,
                    joining_date DATE NULL,
                    official_id_card VARCHAR NULL,
                    invite_code VARCHAR(32) NOT NULL UNIQUE,
                    profile_status VARCHAR(50) NOT NULL DEFAULT 'draft',
                    rejection_reason VARCHAR(500) NULL,
                    blocked_reason VARCHAR(500) NULL,
                    verified_by INTEGER NULL,
                    verified_at TIMESTAMP WITH TIME ZONE NULL,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NULL,
                    CONSTRAINT fk_self_signed_teacher_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    CONSTRAINT fk_self_signed_teacher_verified_by FOREIGN KEY (verified_by) REFERENCES users(id)
                )
                """
            ))
            print("✅ Created self_signed_teachers table")

        # Add foreign key constraint for students.self_signed_teacher_id if possible and not present
        if not db.execute(text(
            """
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_catalog = kcu.constraint_catalog
              AND tc.constraint_schema = kcu.constraint_schema
              AND tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'students'
              AND tc.constraint_type = 'FOREIGN KEY'
              AND kcu.column_name = 'self_signed_teacher_id'
            """
        )).first():
            print("➕ Adding foreign key constraint students.self_signed_teacher_id -> self_signed_teachers.id...")
            try:
                db.execute(text(
                    "ALTER TABLE students ADD CONSTRAINT fk_students_self_signed_teacher "
                    "FOREIGN KEY (self_signed_teacher_id) REFERENCES self_signed_teachers(id)"
                ))
                print("✅ Added students.self_signed_teacher_id foreign key")
            except Exception:
                print("⚠️ Could not add students foreign key constraint at this time.")
        else:
            print("ℹ️  Foreign key constraint for students.self_signed_teacher_id already exists")

        for column_name in ("gender", "dob"):
            result = db.execute(text(
                """
                SELECT is_nullable
                FROM information_schema.columns
                WHERE table_name = 'self_signed_teachers'
                  AND column_name = :column_name
                """), {"column_name": column_name})
            column_info = result.first()
            if column_info and column_info[0] == 'NO':
                print(f"➕ Altering self_signed_teachers.{column_name} to be nullable...")
                db.execute(text(
                    f'ALTER TABLE self_signed_teachers ALTER COLUMN {column_name} DROP NOT NULL'
                ))
                print(f"✅ Altered self_signed_teachers.{column_name} to be nullable")
            else:
                print(f"ℹ️  self_signed_teachers.{column_name} is already nullable")

        db.commit()
        print("\n✅ Database migration completed successfully.")

    except Exception as exc:
        db.rollback()
        print(f"❌ Migration failed: {exc}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    add_self_signed_teacher_schema()
