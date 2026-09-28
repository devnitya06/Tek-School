"""Account Self-Delete Routes

Provides two endpoints:

    POST /account/delete/request-otp
        - Authenticated endpoint for non-admin users to request a deletion OTP
        - Blocked for ADMIN and SUPERADMIN

    POST /account/delete/verify
        - Verifies the OTP and performs soft deletion of the account
        - Invalidates tokens + session
        - Blocked for ADMIN and SUPERADMIN

All actions identify the current user from the JWT token — no user_id accepted
from the client body.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt

from app.db.session import get_db
from app.models.users import User, Token, AccountDeletionOtp
from app.models.user_session import UserSession
from app.schemas.users import UserRole
from app.core.dependencies import get_current_user
from app.utils.email_utility import generate_otp, send_dynamic_email
from pydantic import BaseModel

router = APIRouter(prefix="/account", tags=["Account Deletion"])


# ── Constants ──────────────────────────────────────────────────────────────────
OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60

# Roles that may NOT delete their own account
_ADMIN_ROLES = {UserRole.ADMIN, UserRole.SUPERADMIN}

# Roles that ARE allowed to delete their own account
_SELF_DELETE_ROLES = {
    UserRole.SCHOOL,
    UserRole.TEACHER,
    UserRole.STUDENT,
    UserRole.STAFF,
    UserRole.SELF_SIGNED_STUDENT,
    UserRole.SELF_SIGNED_TEACHER,
}


# ── Pydantic schemas ───────────────────────────────────────────────────────────
class OtpVerifyRequest(BaseModel):
    otp: str


class RequestOtpResponse(BaseModel):
    detail: str


class VerifyDeleteResponse(BaseModel):
    message: str
    account_deleted: bool


# ── Helpers ────────────────────────────────────────────────────────────────────

def _hash_otp(plain_otp: str) -> str:
    """Return a bcrypt hash of the plain OTP."""
    return bcrypt.hashpw(plain_otp.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_otp_hash(plain_otp: str, hashed: str) -> bool:
    """Verify a plain OTP against its bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_otp.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _normalize_role(role_value) -> Optional[UserRole]:
    if isinstance(role_value, UserRole):
        return role_value
    if isinstance(role_value, str):
        try:
            return UserRole(role_value)
        except ValueError:
            return None
    return None


def _reject_admin(current_user: User):
    """Raise 403 if the current user is ADMIN or SUPERADMIN."""
    role = _normalize_role(current_user.role)
    if role in _ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin and Super Admin accounts cannot delete their own account.",
        )


def _reject_already_deleted(current_user: User):
    """Raise 400 if the account is already soft-deleted."""
    if current_user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account is already deleted.",
        )


def _invalidate_user_sessions(db: Session, user_id: int):
    """Delete all refresh tokens and deactivate session for the user."""
    # Delete all stored refresh tokens
    db.query(Token).filter(Token.user_id == user_id).delete(synchronize_session=False)

    # Deactivate session record
    now = datetime.now(timezone.utc)
    sess = db.query(UserSession).filter(UserSession.user_id == user_id).first()
    if sess:
        sess.is_active = False
        sess.last_active_at = now


# ── Endpoint: Request OTP ──────────────────────────────────────────────────────

