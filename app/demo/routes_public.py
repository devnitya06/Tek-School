"""
Demo Management System — Public Routes

Public endpoints (no authentication required):
  GET  /demo/public/check
  GET  /demo/public/available-slots
  POST /demo/public/verify-otp
  POST /demo/public/request
  POST /demo/public/access
"""
from datetime import date, time, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.logger import logger
from app.db.session import get_db
from app.demo.exceptions import DemoAPIException, DemoErrorCode
from app.demo.models import DemoConfiguration, DemoRequest
from app.demo.enums import DemoStatus, ACTIVE_DEMO_STATUSES
from app.demo.schemas import (
    DemoOtpRequest,
    DemoOtpVerifyRequest,
    DemoRequestCreate,
    DemoRequestPublicResponse,
    DemoAccessRequest,
    AvailableSlotsResponse,
    SlotInfo,
)
from app.demo.services import (
    DemoSlotService,
    DemoCapacityService,
    DemoOtpService,
    DemoAccessService,
    DemoEmailService,
    generate_request_code,
    generate_access_code,
    get_configuration_or_404,
    require_active_configuration,
    validate_time_range,
    _parse_hhmm,
    IMAGE_MAX_COUNT,
    IMAGE_MAX_TOTAL_BYTES,
)

router = APIRouter(prefix="/demo/public", tags=["Demo (Public)"])


# ─── 1. Check Existing Demo ───────────────────────────────────────────────────

