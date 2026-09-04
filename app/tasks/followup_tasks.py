"""
Monthly auto follow-up task.

Hardcoded send dates: 1 and 15 of every month.
Runs daily at 5:00 AM IST; only fires on those two dates.

CPU optimisations applied:
  - autoretry_for removed       — prevents retry storms when email fails
  - time_limit=3600             — hard kill after 1 hour (zombie prevention)
  - soft_time_limit=3300        — graceful shutdown warning at 55 min
  - 0.3 s sleep between emails  — smooths bcrypt CPU spikes + avoids SMTP rate-limit
  - Early-skip missing users    — no wasted bcrypt call
  - Per-school error isolation  — one bad email never retries ALL schools
"""

import time as _time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.orm import joinedload
from app.db.session import SessionLocal
from app.models.school import School
from app.utils.email_utility import send_dynamic_email, generate_password
from app.core.security import get_password_hash
from app.core.logger import logger

try:
    import psutil as _psutil
except Exception:
    _psutil = None  # CPU throttle disabled if psutil not available

# Fixed monthly send dates
FOLLOWUP_DATES = {1, 15}

# Seconds to sleep between each email send.
# Spreads bcrypt CPU load over time instead of hitting it in a tight loop.
_EMAIL_SEND_DELAY = 0.3
_FOLLOWUP_TIMEZONE = ZoneInfo("Asia/Kolkata")

# If CPU is still high after sending an email, pause before the next one.
# Lets FastAPI requests and Postgres queries breathe during the batch.
_TASK_CPU_THROTTLE_THRESHOLD = 85.0  # % — pause if CPU exceeds this
_TASK_CPU_THROTTLE_SLEEP = 10.0      # seconds to wait when CPU is high


@shared_task(
    bind=True,
    max_retries=2,              # Reduced from 3 — limits retry pile-up
    default_retry_delay=600,   # Flat 10-min delay — no exponential, predictable
    # autoretry_for REMOVED — email failures used to trigger full-task retries
    # with bcrypt hashing for every school each time → CPU storm.
    # Errors are now caught per-school; the whole task only retries on infra crash.
    time_limit=3600,           # Hard kill after 1 hour (zombie prevention)
    soft_time_limit=3300,      # Graceful warning at 55 min
    rate_limit="2/h",         # Max 2 accidental concurrent runs per hour
)
def send_monthly_followup_emails(self):
    """
    Runs on the 1st and 15th of each month (via crontab in celery_app.py).
    Sends a follow-up credential email to all schools where:
      - followup_enabled is True
      - followup_status is 'pending' (not stopped / not completed)
    """
    now_utc = datetime.now(timezone.utc)
    local_today = now_utc.astimezone(_FOLLOWUP_TIMEZONE)
    if local_today.day not in FOLLOWUP_DATES:
        logger.info(
            f"[followup_emails] Today is {local_today.day}th IST — not a send date. Skipping."
        )
        return

    logger.info(
        f"[followup_emails] Today is {local_today.day}th IST — starting monthly followup emails..."
    )

    db = SessionLocal()
    sent_count = 0
    skip_count = 0
    fail_count = 0
    task_start = _time.monotonic()

    try:
        schools = (
            db.query(School)
            .options(joinedload(School.user))
            .filter(School.followup_enabled.is_(True))
            .filter(School.followup_status == "pending")
            .all()
        )

        total = len(schools)
        logger.info(f"[followup_emails] {total} school(s) eligible for followup.")

        for school in schools:
            # Skip early if no user — avoids a wasted bcrypt call
            if not school.user:
                skip_count += 1
                logger.warning(
                    f"[followup_emails] ⚠️ Skipping {school.school_email} — no linked user."
                )
                continue

            try:
                # bcrypt is CPU-heavy (~100 ms each). Only called after all
                # guards pass, then spread out by _EMAIL_SEND_DELAY below.
                password = generate_password(prefix=school.school_name)

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

                with db.begin_nested():
                    school.user.hashed_password = get_password_hash(password)
                    school.user.is_verified = True
                    school.followup_last_sent_at = now_utc
                sent_count += 1
                logger.info(
                    f"[followup_emails] ✅ Sent to: {school.school_name} ({school.school_email})"
                )

                # Micro-sleep: spreads bcrypt CPU burst + avoids SMTP rate-limit
                _time.sleep(_EMAIL_SEND_DELAY)

                # CPU throttle: if system is still overloaded after sending,
                # pause before the next school so FastAPI/Postgres can breathe.
                if _psutil is not None:
                    try:
                        current_cpu = _psutil.cpu_percent(interval=None)
                        if current_cpu >= _TASK_CPU_THROTTLE_THRESHOLD:
                            logger.warning(
                                "[followup_emails] CPU=%.1f%% — pausing %.0fs to reduce load.",
                                current_cpu, _TASK_CPU_THROTTLE_SLEEP,
                            )
                            _time.sleep(_TASK_CPU_THROTTLE_SLEEP)
                    except Exception:
                        pass  # never block the task due to a CPU check failure

            except SoftTimeLimitExceeded:
                # Commit whatever progress we have, then let the signal propagate
                logger.warning(
                    "[followup_emails] ⏰ Soft time limit — committing partial results."
                )
                db.commit()
                raise

            except Exception as e:
                # Per-school failure: log and continue.
                # Previously one bad address triggered a full-task retry that
                # re-ran bcrypt for every school all over again.
                fail_count += 1
                logger.error(
                    f"[followup_emails] ❌ Failed for {school.school_email} "
                    f"— {type(e).__name__}: {e}",
                    exc_info=False,  # Keep logs concise inside loops
                )

        # Single commit after all schools processed (not inside loop)
        db.commit()

        elapsed = _time.monotonic() - task_start
        logger.info(
            f"[followup_emails] ✅ Done in {elapsed:.1f}s — "
            f"sent={sent_count}, skipped={skip_count}, failed={fail_count}"
        )

    except SoftTimeLimitExceeded:
        raise  # already handled per-iteration

    except Exception as e:
        db.rollback()
        logger.error(
            f"[followup_emails] ❌ CRASH — {type(e).__name__}: {e}", exc_info=True
        )
        # Only retry on unexpected infra crashes, NOT per-school email failures
        raise self.retry(exc=e)

    finally:
        db.close()
