"""
Demo Management System — Business Logic Services

Services:
  DemoSlotService       — generate hourly slots, validate a start_time
  DemoCapacityService   — count bookings, check/reserve with locking
  DemoOtpService        — create/verify OTP for anonymous demo users
  DemoAccessService     — validate access code + IST expiry + brute force
  DemoEmailService      — send OTP / booking / reschedule emails
  generate_request_code — unique 8-char alphanumeric request code
  generate_access_code  — secure 6-digit numeric code
"""
import secrets
import string
import re
import threading
from datetime import datetime, date, time, timedelta, timezone
from typing import List, Optional, Tuple

import pytz
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.core.logger import logger
from app.demo.exceptions import DemoAPIException, DemoErrorCode
from app.demo.models import (
    DemoConfiguration,
    DemoRequest,
    DemoOtp,
    DemoAccessAttempt,
)
from app.demo.enums import (
    DemoStatus,
    ACTIVE_DEMO_STATUSES,
)

# ─── Constants ────────────────────────────────────────────────────────────────

IST = pytz.timezone("Asia/Kolkata")

OTP_EXPIRY_MINUTES = 10
OTP_MAX_RESEND_PER_HOUR = 5        # DEMO_OTP_RATE_LIMITED
OTP_MAX_VERIFY_ATTEMPTS = 5        # DEMO_OTP_ATTEMPTS_EXCEEDED

ACCESS_MAX_ATTEMPTS = 10           # DEMO_ACCESS_RATE_LIMITED
ACCESS_RATE_WINDOW_MINUTES = 30    # rolling window

IMAGE_MAX_COUNT = 10
IMAGE_MAX_TOTAL_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}

FEEDBACK_MAX_LENGTH = 2000


# ─── Helper generators ────────────────────────────────────────────────────────

def generate_request_code() -> str:
    """Generate a unique, human-readable 8-character alphanumeric code, e.g. 'DMRQ3X7A'."""
    chars = string.ascii_uppercase + string.digits
    return "DM" + "".join(secrets.choice(chars) for _ in range(6))


def generate_access_code() -> str:
    """Generate a cryptographically secure 6-digit numeric access code."""
    return "".join(str(secrets.randbelow(10)) for _ in range(6))


def _parse_hhmm(value: str) -> time:
    """Parse 'HH:MM' into a time object. Raises ValueError on bad format."""
    try:
        parts = value.strip().split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError, AttributeError):
        raise ValueError(f"Invalid time format: {value!r}")


# ─── Slot Service ─────────────────────────────────────────────────────────────

class DemoSlotService:
    """
    Generates hourly slots from a DemoConfiguration start_time → end_time.

    Example: start=10:00, end=17:00 → [10:00-11:00, 11:00-12:00, …, 16:00-17:00]
    """

    @staticmethod
    def generate_slots(config: DemoConfiguration) -> List[Tuple[time, time]]:
        """Return list of (slot_start, slot_end) tuples."""
        slots = []
        current = config.start_time
        end = config.end_time
        while True:
            next_hour = (
                datetime.combine(date.today(), current) + timedelta(hours=1)
            ).time()
            if next_hour > end:
                break
            slots.append((current, next_hour))
            current = next_hour
        return slots

    @staticmethod
    def validate_configuration_slots(config: DemoConfiguration) -> None:
        """Raise DemoAPIException if the config cannot generate any valid slots."""
        slots = DemoSlotService.generate_slots(config)
        if not slots:
            raise DemoAPIException(
                422,
                DemoErrorCode.INVALID_SLOT_CONFIGURATION,
                "The configured time range cannot generate valid demo slots.",
            )

    @staticmethod
    def find_slot(config: DemoConfiguration, start_time_str: str) -> Tuple[time, time]:
        """
        Find a specific slot matching start_time_str in the config.
        Returns (start, end) or raises DEMO_INVALID_SLOT.
        """
        try:
            requested_start = _parse_hhmm(start_time_str)
        except ValueError:
            raise DemoAPIException(
                422,
                DemoErrorCode.INVALID_SLOT,
                "The selected demo time slot is invalid.",
            )

        slots = DemoSlotService.generate_slots(config)
        for slot_start, slot_end in slots:
            if slot_start == requested_start:
                return slot_start, slot_end

        raise DemoAPIException(
            422,
            DemoErrorCode.INVALID_SLOT,
            "The selected demo time slot is invalid.",
        )

    @staticmethod
    def validate_weekday(config: DemoConfiguration, demo_date: date) -> None:
        """Raise DEMO_DATE_NOT_AVAILABLE if the weekday is not in config.demo_days."""
        weekday_name = demo_date.strftime("%A").upper()  # "MONDAY" etc.
        if weekday_name not in config.demo_days:
            raise DemoAPIException(
                409,
                DemoErrorCode.DATE_NOT_AVAILABLE,
                "Demo slots are not available on the selected date.",
            )


