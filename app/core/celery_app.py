from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "tek_school",
    broker=settings.REDIS_URL,     # e.g. redis://redis:6379/0
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.student_tasks",
        "app.tasks.followup_tasks",
    ],
)

celery_app.conf.timezone = "Asia/Kolkata"

# ─── Safety defaults ──────────────────────────────────────────────────────────
# Acknowledge tasks only AFTER they succeed, so a worker crash re-queues them.
celery_app.conf.task_acks_late = True
# Reject (not silently drop) a task if the worker process is killed mid-run.
celery_app.conf.task_reject_on_worker_lost = True
# Prevent a single worker from pre-fetching many tasks and blocking others.
celery_app.conf.worker_prefetch_multiplier = 1
# ─────────────────────────────────────────────────────────────────────────────

celery_app.conf.beat_schedule = {
    # 2:00 AM IST — mark expired student subscriptions inactive (bulk UPDATE, cheap)
    "check-student-renewal-everyday": {
        "task": "app.tasks.student_tasks.check_student_renewals",
        "schedule": crontab(hour=2, minute=0),
    },
    # 3:30 AM IST — staggered so both tasks never hit the DB simultaneously.
    # Internally skips non-send dates (7th, 14th, 22nd, 28th only).
    "send-monthly-followup-emails": {
        "task": "app.tasks.followup_tasks.send_monthly_followup_emails",
        "schedule": crontab(hour=3, minute=30),
    },
}
