"""Convert schools.school_medium from VARCHAR(50) to VARCHAR[].

Run from the project root:
    python scripts/migrate_school_medium_to_array.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

from app.core.config import settings


def main():
    engine = create_engine(settings.DATABASE_URL)
    with engine.begin() as conn:
        column_type = conn.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'schools' AND column_name = 'school_medium'"
            )
        ).scalar()

        if column_type == "ARRAY":
            print("school_medium is already VARCHAR[].")
            return
        if column_type not in ("character varying", "text"):
            raise RuntimeError(
                f"Unexpected school_medium type: {column_type!r}; migration stopped."
            )

        conn.execute(text("""
            ALTER TABLE schools
            ALTER COLUMN school_medium TYPE VARCHAR(50)[]
            USING CASE
                WHEN school_medium IS NULL OR trim(school_medium) = '' THEN NULL
                ELSE ARRAY[school_medium]
            END
        """))
        print("Converted school_medium to VARCHAR[] and preserved existing values.")


if __name__ == "__main__":
    main()
