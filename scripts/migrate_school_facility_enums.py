"""
Migration script: Convert Boolean facility columns on the schools table to VARCHAR
so they can store enum string values.

Columns migrated:
  have_digital_board, computer_lab, library,
  transportation_facility, playground_facility, have_cctv_in_campus

Boolean mapping:  TRUE -> yes  |  FALSE -> no  |  NULL -> NULL

Run from the project root:
    python scripts/migrate_school_facility_enums.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.core.config import settings

BOOLEAN_COLUMNS = [
    "have_digital_board",
    "computer_lab",
    "library",
    "transportation_facility",
    "playground_facility",
    "have_cctv_in_campus",
]


def get_column_type(conn, table, column):
    row = conn.execute(
        text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).fetchone()
    return row[0].lower() if row else ""


def migrate_boolean_to_varchar(conn, column):
    tmp = "_tmp_" + column
    print(f"  -> migrating '{column}' ...")
    conn.execute(text(f'ALTER TABLE schools ADD COLUMN IF NOT EXISTS "{tmp}" VARCHAR(50)'))
    conn.execute(text(
        f'UPDATE schools SET "{tmp}" = CASE '
        f'WHEN "{column}" IS TRUE THEN \'yes\' '
        f'WHEN "{column}" IS FALSE THEN \'no\' '
        f'ELSE NULL END'
    ))
    conn.execute(text(f'ALTER TABLE schools DROP COLUMN "{column}"'))
    conn.execute(text(f'ALTER TABLE schools RENAME COLUMN "{tmp}" TO "{column}"'))
    print(f"     OK '{column}' converted.")


def main():
    engine = create_engine(settings.DATABASE_URL)
    with engine.begin() as conn:
        print("=" * 60)
        print("School Facility Enum Migration")
        print("=" * 60)
        for col in BOOLEAN_COLUMNS:
            ct = get_column_type(conn, "schools", col)
            if not ct:
                print(f"  WARN: column '{col}' not found -- skipping.")
            elif ct in ("character varying", "varchar", "text"):
                print(f"  SKIP: '{col}' already VARCHAR.")
            elif ct == "boolean":
                migrate_boolean_to_varchar(conn, col)
            else:
                print(f"  WARN: '{col}' has type '{ct}' -- skipping.")

        it = get_column_type(conn, "schools", "internship")
        if it in ("character varying", "varchar", "text"):
            print("  SKIP: 'internship' already VARCHAR -- no change needed.")
        else:
            print(f"  WARN: 'internship' has type '{it}' -- check manually.")

        print("=" * 60)
        print("Migration complete.")
        print("=" * 60)


if __name__ == "__main__":
    main()
