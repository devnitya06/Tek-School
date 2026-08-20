from datetime import timezone, datetime, timedelta
from app.db.session import SessionLocal
from app.models import Student, SelfSignedStudent, CreditMaster, StudentStatus
# pyrefly: ignore [missing-import]
from celery import shared_task
from sqlalchemy.orm import joinedload
from app.core.logger import logger

CREDIT_COST_PER_STUDENT = 30
@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,   # 5-minute base delay; doubles each retry with retry_backoff
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=3600,    # Cap at 1-hour wait between retries
)
def check_student_renewals(self):
    """Check and mark expired student subscriptions as inactive.

    Uses bulk UPDATE instead of looping to prevent:
    - N+1 queries (1000s of UPDATE statements)
    - Connection pool exhaustion
    - PostgreSQL CPU spikes
    """
    db = SessionLocal()
    try:
        logger.info("[check_student_renewals] Task started")
        # ✅ Use bulk update for School students (efficient)
        expired_count = db.query(Student).filter(
            Student.status_expiry_date != None,
            Student.status_expiry_date < datetime.utcnow(),
            Student.status != StudentStatus.INACTIVE.value
        ).update(
            {Student.status: StudentStatus.INACTIVE.value},
            synchronize_session=False
        )
        logger.info(f"[check_student_renewals] Marked {expired_count} school students inactive")

        # ✅ Use bulk update for Self-Signed students (efficient)
        expired_self_signed_count = db.query(SelfSignedStudent).filter(
            SelfSignedStudent.status_expiry_date != None,
            SelfSignedStudent.status_expiry_date < datetime.utcnow(),
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

    except Exception as e:
        db.rollback()
        logger.error(f"[check_student_renewals] ❌ CRASH — {type(e).__name__}: {e}", exc_info=True)

    finally:
        db.close()
