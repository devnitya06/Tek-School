from app.db.session import engine, ensure_school_followup_columns
from sqlalchemy import text

try:
    ensure_school_followup_columns()
    print('ensure_school_followup_columns: OK')
except Exception as e:
    print('ensure_school_followup_columns: ERROR', repr(e))

with engine.begin() as conn:
    rows = conn.execute(
        text(
            "select column_name from information_schema.columns "
            "where table_schema=current_schema() and table_name='schools' "
            "order by ordinal_position"
        )
    ).fetchall()
    cols = [row[0] for row in rows]
    print('created_by_admin' in cols)
    print('followup_enabled' in cols)
    print('followup_days' in cols)
    print('followup_status' in cols)
    print('followup_note' in cols)
    print('followup_last_sent_at' in cols)
    print('followup_completed_at' in cols)
    print(cols)
