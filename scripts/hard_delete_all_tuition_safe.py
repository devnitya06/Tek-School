from app.db.session import engine
from sqlalchemy import text

print('Connecting to DB and listing tuition_ tables...')
with engine.connect() as conn:
    found = [r[0] for r in conn.execute(text("select table_name from information_schema.tables where table_schema=current_schema() and table_name like 'tuition_%' order by table_name")).fetchall()]

print('Found tables:', found)
# Preferred deletion order (children first)
ordered = [
    'tuition_topic_files',
    'tuition_lesson_topics',
    'tuition_lesson_assignment_mappings',
    'tuition_lessons',
    'tuition_lesson_plan_batches',
    'tuition_lesson_plans',
    'tuition_batches',
    'tuition_batch_student_mappings',
    'tuition_batch_schedules',
    'tuition_batch_approvals',
    'tuition_class_done_records',
    'tuition_teacher_earnings',
]
# Append any found tables not in ordered list
for t in found:
    if t not in ordered:
        ordered.append(t)

print('\nDeletion sequence:')
for t in ordered:
    print('  ', t)

results = []
for t in ordered:
    try:
        with engine.begin() as conn:
            pre = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            conn.execute(text(f"DELETE FROM {t}"))
            post = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
        results.append((t, pre, post, None))
        print(f"Deleted {pre} rows from {t} -> now {post}")
    except Exception as e:
        results.append((t, None, None, str(e)))
        print(f"Failed to delete {t}: {e}")

print('\nSummary:')
for t, pre, post, err in results:
    if err:
        print(f"  {t}: FAILED ({err})")
    else:
        print(f"  {t}: {pre} -> {post}")

print('\nDone.')
