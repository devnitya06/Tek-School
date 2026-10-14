"""One-time fix: add 'agent' value to the userrole PostgreSQL enum."""
from app.db.session import engine
from sqlalchemy import text

with engine.begin() as conn:
    conn.execute(text("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'agent'"))
    print("Added 'agent' to userrole enum")

with engine.connect() as conn:
    result = conn.execute(
        text(
            "SELECT e.enumlabel FROM pg_enum e "
            "JOIN pg_type t ON e.enumtypid = t.oid "
            "WHERE t.typname = :n ORDER BY e.enumsortorder"
        ),
        {"n": "userrole"},
    )
    vals = [row[0] for row in result]
    print("Updated userrole enum values:", vals)
    print("'agent' present:", "agent" in vals)
