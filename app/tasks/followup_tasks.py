"""
Monthly auto follow-up task.

Hardcoded send dates: 7, 14, 22, 28 of every month.
Runs daily; only fires on those four dates.
"""

from datetime import datetime, timezone
from celery import shared_task
from app.db.session import SessionLocal
from app.models.school import School
from app.utils.email_utility import send_dynamic_email, generate_password
from app.core.security import get_password_hash

# Fixed monthly send dates
FOLLOWUP_DATES = {7, 14, 22, 28}


@shared_task
def send_monthly_followup_emails():
    """
    Runs every day. On the 7th, 14th, 22nd, and 28th of the month it sends
    a follow-up credential email to all schools where:
      - followup_enabled is True
      - followup_status is 'pending' (not stopped / not completed)
    """
    today = datetime.now(timezone.utc)
    if today.day not in FOLLOWUP_DATES:
        print(f"ℹ️ Today is the {today.day}th — no scheduled followup date. Skipping.")
        return

    print(f"📅 Today is the {today.day}th — running monthly followup emails...")

    db = SessionLocal()
    try:
        schools = (
            db.query(School)
            .filter(School.followup_enabled.is_(True))
            .filter(School.followup_status == "pending")
            .all()
        )

        sent_count = 0
        for school in schools:
            try:
                # Generate a fresh password and update the user account
                if school.user:
                    password = generate_password(prefix=school.school_name)
                    school.user.hashed_password = get_password_hash(password)
                    school.user.is_verified = True

                    send_dynamic_email(
                        context_key="credential.html",
                        subject="Your BeingIdeal School Account Credentials",
                        recipient_email=school.school_email,
                        context_data={
                            "name": school.school_name,
                            "application_name": "beingideal",
                            "email": school.school_email,
                            "password": password,
                            "note": school.followup_note,
                        },
                        db=db,
                    )

                school.followup_last_sent_at = today
                sent_count += 1
                print(f"✅ Followup sent to school: {school.school_name} ({school.school_email})")

            except Exception as e:
                # Don't rollback inside loop; log and continue to other schools
                print(f"❌ Failed to send followup to {school.school_email}: {e}")
                # Skip this school's commit, continue with others

        # ✅ Single commit after all schools processed (not inside loop)
        db.commit()
        print(f"🎉 Monthly followup complete — {sent_count} email(s) sent.")

    except Exception as e:
        db.rollback()
        print(f"❌ Error in monthly followup task: {e}")

    finally:
        db.close()
