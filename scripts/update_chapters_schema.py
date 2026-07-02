"""Ensure Chapter table has new columns for original and summarized content.

Run with repo root in PYTHONPATH, e.g.:
  $env:PYTHONPATH='D:/TakSchool-Backend/Tek-School'
  D:/TakSchool-Backend/Tek-School/venv/Scripts/python.exe scripts/update_chapters_schema.py
"""

from app.db.session import engine
from sqlalchemy import text


def main():
    with engine.connect() as conn:
        print("Ensuring 'original_book_content' and 'summarized_content' columns exist on 'chapters'...")
        conn.execute(text("ALTER TABLE chapters ADD COLUMN IF NOT EXISTS original_book_content TEXT NULL;"))
        conn.execute(text("ALTER TABLE chapters ADD COLUMN IF NOT EXISTS summarized_content TEXT NULL;"))
        print("Done.")


if __name__ == '__main__':
    main()
