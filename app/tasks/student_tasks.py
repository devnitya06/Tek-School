from datetime import timezone, datetime, timedelta
import time
from app.db.session import SessionLocal
from app.models.students import Student, SelfSignedStudent, StudentStatus
from app.models.admin import CreditMaster
# pyrefly: ignore [missing-import]
from celery import shared_task
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import OperationalError
from app.core.logger import logger

CREDIT_COST_PER_STUDENT = 30
@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,   # 5-minute base delay; doubles each retry with retry_backoff
    autoretry_for=(OperationalError,),  # Retry on connection errors
    retry_backoff=True,
    retry_backoff_max=3600,    # Cap at 1-hour wait between retries
)
def check_student_renewals(self):
    """Check and mark expired student subscriptions as inactive.

    Uses bulk UPDATE instead of looping to prevent:
    - N+1 queries (1000s of UPDATE statements)
    - Connection pool exhaustion
    - PostgreSQL CPU spikes
    
    Retries automatically on connection errors (e.g., database restart).
    """
    db = SessionLocal()
    try:
        logger.info("[check_student_renewals] Task started")
        now = datetime.utcnow()
        
        # ✅ Use bulk update for School students (efficient)
        # Indexed query: status_expiry_date < now AND status != INACTIVE
        expired_count = db.query(Student).filter(
            Student.status_expiry_date.isnot(None),
            Student.status_expiry_date < now,
            Student.status != StudentStatus.INACTIVE.value
        ).update(
            {Student.status: StudentStatus.INACTIVE.value},
            synchronize_session=False
        )
        logger.info(f"[check_student_renewals] Marked {expired_count} school students inactive")

        # ✅ Use bulk update for Self-Signed students (efficient)
        expired_self_signed_count = db.query(SelfSignedStudent).filter(
            SelfSignedStudent.status_expiry_date.isnot(None),
            SelfSignedStudent.status_expiry_date < now,
            SelfSignedStudent.status != StudentStatus.INACTIVE.value
        ).update(
            {SelfSignedStudent.status: StudentStatus.INACTIVE.value},
            synchronize_session=False
        )
        logger.info(f"[check_student_renewals] Marked {expired_self_signed_count} self-signed students inactive")

        # Single commit for all updates (not in loop)
        db.commit()
        total = expired_count + expired_self_signed_count
        logger.info(f"[check_student_renewals] ✅ Done — total marked inactive: {total}")

    except OperationalError as e:
        db.rollback()
        logger.error(
            f"[check_student_renewals] ❌ Database connection error (will retry): {e}",
            exc_info=True
        )
        # Re-raise to trigger Celery retry mechanism
        raise self.retry(exc=e)
    except Exception as e:
        db.rollback()
        logger.error(
            f"[check_student_renewals] ❌ Unexpected error: {type(e).__name__}: {e}",
            exc_info=True
        )
        raise
    finally:
        db.close()
