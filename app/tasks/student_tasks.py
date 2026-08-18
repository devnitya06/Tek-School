from datetime import timezone, datetime, timedelta
from app.db.session import SessionLocal
from app.models import Student, SelfSignedStudent, CreditMaster, StudentStatus
# pyrefly: ignore [missing-import]
from celery import shared_task
from sqlalchemy.orm import joinedload

CREDIT_COST_PER_STUDENT = 30
@shared_task
def check_student_renewals():
    """Check and mark expired student subscriptions as inactive.
    
    Uses bulk update instead of looping to prevent:
    - N+1 queries (1000s of UPDATE statements)
    - Connection pool exhaustion
    - PostgreSQL CPU spikes
    """
    db = SessionLocal()
    try:
        # ✅ Use bulk update for School students (efficient)
        expired_count = db.query(Student).filter(
            Student.status_expiry_date != None,
            Student.status_expiry_date < datetime.utcnow(),
            Student.status != StudentStatus.INACTIVE.value
        ).update(
            {Student.status: StudentStatus.INACTIVE.value},
            synchronize_session=False
        )
        print(f"🚫 Marked {expired_count} school-created students as inactive.")

        # ✅ Use bulk update for Self-Signed students (efficient)
        expired_self_signed_count = db.query(SelfSignedStudent).filter(
            SelfSignedStudent.status_expiry_date != None,
            SelfSignedStudent.status_expiry_date < datetime.utcnow(),
            SelfSignedStudent.status != StudentStatus.INACTIVE.value
        ).update(
            {SelfSignedStudent.status: StudentStatus.INACTIVE.value},
            synchronize_session=False
        )
        print(f"🚫 Marked {expired_self_signed_count} self-signed students as inactive.")

        # Single commit for all updates (not in loop)
        db.commit()
        total = expired_count + expired_self_signed_count
        print(f"🎉 Renewal check completed! Total marked inactive: {total}")

    except Exception as e:
        db.rollback()
        print(f"❌ Error in renewal check: {str(e)}")

    finally:
        db.close()
