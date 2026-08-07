"""
Safe one-off script to add missing `schools` follow-up columns.
Usage:
  # read DATABASE_URL from env
  setx DATABASE_URL "postgresql://user:pass@host:5432/db"
  python scripts/apply_school_followup_columns_safe.py

Or pass DB URL as first arg:
  python scripts/apply_school_followup_columns_safe.py postgresql://user:pass@host:5432/db

This script avoids importing the application package so it won't trigger module-level DB operations.
"""
import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

DB_URL = None
if len(sys.argv) > 1:
    DB_URL = sys.argv[1]
else:
    DB_URL = os.environ.get("DATABASE_URL")

if not DB_URL:
    print("ERROR: DATABASE_URL must be provided via env or first arg")
    sys.exit(2)

# Use a short connect timeout to fail fast when host is unreachable
engine = create_engine(DB_URL, pool_pre_ping=True, connect_args={"connect_timeout": 5})

followup_columns = [
    ('created_by_admin', 'BOOLEAN NOT NULL DEFAULT FALSE'),
    ('followup_enabled', 'BOOLEAN NOT NULL DEFAULT FALSE'),
    ('followup_days', 'INTEGER NOT NULL DEFAULT 0'),
    ('followup_status', "VARCHAR(255) NOT NULL DEFAULT 'inactive'"),
    ('followup_note', 'VARCHAR NULL'),
    ('followup_last_sent_at', 'TIMESTAMP NULL'),
    ('followup_completed_at', 'TIMESTAMP NULL'),
]

try:
    with engine.begin() as conn:
        for col_name, ddl in followup_columns:
            print(f"Ensuring column {col_name} ...")
            conn.execute(text(f'ALTER TABLE schools ADD COLUMN IF NOT EXISTS "{col_name}" {ddl}'))
    print("All followup columns ensured.")
except SQLAlchemyError as e:
    print("SQLAlchemyError:", e)
    sys.exit(3)
except Exception as e:
    print("Error:", e)
    sys.exit(4)
