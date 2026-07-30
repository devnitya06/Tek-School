"""
Script: clear_tuition_class_sessions.py

Clears all rows from the tuition class-session table used by the tuition class-session feature.
"""

from sqlalchemy import text

from app.db.session import SessionLocal


def main():
    db = SessionLocal()
    try:
        table_name = "tuition_teaching_setup_class_sessions"
        count = db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
        print(f"Found {count} rows in {table_name}")
        db.execute(text(f'DELETE FROM "{table_name}"'))
        db.commit()
        print(f"Cleared all rows from {table_name}")
    except Exception as exc:
        db.rollback()
        print(f"Error clearing {table_name}: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
