"""
Migration script: Add missing values to the PostgreSQL `schoolboard` enum type.

Run from the project root:
    python scripts/fix_schoolboard_enum.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from app.core.config import settings

# All values that SHOULD exist in the schoolboard enum (matching SchoolBoard Python enum values)
REQUIRED_VALUES = [
    "cbse",
    "icse",
    "stateboard",
    "ib",
    "other",
    "pre_board_education",
    "cisce",
    "cambridge",
    "nios",
    "higher_education",
    "professional_education",
    "medical_pharma",
    "university",
    "training_coaching",
    "creative_training",
]

def main():
    url = settings.DATABASE_URL
    # Parse psycopg2 connection from SQLAlchemy URL
    # e.g. postgresql://user:pass@host:port/dbname
    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()

    # Fetch current enum values from PostgreSQL
    cur.execute("""
        SELECT enumlabel
        FROM pg_enum
        JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
        WHERE pg_type.typname = 'schoolboard'
        ORDER BY enumsortorder;
    """)
    existing = {row[0] for row in cur.fetchall()}
    print(f"Existing DB enum values: {sorted(existing)}")

    added = []
    skipped = []
    for value in REQUIRED_VALUES:
        if value not in existing:
            print(f"  Adding '{value}' ...")
            cur.execute(f"ALTER TYPE schoolboard ADD VALUE IF NOT EXISTS '{value}';")
            added.append(value)
        else:
            skipped.append(value)

    cur.close()
    conn.close()

    print(f"\nDone. Added: {added}")
    print(f"Already existed: {skipped}")

if __name__ == "__main__":
    main()
