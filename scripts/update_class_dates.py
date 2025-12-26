"""
Migration script to update existing Class records with default start and end dates.
This script:
1. Adds the date columns if they don't exist (as nullable)
2. Updates all existing Class records with default dates
3. Sets the columns to NOT NULL
- class_start_date: 2026-01-01 (January 1, 2026)
- class_end_date: 2026-12-31 (December 31, 2026)
"""
import sys
from datetime import date
from sqlalchemy import inspect, text
from app.db.session import SessionLocal, engine
from app.models.school import Class

def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        return False
    columns = inspector.get_columns(table_name)
    return any(column['name'] == column_name for column in columns)

def update_class_dates():
    """Update all existing Class records with default dates"""
    db = SessionLocal()
    try:
        # Default dates as specified
        default_start_date = date(2026, 1, 1)  # January 1, 2026
        default_end_date = date(2026, 12, 31)  # December 31, 2026
        
        # Step 1: Add columns if they don't exist (as nullable first)
        if not column_exists("classes", "class_start_date"):
            print("📝 Adding class_start_date column...")
            with engine.begin() as conn:
                conn.execute(text('ALTER TABLE "classes" ADD COLUMN "class_start_date" DATE'))
        
        if not column_exists("classes", "class_end_date"):
            print("📝 Adding class_end_date column...")
            with engine.begin() as conn:
                conn.execute(text('ALTER TABLE "classes" ADD COLUMN "class_end_date" DATE'))
        
        # Step 2: Update all classes that don't have dates set
        classes = db.query(Class).filter(
            (Class.class_start_date == None) | (Class.class_end_date == None)
        ).all()
        
        if classes:
            updated_count = 0
            for class_obj in classes:
                if class_obj.class_start_date is None:
                    class_obj.class_start_date = default_start_date
                if class_obj.class_end_date is None:
                    class_obj.class_end_date = default_end_date
                updated_count += 1
            
            db.commit()
            print(f"✅ Successfully updated {updated_count} class(es) with default dates:")
            print(f"   - Start Date: {default_start_date}")
            print(f"   - End Date: {default_end_date}")
        else:
            print("✅ No classes need updating. All classes already have dates set.")
        
        # Step 3: Set columns to NOT NULL
        print("📝 Setting columns to NOT NULL...")
        with engine.begin() as conn:
            # Check current nullability
            inspector = inspect(engine)
            columns = inspector.get_columns("classes")
            start_date_col = next((c for c in columns if c['name'] == 'class_start_date'), None)
            end_date_col = next((c for c in columns if c['name'] == 'class_end_date'), None)
            
            if start_date_col and start_date_col.get('nullable', True):
                conn.execute(text('ALTER TABLE "classes" ALTER COLUMN "class_start_date" SET NOT NULL'))
            
            if end_date_col and end_date_col.get('nullable', True):
                conn.execute(text('ALTER TABLE "classes" ALTER COLUMN "class_end_date" SET NOT NULL'))
        
        print("✅ Migration completed successfully!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Failed to update class dates: {str(e)}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    print("🔄 Starting migration to update class dates...")
    update_class_dates()
    print("✅ Migration completed!")

