import os
import psycopg2
from urllib.parse import urlparse

import sys
sys.path.insert(0, os.getcwd())
try:
    import app.core.config as config
except ImportError:
    config = None

url = os.environ.get('DATABASE_URL')
if not url:
    if config is None:
        raise SystemExit('DATABASE_URL not found and app.core.config import failed')
    url = config.settings.DATABASE_URL
print('using', url)
parsed = urlparse(url)
conn = psycopg2.connect(
    dbname=parsed.path.lstrip('/'),
    user=parsed.username,
    password=parsed.password,
    host=parsed.hostname,
    port=parsed.port,
)
cur = conn.cursor()
cur.execute("ALTER TABLE tuition_lesson_topics DROP CONSTRAINT IF EXISTS tuition_lesson_topics_lesson_plan_id_fkey")
cur.execute(
    "ALTER TABLE tuition_lesson_topics ADD CONSTRAINT tuition_lesson_topics_lesson_id_fkey FOREIGN KEY (lesson_id) REFERENCES tuition_lessons(id)"
)
conn.commit()
cur.execute("SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = %s::regclass AND contype = 'f'", ('tuition_lesson_topics',))
for row in cur.fetchall():
    print(row[0], row[1])
cur.close()
conn.close()