@router.post(
    "/delete/request-otp",
    response_model=RequestOtpResponse,
    summary="Request account deletion OTP",
    description=(
        "Send a 6-digit OTP to the authenticated user's registered email. "
        "Only allowed for non-admin roles. "
        "ADMIN and SUPERADMIN receive 403. "
        "OTP expires in 5 minutes. Resend allowed after 60-second cooldown."
    ),
)
def request_deletion_otp(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RequestOtpResponse:
    # ── Guard: must not be admin
    _reject_admin(current_user)

    # ── Guard: must not already be deleted
    _reject_already_deleted(current_user)

    now = datetime.now(timezone.utc)

    # ── Check resend cooldown: most-recent active OTP for this user
    existing = (
        db.query(AccountDeletionOtp)
        .filter(
            AccountDeletionOtp.user_id == current_user.id,
            AccountDeletionOtp.is_verified.is_(False),
        )
        .order_by(AccountDeletionOtp.created_at.desc())
        .first()
    )

    if existing:
        # Enforce resend cooldown
        created_at = existing.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        seconds_since_request = (now - created_at).total_seconds()
        if seconds_since_request < OTP_RESEND_COOLDOWN_SECONDS:
            remaining = int(OTP_RESEND_COOLDOWN_SECONDS - seconds_since_request)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {remaining} seconds before requesting a new OTP.",
            )
        # Invalidate the previous unverified OTP
        existing.is_verified = True  # mark consumed so it cannot be used
        existing.verified_at = now

    # ── Generate OTP
    plain_otp = generate_otp(6)
    otp_hash = _hash_otp(plain_otp)
    expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)

    new_otp = AccountDeletionOtp(
        user_id=current_user.id,
        otp_hash=otp_hash,
        expires_at=expires_at,
        attempts=0,
        max_attempts=OTP_MAX_ATTEMPTS,
        is_verified=False,
        created_at=now,
    )
    db.add(new_otp)
    db.commit()

    # ── Send OTP email (reuse existing template)
    try:
        send_dynamic_email(
            context_key="otp_verify.html",
            subject="Your Account Deletion OTP",
            recipient_email=current_user.email,
            context_data={
                "email": current_user.email,
                "OTP": plain_otp,
                "current_year": datetime.now().year,
            },
            db=db,
        )
    except Exception as e:
        # Roll back OTP creation if email fails
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send OTP email. Please try again.",
        )

    return RequestOtpResponse(
        detail="An OTP has been sent to your registered email. It expires in 5 minutes."
    )


# ── Endpoint: Verify OTP & Soft Delete ────────────────────────────────────────

@router.post(
    "/delete/verify",
    response_model=VerifyDeleteResponse,
    summary="Verify deletion OTP and soft-delete account",
    description=(
        "Verify the 6-digit OTP and permanently soft-delete the authenticated user's account. "
        "The account will no longer be accessible, but historical records are preserved. "
        "All active sessions and refresh tokens are immediately invalidated."
    ),
)
def verify_deletion_otp(
    body: OtpVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VerifyDeleteResponse:
    # ── Guard: must not be admin (re-check to prevent bypass)
    _reject_admin(current_user)

    # ── Guard: must not already be deleted
    _reject_already_deleted(current_user)

    now = datetime.now(timezone.utc)

    # ── Find the most-recent valid (unverified, unexpired) deletion OTP
    pending_otp = (
        db.query(AccountDeletionOtp)
        .filter(
            AccountDeletionOtp.user_id == current_user.id,
            AccountDeletionOtp.is_verified.is_(False),
        )
        .order_by(AccountDeletionOtp.created_at.desc())
        .first()
    )

    if not pending_otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active deletion OTP found. Please request a new OTP first.",
        )

    # ── Check expiry
    expires_at = pending_otp.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if now > expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Please request a new OTP.",
        )

    # ── Check attempt limit
    if pending_otp.attempts >= pending_otp.max_attempts:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum OTP verification attempts exceeded. Please request a new OTP.",
        )

    # ── Increment attempt count BEFORE verifying (prevents timing attacks)
    pending_otp.attempts += 1
    db.flush()

    # ── Verify OTP hash
    if not _verify_otp_hash(body.otp.strip(), pending_otp.otp_hash):
        db.commit()  # persist the incremented attempt count
        remaining = pending_otp.max_attempts - pending_otp.attempts
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid OTP. {remaining} attempt(s) remaining.",
        )

    # ── OTP valid — begin transactional soft deletion ─────────────────────────
    try:
        # 1. Mark OTP as consumed
        pending_otp.is_verified = True
        pending_otp.verified_at = now

        # 2. Soft-delete the user
        current_user.is_deleted = True
        current_user.deleted_at = now
        current_user.deleted_by = current_user.id  # self-deletion
        current_user.deletion_reason = "USER_REQUESTED"

        # 3. Disable the account so is_active checks also reject the user
        current_user.is_active = False

        # 4. Invalidate sessions and refresh tokens
        _invalidate_user_sessions(db, current_user.id)

        # 5. Commit everything atomically
        db.commit()

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete account. Please try again.",
        )

    return VerifyDeleteResponse(
        message="Your account has been deleted successfully.",
        account_deleted=True,
    )
