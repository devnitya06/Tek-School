"""
clear_assignments.py
Deletes ALL assignment-related data from the database.
Run with: python clear_assignments.py
"""
from app.db.session import engine
from sqlalchemy import text

TABLES_IN_ORDER = [
    # Child tables first (FK constraints)
    "doubt_replies",
    "assignment_doubts",
    "assignment_reports",
    "chapter_feedback",          # actual table name
    "student_assignment_attempts",
    "student_assignment_progress",
    "assignment_key_points",
    "assignment_images",
    "assignment_pdfs",
    "assignment_video_links",
    "assignment_media_banners",
    "publish_configurations",
    "assignment_questions",
    "teacher_ratings",
    "assignment_views",
    "favorite_teachers",
    # Parent table last
    "assignments",
]

def clear_assignments():
    print("Clearing ALL assignment data...\n")
    total_deleted = 0
    for table in TABLES_IN_ORDER:
        # Each table in its own transaction so one failure doesn't block others
        try:
            with engine.begin() as conn:
                result = conn.execute(text(f"DELETE FROM {table}"))
                n = result.rowcount
                total_deleted += n
                print(f"  OK   {table}: {n} rows deleted")
        except Exception as e:
            msg = str(e).split('\n')[0]
            print(f"  SKIP {table}: {msg}")

    print(f"\nDone. Total rows deleted: {total_deleted}")

if __name__ == "__main__":
    clear_assignments()
