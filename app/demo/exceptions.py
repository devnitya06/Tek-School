"""
Demo Management System — Custom Exception

All expected business/validation errors are raised as DemoAPIException.
This is registered as a FastAPI exception handler in app/main.py.

Usage:
    raise DemoAPIException(
        status_code=409,
        error_code="DEMO_SLOT_FULL",
        message="The selected demo time slot is full. Please choose another slot."
    )
"""
from fastapi import Request
from fastapi.responses import JSONResponse


class DemoAPIException(Exception):
    """
    Structured API exception for all expected Demo Management System errors.

    Never use this for unexpected programming bugs — let those propagate to
    the global unhandled_exception_handler in main.py.
    """

    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        details=None,
    ):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details
        super().__init__(message)


async def demo_api_exception_handler(request: Request, exc: DemoAPIException):
    """FastAPI exception handler — returns clean JSON for all DemoAPIException instances."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error_code": exc.error_code,
            "message": exc.message,
            "details": exc.details,
        },
    )


# ─── Stable Error Code Registry ──────────────────────────────────────────────
# DO NOT rename these codes after shipping — frontend clients depend on them.

class DemoErrorCode:
    # General validation
    VALIDATION_ERROR = "DEMO_VALIDATION_ERROR"
    REQUIRED_FIELD = "DEMO_REQUIRED_FIELD"
    INVALID_EMAIL = "DEMO_INVALID_EMAIL"
    INVALID_PHONE = "DEMO_INVALID_PHONE"
    INVALID_DATE = "DEMO_INVALID_DATE"
    INVALID_TIME = "DEMO_INVALID_TIME"
    INVALID_URL = "DEMO_INVALID_URL"

    # Configuration
    CONFIGURATION_NOT_FOUND = "DEMO_CONFIGURATION_NOT_FOUND"
    CONFIGURATION_INACTIVE = "DEMO_CONFIGURATION_INACTIVE"
    INVALID_TIME_RANGE = "DEMO_INVALID_TIME_RANGE"
    INVALID_USER_LIMIT = "DEMO_INVALID_USER_LIMIT"
    DAYS_REQUIRED = "DEMO_DAYS_REQUIRED"
    INVALID_DAY = "DEMO_INVALID_DAY"
    PRESENTER_REQUIRED = "DEMO_PRESENTER_REQUIRED"
    LINK_REQUIRED = "DEMO_LINK_REQUIRED"
    INVALID_SLOT_CONFIGURATION = "DEMO_INVALID_SLOT_CONFIGURATION"

    # Public check
    EMAIL_REQUIRED = "DEMO_EMAIL_REQUIRED"
    REQUEST_NOT_FOUND = "DEMO_REQUEST_NOT_FOUND"

    # Active demo
    ACTIVE_REQUEST_EXISTS = "DEMO_ACTIVE_REQUEST_EXISTS"

    # OTP
    OTP_REQUIRED = "DEMO_OTP_REQUIRED"
    INVALID_OTP = "DEMO_INVALID_OTP"
    OTP_EXPIRED = "DEMO_OTP_EXPIRED"
    OTP_ALREADY_VERIFIED = "DEMO_OTP_ALREADY_VERIFIED"
    OTP_VERIFICATION_REQUIRED = "DEMO_OTP_VERIFICATION_REQUIRED"
    OTP_RATE_LIMITED = "DEMO_OTP_RATE_LIMITED"
    OTP_ATTEMPTS_EXCEEDED = "DEMO_OTP_ATTEMPTS_EXCEEDED"

    # Slot
    NO_AVAILABLE_CONFIGURATION = "DEMO_NO_AVAILABLE_CONFIGURATION"
    DATE_NOT_AVAILABLE = "DEMO_DATE_NOT_AVAILABLE"
    CONFIGURATION_DATE_MISMATCH = "DEMO_CONFIGURATION_DATE_MISMATCH"
    INVALID_SLOT = "DEMO_INVALID_SLOT"
    SLOT_UNAVAILABLE = "DEMO_SLOT_UNAVAILABLE"
    SLOT_FULL = "DEMO_SLOT_FULL"
    CAPACITY_CONFLICT = "DEMO_CAPACITY_CONFLICT"

    # Booking
    DUPLICATE_REQUEST = "DEMO_DUPLICATE_REQUEST"

    # Access code
    ACCESS_CODE_REQUIRED = "DEMO_ACCESS_CODE_REQUIRED"
    INVALID_ACCESS_CODE_FORMAT = "DEMO_INVALID_ACCESS_CODE_FORMAT"
    INVALID_ACCESS_CODE = "DEMO_INVALID_ACCESS_CODE"
    ACCESS_CODE_EXPIRED = "DEMO_ACCESS_CODE_EXPIRED"
    ACCESS_RATE_LIMITED = "DEMO_ACCESS_RATE_LIMITED"

    # Status
    INVALID_STATUS = "DEMO_INVALID_STATUS"
    INVALID_STATUS_TRANSITION = "DEMO_INVALID_STATUS_TRANSITION"

    # Reschedule
    RESCHEDULE_NOT_ALLOWED = "DEMO_RESCHEDULE_NOT_ALLOWED"

    # Images
    INVALID_IMAGE_TYPE = "DEMO_INVALID_IMAGE_TYPE"
    IMAGE_LIMIT_EXCEEDED = "DEMO_IMAGE_LIMIT_EXCEEDED"
    IMAGE_SIZE_EXCEEDED = "DEMO_IMAGE_SIZE_EXCEEDED"
    IMAGE_NOT_FOUND = "DEMO_IMAGE_NOT_FOUND"

    # Feedback
    FEEDBACK_REQUIRED = "DEMO_FEEDBACK_REQUIRED"
    FEEDBACK_TOO_LONG = "DEMO_FEEDBACK_TOO_LONG"
