"""
Migration script to add registration_no to students and education to parents.
Run this script to update the database schema.
"""

import sys
from sqlalchemy import text
from app.db.session import SessionLocal


def add_registration_and_parent_education_fields():
    """
    Add registration_no to the students table and education to the parents table.
    """
    db = SessionLocal()
    try:
        result = db.execute(text("""
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE (table_name = 'students' AND column_name = 'registration_no')
               OR (table_name = 'parents' AND column_name = 'education')
        """))

        existing_columns = {f"{row[0]}.{row[1]}" for row in result.fetchall()}

        if 'students.registration_no' in existing_columns:
            print("ℹ️  students.registration_no column already exists")
        else:
            print("➕ Adding students.registration_no column...")
            db.execute(text("ALTER TABLE students ADD COLUMN registration_no VARCHAR(50)"))
            print("✅ students.registration_no column added")

        if 'parents.education' in existing_columns:
            print("ℹ️  parents.education column already exists")
        else:
            print("➕ Adding parents.education column...")
            db.execute(text("ALTER TABLE parents ADD COLUMN education VARCHAR(150)"))
            print("✅ parents.education column added")

        db.commit()

        print("\n" + "="*50)
        print("✅ Database migration completed successfully!")
        print("New optional fields added:")
        print("  - students.registration_no")
        print("  - parents.education")
        print("="*50)

    except Exception as e:
        db.rollback()
        print(f"❌ Error during migration: {str(e)}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    print("🚀 Starting database migration for student registration and parent education fields...")
    add_registration_and_parent_education_fields()
