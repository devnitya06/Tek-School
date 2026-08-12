"""
Migration script to add institution_class column to schools table
"""
import os
import sys
from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

def add_institution_class_column():
    """Add institution_class column to schools table"""
    engine = create_engine(settings.DATABASE_URL)
    
    try:
        with engine.connect() as connection:
            # Check if column already exists
            inspector = inspect(connection)
            columns = [col['name'] for col in inspector.get_columns('schools')]
            
            if 'institution_class' in columns:
                print("✅ institution_class column already exists")
                return
            
            # Add the column
            connection.execute(text("""
                ALTER TABLE schools
                ADD COLUMN institution_class VARCHAR(255) NULL;
            """))
            connection.commit()
            print("✅ institution_class column added successfully")
            
    except Exception as e:
        print(f"❌ Error adding institution_class column: {str(e)}")
        raise

if __name__ == "__main__":
    add_institution_class_column()