# ─── Capacity Service ─────────────────────────────────────────────────────────

class DemoCapacityService:
    """
    Provides concurrency-safe capacity checks using SELECT FOR UPDATE.
    Must be called inside an active SQLAlchemy transaction.
    """

    @staticmethod
    def count_bookings(
        db: Session,
        config_id: int,
        demo_date: date,
        slot_start: time,
        exclude_request_id: Optional[int] = None,
    ) -> int:
        """Count active bookings for a slot (optionally excluding a request being rescheduled)."""
        active_statuses = [s.value for s in ACTIVE_DEMO_STATUSES]
        q = db.query(func.count(DemoRequest.id)).filter(
            DemoRequest.config_id == config_id,
            DemoRequest.demo_date == demo_date,
            DemoRequest.start_time == slot_start,
            DemoRequest.status.in_(active_statuses),
        )
        if exclude_request_id is not None:
            q = q.filter(DemoRequest.id != exclude_request_id)
        return q.scalar() or 0

    @staticmethod
    def check_and_lock_slot(
        db: Session,
        config: DemoConfiguration,
        demo_date: date,
        slot_start: time,
        exclude_request_id: Optional[int] = None,
    ) -> None:
        """
        Use SELECT FOR UPDATE to lock the slot rows during a transaction,
        then check capacity. Raises DEMO_CAPACITY_CONFLICT if full.

        This prevents two concurrent bookings from both reading 'available'
        and then both inserting — the second transaction blocks until the
        first commits, then rechecks.
        """
        active_statuses = [s.value for s in ACTIVE_DEMO_STATUSES]

        # Lock all rows for this slot — blocks concurrent transactions
        stmt = (
            select(DemoRequest)
            .where(
                DemoRequest.config_id == config.id,
                DemoRequest.demo_date == demo_date,
                DemoRequest.start_time == slot_start,
                DemoRequest.status.in_(active_statuses),
            )
            .with_for_update()
        )
        locked_rows = db.execute(stmt).scalars().all()
        count = len(locked_rows)
        if exclude_request_id is not None:
            count = sum(1 for r in locked_rows if r.id != exclude_request_id)

        if count >= config.user_limit:
            raise DemoAPIException(
                409,
                DemoErrorCode.CAPACITY_CONFLICT,
                "The selected demo slot became unavailable. Please choose another slot.",
            )


# ─── OTP Service ──────────────────────────────────────────────────────────────

