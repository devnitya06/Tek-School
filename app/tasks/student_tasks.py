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
            .options(joinedload(Student.school))
            .filter(Student.status_expiry_date != None)
            .filter(Student.status_expiry_date < datetime.utcnow())
            .filter(Student.status != StudentStatus.INACTIVE.value)
            .all()
        )

        if not expired_students:
            print("✅ No students need renewal today.")
        else:
            # 2️⃣ Group students by school_id for credit checks
            schools = {}
            for student in expired_students:
                schools.setdefault(student.school_id, []).append(student)

            for school_id, students in schools.items():
                # Fetch credit for this school
                credit = (
                    db.query(CreditMaster)
                    .filter(CreditMaster.school_id == school_id)
                    .first()
                )

                if not credit:
                    print(f"⚠️ No credit account found for school {school_id}")
                    for s in students:
                        s.status = StudentStatus.INACTIVE.value
                    continue

                for student in students:
                    if credit.available_credit >= CREDIT_COST_PER_STUDENT:
                        # ✅ Renew student
                        credit.used_credit += CREDIT_COST_PER_STUDENT
                        credit.calculate_available_credit()

                        student.status = StudentStatus.ACTIVE.value
                        # Example: 30 days renewal (can make it dynamic)
                        student.status_expiry_date = datetime.now(timezone.utc) + timedelta(days=30)
                        print(f"✅ Renewed student {student.id} for 30 days.")
                    else:
                        # ❌ Not enough credit
                        student.status = StudentStatus.INACTIVE.value
                        print(f"🚫 Not enough credits for student {student.id}. Marked inactive.")

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
