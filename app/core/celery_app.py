from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "tek_school",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.student_tasks",
        "app.tasks.followup_tasks",
    ],
)

celery_app.conf.timezone = "Asia/Kolkata"

# ─── CPU / Memory safeguards ──────────────────────────────────────────────────
# Acknowledge tasks only AFTER they succeed — worker crash re-queues them.
celery_app.conf.task_acks_late = True
# Reject (don't silently drop) a task if the worker is killed mid-run.
celery_app.conf.task_reject_on_worker_lost = True
# Prevent one worker from pre-fetching many tasks and blocking others.
celery_app.conf.worker_prefetch_multiplier = 1
# ✅ Recycle each worker process after 50 tasks — prevents slow memory leaks
#    from accumulating and pushing the OS to swap (which spikes CPU).
celery_app.conf.worker_max_tasks_per_child = 50
# ✅ Global hard time limit: kill any task that runs longer than 2 hours.
#    Prevents zombie tasks from consuming CPU indefinitely.
celery_app.conf.task_time_limit = 7200          # 2 hours hard kill
celery_app.conf.task_soft_time_limit = 6900     # 115 min graceful warning
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
