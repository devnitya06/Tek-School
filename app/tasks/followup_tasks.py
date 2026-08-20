"""
Monthly auto follow-up task.

Hardcoded send dates: 7, 14, 22, 28 of every month.
Runs daily; only fires on those four dates.
"""

from datetime import datetime, timezone
from celery import shared_task
from sqlalchemy.orm import joinedload
from app.db.session import SessionLocal
from app.models.school import School
from app.utils.email_utility import send_dynamic_email, generate_password
from app.core.security import get_password_hash
from app.core.logger import logger

# Fixed monthly send dates
FOLLOWUP_DATES = {7, 14, 22, 28}


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,   # 5-minute base delay; doubles each retry with retry_backoff
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=3600,    # Cap at 1-hour wait between retries
)
def send_monthly_followup_emails(self):
    """
    Runs on the 7th, 14th, 22nd, and 28th of each month (via crontab in celery_app.py).
    Sends a follow-up credential email to all schools where:
      - followup_enabled is True
      - followup_status is 'pending' (not stopped / not completed)
    """
    today = datetime.now(timezone.utc)
    if today.day not in FOLLOWUP_DATES:
        logger.info(f"[followup_emails] Today is {today.day}th — not a send date. Skipping.")
        return

    logger.info(f"[followup_emails] Today is {today.day}th — starting monthly followup emails...")

    db = SessionLocal()
    try:
        # joinedload(School.user) prevents N+1: loads all users in one JOIN
        # instead of firing a separate SELECT for each school in the loop below.
        schools = (
            db.query(School)
            .options(joinedload(School.user))
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
                logger.info(f"[followup_emails] ✅ Sent to: {school.school_name} ({school.school_email})")

            except Exception as e:
                # Don't rollback inside loop; log and continue to other schools
                logger.error(
                    f"[followup_emails] ❌ Failed for {school.school_email} "
                    f"— {type(e).__name__}: {e}",
                    exc_info=True
                )

        # ✅ Single commit after all schools processed (not inside loop)
        db.commit()
        logger.info(f"[followup_emails] ✅ Done — {sent_count} email(s) sent.")

    except Exception as e:
        db.rollback()
        logger.error(f"[followup_emails] ❌ CRASH — {type(e).__name__}: {e}", exc_info=True)

    finally:
        db.close()
