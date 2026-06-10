"""
Migration script to add the self-signed teacher teaching configuration schema.
Run this script once after deploying the Self Sign Teacher teaching configuration feature.
"""

import sys
from sqlalchemy import text
from app.db.session import SessionLocal


def add_self_signed_teacher_teaching_configuration_schema():
    db = SessionLocal()
    try:
        print("🚀 Starting teaching configuration database migration...")

        result = db.execute(text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'self_signed_teacher_teaching_configurations'
              AND table_schema = 'public'
            """
        ))
        if result.first():
            print("ℹ️  Table self_signed_teacher_teaching_configurations already exists")
            return

        print("➕ Creating self_signed_teacher_teaching_configurations table...")
        db.execute(text(
            """
            CREATE TABLE self_signed_teacher_teaching_configurations (
                id SERIAL PRIMARY KEY,
                self_signed_teacher_id INTEGER NOT NULL,
                board_id VARCHAR(50) NOT NULL,
                class_id INTEGER NOT NULL,
                subject_ids INTEGER[] NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NULL,
                CONSTRAINT fk_teaching_configuration_teacher
                    FOREIGN KEY (self_signed_teacher_id)
                    REFERENCES self_signed_teachers(id) ON DELETE CASCADE,
                CONSTRAINT fk_teaching_configuration_class
                    FOREIGN KEY (class_id)
                    REFERENCES school_classes_subjects(id)
            )
            """
        ))
        print("✅ Created self_signed_teacher_teaching_configurations table")

        db.commit()
        print("\n✅ Teaching configuration migration completed successfully.")

    except Exception as exc:
        db.rollback()
        print(f"❌ Migration failed: {exc}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    add_self_signed_teacher_teaching_configuration_schema()
