from app.db.session import engine
from sqlalchemy import text

followup_columns = [
    ('created_by_admin', 'BOOLEAN NOT NULL DEFAULT FALSE'),
    ('followup_enabled', 'BOOLEAN NOT NULL DEFAULT FALSE'),
    ('followup_days', 'INTEGER NOT NULL DEFAULT 0'),
    ('followup_status', "VARCHAR(255) NOT NULL DEFAULT 'inactive'"),
    ('followup_note', 'VARCHAR NULL'),
    ('followup_last_sent_at', 'TIMESTAMP NULL'),
    ('followup_completed_at', 'TIMESTAMP NULL'),
]

with engine.begin() as conn:
    for col_name, ddl in followup_columns:
        print('adding', col_name)
        conn.execute(text(f'ALTER TABLE schools ADD COLUMN IF NOT EXISTS "{col_name}" {ddl}'))

with engine.begin() as conn:
    rows = conn.execute(
        text(
            "select column_name from information_schema.columns "
            "where table_schema=current_schema() and table_name='schools' "
            "order by ordinal_position"
        )
    ).fetchall()
    cols = [row[0] for row in rows]
    print('result', cols)
