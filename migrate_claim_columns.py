"""One-time migration: add claim_status and claim_completed_at to schools table."""
from app.db.session import engine
from sqlalchemy import text

with engine.begin() as conn:
    conn.execute(text(
        "ALTER TABLE schools ADD COLUMN IF NOT EXISTS claim_status VARCHAR(50) DEFAULT 'unclaimed'"
    ))
    conn.execute(text(
        "ALTER TABLE schools ADD COLUMN IF NOT EXISTS claim_completed_at TIMESTAMP NULL"
    ))

print("Migration complete: claim_status and claim_completed_at added to schools table.")
