"""
Migration script to add optional student profile fields to students table.
Run this script to update the database schema.
"""

import sys
from sqlalchemy import text
from app.db.session import SessionLocal


def add_student_profile_fields():
    """
    Add blood_group, date_of_admission, previous_class_marks_obtained,
    previous_class_overall_percentage, and previous_class_final_grade columns
    to the students table.
    """
    db = SessionLocal()
    try:
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'students'
            AND column_name IN (
                'blood_group',
                'date_of_admission',
                'previous_class_marks_obtained',
                'previous_class_overall_percentage',
                'previous_class_final_grade'
            )
        """))

        existing_columns = {row[0] for row in result.fetchall()}

        if 'blood_group' in existing_columns:
            print("ℹ️  blood_group column already exists")
        else:
            print("➕ Adding blood_group column...")
            db.execute(text('ALTER TABLE students ADD COLUMN blood_group VARCHAR(20)'))
            print("✅ blood_group column added")

        if 'date_of_admission' in existing_columns:
            print("ℹ️  date_of_admission column already exists")
        else:
            print("➕ Adding date_of_admission column...")
            db.execute(text('ALTER TABLE students ADD COLUMN date_of_admission DATE'))
            print("✅ date_of_admission column added")

        if 'previous_class_marks_obtained' in existing_columns:
            print("ℹ️  previous_class_marks_obtained column already exists")
        else:
            print("➕ Adding previous_class_marks_obtained column...")
            db.execute(text('ALTER TABLE students ADD COLUMN previous_class_marks_obtained INTEGER'))
            print("✅ previous_class_marks_obtained column added")

        if 'previous_class_overall_percentage' in existing_columns:
            print("ℹ️  previous_class_overall_percentage column already exists")
        else:
            print("➕ Adding previous_class_overall_percentage column...")
            db.execute(text('ALTER TABLE students ADD COLUMN previous_class_overall_percentage FLOAT'))
            print("✅ previous_class_overall_percentage column added")

        if 'previous_class_final_grade' in existing_columns:
            print("ℹ️  previous_class_final_grade column already exists")
        else:
            print("➕ Adding previous_class_final_grade column...")
            db.execute(text('ALTER TABLE students ADD COLUMN previous_class_final_grade VARCHAR(20)'))
            print("✅ previous_class_final_grade column added")

        db.commit()

        print("\n" + "="*50)
        print("✅ Database migration completed successfully!")
        print("New optional student profile fields added to students table:")
        print("  - blood_group")
        print("  - date_of_admission")
        print("  - previous_class_marks_obtained")
        print("  - previous_class_overall_percentage")
        print("  - previous_class_final_grade")
        print("="*50)

    except Exception as e:
        db.rollback()
        print(f"❌ Error during migration: {str(e)}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    print("🚀 Starting database migration for student profile fields...")
    add_student_profile_fields()
