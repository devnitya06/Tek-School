"""Agent Routes - Phase 1, 2 & 3

Phase 1:
  POST   /agent/agents/                              - Step 1: Create agent account
  PATCH  /agent/agents/{id}                          - Step 2: Fill full profile (admin/superadmin)
  PATCH  /agent/agents/{id}/permissions              - Update permission flags (admin only)
  GET    /agent/agents/                              - List all agents
  GET    /agent/agents/{id}                          - Get agent by profile ID
  GET    /agent/agent/me                             - Agent views own profile (read-only)
  DELETE /agent/agents/{id}                          - Soft-delete agent (admin)

Phase 2:
  POST   /agent/agents/{id}/configuration            - Create payment configuration (admin/superadmin)
  PUT    /agent/agents/{id}/configuration            - Update payment configuration (admin/superadmin)
  GET    /agent/agents/{id}/configuration            - Get current configuration
  POST   /agent/agent/consent                        - Agent sets bonus preference

Phase 3:
  POST   /agent/agents/{id}/payment-account          - Create payment account (admin/superadmin)
  PUT    /agent/agents/{id}/payment-account          - Update payment account (admin/superadmin)
  GET    /agent/agents/{id}/payment-account          - Get payment account (admin/superadmin/own agent)
  GET    /agent/earnings/summary                     - Earnings summary (own agent)
  GET    /agent/earnings/history                     - Earnings + withdrawal history (own agent)
  POST   /agent/withdrawals                          - Submit withdrawal request (own agent)
  GET    /agent/withdrawals                          - List own withdrawal requests
  GET    /agent/withdrawals/{id}                     - Get own withdrawal request
  GET    /agent/agents/{id}/withdrawals              - Admin: list agent withdrawals
  GET    /agent/agents/{id}/withdrawals/{wid}        - Admin: get specific withdrawal
  PATCH  /agent/agents/{id}/withdrawals/{wid}/approve   - Admin: approve withdrawal
  PATCH  /agent/agents/{id}/withdrawals/{wid}/reject    - Admin: reject withdrawal
  PATCH  /agent/agents/{id}/withdrawals/{wid}/mark-paid - Admin: mark paid (multipart)
"""

from app.models.agent_config import AgentPaymentConfig
from app.models.agent_payment import (
    AgentPaymentAccount,
    AgentWithdrawal,
    AgentWithdrawalHistory,
    PaymentMethod,
    WithdrawalStatus,
)
from app.utils.email_utility import generate_password
from app.utils.s3 import upload_multipart_file_to_s3, delete_s3_object
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.agent import AgentProfile, StipendType
from app.models.agent_config import AgentEarning, AgentEarningStatus
from app.models.users import User, Token
from app.models.user_session import UserSession
from app.schemas.agent import (
    AgentConsentRequest,
    AgentCreateRequest,
    AgentCreateResponse,
    AgentListItem,
    AgentPermissionUpdate,
    AgentProfileResponse,
    AgentProfileUpdate,
)
from app.schemas.agent_config import (
    AgentConfigRequest,
    AgentConfigResponse,
    ActivityConfigResponse,
    StipendConfigResponse,
)
from app.schemas.agent_payment import (
    PaymentAccountRequest,
    PaymentAccountResponse,
    EarningsSummaryResponse,
    EarningsCategoryBreakdown,
    EarningHistoryItem,
    WithdrawalHistoryItem,
    WithdrawalCreateRequest,
    WithdrawalResponse,
    ApproveWithdrawalRequest,
    RejectWithdrawalRequest,
    WithdrawalAuditItem,
    _mask_account,
    ALLOWED_PROOF_EXTS,
    MAX_PROOF_SIZE,
)
from app.schemas.users import UserRole
from app.utils.email_utility import send_dynamic_email
from app.utils.permission import require_roles, _normalize_role

