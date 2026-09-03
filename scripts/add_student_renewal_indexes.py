"""
Migration script: Add indexes to optimize student renewal queries.

These indexes prevent full table scans and lock contention during bulk updates
of expired student records.

Run from project root:
    python scripts/add_student_renewal_indexes.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.db.session import SessionLocal
from app.core.logger import logger

INDEXES_TO_CREATE = [
    {
        "table": "schools",
        "index_name": "idx_schools_pagination",
        "columns": "(created_at DESC, id)",
        "description": "Stable ORDER BY created_at DESC plus id tie-breaker for admin pagination",
    },
    {
        "table": "students",
        "index_name": "idx_students_status_expiry_date_status",
        "columns": "(status_expiry_date, status)",
        "description": "Composite index for renewal query (WHERE status_expiry_date < now AND status != INACTIVE)",
    },
    {
        "table": "self_signed_students",
        "index_name": "idx_self_signed_students_status_expiry_date_status",
        "columns": "(status_expiry_date, status)",
        "description": "Composite index for self-signed renewal query",
    },
]


def main():
    db = SessionLocal()
    try:
        for idx_config in INDEXES_TO_CREATE:
            table = idx_config["table"]
            index_name = idx_config["index_name"]
            columns = idx_config["columns"]
            description = idx_config["description"]

            # Check if index already exists
            check_query = f"""
                SELECT 1 FROM pg_indexes
                WHERE tablename = '{table}' AND indexname = '{index_name}'
            """
            result = db.execute(text(check_query)).fetchone()

            if result:
                logger.info(f"✓ Index {index_name} already exists on {table}")
                continue

            # Create the index
            create_query = f"CREATE INDEX {index_name} ON {table} {columns}"
            logger.info(f"Creating index: {index_name} — {description}")
            db.execute(text(create_query))
            db.commit()
            logger.info(f"✓ Index {index_name} created successfully")

    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to create indexes: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)
    finally:
        db.close()

    logger.info("\n✅ All indexes created or verified")


if __name__ == "__main__":
    main()