@router.get("/check")
def check_existing_demo(
    email: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Check whether the given email has an active demo request.
    Returns eligibility status — does NOT expose access_code or sensitive fields.
    """
    if not email or not email.strip():
        raise DemoAPIException(
            422,
            DemoErrorCode.EMAIL_REQUIRED,
            "Email address is required.",
        )

    email = email.strip().lower()
    active_statuses = [s.value for s in ACTIVE_DEMO_STATUSES]

    demo_request = (
        db.query(DemoRequest)
        .filter(
            DemoRequest.email == email,
            DemoRequest.status.in_(active_statuses),
        )
        .order_by(DemoRequest.demo_date.desc())
        .first()
    )

    if not demo_request:
        return {
            "success": True,
            "has_active_demo": False,
            "message": "No active demo request found for this email address.",
        }

    return {
        "success": True,
        "has_active_demo": True,
        "message": "An active demo request exists for this email address.",
        "data": {
            "request_code": demo_request.request_code,
            "status": demo_request.status,
            "demo_date": str(demo_request.demo_date),
            "start_time": demo_request.start_time.strftime("%H:%M"),
            "end_time": demo_request.end_time.strftime("%H:%M"),
        },
    }


# ─── 2. Available Slots ───────────────────────────────────────────────────────

@router.get("/available-slots")
def get_available_slots(
    date_str: Optional[str] = Query(None, alias="date", description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """
    Return all available time slots for a given date.
    Groups by configuration, shows capacity and remaining slots.
    """
    if not date_str:
        raise DemoAPIException(
            422,
            DemoErrorCode.INVALID_DATE,
            "Please provide a valid demo date.",
        )
    try:
        selected_date = date.fromisoformat(date_str)
    except ValueError:
        raise DemoAPIException(
            422,
            DemoErrorCode.INVALID_DATE,
            "Please provide a valid demo date.",
        )

    weekday_name = selected_date.strftime("%A").upper()

    # Find all active configurations that include this weekday
    all_active_configs = (
        db.query(DemoConfiguration)
        .filter(DemoConfiguration.is_active == True)
        .all()
    )

    matching_configs = [
        c for c in all_active_configs if weekday_name in (c.demo_days or [])
    ]

    if not matching_configs:
        raise DemoAPIException(
            404,
            DemoErrorCode.NO_AVAILABLE_CONFIGURATION,
            "No active demo configuration is available for the selected date.",
        )

    slots = []
    for config in matching_configs:
        slot_list = DemoSlotService.generate_slots(config)
        for slot_start, slot_end in slot_list:
            booked_count = DemoCapacityService.count_bookings(
                db, config.id, selected_date, slot_start
            )
            remaining = max(0, config.user_limit - booked_count)
            slots.append(
                SlotInfo(
                    config_id=config.id,
                    start_time=slot_start.strftime("%H:%M"),
                    end_time=slot_end.strftime("%H:%M"),
                    presented_by=config.presented_by,
                    user_limit=config.user_limit,
                    booked_count=booked_count,
                    remaining=remaining,
                    is_available=remaining > 0,
                )
            )

    return {
        "success": True,
        "data": {
            "date": date_str,
            "slots": [s.model_dump() for s in slots],
        },
    }


# ─── 3. Verify OTP ───────────────────────────────────────────────────────────

@router.post("/verify-otp")
def verify_demo_otp(
    payload: DemoOtpVerifyRequest,
    db: Session = Depends(get_db),
):
    """
    Verify the OTP sent to the email address.
    If the OTP is tied to a pending booking request, the actual DemoRequest is created here.
    """
    verification = DemoOtpService.verify_otp(db, str(payload.email), payload.otp)

    if isinstance(verification, DemoRequest):
        return {
            "success": True,
            "message": "Your demo request has been submitted successfully.",
            "data": {
                "id": verification.id,
                "request_code": verification.request_code,
                "status": verification.status,
                "demo_date": str(verification.demo_date),
                "start_time": verification.start_time.strftime("%H:%M"),
                "end_time": verification.end_time.strftime("%H:%M"),
                "presented_by": verification.presented_by,
            },
        }

    return {
        "success": True,
        "message": "Email address verified successfully.",
    }


# ─── 5. Create Demo Request ───────────────────────────────────────────────────

@router.post("/request")
def create_demo_request(
    payload: DemoRequestCreate,
    db: Session = Depends(get_db),
):
    """
    Save the booking request as a temporary pending OTP payload.
    The actual DemoRequest is created only after the user verifies the OTP.
    """
    email = str(payload.email).lower()

    active_statuses = [s.value for s in ACTIVE_DEMO_STATUSES]
    existing = (
        db.query(DemoRequest)
        .filter(
            DemoRequest.email == email,
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

    config = get_configuration_or_404(db, payload.config_id)
    require_active_configuration(config)
    DemoSlotService.validate_weekday(config, payload.demo_date)
    slot_start, slot_end = DemoSlotService.find_slot(config, payload.start_time)

    try:
        DemoCapacityService.check_and_lock_slot(
            db, config, payload.demo_date, slot_start
        )
    except DemoAPIException:
        raise

    otp_record = DemoOtpService.send_otp(
        db,
        email,
        request_payload=payload.model_dump(mode="json"),
    )
    DemoEmailService.send_otp_email(email, otp_record.otp_code)

    return {
        "success": True,
        "message": "OTP sent successfully. Please verify it to complete your demo booking.",
    }


# ─── 6. Access Demo ───────────────────────────────────────────────────────────

@router.post("/access")
def access_demo(
    payload: DemoAccessRequest,
    db: Session = Depends(get_db),
):
    """
    Access demo details using email + 6-digit access code.
    Returns demonstration_link and full demo details.
    Access code expires at 23:59:59 IST on the demo_date.
    """
    import re as _re

    email = str(payload.email).lower()
    access_code = payload.access_code

    # Validate format
    if not _re.fullmatch(r"\d{6}", access_code):
        raise DemoAPIException(
            422,
            DemoErrorCode.INVALID_ACCESS_CODE_FORMAT,
            "Access code must be exactly 6 digits.",
        )

    # Validate and retrieve
    demo_request = DemoAccessService.validate_access(db, email, access_code)

    return {
        "success": True,
        "message": "Access granted.",
        "data": {
            "id": demo_request.id,
            "request_code": demo_request.request_code,
            "full_name": demo_request.full_name,
            "email": demo_request.email,
            "demo_date": str(demo_request.demo_date),
            "start_time": demo_request.start_time.strftime("%H:%M"),
            "end_time": demo_request.end_time.strftime("%H:%M"),
            "presented_by": demo_request.presented_by,
            "demonstration_link": demo_request.demonstration_link,
            "status": demo_request.status,
        },
    }
