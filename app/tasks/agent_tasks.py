from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from celery import shared_task
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.logger import logger
from app.db.session import SessionLocal
from app.models.agent import AgentProfile, StipendType
from app.models.agent_config import AgentEarning, AgentStipendRate
from app.models.users import User


_IST = ZoneInfo("Asia/Kolkata")


def _previous_month(today: date) -> tuple[date, date]:
    month_start = today.replace(day=1)
    if month_start.month == 1:
        previous_start = date(month_start.year - 1, 12, 1)
    else:
        previous_start = date(month_start.year, month_start.month - 1, 1)
    return previous_start, month_start


def generate_monthly_agent_stipends_for_period(
    db,
    period_start: date,
    period_end: date,
) -> int:
    """Create one full-month stipend per eligible Agent, using effective snapshots."""
    period_key = period_start.strftime("%Y-%m")
    created_count = 0
    agents = (
        db.query(AgentProfile)
        .join(User, User.id == AgentProfile.user_id)
        .filter(AgentProfile.stipend_type == StipendType.WITH_STIPEND)
        .all()
    )

    now = datetime.now(timezone.utc)
    for profile in agents:
        rate = (
            db.query(AgentStipendRate)
            .filter(
                AgentStipendRate.agent_profile_id == profile.id,
                AgentStipendRate.effective_from <= period_start,
            )
            .order_by(AgentStipendRate.effective_from.desc())
            .first()
        )
        if not rate or not rate.is_enabled or rate.monthly_rate <= 0:
            continue

        earning = AgentEarning(
            agent_profile_id=profile.id,
            earning_type="MONTHLY_STIPEND",
            status="APPROVED",
            reference_type="calendar_month",
            reference_id=period_key,
            applied_rate=rate.monthly_rate,
            amount=rate.monthly_rate,
            earning_date=period_end - timedelta(days=1),
            description=f"Monthly stipend for {period_key}.",
            approved_at=now,
        )
        try:
            with db.begin_nested():
                db.add(earning)
                db.flush()
            created_count += 1
        except IntegrityError:
            logger.info(
                "[agent_stipends] Duplicate monthly stipend ignored: profile=%s month=%s",
                profile.id,
                period_key,
            )

    db.commit()
    return created_count


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_backoff_max=3600,
)
def generate_monthly_agent_stipends(self):
    """Process the previous calendar month on the first day of each month."""
    db = SessionLocal()
    try:
        today_ist = datetime.now(_IST).date()
        period_start, period_end = _previous_month(today_ist)
        count = generate_monthly_agent_stipends_for_period(db, period_start, period_end)
        logger.info(
            "[agent_stipends] Created %s stipend earnings for %s",
            count,
            period_start.strftime("%Y-%m"),
        )
        return {"period": period_start.strftime("%Y-%m"), "created": count}
    except Exception:
        db.rollback()
        logger.exception("[agent_stipends] Monthly stipend processing failed")
        raise
    finally:
        db.close()
