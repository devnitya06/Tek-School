import sys
from sqlalchemy import text

from app.db.session import SessionLocal, Base

# Import all models so they are registered in Base.metadata
# Example:
# from app.models import *


def clear_tables(table_names=None):
    db = SessionLocal()

    try:
        all_tables = list(Base.metadata.sorted_tables)

        if not all_tables:
            print(
                "No tables found in metadata. Make sure all models are imported."
            )
            return

        if table_names:
            requested = set(table_names)
            available = {table.name for table in all_tables}

            missing = requested - available
            if missing:
                print(
                    f"Warning: Tables not found: {', '.join(sorted(missing))}"
                )

            tables_to_clear = [
                table for table in all_tables if table.name in requested
            ]

            if not tables_to_clear:
                print("No matching tables found.")
                return
        else:
            tables_to_clear = all_tables

        print("\nThe following tables will be cleared:")
        for table in tables_to_clear:
            print(f"  - {table.name}")

        confirmation = input(
            "\nThis will DELETE ALL DATA and RESET IDs. Type YES to continue: "
        )

        if confirmation.strip().upper() != "YES":
            print("Operation cancelled.")
            return

        for table in tables_to_clear:
            print(f"Clearing {table.name}...")
            # Preserve superadmin credential: don't fully truncate `users` table.
            if table.name == "users":
                print("  - Preserving users with role 'superadmin' or 'admin'. Deleting others...")
                # Delete all users except those with admin/superadmin roles
                db.execute(
                    text(f'DELETE FROM "{table.name}" WHERE role NOT IN (\'superadmin\', \'admin\')')
                )
                # Reset the id sequence to the current max(id) to keep identities contiguous
                db.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('\"{table.name}\"','id'), COALESCE((SELECT MAX(id) FROM \"{table.name}\"), 1), true)"
                    )
                )
            else:
                db.execute(
                    text(
                        f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'
                    )
                )

        db.commit()
        print("\n✅ Tables cleared successfully.")

    except Exception as exc:
        db.rollback()
        print(f"\n❌ Failed to clear tables: {exc}")

    finally:
        db.close()


if __name__ == "__main__":
    table_names = sys.argv[1:]

    if table_names:
        print(f"Target tables: {', '.join(table_names)}")
    else:
        print("Target: ALL TABLES")

    clear_tables(table_names)