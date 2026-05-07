"""
Migration script to add register_no and establishment_month fields to schools table.
Run this script to update the database schema.
"""

import sys
from sqlalchemy import text
from app.db.session import SessionLocal, engine

def add_school_profile_fields():
    """
    Add register_no and establishment_month columns to the schools table.
    """
    db = SessionLocal()
    try:
        # Check if columns already exist
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'schools'
            AND column_name IN ('register_no', 'establishment_month')
        """))

        existing_columns = [row[0] for row in result.fetchall()]

        if 'register_no' in existing_columns:
            print("ℹ️  register_no column already exists")
        else:
            print("➕ Adding register_no column...")
            db.execute(text("ALTER TABLE schools ADD COLUMN register_no VARCHAR"))
            print("✅ register_no column added")

        if 'establishment_month' in existing_columns:
            print("ℹ️  establishment_month column already exists")
        else:
            print("➕ Adding establishment_month column...")
            db.execute(text("ALTER TABLE schools ADD COLUMN establishment_month INTEGER"))
            print("✅ establishment_month column added")

        # Commit changes
        db.commit()
        print("\n" + "="*50)
        print("✅ Database migration completed successfully!")
        print("New fields added to schools table:")
        print("  - register_no (VARCHAR)")
        print("  - establishment_month (INTEGER, 1-12)")
        print("="*50)

    except Exception as e:
        db.rollback()
        print(f"❌ Error during migration: {str(e)}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 Starting database migration for school profile fields...")
    add_school_profile_fields()