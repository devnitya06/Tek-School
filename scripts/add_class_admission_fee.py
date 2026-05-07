"""
Migration script to add admission_fee field to classes table.
Run this script to update the database schema.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.db.session import SessionLocal, engine

def add_admission_fee_column():
    """
    Add admission_fee column to the classes table.
    """
    db = SessionLocal()
    try:
        # Check if column already exists
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'classes'
            AND column_name = 'admission_fee'
        """))
        if result.fetchone():
            print("admission_fee column already exists in classes table.")
            return

        # Add admission_fee column to classes table
        db.execute(text("ALTER TABLE classes ADD COLUMN admission_fee FLOAT DEFAULT 0.0"))
        db.commit()
        print("Successfully added admission_fee column to classes table.")
    except Exception as e:
        db.rollback()
        print(f"Error adding admission_fee column: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    add_admission_fee_column()