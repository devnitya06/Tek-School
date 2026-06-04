from datetime import timezone, datetime, timedelta
from app.db.session import SessionLocal
from app.models import Student, SelfSignedStudent, CreditMaster, StudentStatus
# pyrefly: ignore [missing-import]
from celery import shared_task
from sqlalchemy.orm import joinedload

CREDIT_COST_PER_STUDENT = 30
@shared_task
def check_student_renewals():
    db = SessionLocal()
    try:
        # 1️⃣ Get all students whose renewal date has expired
        expired_students = (
            db.query(Student)
            .filter(Student.status_expiry_date != None)
            .filter(Student.status_expiry_date < datetime.utcnow())
            .filter(Student.status != StudentStatus.INACTIVE.value)
            .all()
        )

        for student in expired_students:
            student.status = StudentStatus.INACTIVE.value
            print(f"🚫 Student {student.id} trial/subscription expired. Marked inactive.")

        # Check SelfSignedStudent renewals
        expired_self_signed = (
            db.query(SelfSignedStudent)
            .filter(SelfSignedStudent.status_expiry_date != None)
            .filter(SelfSignedStudent.status_expiry_date < datetime.utcnow())
            .filter(SelfSignedStudent.status != StudentStatus.INACTIVE.value)
            .all()
        )

        for student in expired_self_signed:
            student.status = StudentStatus.INACTIVE.value
            print(f"🚫 Self-signed student {student.id} trial/subscription expired. Marked inactive.")

        db.commit()
        print("🎉 Renewal check completed successfully!")

    except Exception as e:
        db.rollback()
        print(f"❌ Error in renewal check: {str(e)}")

    finally:
        db.close()
