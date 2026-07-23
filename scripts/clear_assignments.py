"""
Script: clear_assignments.py

Deletes all rows from every assignment-related table in FK-safe order.
Child tables are cleared first so no FK constraint is violated.

Usage:
    python -m scripts.clear_assignments
"""

from sqlalchemy import text
from app.db.session import SessionLocal

# Tables in dependency order (children before parents)
ASSIGNMENT_TABLES = [
    # Mapping tables / child dependants first
    "tuition_lesson_assignment_mappings",
    # Doubt replies → doubts
    "doubt_replies",
    "assignment_doubts",
    # Student-level tables
    "student_assignment_attempts",
    "student_assignment_progress",
    "assignment_students",          # home_assignment children
    "assignment_task_statuses",     # if this table exists
    "assignment_tasks",             # home_assignment children
    # Feedback / activity
    "chapter_feedback",
    "assignment_views",
    "assignment_reports",
    # Publish config (1-1 with assignment)
    "publish_configurations",
    # Assignment media / content
    "assignment_key_points",
    "assignment_questions",
    "assignment_images",
    "assignment_pdfs",
    "assignment_video_links",
    "assignment_media_banners",
    # Root tables last
    "home_assignments",
    "assignments",
]


def clear_assignments():
    db = SessionLocal()
    try:
        # Discover which tables actually exist in the DB
        existing = {
            row[0]
            for row in db.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                )
            ).fetchall()
        }

        to_clear = [t for t in ASSIGNMENT_TABLES if t in existing]
        skipped  = [t for t in ASSIGNMENT_TABLES if t not in existing]

        print("\n📋 Tables to be cleared:")
        for t in to_clear:
            count = db.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
            print(f"   {t:<50} {count:>6} rows")

        if skipped:
            print("\n⚠️  Tables not found in DB (skipped):")
            for t in skipped:
                print(f"   {t}")

        total_rows = sum(
            db.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
            for t in to_clear
        )

        if total_rows == 0:
            print("\n✅ All assignment tables are already empty. Nothing to do.")
            return

        confirm = input(
            f"\n⚠️  This will permanently DELETE {total_rows} rows across "
            f"{len(to_clear)} tables.\n"
            "   Type YES to continue: "
        )
        if confirm.strip().upper() != "YES":
            print("Operation cancelled.")
            return

        deleted = {}
        for table in to_clear:
            result = db.execute(text(f'DELETE FROM "{table}"'))
            deleted[table] = result.rowcount

        db.commit()

        print("\n✅ Cleared successfully:")
        for table, count in deleted.items():
            if count:
                print(f"   {table:<50} {count:>6} rows deleted")

        print(f"\n   Total rows deleted: {sum(deleted.values())}")

    except Exception as exc:
        db.rollback()
        print(f"\n❌ Error: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    clear_assignments()