class DemoOtpService:
    """
    Manages anonymous OTP lifecycle for demo bookings.
    Uses the DemoOtp table — no dependency on the users table.
    """

    @staticmethod
    def _now_utc() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def get_active_otp(db: Session, email: str) -> Optional[DemoOtp]:
        """Get the most recent non-expired OTP for an email."""
        return (
            db.query(DemoOtp)
            .filter(
                DemoOtp.email == email.lower(),
                DemoOtp.expires_at > DemoOtpService._now_utc(),
            )
            .order_by(DemoOtp.created_at.desc())
            .first()
        )

    @staticmethod
    @staticmethod
    def send_otp(db: Session, email: str, request_payload: Optional[dict] = None) -> DemoOtp:
        """
        Create and store a new OTP for the given email.
        Enforces resend rate limiting (OTP_MAX_RESEND_PER_HOUR).
        """
        email = email.lower()

        # Check resend rate — look for any OTP created in the last hour
        one_hour_ago = DemoOtpService._now_utc() - timedelta(hours=1)
        recent_count = (
            db.query(func.count(DemoOtp.id))
            .filter(
                DemoOtp.email == email,
                DemoOtp.created_at >= one_hour_ago,
            )
            .scalar()
            or 0
        )
        if recent_count >= OTP_MAX_RESEND_PER_HOUR:
            raise DemoAPIException(
                429,
                DemoErrorCode.OTP_RATE_LIMITED,
                "Too many OTP requests. Please try again later.",
            )

        from app.utils.email_utility import generate_otp

        otp_code = generate_otp(6)
        expires_at = DemoOtpService._now_utc() + timedelta(minutes=OTP_EXPIRY_MINUTES)

        otp_record = DemoOtp(
            email=email,
            otp_code=otp_code,
            is_verified=False,
            attempt_count=0,
            resend_count=recent_count,
            request_payload=request_payload,
            expires_at=expires_at,
        )
        db.add(otp_record)
        db.commit()
        db.refresh(otp_record)
        return otp_record

    @staticmethod
    def _create_demo_request_from_payload(db: Session, email: str, payload: dict) -> DemoRequest:
        from app.demo.schemas import DemoRequestCreate

        request_data = DemoRequestCreate.model_validate(payload)
        request_email = str(request_data.email).lower()
        if request_email != email:
            raise DemoAPIException(
                400,
                DemoErrorCode.INVALID_EMAIL,
                "The email in the OTP request does not match the verified email.",
            )

        active_statuses = [s.value for s in ACTIVE_DEMO_STATUSES]
        existing = (
            db.query(DemoRequest)
            .filter(
                DemoRequest.email == request_email,
                DemoRequest.status.in_(active_statuses),
            )
            .first()
        )
        if existing:
            raise DemoAPIException(
                409,
                DemoErrorCode.ACTIVE_REQUEST_EXISTS,
                "You already have an active demo request and cannot create another request at this time.",
            )

        config = get_configuration_or_404(db, request_data.config_id)
        require_active_configuration(config)
        DemoSlotService.validate_weekday(config, request_data.demo_date)
        slot_start, slot_end = DemoSlotService.find_slot(config, request_data.start_time)
        DemoCapacityService.check_and_lock_slot(
            db,
            config,
            request_data.demo_date,
            slot_start,
        )

        for _ in range(5):
            request_code = generate_request_code()
            if not db.query(DemoRequest).filter(DemoRequest.request_code == request_code).first():
                break

        access_code = generate_access_code()
        demo_request = DemoRequest(
            request_code=request_code,
            email=request_email,
            user_category=request_data.user_category.value,
            institution_name=request_data.institution_name,
            full_name=request_data.full_name,
            designation=request_data.designation,
            phone=request_data.phone,
            institution_address=request_data.institution_address,
            area_of_interest=request_data.area_of_interest,
            config_id=config.id,
            demo_date=request_data.demo_date,
            start_time=slot_start,
            end_time=slot_end,
            presented_by=config.presented_by,
            demonstration_link=config.demonstration_link,
            status=DemoStatus.PENDING.value,
            access_code=access_code,
        )
        db.add(demo_request)
        try:
            db.commit()
            db.refresh(demo_request)
        except IntegrityError:
            db.rollback()
            raise DemoAPIException(
                409,
                DemoErrorCode.CAPACITY_CONFLICT,
                "The selected demo slot became unavailable. Please choose another slot.",
            )

        DemoEmailService.queue_booking_confirmation(demo_request)
        return demo_request

    @staticmethod
    def verify_otp(db: Session, email: str, otp_code: str):
        """
        Verify OTP code for an email.
        On a request-bound OTP, finalize the pending demo request after successful verification.
        """
        email = email.lower()

        latest_otp = (
            db.query(DemoOtp)
            .filter(DemoOtp.email == email)
            .order_by(DemoOtp.created_at.desc())
            .first()
        )

        if latest_otp is None:
            raise DemoAPIException(
                400,
                DemoErrorCode.INVALID_OTP,
                "The OTP you entered is invalid.",
            )

        if latest_otp.is_expired:
            db.delete(latest_otp)
            db.commit()
            raise DemoAPIException(
                400,
                DemoErrorCode.OTP_EXPIRED,
                "The OTP has expired. Please request a new OTP.",
            )

        if latest_otp.is_verified:
            raise DemoAPIException(
                409,
                DemoErrorCode.OTP_ALREADY_VERIFIED,
                "The email address has already been verified.",
            )

        if latest_otp.attempt_count >= OTP_MAX_VERIFY_ATTEMPTS:
            raise DemoAPIException(
                429,
                DemoErrorCode.OTP_ATTEMPTS_EXCEEDED,
                "Too many incorrect OTP attempts. Please request a new OTP.",
            )

        latest_otp.attempt_count += 1
        db.commit()

        if latest_otp.otp_code != otp_code:
            remaining = OTP_MAX_VERIFY_ATTEMPTS - latest_otp.attempt_count
            if remaining <= 0:
                raise DemoAPIException(
                    429,
                    DemoErrorCode.OTP_ATTEMPTS_EXCEEDED,
                    "Too many incorrect OTP attempts. Please request a new OTP.",
                )
            raise DemoAPIException(
                400,
                DemoErrorCode.INVALID_OTP,
                "The OTP you entered is invalid.",
            )

        if latest_otp.request_payload is not None:
            demo_request = DemoOtpService._create_demo_request_from_payload(
                db,
                email,
                latest_otp.request_payload,
            )
            db.delete(latest_otp)
            db.commit()
            return demo_request

        latest_otp.is_verified = True
        db.commit()
        db.refresh(latest_otp)
        return latest_otp

    @staticmethod
    def check_email_verified(db: Session, email: str) -> None:
        """
        Raise DEMO_OTP_VERIFICATION_REQUIRED if the email has no verified OTP.
        Call this before creating a demo request.
        """
        email = email.lower()
        verified_otp = (
            db.query(DemoOtp)
            .filter(
                DemoOtp.email == email,
                DemoOtp.is_verified == True,
            )
            .order_by(DemoOtp.created_at.desc())
            .first()
        )
        if verified_otp is None:
            raise DemoAPIException(
                403,
                DemoErrorCode.OTP_VERIFICATION_REQUIRED,
                "Please verify your email address before submitting the demo request.",
            )