router = APIRouter(tags=["Agent"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_profile_or_404(profile_id: int, db: Session) -> AgentProfile:
    p = db.query(AgentProfile).filter(AgentProfile.id == profile_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Agent profile not found.")
    return p


def _get_profile_by_user_or_404(user_id: int, db: Session) -> AgentProfile:
    p = db.query(AgentProfile).filter(AgentProfile.user_id == user_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Agent profile not found.")
    return p


def _serialize(user: User, profile: AgentProfile) -> dict:
    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
    return {
        "user_id": user.id,
        "role": role_val,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "verification_status": user.verification_status,
        "profile_completed": user.profile_completed,
        "created_at": user.created_at,
        "id": profile.id,
        "agent_id": profile.agent_id,
        "first_name": profile.first_name,
        "last_name": profile.last_name,
        "phone": profile.phone,
        "email": profile.email,
        "stipend_type": profile.stipend_type,
        "gender": profile.gender,
        "dob": profile.dob,
        "qualification": profile.qualification,
        "university": profile.university,
        "designation": profile.designation,
        "experience": profile.experience,
        "pin_code": profile.pin_code,
        "division": profile.division,
        "district": profile.district,
        "state": profile.state,
        "landmark": profile.landmark,
        "can_onboard_school": profile.can_onboard_school,
        "can_enroll_student": profile.can_enroll_student,
        "can_collect_fees": profile.can_collect_fees,
        "can_do_followup": profile.can_do_followup,
        "can_verify_documents": profile.can_verify_documents,
        "can_coordinate_events": profile.can_coordinate_events,
        "wants_initial_bonus": profile.wants_initial_bonus,
        "profile_completed_step2": profile.profile_completed_step2,
        "profile_created_at": profile.created_at,
        "profile_updated_at": profile.updated_at,
    }


def _step2_is_complete(profile: AgentProfile) -> bool:
    required = [
        profile.gender, profile.dob, profile.qualification,
        profile.university, profile.designation, profile.experience,
        profile.pin_code, profile.landmark,
    ]
    return all(f is not None for f in required)


# ---------------------------------------------------------------------------
# Step 1: CREATE
# ---------------------------------------------------------------------------

@router.post(
    "/agents/",
    status_code=status.HTTP_201_CREATED,
    response_model=AgentCreateResponse,
    summary="Step 1 - Create Agent account",
    description=(
        "ADMIN / SUPERADMIN creates an Agent with minimal details: "
        "first_name, last_name, phone, email, stipend_type, password. "
        "Both users and agent_profiles rows are created in one transaction. "
        "Full profile is filled in Step 2 (PATCH /agents/{id})."
    ),
)
def create_agent(
    data: AgentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    # Auto-generate a secure password — never exposed to admin, only emailed to agent
    plain_password = generate_password(prefix=data.first_name)

    try:
        full_name = f"{data.first_name} {data.last_name}".strip()
        agent_user = User(
            name=full_name,
            email=data.email,
            phone=data.phone,
            role=UserRole.AGENT,
            hashed_password=get_password_hash(plain_password),
            is_verified=True,
            is_active=True,
            verification_status="approved",
            profile_completed=False,
        )
        db.add(agent_user)
        db.flush()

        profile = AgentProfile(
            user_id=agent_user.id,
            first_name=data.first_name,
            last_name=data.last_name,
            phone=data.phone,
            email=data.email,
            stipend_type=data.stipend_type,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

    except IntegrityError as exc:
        db.rollback()
        msg = str(exc).lower()
        if "email" in msg:
            raise HTTPException(status_code=409, detail="An account with this email already exists.")
        raise HTTPException(status_code=400, detail="Could not create agent. Check input data.")
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error while creating agent.")

    # Email credentials to agent — non-fatal: account is committed regardless
    email_sent = False
    try:
        from datetime import datetime as _dt
        send_dynamic_email(
            context_key="credential.html",
            subject="Your Agent Account Credentials",
            recipient_email=data.email,
            context_data={
                "email": data.email,
                "password": plain_password,
                "application_name": getattr(settings, "PROJECT_NAME", "Tek-School"),
                "note": (
                    f"Hi {data.first_name}, your Agent account (ID: {profile.agent_id}) "
                    "has been created. Use the credentials above to log in and complete your profile."
                ),
                "login_url": getattr(settings, "FRONTEND_URL", ""),
                "current_year": _dt.now().year,
            },
            db=db,
        )
        email_sent = True
    except Exception as exc_email:
        logger.warning(
            "[AGENT] Credential email failed for %s (agent_id=%s): %s",
            data.email, profile.agent_id, str(exc_email),
        )

    return AgentCreateResponse(
        detail=(
            "Agent created successfully. Credentials sent to the agent's email."
            if email_sent
            else "Agent created successfully. Note: credential email could not be delivered."
        ),
        user_id=agent_user.id,
        agent_id=profile.agent_id,
    )


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

@router.get(
    "/agents/",
    response_model=List[AgentListItem],
    summary="List all Agents",
)
def list_agents(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
    include_deleted: bool = Query(default=False),
    profile_complete: Optional[bool] = Query(default=None, description="Filter by step-2 completion"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    query = (
        db.query(User, AgentProfile)
        .join(AgentProfile, AgentProfile.user_id == User.id)
        .filter(User.role == UserRole.AGENT)
    )
    if not include_deleted:
        query = query.filter(User.is_deleted.is_(False))
    if profile_complete is not None:
        query = query.filter(AgentProfile.profile_completed_step2.is_(profile_complete))

    rows = query.offset(skip).limit(limit).all()
    result = []
    for user, profile in rows:
        result.append(AgentListItem(
            user_id=user.id,
            is_active=user.is_active,
            is_deleted=user.is_deleted,
            id=profile.id,
            agent_id=profile.agent_id,
            first_name=profile.first_name,
            last_name=profile.last_name,
            phone=profile.phone,
            email=profile.email,
            state=profile.state,
            stipend_type=profile.stipend_type,
            profile_completed_step2=profile.profile_completed_step2,
            created_at=user.created_at,
        ))
    return result


# ---------------------------------------------------------------------------
# GET by profile ID (admin)
# ---------------------------------------------------------------------------

@router.get(
    "/agents/{agent_profile_id}",
    response_model=AgentProfileResponse,
    summary="Get Agent profile by profile ID",
)
def get_agent(
    agent_profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    profile = _get_profile_or_404(agent_profile_id, db)
    user = db.query(User).filter(User.id == profile.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Associated user not found.")
    return _serialize(user, profile)


# ---------------------------------------------------------------------------
# GET ME (agent's own profile)
# ---------------------------------------------------------------------------

@router.get(
    "/agent/me",
    response_model=AgentProfileResponse,
    summary="Agent views own profile",
)
def get_my_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.AGENT)),
):
    profile = _get_profile_by_user_or_404(current_user.id, db)
    return _serialize(current_user, profile)


# ---------------------------------------------------------------------------
# Step 2: UPDATE PROFILE (admin updates agent's full profile)
# ---------------------------------------------------------------------------

@router.patch(
    "/agents/{agent_profile_id}",
    response_model=AgentProfileResponse,
    summary="Step 2 - Update Agent full profile (admin)",
    description=(
        "ADMIN / SUPERADMIN fills or updates all profile fields. "
        "Editable: first_name, last_name, phone, email, stipend_type, gender, dob, "
        "qualification, university, designation, experience, pin_code, division, "
        "district, state, landmark. "
        "Permission flags are managed separately via /agents/{id}/permissions."
    ),
)
def update_agent(
    agent_profile_id: int,
    data: AgentProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    profile = _get_profile_or_404(agent_profile_id, db)
    user = db.query(User).filter(User.id == profile.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Associated user not found.")
    if user.is_deleted:
        raise HTTPException(status_code=400, detail="Cannot update a soft-deleted agent.")

    fields = data.model_dump(exclude_unset=True)

    # Sync selected fields back to users table too
    USER_SYNC_FIELDS = {"first_name", "last_name", "phone", "email"}
    for key, val in fields.items():
        if key in USER_SYNC_FIELDS:
            if key in ("first_name", "last_name"):
                # Rebuild users.name from whatever we have
                fn = fields.get("first_name", profile.first_name)
                ln = fields.get("last_name",  profile.last_name)
                user.name = f"{fn} {ln}".strip()
            elif key == "phone":
                user.phone = val
            elif key == "email":
                user.email = val
        setattr(profile, key, val)

    # Auto-mark profile_completed_step2 when required fields are all filled
    if _step2_is_complete(profile):
        profile.profile_completed_step2 = True
        user.profile_completed = True

    try:
        db.commit()
        db.refresh(profile)
        db.refresh(user)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error while updating agent profile.")

    return _serialize(user, profile)


# ---------------------------------------------------------------------------
# UPDATE PERMISSIONS (admin only)
# ---------------------------------------------------------------------------

@router.patch(
    "/agents/{agent_profile_id}/permissions",
    response_model=AgentProfileResponse,
    summary="Update Agent activity permissions (admin only)",
)
def update_agent_permissions(
    agent_profile_id: int,
    data: AgentPermissionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    profile = _get_profile_or_404(agent_profile_id, db)
    user = db.query(User).filter(User.id == profile.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Associated user not found.")
    if user.is_deleted:
        raise HTTPException(status_code=400, detail="Cannot update a soft-deleted agent.")

    for field, val in data.model_dump(exclude_unset=True).items():
        setattr(profile, field, val)

    try:
        db.commit()
        db.refresh(profile)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error while updating permissions.")

    return _serialize(user, profile)


# ---------------------------------------------------------------------------
# SOFT DELETE (admin only)
# ---------------------------------------------------------------------------

@router.delete(
    "/agents/{agent_profile_id}",
    summary="Soft-delete an Agent account (admin)",
)
def delete_agent(
    agent_profile_id: int,
    reason: Optional[str] = Query(default=None, max_length=255),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    profile = _get_profile_or_404(agent_profile_id, db)
    user = db.query(User).filter(User.id == profile.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Associated user not found.")
    if user.is_deleted:
        raise HTTPException(status_code=400, detail="Agent is already deleted.")

    now = datetime.now(timezone.utc)
    try:
        user.is_deleted = True
        user.deleted_at = now
        user.deleted_by = current_user.id
        user.deletion_reason = reason or "ADMIN_DELETED"
        user.is_active = False
        db.query(Token).filter(Token.user_id == user.id).delete(synchronize_session=False)
        sess = db.query(UserSession).filter(UserSession.user_id == user.id).first()
        if sess:
            sess.is_active = False
            sess.last_active_at = now
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error while deleting agent.")

    return {
        "detail": "Agent account soft-deleted successfully.",
        "user_id": user.id,
        "agent_id": profile.agent_id,
        "deleted_at": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# Phase 2: CONSENT
# ---------------------------------------------------------------------------

@router.post(
    "/agent/consent",
    summary="Set Agent initial bonus preference",
    description="Agent sets their initial bonus preference (wants_initial_bonus). Can be updated at any time.",
)
def agent_consent(
    data: AgentConsentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.AGENT)),
):
    profile = _get_profile_by_user_or_404(current_user.id, db)
    if current_user.is_deleted:
        raise HTTPException(status_code=400, detail="This account has been deleted.")

    profile.wants_initial_bonus = data.wants_initial_bonus

    try:
        db.commit()
        db.refresh(profile)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error while saving preference.")

    return {
        "detail": "Preference saved successfully.",
        "wants_initial_bonus": profile.wants_initial_bonus,
    }


# ---------------------------------------------------------------------------
# Phase 2: PAYMENT CONFIGURATION
# ---------------------------------------------------------------------------

def _config_to_response(profile: "AgentProfile", cfg: "AgentPaymentConfig") -> dict:  # noqa: F821
    """Serialize an AgentPaymentConfig to the AgentConfigResponse dict."""
    from decimal import Decimal
    return {
        "agent_profile_id": profile.id,
        "agent_id": profile.agent_id,
        "institution_digital_profile": {
            "is_enabled": cfg.idp_is_enabled,
            "rate": Decimal(str(cfg.idp_rate)),
        },
        "daily_stipend": {
            "is_enabled": cfg.stipend_is_enabled,
            "daily_rate": Decimal(str(cfg.stipend_daily_rate)),
        },
        "physical_verification": {
            "is_enabled": cfg.pv_is_enabled,
            "rate": Decimal(str(cfg.pv_rate)),
        },
        "online_demonstration": {
            "is_enabled": cfg.od_is_enabled,
            "rate": Decimal(str(cfg.od_rate)),
        },
        "offline_demonstration": {
            "is_enabled": cfg.offd_is_enabled,
            "rate": Decimal(str(cfg.offd_rate)),
        },
        "other_activities": {
            "is_enabled": cfg.oa_is_enabled,
            "rate": Decimal(str(cfg.oa_rate)),
        },
        "initial_bonus": Decimal(str(cfg.initial_bonus)),
        "is_bonus_withdrawn": cfg.is_bonus_withdrawn,
        "created_at": cfg.created_at,
        "updated_at": cfg.updated_at,
    }


@router.post(
    "/agents/{agent_profile_id}/configuration",
    status_code=status.HTTP_201_CREATED,
    summary="Create Agent payment configuration (ADMIN / SUPERADMIN)",
    description=(
        "Creates the initial payment configuration for an Agent. "
        "Returns 409 if a configuration already exists — use PUT to update."
    ),
)
def create_agent_config(
    agent_profile_id: int,
    data: AgentConfigRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    from app.models.agent_config import AgentPaymentConfig

    profile = _get_profile_or_404(agent_profile_id, db)
    user = db.query(User).filter(User.id == profile.user_id).first()
    if not user or _normalize_role(user.role) != UserRole.AGENT:
        raise HTTPException(status_code=400, detail="Target user is not an Agent.")

    # Reject duplicate configuration
    existing = db.query(AgentPaymentConfig).filter(
        AgentPaymentConfig.agent_profile_id == profile.id
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="A configuration already exists for this Agent. Use PUT to update.",
        )

    cfg = AgentPaymentConfig(
        agent_profile_id=profile.id,
        idp_is_enabled=data.institution_digital_profile.is_enabled,
        idp_rate=data.institution_digital_profile.rate,
        stipend_is_enabled=data.daily_stipend.is_enabled,
        stipend_daily_rate=data.daily_stipend.daily_rate,
        pv_is_enabled=data.physical_verification.is_enabled,
        pv_rate=data.physical_verification.rate,
        od_is_enabled=data.online_demonstration.is_enabled,
        od_rate=data.online_demonstration.rate,
        offd_is_enabled=data.offline_demonstration.is_enabled,
        offd_rate=data.offline_demonstration.rate,
        oa_is_enabled=data.other_activities.is_enabled,
        oa_rate=data.other_activities.rate,
        initial_bonus=data.initial_bonus,
        is_bonus_withdrawn=False,           # always false on creation
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    try:
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Duplicate configuration detected (concurrent request). "
                   "Use PUT to update the existing configuration.",
        )
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error while creating configuration.")

    return _config_to_response(profile, cfg)


@router.put(
    "/agents/{agent_profile_id}/configuration",
    summary="Update Agent payment configuration (ADMIN / SUPERADMIN)",
    description=(
        "Updates the existing configuration record in-place. "
        "Does NOT create a second record or version. "
        "created_at is preserved. updated_at is auto-refreshed. "
        "is_bonus_withdrawn is never changed by this endpoint."
    ),
)
def update_agent_config(
    agent_profile_id: int,
    data: AgentConfigRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):

    profile = _get_profile_or_404(agent_profile_id, db)
    user = db.query(User).filter(User.id == profile.user_id).first()
    if not user or _normalize_role(user.role) != UserRole.AGENT:
        raise HTTPException(status_code=400, detail="Target user is not an Agent.")

    cfg = db.query(AgentPaymentConfig).filter(
        AgentPaymentConfig.agent_profile_id == profile.id
    ).first()
    if not cfg:
        raise HTTPException(
            status_code=404,
            detail="No configuration found for this Agent. Use POST to create one.",
        )

    # Apply updates — is_bonus_withdrawn is intentionally excluded
    cfg.idp_is_enabled = data.institution_digital_profile.is_enabled
    cfg.idp_rate = data.institution_digital_profile.rate
    cfg.stipend_is_enabled = data.daily_stipend.is_enabled
    cfg.stipend_daily_rate = data.daily_stipend.daily_rate
    cfg.pv_is_enabled = data.physical_verification.is_enabled
    cfg.pv_rate = data.physical_verification.rate
    cfg.od_is_enabled = data.online_demonstration.is_enabled
    cfg.od_rate = data.online_demonstration.rate
    cfg.offd_is_enabled = data.offline_demonstration.is_enabled
    cfg.offd_rate = data.offline_demonstration.rate
    cfg.oa_is_enabled = data.other_activities.is_enabled
    cfg.oa_rate = data.other_activities.rate
    cfg.initial_bonus = data.initial_bonus
    cfg.updated_by = current_user.id
    # created_at is never touched — preserved by the ORM

    try:
        db.commit()
        db.refresh(cfg)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error while updating configuration.")

    return _config_to_response(profile, cfg)


@router.get(
    "/agents/{agent_profile_id}/configuration",
    summary="Get Agent payment configuration",
    description=(
        "Returns the current configuration including all activity rates and enabled flags. "
        "Disabled activities remain visible with their configured rate. "
        "Returns 404 if no configuration exists yet."
    ),
)
def get_agent_config(
    agent_profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SUPERADMIN, UserRole.ADMIN, UserRole.AGENT)),
):
    from app.models.agent_config import AgentPaymentConfig

    profile = _get_profile_or_404(agent_profile_id, db)

    # Agents can only view their own configuration
    current_role = _normalize_role(current_user.role)
    if current_role == UserRole.AGENT:
        own_profile = db.query(AgentProfile).filter(
            AgentProfile.user_id == current_user.id
        ).first()
        if not own_profile or own_profile.id != profile.id:
            raise HTTPException(
                status_code=403,
                detail="Agents can only view their own configuration.",
            )

    cfg = db.query(AgentPaymentConfig).filter(
        AgentPaymentConfig.agent_profile_id == profile.id
    ).first()
    if not cfg:
        raise HTTPException(
            status_code=404,
            detail="No configuration found for this Agent.",
        )

    return _config_to_response(profile, cfg)


# ---------------------------------------------------------------------------
# PHASE 3 ROUTES (Payment Account, Earnings, Withdrawals)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Phase 3 Helpers
# ---------------------------------------------------------------------------

def _get_own_profile_or_404(current_user: User, db: Session) -> AgentProfile:
    """Get authenticated user's own AgentProfile, 404 if missing."""
    p = db.query(AgentProfile).filter(AgentProfile.user_id == current_user.id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Agent profile not found.")
    return p


def _assert_agent_owns_withdrawal(profile: AgentProfile, withdrawal: AgentWithdrawal):
    """Raise 404 if the withdrawal does not belong to this agent."""
    if withdrawal.agent_profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Withdrawal request not found.")


def _serialize_payment_account(acct: AgentPaymentAccount) -> dict:
    masked = _mask_account(acct.bank_account_number) if acct.bank_account_number else None
    return {
        "id": acct.id,
        "agent_profile_id": acct.agent_profile_id,
        "account_holder_name": acct.account_holder_name,
        "payment_method": acct.payment_method,
        "upi_id": acct.upi_id,
        "bank_account_masked": masked,
        "ifsc_code": acct.ifsc_code,
        "bank_name": acct.bank_name,
        "branch_name": acct.branch_name,
        "created_at": acct.created_at,
        "updated_at": acct.updated_at,
    }


def _snapshot_payment_account(acct: AgentPaymentAccount) -> dict:
    """Return a snapshot dict to embed in a withdrawal record."""
    return {
        "payment_method_snapshot": acct.payment_method,
        "upi_id_snapshot": acct.upi_id,
        "bank_account_masked_snapshot": _mask_account(acct.bank_account_number) if acct.bank_account_number else None,
        "ifsc_snapshot": acct.ifsc_code,
        "bank_name_snapshot": acct.bank_name,
        "account_holder_name_snapshot": acct.account_holder_name,
    }


def _calc_earnings_summary(profile: AgentProfile, db: Session) -> dict:
    """Calculate earnings summary from agent_earnings and agent_withdrawals tables."""
    from decimal import Decimal as D
    from app.models.agent_config import AgentEarningStatus

    rows = db.query(AgentEarning).filter(
        AgentEarning.agent_profile_id == profile.id
    ).all()

    total_approved = D("0")
    total_pending = D("0")
    total_rejected = D("0")
    breakdown_map: dict = {}

    for e in rows:
        amt = D(str(e.amount))
        et = e.earning_type
        if et not in breakdown_map:
            breakdown_map[et] = {"approved": D("0"), "pending": D("0"), "rejected": D("0"), "count": 0}
        breakdown_map[et]["count"] += 1
        if e.status == AgentEarningStatus.APPROVED.value:
            total_approved += amt
            breakdown_map[et]["approved"] += amt
        elif e.status == AgentEarningStatus.PENDING.value:
            total_pending += amt
            breakdown_map[et]["pending"] += amt
        elif e.status == AgentEarningStatus.REJECTED.value:
            total_rejected += amt
            breakdown_map[et]["rejected"] += amt

    # Withdrawals
    withdrawals = db.query(AgentWithdrawal).filter(
        AgentWithdrawal.agent_profile_id == profile.id
    ).all()

    reserved = D("0")
    paid = D("0")
    for w in withdrawals:
        amt = D(str(w.requested_amount))
        if w.status in (WithdrawalStatus.PENDING.value, WithdrawalStatus.APPROVED.value):
            reserved += amt
        elif w.status == WithdrawalStatus.PAID.value:
            paid += D(str(w.actual_paid_amount)) if w.actual_paid_amount else amt

    available = total_approved - reserved - paid
    if available < 0:
        available = D("0")

    breakdown = [
        {
            "earning_type": et,
            "total_approved": v["approved"],
            "total_pending": v["pending"],
            "total_rejected": v["rejected"],
            "count": v["count"],
        }
        for et, v in breakdown_map.items()
    ]

    return {
        "total_approved_earnings": total_approved,
        "total_pending_earnings": total_pending,
        "total_rejected_earnings": total_rejected,
        "total_withdrawal_requested": reserved,
        "total_reserved_amount": reserved,
        "total_paid_amount": paid,
        "available_balance": available,
        "currency": "INR",
        "breakdown": breakdown,
    }


def _record_withdrawal_history(
    db: Session,
    withdrawal: AgentWithdrawal,
    from_status: Optional[str],
    to_status: str,
    action: str,
    actor_id: Optional[int],
    remarks: Optional[str] = None,
    transaction_id: Optional[str] = None,
    transaction_date=None,
    payment_proof_url: Optional[str] = None,
    actual_paid_amount=None,
):
    entry = AgentWithdrawalHistory(
        withdrawal_id=withdrawal.id,
        agent_profile_id=withdrawal.agent_profile_id,
        from_status=from_status,
        to_status=to_status,
        action=action,
        actor_user_id=actor_id,
        remarks=remarks,
        transaction_id=transaction_id,
        transaction_date=transaction_date,
        payment_proof_url=payment_proof_url,
        actual_paid_amount=actual_paid_amount,
    )
    db.add(entry)


# ---------------------------------------------------------------------------
# Phase 3: PAYMENT ACCOUNT — POST (create)
# ---------------------------------------------------------------------------

@router.post(
    "/agents/{agent_profile_id}/payment-account",
    status_code=status.HTTP_201_CREATED,
    summary="Create Agent payment account (ADMIN / SUPERADMIN)",
    description=(
        "Creates the payment account for an Agent. "
        "Returns 409 if an account already exists — use PUT to update. "
        "Only UPI and BANK_TRANSFER are accepted. "
        "confirm_bank_account_number is validated but never stored. "
        "Bank account numbers are masked in responses."
    ),
)
def create_payment_account(
    agent_profile_id: int,
    data: PaymentAccountRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    profile = _get_profile_or_404(agent_profile_id, db)

    existing = db.query(AgentPaymentAccount).filter(
        AgentPaymentAccount.agent_profile_id == profile.id
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="A payment account already exists for this Agent. Use PUT to update.",
        )

    acct = AgentPaymentAccount(
        agent_profile_id=profile.id,
        account_holder_name=data.account_holder_name,
        payment_method=data.payment_method.value,
        upi_id=data.upi_id if data.payment_method == PaymentMethod.UPI else None,
        bank_account_number=data.bank_account_number if data.payment_method == PaymentMethod.BANK_TRANSFER else None,
        ifsc_code=data.ifsc_code if data.payment_method == PaymentMethod.BANK_TRANSFER else None,
        bank_name=data.bank_name if data.payment_method == PaymentMethod.BANK_TRANSFER else None,
        branch_name=data.branch_name if data.payment_method == PaymentMethod.BANK_TRANSFER else None,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    try:
        db.add(acct)
        db.commit()
        db.refresh(acct)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate payment account detected.")
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error while creating payment account.")

    return _serialize_payment_account(acct)


# ---------------------------------------------------------------------------
# Phase 3: PAYMENT ACCOUNT — PUT (update)
# ---------------------------------------------------------------------------

@router.put(
    "/agents/{agent_profile_id}/payment-account",
    summary="Update Agent payment account (ADMIN / SUPERADMIN)",
    description=(
        "Updates the existing payment account in-place. "
        "Changing payment method safely clears obsolete fields. "
        "confirm_bank_account_number is validated but never stored."
    ),
)
def update_payment_account(
    agent_profile_id: int,
    data: PaymentAccountRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    profile = _get_profile_or_404(agent_profile_id, db)

    acct = db.query(AgentPaymentAccount).filter(
        AgentPaymentAccount.agent_profile_id == profile.id
    ).first()
    if not acct:
        raise HTTPException(
            status_code=404,
            detail="No payment account found for this Agent. Use POST to create one.",
        )

    acct.account_holder_name = data.account_holder_name
    acct.payment_method = data.payment_method.value
    if data.payment_method == PaymentMethod.UPI:
        acct.upi_id = data.upi_id
        acct.bank_account_number = None
        acct.ifsc_code = None
        acct.bank_name = None
        acct.branch_name = None
    else:
        acct.upi_id = None
        acct.bank_account_number = data.bank_account_number
        acct.ifsc_code = data.ifsc_code
        acct.bank_name = data.bank_name
        acct.branch_name = data.branch_name
    acct.updated_by = current_user.id

    try:
        db.commit()
        db.refresh(acct)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error while updating payment account.")

    return _serialize_payment_account(acct)


# ---------------------------------------------------------------------------
# Phase 3: PAYMENT ACCOUNT — GET
# ---------------------------------------------------------------------------

@router.get(
    "/agents/{agent_profile_id}/payment-account",
    summary="Get Agent payment account",
)
def get_payment_account(
    agent_profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN, UserRole.AGENT)),
):
    profile = _get_profile_or_404(agent_profile_id, db)

    # Agents can only view their own account
    current_role = _normalize_role(current_user.role)
    if current_role == UserRole.AGENT:
        own = db.query(AgentProfile).filter(AgentProfile.user_id == current_user.id).first()
        if not own or own.id != profile.id:
            raise HTTPException(status_code=403, detail="Agents can only view their own payment account.")

    acct = db.query(AgentPaymentAccount).filter(
        AgentPaymentAccount.agent_profile_id == profile.id
    ).first()
    if not acct:
        raise HTTPException(status_code=404, detail="No payment account found for this Agent.")

    return _serialize_payment_account(acct)


# ---------------------------------------------------------------------------
# Phase 3: EARNINGS SUMMARY
#   AGENT     → always own data, agent_id ignored
#   ADMIN/SA  → must pass ?agent_id= to specify which agent
# ---------------------------------------------------------------------------

@router.get(
    "/earnings/summary",
    summary="Earnings summary — AGENT (own) or ADMIN/SUPERADMIN (?agent_id=)",
    description=(
        "**AGENT**: returns own earnings summary. `agent_id` param is ignored.\n\n"
        "**ADMIN / SUPERADMIN**: must supply `?agent_id=<profile_id>` to view a specific agent's summary."
    ),
)
def get_earnings_summary(
    agent_id: Optional[int] = Query(default=None, description="Agent profile ID (ADMIN/SUPERADMIN only)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.AGENT, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    current_role = _normalize_role(current_user.role)

    if current_role == UserRole.AGENT:
        # Agents always see their own data — agent_id param is silently ignored
        profile = _get_own_profile_or_404(current_user, db)
    else:
        # Admin / SuperAdmin must provide agent_id
        if agent_id is None:
            raise HTTPException(
                status_code=400,
                detail="ADMIN/SUPERADMIN must supply ?agent_id= to view an agent's earnings.",
            )
        profile = _get_profile_or_404(agent_id, db)

    return _calc_earnings_summary(profile, db)


# ---------------------------------------------------------------------------
# Phase 3: EARNINGS HISTORY
#   AGENT     → always own data, agent_id ignored
#   ADMIN/SA  → must pass ?agent_id= to specify which agent
# ---------------------------------------------------------------------------

@router.get(
    "/earnings/history",
    summary="Earnings + withdrawal history — AGENT (own) or ADMIN/SUPERADMIN (?agent_id=)",
    description=(
        "**AGENT**: returns own earnings + withdrawal history. `agent_id` param is ignored.\n\n"
        "**ADMIN / SUPERADMIN**: must supply `?agent_id=<profile_id>` to view a specific agent's history."
    ),
)
def get_earnings_history(
    agent_id: Optional[int] = Query(default=None, description="Agent profile ID (ADMIN/SUPERADMIN only)"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.AGENT, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    current_role = _normalize_role(current_user.role)

    if current_role == UserRole.AGENT:
        profile = _get_own_profile_or_404(current_user, db)
    else:
        if agent_id is None:
            raise HTTPException(
                status_code=400,
                detail="ADMIN/SUPERADMIN must supply ?agent_id= to view an agent's history.",
            )
        profile = _get_profile_or_404(agent_id, db)

    return _build_earnings_history(profile, db, skip, limit, status_filter)


def _build_earnings_history(
    profile: AgentProfile,
    db: Session,
    skip: int,
    limit: int,
    status_filter: Optional[str],
) -> dict:
    """Shared earnings + withdrawal history builder."""
    eq = db.query(AgentEarning).filter(AgentEarning.agent_profile_id == profile.id)
    if status_filter:
        eq = eq.filter(AgentEarning.status == status_filter.upper())
    earnings = eq.order_by(AgentEarning.created_at.desc()).offset(skip).limit(limit).all()

    wq = db.query(AgentWithdrawal).filter(AgentWithdrawal.agent_profile_id == profile.id)
    if status_filter:
        wq = wq.filter(AgentWithdrawal.status == status_filter.upper())
    withdrawals = wq.order_by(AgentWithdrawal.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "earnings": [
            {
                "id": e.id,
                "earning_type": e.earning_type,
                "reference_type": e.reference_type,
                "reference_id": e.reference_id,
                "description": e.description,
                "applied_rate": e.applied_rate,
                "amount": e.amount,
                "status": e.status,
                "earning_date": e.earning_date,
                "created_at": e.created_at,
                "approved_at": e.approved_at,
            }
            for e in earnings
        ],
        "withdrawals": [
            {
                "id": w.id,
                "requested_amount": w.requested_amount,
                "status": w.status,
                "agent_remarks": w.agent_remarks,
                "payment_method": w.payment_method_snapshot,
                "bank_account_masked": w.bank_account_masked_snapshot,
                "upi_id": w.upi_id_snapshot,
                "created_at": w.created_at,
                "reviewed_at": w.reviewed_at,
                "transaction_id": w.transaction_id,
                "transaction_date": w.transaction_date,
                "actual_paid_amount": w.actual_paid_amount,
                "admin_remarks": w.admin_remarks,
                "rejection_reason": w.rejection_reason,
                "paid_at": w.paid_at,
            }
            for w in withdrawals
        ],
    }


# ---------------------------------------------------------------------------
# Phase 3: SUBMIT WITHDRAWAL (own agent)
# ---------------------------------------------------------------------------

@router.post(
    "/withdrawals",
    status_code=status.HTTP_201_CREATED,
    summary="Submit withdrawal request (AGENT)",
    description=(
        "Agent submits a withdrawal request for their available balance. "
        "Amount is atomically reserved at creation. "
        "Agent ID comes from the authenticated user — cannot be spoofed. "
        "Agent must have a saved payment account."
    ),
)
def create_withdrawal(
    data: WithdrawalCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.AGENT)),
):
    profile = _get_own_profile_or_404(current_user, db)

    if current_user.is_deleted:
        raise HTTPException(status_code=400, detail="This account has been deleted.")

    # Must have a payment account
    acct = db.query(AgentPaymentAccount).filter(
        AgentPaymentAccount.agent_profile_id == profile.id
    ).with_for_update().first()
    if not acct:
        raise HTTPException(
            status_code=400,
            detail="You must have a saved payment account before submitting a withdrawal.",
        )

    # Calculate available balance (lock earnings rows to prevent concurrent race)
    summary = _calc_earnings_summary(profile, db)
    available = summary["available_balance"]

    if data.amount > available:
        raise HTTPException(
            status_code=400,
            detail=f"Requested amount {data.amount} exceeds available balance {available}.",
        )

    snap = _snapshot_payment_account(acct)

    withdrawal = AgentWithdrawal(
        agent_profile_id=profile.id,
        requested_amount=data.amount,
        status=WithdrawalStatus.PENDING.value,
        agent_remarks=data.remarks,
        reservation_released=False,
        **snap,
    )
    try:
        db.add(withdrawal)
        db.flush()
        _record_withdrawal_history(
            db, withdrawal,
            from_status=None,
            to_status=WithdrawalStatus.PENDING.value,
            action="CREATED",
            actor_id=current_user.id,
        )
        db.commit()
        db.refresh(withdrawal)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error while creating withdrawal request.")

    return _serialize_withdrawal(withdrawal)


# ---------------------------------------------------------------------------
# Phase 3: LIST OWN WITHDRAWALS (agent)
# ---------------------------------------------------------------------------

@router.get(
    "/withdrawals",
    summary="List own withdrawal requests (AGENT)",
)
def list_own_withdrawals(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.AGENT)),
):
    profile = _get_own_profile_or_404(current_user, db)
    q = db.query(AgentWithdrawal).filter(AgentWithdrawal.agent_profile_id == profile.id)
    if status_filter:
        q = q.filter(AgentWithdrawal.status == status_filter.upper())
    withdrawals = q.order_by(AgentWithdrawal.created_at.desc()).offset(skip).limit(limit).all()
    return [_serialize_withdrawal(w) for w in withdrawals]


# ---------------------------------------------------------------------------
# Phase 3: GET OWN WITHDRAWAL (agent)
# ---------------------------------------------------------------------------

@router.get(
    "/withdrawals/{request_id}",
    summary="Get own withdrawal request (AGENT)",
)
def get_own_withdrawal(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.AGENT)),
):
    profile = _get_own_profile_or_404(current_user, db)
    w = db.query(AgentWithdrawal).filter(AgentWithdrawal.id == request_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Withdrawal request not found.")
    _assert_agent_owns_withdrawal(profile, w)
    return _serialize_withdrawal(w)


# ---------------------------------------------------------------------------
# Shared withdrawal serializer
# ---------------------------------------------------------------------------

def _serialize_withdrawal(w: AgentWithdrawal) -> dict:
    return {
        "id": w.id,
        "agent_profile_id": w.agent_profile_id,
        "requested_amount": w.requested_amount,
        "status": w.status,
        "agent_remarks": w.agent_remarks,
        "payment_method_snapshot": w.payment_method_snapshot,
        "upi_id_snapshot": w.upi_id_snapshot,
        "bank_account_masked_snapshot": w.bank_account_masked_snapshot,
        "ifsc_snapshot": w.ifsc_snapshot,
        "bank_name_snapshot": w.bank_name_snapshot,
        "account_holder_name_snapshot": w.account_holder_name_snapshot,
        "admin_remarks": w.admin_remarks,
        "rejection_reason": w.rejection_reason,
        "reviewed_at": w.reviewed_at,
        "transaction_id": w.transaction_id,
        "transaction_date": w.transaction_date,
        "actual_paid_amount": w.actual_paid_amount,
        "paid_at": w.paid_at,
        "created_at": w.created_at,
        "updated_at": w.updated_at,
    }


# ---------------------------------------------------------------------------
# Phase 3: ADMIN — LIST AGENT WITHDRAWALS
# ---------------------------------------------------------------------------

@router.get(
    "/agents/{agent_profile_id}/withdrawals",
    summary="List withdrawals for an Agent (ADMIN / SUPERADMIN)",
)
def admin_list_agent_withdrawals(
    agent_profile_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    profile = _get_profile_or_404(agent_profile_id, db)
    q = db.query(AgentWithdrawal).filter(AgentWithdrawal.agent_profile_id == profile.id)
    if status_filter:
        q = q.filter(AgentWithdrawal.status == status_filter.upper())
    withdrawals = q.order_by(AgentWithdrawal.created_at.desc()).offset(skip).limit(limit).all()
    return [_serialize_withdrawal(w) for w in withdrawals]


# ---------------------------------------------------------------------------
# Phase 3: ADMIN — GET SPECIFIC WITHDRAWAL
# ---------------------------------------------------------------------------

@router.get(
    "/agents/{agent_profile_id}/withdrawals/{request_id}",
    summary="Get a specific Agent withdrawal (ADMIN / SUPERADMIN)",
)
def admin_get_agent_withdrawal(
    agent_profile_id: int,
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    profile = _get_profile_or_404(agent_profile_id, db)
    w = db.query(AgentWithdrawal).filter(
        AgentWithdrawal.id == request_id,
        AgentWithdrawal.agent_profile_id == profile.id,
    ).first()
    if not w:
        raise HTTPException(status_code=404, detail="Withdrawal request not found for this Agent.")
    return _serialize_withdrawal(w)


# ---------------------------------------------------------------------------
# Phase 3: ADMIN — APPROVE WITHDRAWAL
# ---------------------------------------------------------------------------

@router.patch(
    "/agents/{agent_profile_id}/withdrawals/{request_id}/approve",
    summary="Approve a withdrawal request (ADMIN / SUPERADMIN)",
)
def admin_approve_withdrawal(
    agent_profile_id: int,
    request_id: int,
    data: ApproveWithdrawalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    profile = _get_profile_or_404(agent_profile_id, db)
    w = db.query(AgentWithdrawal).filter(
        AgentWithdrawal.id == request_id,
        AgentWithdrawal.agent_profile_id == profile.id,
    ).with_for_update().first()
    if not w:
        raise HTTPException(status_code=404, detail="Withdrawal request not found for this Agent.")
    if w.status != WithdrawalStatus.PENDING.value:
        raise HTTPException(
            status_code=400,
            detail=f"Only PENDING requests can be approved. Current status: {w.status}",
        )

    prev = w.status
    w.status = WithdrawalStatus.APPROVED.value
    w.admin_remarks = data.admin_remarks
    w.reviewed_by = current_user.id
    w.reviewed_at = datetime.now(timezone.utc)

    try:
        _record_withdrawal_history(
            db, w,
            from_status=prev, to_status=w.status,
            action="APPROVED", actor_id=current_user.id,
            remarks=data.admin_remarks,
        )
        db.commit()
        db.refresh(w)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error while approving withdrawal.")

    return _serialize_withdrawal(w)


# ---------------------------------------------------------------------------
# Phase 3: ADMIN — REJECT WITHDRAWAL
# ---------------------------------------------------------------------------

@router.patch(
    "/agents/{agent_profile_id}/withdrawals/{request_id}/reject",
    summary="Reject a withdrawal request (ADMIN / SUPERADMIN)",
)
def admin_reject_withdrawal(
    agent_profile_id: int,
    request_id: int,
    data: RejectWithdrawalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    profile = _get_profile_or_404(agent_profile_id, db)
    w = db.query(AgentWithdrawal).filter(
        AgentWithdrawal.id == request_id,
        AgentWithdrawal.agent_profile_id == profile.id,
    ).with_for_update().first()
    if not w:
        raise HTTPException(status_code=404, detail="Withdrawal request not found for this Agent.")
    if w.status not in (WithdrawalStatus.PENDING.value, WithdrawalStatus.APPROVED.value):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject a request with status: {w.status}",
        )
    if w.reservation_released:
        raise HTTPException(status_code=400, detail="Reservation already released for this request.")

    prev = w.status
    w.status = WithdrawalStatus.REJECTED.value
    w.rejection_reason = data.rejection_reason
    w.reviewed_by = current_user.id
    w.reviewed_at = datetime.now(timezone.utc)
    w.reservation_released = True   # release reservation exactly once

    try:
        _record_withdrawal_history(
            db, w,
            from_status=prev, to_status=w.status,
            action="REJECTED", actor_id=current_user.id,
            remarks=data.rejection_reason,
        )
        db.commit()
        db.refresh(w)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error while rejecting withdrawal.")

    return _serialize_withdrawal(w)


# ---------------------------------------------------------------------------
# Phase 3: ADMIN — MARK PAID (multipart/form-data)
# ---------------------------------------------------------------------------

@router.patch(
    "/agents/{agent_profile_id}/withdrawals/{request_id}/mark-paid",
    summary="Mark withdrawal as paid — multipart (ADMIN / SUPERADMIN)",
    description=(
        "Requires: transaction_id, transaction_date, actual_paid_amount, payment_proof_image. "
        "Image must be JPEG/PNG/WebP ≤ 5 MB. "
        "Request must be in APPROVED status. "
        "A request already marked PAID cannot be processed again."
    ),
)
def admin_mark_paid(
    agent_profile_id: int,
    request_id: int,
    transaction_id: str = Form(..., max_length=128),
    transaction_date: date = Form(...),
    actual_paid_amount: Decimal = Form(...),
    admin_remarks: Optional[str] = Form(None),
    payment_proof_image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    # 1. Auth + fetch profile and withdrawal
    profile = _get_profile_or_404(agent_profile_id, db)
    w = db.query(AgentWithdrawal).filter(
        AgentWithdrawal.id == request_id,
        AgentWithdrawal.agent_profile_id == profile.id,
    ).with_for_update().first()
    if not w:
        raise HTTPException(status_code=404, detail="Withdrawal request not found for this Agent.")

    # 2. Status guard — must be APPROVED; cannot re-pay
    if w.status == WithdrawalStatus.PAID.value:
        raise HTTPException(status_code=400, detail="This withdrawal has already been marked as paid.")
    if w.status != WithdrawalStatus.APPROVED.value:
        raise HTTPException(
            status_code=400,
            detail=f"Only APPROVED requests can be marked paid. Current status: {w.status}",
        )

    # 3. Validate amount
    if actual_paid_amount <= 0:
        raise HTTPException(status_code=400, detail="actual_paid_amount must be greater than zero.")
    if actual_paid_amount != Decimal(str(w.requested_amount)):
        raise HTTPException(
            status_code=400,
            detail=(
                f"actual_paid_amount ({actual_paid_amount}) must equal "
                f"the approved requested amount ({w.requested_amount})."
            ),
        )

    # 4. Validate transaction_id uniqueness
    if not transaction_id.strip():
        raise HTTPException(status_code=400, detail="transaction_id must not be empty.")
    existing_txn = db.query(AgentWithdrawal).filter(
        AgentWithdrawal.transaction_id == transaction_id,
        AgentWithdrawal.id != w.id,
    ).first()
    if existing_txn:
        raise HTTPException(status_code=409, detail="This transaction_id has already been used.")

    # 5. Validate and upload payment proof image
    ext = payment_proof_image.filename.split(".")[-1].lower() if payment_proof_image.filename else ""
    if ext not in ALLOWED_PROOF_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image format '{ext}'. Allowed: {', '.join(ALLOWED_PROOF_EXTS)}",
        )
    # Check content type too
    ct = (payment_proof_image.content_type or "").lower()
    if ct and not any(ct.startswith(f"image/{x}") for x in ["jpeg", "jpg", "png", "webp"]):
        raise HTTPException(status_code=400, detail=f"Unsupported content type: {ct}")

    # Check file size
    payment_proof_image.file.seek(0, 2)
    file_size = payment_proof_image.file.tell()
    payment_proof_image.file.seek(0)
    if file_size > MAX_PROOF_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Payment proof image exceeds 5 MB limit (size: {file_size // (1024*1024)}MB).",
        )

    # Upload to S3
    proof_url = None
    try:
        proof_url = upload_multipart_file_to_s3(
            payment_proof_image,
            filename_prefix=f"agent-payment-proof/{agent_profile_id}",
            max_size=MAX_PROOF_SIZE,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to upload payment proof image.")

    # 6. Record payment, update status atomically
    prev = w.status
    w.status = WithdrawalStatus.PAID.value
    w.transaction_id = transaction_id
    w.transaction_date = transaction_date
    w.actual_paid_amount = actual_paid_amount
    w.payment_proof_url = proof_url
    w.admin_remarks = admin_remarks
    w.paid_by = current_user.id
    w.paid_at = datetime.now(timezone.utc)
    w.reservation_released = True   # reservation consumed by payment

    try:
        _record_withdrawal_history(
            db, w,
            from_status=prev, to_status=w.status,
            action="PAID", actor_id=current_user.id,
            remarks=admin_remarks,
            transaction_id=transaction_id,
            transaction_date=transaction_date,
            payment_proof_url=proof_url,
            actual_paid_amount=actual_paid_amount,
        )
        db.commit()
        db.refresh(w)
    except IntegrityError:
        db.rollback()
        # Attempt S3 cleanup
        try:
            if proof_url:
                delete_s3_object(proof_url)
        except Exception:
            pass
        raise HTTPException(
            status_code=409,
            detail="Duplicate transaction_id detected. The withdrawal was not marked paid.",
        )
    except SQLAlchemyError:
        db.rollback()
        try:
            if proof_url:
                delete_s3_object(proof_url)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Database error while marking withdrawal as paid.")

    return _serialize_withdrawal(w)


# ---------------------------------------------------------------------------
# Phase 3: ADMIN — GET WITHDRAWAL AUDIT HISTORY
# ---------------------------------------------------------------------------

@router.get(
    "/agents/{agent_profile_id}/withdrawals/{request_id}/history",
    summary="Get withdrawal audit history (ADMIN / SUPERADMIN)",
)
def admin_get_withdrawal_history(
    agent_profile_id: int,
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    profile = _get_profile_or_404(agent_profile_id, db)
    w = db.query(AgentWithdrawal).filter(
        AgentWithdrawal.id == request_id,
        AgentWithdrawal.agent_profile_id == profile.id,
    ).first()
    if not w:
        raise HTTPException(status_code=404, detail="Withdrawal request not found for this Agent.")

    history = db.query(AgentWithdrawalHistory).filter(
        AgentWithdrawalHistory.withdrawal_id == w.id
    ).order_by(AgentWithdrawalHistory.created_at).all()

    return [
        {
            "id": h.id,
            "from_status": h.from_status,
            "to_status": h.to_status,
            "action": h.action,
            "actor_user_id": h.actor_user_id,
            "remarks": h.remarks,
            "transaction_id": h.transaction_id,
            "transaction_date": h.transaction_date,
            "actual_paid_amount": h.actual_paid_amount,
            "created_at": h.created_at,
        }
        for h in history
    ]
