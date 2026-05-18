"""
Migration script to create/update tables for CommunicationSection and Achievement models.
Run this script with the project's virtualenv active:

    python scripts/update_db_communication_achievements.py

It uses existing helpers in `app.db.session` to create tables and add missing columns
based on SQLAlchemy models (safe idempotent operations).
"""

import sys
from sqlalchemy import inspect
from app.db.session import engine, create_tables, add_missing_columns


def ensure_comm_and_ach_tables():
    inspector = inspect(engine)
    required_tables = ["communication_sections", "achievements"]

    missing = [t for t in required_tables if not inspector.has_table(t)]

    if missing:
        print("➕ Missing tables detected:", ", ".join(missing))
        print("Creating tables from SQLAlchemy models...")
        create_tables()
    else:
        print("ℹ️  All required tables already exist.")

    print("🔄 Ensuring model columns exist and adding any missing columns...")
    add_missing_columns()

    # Re-inspect and report
    inspector = inspect(engine)
    for t in required_tables:
        if inspector.has_table(t):
            print(f"✅ Table '{t}' exists")
        else:
            print(f"❌ Table '{t}' is still missing")


if __name__ == "__main__":
    print("🚀 Starting DB update: CommunicationSection & Achievement...")
    try:
        ensure_comm_and_ach_tables()
        print("\n✅ Database update finished successfully.")
    except Exception as e:
        print(f"❌ Database update failed: {e}")
        sys.exit(1)
