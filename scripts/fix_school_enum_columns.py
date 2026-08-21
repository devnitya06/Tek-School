"""
Migration script: Convert school_type, school_medium, school_board columns
from native PostgreSQL enum types to VARCHAR(50).

The Python model uses SchoolAccountTypeDecorator (impl = String), so the DB
columns must be VARCHAR — not native PG enums.  When the column is still a
native enum, PostgreSQL rejects lowercase values like "private" because the
enum labels may differ in case, causing the 500 error:
    invalid input value for enum schooltype: "private"

Run from the project root:
    python scripts/fix_school_enum_columns.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.core.config import settings

# Columns to migrate and the PG enum type name each one currently uses.
# If the column is already VARCHAR the script will skip it safely.
ENUM_COLUMNS = {
    "school_type":   "schooltype",
    "school_medium": "schoolmedium",
    "school_board":  "schoolboard",
}


def get_column_type(conn, table: str, column: str) -> str:
    row = conn.execute(
        text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).fetchone()
    return row[0].lower() if row else ""


def convert_enum_to_varchar(conn, column: str):
    """
    Safely converts a native-enum column to VARCHAR(50) while preserving data.
    Uses a temp column so the rename is atomic inside the same transaction.
    """
    tmp = f"_tmp_{column}"
    print(f"  -> converting '{column}' from enum to VARCHAR ...")

    # 1. Add a temporary VARCHAR column
    conn.execute(text(
        f'ALTER TABLE schools ADD COLUMN IF NOT EXISTS "{tmp}" VARCHAR(50)'
    ))

    # 2. Copy existing values (cast to text to handle any case)
    conn.execute(text(
        f'UPDATE schools SET "{tmp}" = "{column}"::text'
    ))

    # 3. Drop the old enum column
    conn.execute(text(f'ALTER TABLE schools DROP COLUMN "{column}"'))

    # 4. Rename temp column to original name
    conn.execute(text(f'ALTER TABLE schools RENAME COLUMN "{tmp}" TO "{column}"'))

    print(f"     OK '{column}' is now VARCHAR(50).")


def main():
    engine = create_engine(settings.DATABASE_URL)
    with engine.begin() as conn:
        print("=" * 60)
        print("School Enum -> VARCHAR Migration")
        print("=" * 60)

        for col, pg_type in ENUM_COLUMNS.items():
            ct = get_column_type(conn, "schools", col)
            if not ct:
                print(f"  WARN: column '{col}' not found in 'schools' table -- skipping.")
            elif ct in ("character varying", "varchar", "text"):
                print(f"  SKIP: '{col}' is already VARCHAR -- no change needed.")
            elif ct == "user-defined":
                # Native PG enum shows as 'USER-DEFINED' in information_schema
                convert_enum_to_varchar(conn, col)
            else:
                print(f"  WARN: '{col}' has unexpected type '{ct}' -- skipping.")

        print("=" * 60)
        print("Migration complete.")
        print("=" * 60)


if __name__ == "__main__":
    main()