# ─── Access Service ───────────────────────────────────────────────────────────

class DemoAccessService:
    """
    Validates the 6-digit access code for a demo request.
    Checks expiration using IST timezone.
    Protects against brute force via DemoAccessAttempt table.
    """

    @staticmethod
    def _now_ist() -> datetime:
        return datetime.now(IST)

    @staticmethod
    def _is_access_code_expired(demo_request: DemoRequest) -> bool:
        """
        Access code is valid until 23:59:59 IST on the demo_date.
        """
        now_ist = DemoAccessService._now_ist()
        expiry_ist = IST.localize(
            datetime.combine(demo_request.demo_date, time(23, 59, 59))
        )
        return now_ist > expiry_ist

    @staticmethod
    def check_rate_limit(db: Session, email: str) -> None:
        """
        Raise DEMO_ACCESS_RATE_LIMITED if too many failed attempts in the window.
        """
        email = email.lower()
        window_start = datetime.now(timezone.utc) - timedelta(
            minutes=ACCESS_RATE_WINDOW_MINUTES
        )

        attempt = (
            db.query(DemoAccessAttempt)
            .filter(DemoAccessAttempt.email == email)
            .first()
        )

        if attempt:
            # Check if window has reset
            w_start = attempt.window_start
            if w_start.tzinfo is None:
                w_start = w_start.replace(tzinfo=timezone.utc)
            if w_start < window_start:
                # Reset the window
                attempt.attempt_count = 0
                attempt.window_start = datetime.now(timezone.utc)
                db.commit()
            elif attempt.attempt_count >= ACCESS_MAX_ATTEMPTS:
                raise DemoAPIException(
                    429,
                    DemoErrorCode.ACCESS_RATE_LIMITED,
                    "Too many access attempts. Please try again later.",
                )

    @staticmethod
    def record_failed_attempt(db: Session, email: str) -> None:
        email = email.lower()
        attempt = (
            db.query(DemoAccessAttempt)
            .filter(DemoAccessAttempt.email == email)
            .first()
        )
        if attempt:
            attempt.attempt_count += 1
        else:
            attempt = DemoAccessAttempt(email=email, attempt_count=1)
            db.add(attempt)
        db.commit()

    @staticmethod
    def reset_attempts(db: Session, email: str) -> None:
        email = email.lower()
        attempt = (
            db.query(DemoAccessAttempt)
            .filter(DemoAccessAttempt.email == email)
            .first()
        )
        if attempt:
            attempt.attempt_count = 0
            db.commit()

    @staticmethod
    def validate_access(
        db: Session, email: str, access_code: str
    ) -> DemoRequest:
        """
        Full access code validation flow:
        1. Rate limit check
        2. Find demo request by email
        3. Validate access code match
        4. Check expiration (IST)
        Returns the DemoRequest on success.
        """
        email_lower = email.lower()

        # 1. Rate limit
        DemoAccessService.check_rate_limit(db, email_lower)

        # 2. Find request — look for active statuses first
        active_statuses = [s.value for s in ACTIVE_DEMO_STATUSES]
        demo_request = (
            db.query(DemoRequest)
            .filter(
                DemoRequest.email == email_lower,
                DemoRequest.status.in_(active_statuses),
            )
            .order_by(DemoRequest.demo_date.desc())
            .first()
        )

        if demo_request is None:
            # Try any status (so expired access still gives correct message)
            demo_request = (
                db.query(DemoRequest)
                .filter(DemoRequest.email == email_lower)
                .order_by(DemoRequest.demo_date.desc())
                .first()
            )

        if demo_request is None or demo_request.access_code != access_code:
            DemoAccessService.record_failed_attempt(db, email_lower)
            raise DemoAPIException(
                401,
                DemoErrorCode.INVALID_ACCESS_CODE,
                "The email address or access code is incorrect.",
            )

        # 3. Check expiration
        if DemoAccessService._is_access_code_expired(demo_request):
            raise DemoAPIException(
                410,
                DemoErrorCode.ACCESS_CODE_EXPIRED,
                "The demo access code has expired because the demo date has ended.",
            )

        # Success — reset attempts
        DemoAccessService.reset_attempts(db, email_lower)
        return demo_request


