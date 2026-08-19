"""Create placement tables and migrate campus_month in an existing database.

Run from the repository root after configuring DATABASE_URL.
"""

from sqlalchemy import inspect, text

from app.db.session import engine
from app.models.placement import PlacementAchiever, PlacementPartner


def main() -> None:
    PlacementPartner.__table__.create(bind=engine, checkfirst=True)
    PlacementAchiever.__table__.create(bind=engine, checkfirst=True)
    inspector = inspect(engine)
    columns = {column["name"]: column for column in inspector.get_columns("placement_partners")}
    if "campus_date" in columns and "campus_month" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE placement_partners RENAME COLUMN campus_date TO campus_month"))
        columns = {column["name"]: column for column in inspect(engine).get_columns("placement_partners")}
    campus_column = columns.get("campus_month")
    if campus_column and "date" in str(campus_column["type"]).lower():
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE placement_partners ALTER COLUMN campus_month TYPE INTEGER USING EXTRACT(MONTH FROM campus_month)::INTEGER"))
    print("Placement tables are ready.")


if __name__ == "__main__":
    main()