from celery import shared_task
from app.core.logger import logger
from app.db.session import SessionLocal
from app.demo.models import DemoRequest
from app.demo.services import DemoEmailService


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_demo_booking_confirmation_email(self, request_id: int):
    db = SessionLocal()
    try:
        demo_request = db.query(DemoRequest).filter(DemoRequest.id == request_id).first()
        if not demo_request:
            logger.warning("[DEMO_EMAIL_TASK] Booking confirmation skipped: request_id=%s not found", request_id)
            return
        DemoEmailService.send_booking_confirmation(demo_request)
        db.close()
    except Exception as exc:
        logger.exception("[DEMO_EMAIL_TASK] Booking confirmation failed for request_id=%s: %s", request_id, exc)
        raise self.retry(exc=exc)
    finally:
        if db:
            db.close()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_demo_reschedule_notification_email(self, request_id: int):
    db = SessionLocal()
    try:
        demo_request = db.query(DemoRequest).filter(DemoRequest.id == request_id).first()
        if not demo_request:
            logger.warning("[DEMO_EMAIL_TASK] Reschedule notification skipped: request_id=%s not found", request_id)
            return
        DemoEmailService.send_reschedule_notification(demo_request)
        db.close()
    except Exception as exc:
        logger.exception("[DEMO_EMAIL_TASK] Reschedule notification failed for request_id=%s: %s", request_id, exc)
        raise self.retry(exc=exc)
    finally:
        if db:
            db.close()
