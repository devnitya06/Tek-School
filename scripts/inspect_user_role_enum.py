from app.db.session import engine
from sqlalchemy import inspect
insp = inspect(engine)
cols = insp.get_columns('users')
for c in cols:
    if c['name'] == 'role':
        print('role column type:', type(c['type']).__name__, str(c['type']))
        print(c)

# Check if users.role is an enum type in PostgreSQL and list enum labels
conn = engine.raw_connection()
try:
    cur = conn.cursor()
    cur.execute("SELECT t.typname, e.enumlabel FROM pg_type t JOIN pg_enum e ON t.oid = e.enumtypid JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace WHERE t.typname = 'userrole';")
    rows = cur.fetchall()
    print('pg userrole enum rows:')
    for row in rows:
        print(row)
    cur.close()
finally:
    conn.close()