# ─── Email Service ────────────────────────────────────────────────────────────

class DemoEmailService:
    """
    Wraps the existing email_utility for demo-specific emails.
    Email failures are logged but never block the main flow.
    """

    @staticmethod
    def send_otp_email(email: str, otp_code: str) -> None:
        try:
            from app.utils.email_utility import send_dynamic_email
            send_dynamic_email(
                context_key="demo_otp.html",
                subject="Your Demo Booking OTP — BeingIdeal",
                recipient_email=email,
                context_data={
                    "email": email,
                    "OTP": otp_code,
                    "current_year": datetime.now().year,
                },
                db=None,
            )
        except Exception as exc:
            logger.warning("[DEMO_EMAIL] Failed to send OTP email to %s: %s", email, exc)

    @staticmethod
    def send_booking_confirmation(demo_request: DemoRequest) -> None:
        try:
            from app.utils.email_utility import send_dynamic_email

            send_dynamic_email(
                context_key="demo_booking_confirmation.html",
                subject="Demo Booking Confirmed — BeingIdeal",
                recipient_email=demo_request.email,
                context_data={
                    "email": demo_request.email,
                    "full_name": demo_request.full_name,
                    "request_code": demo_request.request_code,
                    "access_code": demo_request.access_code,
                    "demo_date": demo_request.demo_date.strftime("%B %d, %Y"),
                    "start_time": demo_request.start_time.strftime("%I:%M %p"),
                    "end_time": demo_request.end_time.strftime("%I:%M %p"),
                    "presented_by": demo_request.presented_by,
                    "demonstration_link": demo_request.demonstration_link,
                    "current_year": datetime.now().year,
                },
                db=None,
            )
        except Exception as exc:
            logger.warning(
                "[DEMO_EMAIL] Failed to send booking confirmation to %s: %s",
                demo_request.email,
                exc,
            )

    @staticmethod
    def queue_booking_confirmation(demo_request: DemoRequest) -> None:
        """Fire-and-forget the email task without blocking the request thread."""

        def _deliver_in_background() -> None:
            try:
                from app.core.celery_app import celery_app
                celery_app.send_task(
                    "app.tasks.demo_email_tasks.send_demo_booking_confirmation_email",
                    args=[demo_request.id],
                )
            except Exception as exc:
                logger.warning(
                    "[DEMO_EMAIL] Celery queue unavailable for booking confirmation. Falling back to direct background send. Request_id=%s error=%s",
                    demo_request.id,
                    exc,
                )
                try:
                    DemoEmailService.send_booking_confirmation(demo_request)
                except Exception as fallback_exc:
                    logger.warning(
                        "[DEMO_EMAIL] Direct background fallback failed for booking confirmation. Request_id=%s error=%s",
                        demo_request.id,
                        fallback_exc,
                    )

        background_thread = threading.Thread(
            target=_deliver_in_background,
            daemon=True,
            name=f"demo-booking-email-{demo_request.id}",
        )
        background_thread.start()

    @staticmethod
    def send_reschedule_notification(demo_request: DemoRequest) -> None:
        try:
            from app.utils.email_utility import send_dynamic_email

            send_dynamic_email(
                context_key="demo_reschedule.html",
                subject="Demo Rescheduled — BeingIdeal",
                recipient_email=demo_request.email,
                context_data={
                    "email": demo_request.email,
                    "full_name": demo_request.full_name,
                    "request_code": demo_request.request_code,
                    "access_code": demo_request.access_code,
                    "demo_date": demo_request.demo_date.strftime("%B %d, %Y"),
                    "start_time": demo_request.start_time.strftime("%I:%M %p"),
                    "end_time": demo_request.end_time.strftime("%I:%M %p"),
                    "presented_by": demo_request.presented_by,
                    "demonstration_link": demo_request.demonstration_link,
                    "current_year": datetime.now().year,
                },
                db=None,
            )
        except Exception as exc:
            logger.warning(
                "[DEMO_EMAIL] Failed to send reschedule notification to %s: %s",
                demo_request.email,
                exc,
            )

    @staticmethod
    def queue_reschedule_notification(demo_request: DemoRequest) -> None:
        """Fire-and-forget the reschedule email task without blocking the request thread."""

        def _deliver_in_background() -> None:
            try:
                from app.core.celery_app import celery_app
                celery_app.send_task(
                    "app.tasks.demo_email_tasks.send_demo_reschedule_notification_email",
                    args=[demo_request.id],
                )
            except Exception as exc:
                logger.warning(
                    "[DEMO_EMAIL] Celery queue unavailable for reschedule notification. Falling back to direct background send. Request_id=%s error=%s",
                    demo_request.id,
                    exc,
                )
                try:
                    DemoEmailService.send_reschedule_notification(demo_request)
                except Exception as fallback_exc:
                    logger.warning(
                        "[DEMO_EMAIL] Direct background fallback failed for reschedule notification. Request_id=%s error=%s",
                        demo_request.id,
                        fallback_exc,
                    )

        background_thread = threading.Thread(
            target=_deliver_in_background,
            daemon=True,
            name=f"demo-reschedule-email-{demo_request.id}",
        )
        background_thread.start()


# ─── Configuration Helpers ────────────────────────────────────────────────────

def get_configuration_or_404(db: Session, config_id: int) -> DemoConfiguration:
    config = db.query(DemoConfiguration).filter(DemoConfiguration.id == config_id).first()
    if not config:
        raise DemoAPIException(
            404,
            DemoErrorCode.CONFIGURATION_NOT_FOUND,
            "Demo configuration was not found.",
        )
    return config


def require_active_configuration(config: DemoConfiguration) -> None:
    if not config.is_active:
        raise DemoAPIException(
            409,
            DemoErrorCode.CONFIGURATION_INACTIVE,
            "This demo configuration is currently inactive.",
        )


def validate_time_range(start_time_str: str, end_time_str: str) -> Tuple[time, time]:
    """Parse and validate start < end, return (start, end) time objects."""
    try:
        start = _parse_hhmm(start_time_str)
        end = _parse_hhmm(end_time_str)
    except ValueError:
        raise DemoAPIException(
            422,
            DemoErrorCode.INVALID_TIME,
            "Please provide a valid time.",
        )
    if end <= start:
        raise DemoAPIException(
            422,
            DemoErrorCode.INVALID_TIME_RANGE,
            "Demo end time must be later than the start time.",
        )
    return start, end
