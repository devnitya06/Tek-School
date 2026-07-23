"""
Script: clear_assignments_db.py

Clears all rows from every table defined in app/models/assignments/assignment.py.
Deletes in FK-safe order (children before parents).

Usage:
    python -m scripts.clear_assignments_db
"""

from sqlalchemy import text
from app.db.session import SessionLocal

# All tables from models/assignments/assignment.py
# Listed children-first so FK constraints are never violated.
TABLES_IN_ORDER = [
    # children of assignment_doubts
    "doubt_replies",

    # children of assignment_questions
    # (assignment_doubts references both assignments + assignment_questions)
    "assignment_doubts",

    # children of student_assignment_attempts / progress
    "student_assignment_attempts",
    "student_assignment_progress",

    # chapter feedback
    "chapter_feedback",

    # views / reports
    "assignment_views",
    "assignment_reports",

    # publish config (1-1 with assignments)
    "publish_configurations",

    # assignment content children
    "assignment_key_points",
    "assignment_questions",
    "assignment_images",
    "assignment_pdfs",
    "assignment_video_links",
    "assignment_media_banners",

    # misc standalone tables from the same file
    "teacher_ratings",
    "favorite_teachers",

    # root table last
    "assignments",
]


def main():
    db = SessionLocal()
    try:
        # Find which tables actually exist in the DB right now
        existing_tables = {
            row[0]
            for row in db.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).fetchall()
        }

        to_clear = [t for t in TABLES_IN_ORDER if t in existing_tables]
        not_found = [t for t in TABLES_IN_ORDER if t not in existing_tables]

        # Show preview with row counts
        print("\n[PREVIEW] Assignment tables:")
        print(f"  {'Table':<45} {'Rows':>8}")
        print("  " + "-" * 54)

        total_rows = 0
        for table in to_clear:
            count = db.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
            total_rows += count
            marker = "  " if count == 0 else "> "
            print(f"  {marker}{table:<43} {count:>8}")

        print("  " + "-" * 54)
        print(f"  {'TOTAL':<45} {total_rows:>8}")

        if not_found:
            print(f"\n[WARN] Tables not found in DB (skipped): {', '.join(not_found)}")

        if total_rows == 0:
            print("\n[OK] All tables are already empty. Nothing to do.")
            return

        # Confirm before deleting
        print(
            f"\n[!] This will permanently DELETE {total_rows} rows "
            f"across {len(to_clear)} tables."
        )
        confirm = input("    Type YES to continue: ").strip().upper()
        if confirm != "YES":
            print("Operation cancelled.")
            return

        # Delete
        print()
        deleted_summary = {}
        for table in to_clear:
            result = db.execute(text(f'DELETE FROM "{table}"'))
            deleted_summary[table] = result.rowcount
            if result.rowcount:
                print(f"  [DEL] {table:<45} {result.rowcount:>6} rows deleted")

        db.commit()

        total_deleted = sum(deleted_summary.values())
        print(f"\n[DONE] {total_deleted} rows deleted across {len(to_clear)} tables.")

    except Exception as exc:
        db.rollback()
        print(f"\n[ERROR] {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
