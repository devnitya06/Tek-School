"""
Migration script to add register_no and establishment_month fields to schools table.
Run this script to update the database schema.
"""

import sys
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.db.session import SessionLocal

def add_school_profile_fields():
    """
    Add register_no, establishment_month, and new school profile columns to the schools table.
    """
    db = SessionLocal()
    try:
        # Check if columns already exist
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'schools'
            AND column_name IN (
                'register_no', 'establishment_month',
                'hostel', 'computer_lab', 'medical_faculties',
                'job_assurance', 'admission_process', 'internship',
                'lms_facility', 'alumni_network', 'library',
                'available_classes', 'photo_gallery_batches'
            )
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

        if 'hostel' in existing_columns:
            print("ℹ️  hostel column already exists")
        else:
            print("➕ Adding hostel column...")
            db.execute(text("ALTER TABLE schools ADD COLUMN hostel VARCHAR[]"))
            print("✅ hostel column added")

        if 'computer_lab' in existing_columns:
            print("ℹ️  computer_lab column already exists")
        else:
            print("➕ Adding computer_lab column...")
            db.execute(text("ALTER TABLE schools ADD COLUMN computer_lab BOOLEAN"))
            print("✅ computer_lab column added")

        if 'medical_faculties' in existing_columns:
            print("ℹ️  medical_faculties column already exists")
        else:
            print("➕ Adding medical_faculties column...")
            db.execute(text("ALTER TABLE schools ADD COLUMN medical_faculties VARCHAR"))
            print("✅ medical_faculties column added")

        if 'job_assurance' in existing_columns:
            print("ℹ️  job_assurance column already exists")
        else:
            print("➕ Adding job_assurance column...")
            db.execute(text("ALTER TABLE schools ADD COLUMN job_assurance VARCHAR"))
            print("✅ job_assurance column added")

        if 'admission_process' in existing_columns:
            print("ℹ️  admission_process column already exists")
        else:
            print("➕ Adding admission_process column...")
            db.execute(text("ALTER TABLE schools ADD COLUMN admission_process VARCHAR"))
            print("✅ admission_process column added")

        if 'internship' in existing_columns:
            print("ℹ️  internship column already exists")
        else:
            print("➕ Adding internship column...")
            db.execute(text("ALTER TABLE schools ADD COLUMN internship VARCHAR"))
            print("✅ internship column added")

        if 'lms_facility' in existing_columns:
            print("ℹ️  lms_facility column already exists")
        else:
            print("➕ Adding lms_facility column...")
            db.execute(text("ALTER TABLE schools ADD COLUMN lms_facility BOOLEAN"))
            print("✅ lms_facility column added")

        if 'alumni_network' in existing_columns:
            print("ℹ️  alumni_network column already exists")
        else:
            print("➕ Adding alumni_network column...")
            db.execute(text("ALTER TABLE schools ADD COLUMN alumni_network BOOLEAN"))
            print("✅ alumni_network column added")

        if 'library' in existing_columns:
            print("ℹ️  library column already exists")
        else:
            print("➕ Adding library column...")
            db.execute(text("ALTER TABLE schools ADD COLUMN library BOOLEAN"))
            print("✅ library column added")

        if 'available_classes' in existing_columns:
            print("ℹ️  available_classes column already exists")
        else:
            print("➕ Adding available_classes column...")
            db.execute(text("ALTER TABLE schools ADD COLUMN available_classes VARCHAR[]"))
            print("✅ available_classes column added")

        if 'photo_gallery_batches' in existing_columns:
            print("ℹ️  photo_gallery_batches column already exists")
        else:
            print("➕ Adding photo_gallery_batches column...")
            db.execute(text("ALTER TABLE schools ADD COLUMN photo_gallery_batches JSON"))
            print("✅ photo_gallery_batches column added")

        # Commit changes
        db.commit()
        print("\n" + "="*50)
        print("✅ Database migration completed successfully!")
        print("New fields added to schools table:")
        print("  - register_no (VARCHAR)")
        print("  - establishment_month (INTEGER, 1-12)")
        print("="*50)

    except SQLAlchemyError as e:
        db.rollback()
        print(f"❌ Error during migration: {e!s}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 Starting database migration for school profile fields...")
    add_school_profile_fields()