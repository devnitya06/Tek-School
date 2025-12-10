from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "tek_school",
    broker=settings.REDIS_URL,     # e.g. redis://redis:6379/0
    backend=settings.REDIS_URL,
)

celery_app.conf.timezone = "Asia/Kolkata"
celery_app.conf.beat_schedule = {
    "check-student-renewal-everyday": {
        "task": "app.tasks.student_tasks.check_student_renewals",
        "schedule": 86400,  # every 24 hours
    },
}
