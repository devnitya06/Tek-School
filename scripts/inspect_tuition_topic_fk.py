import os
import psycopg2
from urllib.parse import urlparse
import app.core.config as config

url = os.environ.get('DATABASE_URL') or config.settings.DATABASE_URL
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
cur.execute("SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='tuition_lesson_topics'::regclass AND contype='f';")
for row in cur.fetchall():
    print(row[0], row[1])
cur.close()
conn.close()
