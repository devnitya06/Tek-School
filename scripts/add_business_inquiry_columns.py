"""
Migration script to add new columns to business_inquiry table:
- prefer_time
- remark
- is_seen
- seen_at
"""
import os
import sys
from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

def add_business_inquiry_columns():
    """Add new columns to business_inquiry table"""
    engine = create_engine(settings.DATABASE_URL)
    
    try:
        with engine.connect() as connection:
            # Check which columns already exist
            inspector = inspect(connection)
            columns = [col['name'] for col in inspector.get_columns('business_inquiry')]
            
            operations = []
            
            if 'prefer_time' not in columns:
                operations.append("ALTER TABLE business_inquiry ADD COLUMN prefer_time VARCHAR(50) NULL;")
            
            if 'remark' not in columns:
                operations.append("ALTER TABLE business_inquiry ADD COLUMN remark TEXT NULL;")
            
            if 'is_seen' not in columns:
                operations.append("ALTER TABLE business_inquiry ADD COLUMN is_seen BOOLEAN NOT NULL DEFAULT FALSE;")
            
            if 'seen_at' not in columns:
                operations.append("ALTER TABLE business_inquiry ADD COLUMN seen_at TIMESTAMP WITH TIME ZONE NULL;")
            
            if operations:
                for op in operations:
                    connection.execute(text(op))
                connection.commit()
                print(f"✅ Added {len(operations)} column(s) to business_inquiry table")
            else:
                print("✅ All columns already exist")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise

if __name__ == "__main__":
    add_business_inquiry_columns()
