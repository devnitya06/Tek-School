"""Agent routes for profiles, configuration, earnings, onboarding and withdrawals.

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

Dashboard statistics:
  GET    /agent/agents/{id}/dashboard-statistics - Agent or admin: profile statistics
  GET    /agent/admin/dashboard-statistics       - Admin: overall Agent statistics
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
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.agent import AgentProfile, StipendType
from app.models.agent_config import (
    AgentEarning,
    AgentEarningStatus,
    AgentEarningType,
    AgentStipendRate,
)
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
    description=(
        "pay_request counts all withdrawal requests regardless of status. "
        "no_of_tasks is zero because no Agent-linked task records exist in the current schema."
    ),
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

    withdrawal_counts = (
        db.query(
            AgentWithdrawal.agent_profile_id.label("agent_profile_id"),
            func.count(AgentWithdrawal.id).label("pay_request"),
        )
        .group_by(AgentWithdrawal.agent_profile_id)
        .subquery()
    )
    rows = (
        query.outerjoin(
            withdrawal_counts,
            withdrawal_counts.c.agent_profile_id == AgentProfile.id,
        )
        .add_columns(withdrawal_counts.c.pay_request)
        .offset(skip)
        .limit(limit)
        .all()
    )
    result = []
    for user, profile, pay_request in rows:
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
            district=profile.district,
            designation=profile.designation,
            no_of_tasks=0,
            pay_request=pay_request or 0,
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


def _stats_period(month: Optional[int], year: Optional[int]):
    if (month is None) != (year is None):
        raise HTTPException(
            status_code=422,
            detail="Both month and year must be provided together.",
        )
    if month is None:
        return None

    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)
    start_at = datetime.combine(start_date, time.min, tzinfo=_AGENT_TIMEZONE)
    end_at = datetime.combine(end_date, time.min, tzinfo=_AGENT_TIMEZONE)
    return start_date, end_date, start_at, end_at


def _earning_date_filter(query, period):
    if period is None:
        return query
    start_date, end_date, start_at, end_at = period
    return query.filter(
        or_(
            and_(
                AgentEarning.earning_date >= start_date,
                AgentEarning.earning_date < end_date,
            ),
            and_(
                AgentEarning.earning_date.is_(None),
                AgentEarning.created_at >= start_at,
                AgentEarning.created_at < end_at,
            ),
        )
    )


@router.get(
    "/agents/{agent_profile_id}/dashboard-statistics",
    summary="Get Agent dashboard statistics",
)
def get_agent_dashboard_statistics(
    agent_profile_id: int,
    month: Optional[int] = Query(default=None, ge=1, le=12),
    year: Optional[int] = Query(default=None, ge=1000, le=9999),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.ADMIN, UserRole.SUPERADMIN, UserRole.AGENT)
    ),
):
    period = _stats_period(month, year)
    if _normalize_role(current_user.role) == UserRole.AGENT:
        own_profile = _get_profile_by_user_or_404(current_user.id, db)
        if own_profile.id != agent_profile_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Agents can only view their own dashboard statistics.",
            )
        profile = own_profile
    else:
        profile = _get_profile_or_404(agent_profile_id, db)

    listings = db.query(func.count(School.id)).filter(
        School.created_by_agent_profile_id == profile.id,
        School.institution_verification_status == _IVS_APPROVED,
    )
    if period is not None:
        start_date, end_date, start_at, end_at = period
        listings = listings.filter(
            or_(
                and_(
                    School.institution_verified_at >= start_at,
                    School.institution_verified_at < end_at,
                ),
                and_(
                    School.institution_verified_at.is_(None),
                    School.created_at >= start_at,
                    School.created_at < end_at,
                ),
            )
        )
    institution_listing = listings.scalar() or 0

    earnings_query = db.query(func.coalesce(func.sum(AgentEarning.amount), 0)).filter(
        AgentEarning.agent_profile_id == profile.id,
        AgentEarning.status == AgentEarningStatus.APPROVED.value,
    )
    net_earnings = Decimal(str(_earning_date_filter(earnings_query, period).scalar() or 0))

    return {
        "agent_profile_id": profile.id,
        "institution_listing": institution_listing,
        "demonstration": 0,
        "field_verification": 0,
        "net_earnings": net_earnings,
        "currency": "INR",
        "month": month,
        "year": year,
        "definitions": {
            "institution_listing": "Approved agent-created schools, counted by approval date.",
            "demonstration": "Zero until Agent-linked demonstration records exist.",
            "field_verification": "Zero until Agent-linked field-verification records exist.",
            "net_earnings": (
                "Sum of APPROVED ledger earnings; withdrawals are not subtracted."
            ),
        },
    }


@router.get(
    "/admin/dashboard-statistics",
    summary="Get overall Agent dashboard statistics (Admin)",
)
def get_admin_agent_dashboard_statistics(
    month: Optional[int] = Query(default=None, ge=1, le=12),
    year: Optional[int] = Query(default=None, ge=1000, le=9999),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    period = _stats_period(month, year)
    agents = (
        db.query(User)
        .join(AgentProfile, AgentProfile.user_id == User.id)
        .filter(User.role == UserRole.AGENT, User.is_deleted.is_(False))
    )
    total_agents = agents.count()
    active_agents = agents.filter(User.is_active.is_(True)).count()
    inactive_agents = total_agents - active_agents

    earnings_query = db.query(func.coalesce(func.sum(AgentEarning.amount), 0)).filter(
        AgentEarning.status == AgentEarningStatus.APPROVED.value,
    )
    agent_earnings = Decimal(str(_earning_date_filter(earnings_query, period).scalar() or 0))

    pending_withdrawals = db.query(
        func.coalesce(func.sum(AgentWithdrawal.requested_amount), 0)
    ).filter(AgentWithdrawal.status == WithdrawalStatus.PENDING.value)
    if period is not None:
        _, _, start_at, end_at = period
        pending_withdrawals = pending_withdrawals.filter(
            AgentWithdrawal.created_at >= start_at,
            AgentWithdrawal.created_at < end_at,
        )
    pending_withdrawal = Decimal(str(pending_withdrawals.scalar() or 0))

    return {
        "total_agents": total_agents,
        "active_agents": active_agents,
        "inactive_agents": inactive_agents,
        "agent_earnings": agent_earnings,
        "pending_withdrawal": pending_withdrawal,
        "currency": "INR",
        "month": month,
        "year": year,
        "definitions": {
            "agent_counts": "Current status counts exclude soft-deleted Agent accounts.",
            "agent_earnings": "Sum of APPROVED ledger entries; paid withdrawals are not expenses.",
            "pending_withdrawal": "Sum of PENDING requests created in the selected period.",
        },
    }


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
        logger.exception(
            "Database error updating agent profile (agent_profile_id=%s)",
            agent_profile_id,
        )
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
        if data.wants_initial_bonus:
            config = db.query(AgentPaymentConfig).filter(
                AgentPaymentConfig.agent_profile_id == profile.id
            ).first()
            if config:
                _issue_initial_bonus_if_eligible(db, profile, config)
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
        "monthly_stipend": {
            "is_enabled": cfg.stipend_monthly_is_enabled,
            "monthly_rate": Decimal(str(cfg.stipend_monthly_rate)),
            "effective_from": cfg.stipend_effective_from,
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
        "effective_from": cfg.effective_from,
        "created_at": cfg.created_at,
        "updated_at": cfg.updated_at,
    }


_AGENT_TIMEZONE = ZoneInfo("Asia/Kolkata")


def _next_stipend_effective_date(today: Optional[date] = None) -> date:
    today = today or datetime.now(_AGENT_TIMEZONE).date()
    if today.month == 12:
        return date(today.year + 1, 1, 1)
    return date(today.year, today.month + 1, 1)


def _save_stipend_rate_snapshot(
    db: Session,
    profile_id: int,
    is_enabled: bool,
    monthly_rate: Decimal,
) -> None:
    effective_date = _next_stipend_effective_date()
    snapshot = (
        db.query(AgentStipendRate)
        .filter(
            AgentStipendRate.agent_profile_id == profile_id,
            AgentStipendRate.effective_from == effective_date,
        )
        .first()
    )
    if snapshot is None:
        snapshot = AgentStipendRate(
            agent_profile_id=profile_id,
            effective_from=effective_date,
        )
        db.add(snapshot)
    snapshot.is_enabled = is_enabled
    snapshot.monthly_rate = monthly_rate


def _issue_initial_bonus_if_eligible(
    db: Session,
    profile: AgentProfile,
    config: AgentPaymentConfig,
) -> bool:
    if not profile.wants_initial_bonus or config.initial_bonus <= 0:
        return False

    bonus_ref = f"agent-{profile.id}"
    existing_bonus = db.query(AgentEarning.id).filter(
        AgentEarning.agent_profile_id == profile.id,
        AgentEarning.earning_type == AgentEarningType.INITIAL_BONUS.value,
        AgentEarning.reference_id == bonus_ref,
    ).first()
    if existing_bonus:
        return False

    now = datetime.now(timezone.utc)
    earning = AgentEarning(
        agent_profile_id=profile.id,
        earning_type=AgentEarningType.INITIAL_BONUS.value,
        status=AgentEarningStatus.APPROVED.value,
        reference_type="agent_consent",
        reference_id=bonus_ref,
        applied_rate=config.initial_bonus,
        amount=config.initial_bonus,
        earning_date=now.date(),
        description="Initial bonus earned after Agent consent.",
        approved_at=now,
    )
    try:
        with db.begin_nested():
            db.add(earning)
            db.flush()
        return True
    except IntegrityError:
        logger.info(
            "[Agent] Duplicate initial bonus prevented for agent_profile_id=%s",
            profile.id,
        )
        return False


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
        stipend_monthly_is_enabled=data.monthly_stipend.is_enabled,
        stipend_monthly_rate=data.monthly_stipend.monthly_rate,
        stipend_effective_from=_next_stipend_effective_date(),
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
        effective_from=datetime.now(timezone.utc),
    )
    try:
        db.add(cfg)
        db.flush()
        _issue_initial_bonus_if_eligible(db, profile, cfg)
        _save_stipend_rate_snapshot(
            db,
            profile.id,
            data.monthly_stipend.is_enabled,
            data.monthly_stipend.monthly_rate,
        )
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
        "created_at is preserved. effective_from is generated by the backend. "
        "Monthly stipend rates become effective on the first day of the next calendar month. "
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
    ).with_for_update().first()
    if not cfg:
        raise HTTPException(
            status_code=404,
            detail="No configuration found for this Agent. Use POST to create one.",
        )

    # Apply updates — is_bonus_withdrawn is intentionally excluded
    cfg.idp_is_enabled = data.institution_digital_profile.is_enabled
    cfg.idp_rate = data.institution_digital_profile.rate
    cfg.stipend_monthly_is_enabled = data.monthly_stipend.is_enabled
    cfg.stipend_monthly_rate = data.monthly_stipend.monthly_rate
    cfg.stipend_effective_from = _next_stipend_effective_date()
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
    cfg.effective_from = datetime.now(timezone.utc)
    # created_at is never touched — preserved by the ORM

    try:
        _issue_initial_bonus_if_eligible(db, profile, cfg)
        _save_stipend_rate_snapshot(
            db,
            profile.id,
            data.monthly_stipend.is_enabled,
            data.monthly_stipend.monthly_rate,
        )
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


# ===========================================================================
# Phase 4 — Agent Institution Digital Profile
# ===========================================================================

# ---------------------------------------------------------------------------
# Imports (phase-4 specific)
# ---------------------------------------------------------------------------
from datetime import date as _date
from decimal import Decimal as _Decimal

from app.models.school import School, SchoolInfo, SchoolClassFee
from app.models.admin import FAQ, school_faqs
from app.schemas.school import (
    AgentSchoolCreateRequest,
    AgentSchoolDetailResponse,
    AgentSchoolListItem,
    AgentSchoolSubmitRequest,
    InstitutionApproveRequest,
    InstitutionRejectRequest,
    InstitutionVerificationListItem,
)

# Statuses used in the institution lifecycle
_IVS_DRAFT = "DRAFT"
_IVS_PENDING = "PENDING"
_IVS_APPROVED = "APPROVED"
_IVS_REJECTED = "REJECTED"

# Fields Agents may NOT modify on the school profile (immutable / admin-only)
_AGENT_FORBIDDEN_SCHOOL_FIELDS = {
    "created_by_role", "created_by_user_id", "created_by_name",
    "created_by_agent_profile_id",
    "institution_verification_status",
    "institution_submitted_at", "institution_submitted_by_agent_id",
    "institution_verified_by", "institution_verified_at",
    "institution_rejection_reason", "is_verified", "is_business_approved",
    "is_promotion_pending", "created_by_admin", "user_id", "id",
    "confirms_educational_institution", "confirms_contact_information",
    "confirmation_educational_at", "confirmation_contact_at",
}


# ---------------------------------------------------------------------------
# Phase-4 helpers
# ---------------------------------------------------------------------------

def _resolve_agent_for_phase4(current_user: User, db: Session):
    """Return (agent_profile, payment_config).  Raises 403 if not eligible."""
    if current_user.role != UserRole.AGENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only AGENT accounts can access institution digital profile features.",
        )
    profile = db.query(AgentProfile).filter(AgentProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Agent profile not found.")

    config = db.query(AgentPaymentConfig).filter(
        AgentPaymentConfig.agent_profile_id == profile.id
    ).first()
    if not config or not config.idp_is_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Agent school onboarding is not enabled for your account. "
                "Contact your administrator."
            ),
        )
    return profile, config


def _get_agent_school_or_403(school_id: str, agent_profile: AgentProfile, db: Session) -> School:
    """Return the school only if it belongs to this agent.  Raises 403/404 otherwise."""
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="Institution not found.")
    if school.created_by_agent_profile_id != agent_profile.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this institution.",
        )
    return school


def _assert_agent_school_editable(school: School):
    """Raise 403 if the school is in PENDING/APPROVED state (read-only to agent)."""
    if school.institution_verification_status in (_IVS_PENDING, _IVS_APPROVED):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Institution is currently in '{school.institution_verification_status}' status "
                "and cannot be edited by the Agent."
            ),
        )


def _serialize_school_for_agent(school: School) -> dict:
    return {
        "school_id": school.id,
        "school_name": school.school_name,
        "school_email": school.school_email,
        "school_phone": school.school_phone,
        "city": school.city,
        "district": school.district,
        "state": school.state,
        "pin_code": school.pin_code,
        "country": school.country,
        "school_board": school.school_board.value if hasattr(school.school_board, "value") else school.school_board,
        "school_type": school.school_type.value if hasattr(school.school_type, "value") else school.school_type,
        "institution_categories": school.institution_categories,
        "principal_name": school.principal_name,
        "location": school.school_location,
        "website": school.school_website,
        "confirms_educational_institution": school.confirms_educational_institution,
        "confirms_contact_information": school.confirms_contact_information,
        "institution_verification_status": school.institution_verification_status,
        "institution_submitted_at": school.institution_submitted_at,
        "institution_verified_at": school.institution_verified_at,
        "institution_rejection_reason": school.institution_rejection_reason,
        "created_by_role": school.created_by_role,
        "created_by_name": school.created_by_name,
        "created_at": school.created_at,
    }


def _apply_institution_submission_confirmations(
    school: School, data: AgentSchoolSubmitRequest, submitted_at: datetime
) -> None:
    school.confirms_educational_institution = data.confirms_educational_institution
    school.confirms_contact_information = data.confirms_contact_information
    school.confirmation_educational_at = submitted_at
    school.confirmation_contact_at = submitted_at


# ---------------------------------------------------------------------------
# Phase 4: AGENT — Create Institution
# ---------------------------------------------------------------------------

@router.post(
    "/institutions/",
    status_code=status.HTTP_201_CREATED,
    summary="Phase 4 — Agent creates an institution for digital profile",
    description=(
        "Creates a school record owned by the authenticated Agent with "
        "institution_verification_status = DRAFT. Confirmation declarations "
        "are collected when the completed institution is submitted for "
        "verification. Requires idp_is_enabled."
    ),
)
def agent_create_institution(
    data: AgentSchoolCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.AGENT)),
):
    agent_profile, config = _resolve_agent_for_phase4(current_user, db)
    if not config.idp_is_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Institution Digital Profile feature is not enabled for your account.",
        )

    # ── Duplicate email check ────────────────────────────────────────────────
    existing_user = db.query(User).filter(User.email == data.school_email.strip().lower()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user account with this email already exists.",
        )

    try:
        # Create a school-role user with a system-generated password
        plain_password = generate_password(prefix=data.school_name)
        school_user = User(
            name=data.school_name,
            email=data.school_email.strip().lower(),
            phone=data.school_phone.strip(),
            role=UserRole.SCHOOL,
            hashed_password=get_password_hash(plain_password),
            is_verified=False,
            is_active=True,
        )
        db.add(school_user)
        db.flush()

        creator_full_name = f"{agent_profile.first_name} {agent_profile.last_name}".strip()
        school = School(
            user_id=school_user.id,
            school_name=data.school_name,
            school_email=data.school_email.strip().lower(),
            school_phone=data.school_phone.strip(),
            school_website=data.website,
            school_location=data.location,
            district=data.district,
            state=data.state,
            pin_code=data.pin_code,
            block_division=data.block_division,
            country=data.country or "India",
            institution_categories=data.institution_categories,
            principal_name=data.principal_name,
            principal_phone=data.principal_phone,
            principal_email=data.principal_email,
            account_type="listing",
            is_verified=False,
            is_business_approved=False,
            default_settlement_channel="cash_offline",
            created_by_admin=False,
            followup_enabled=False,
            followup_status="inactive",
            # Phase 4 creator tracking (captured server-side — never from client)
            created_by_role="agent",
            created_by_user_id=current_user.id,
            created_by_name=creator_full_name,
            created_by_agent_profile_id=agent_profile.id,
            # Confirmations
            confirms_educational_institution=False,
            confirms_contact_information=False,
            # Verification lifecycle — starts as DRAFT
            institution_verification_status=_IVS_DRAFT,
        )
        db.add(school)
        db.commit()
        db.refresh(school)

    except IntegrityError as exc:
        db.rollback()
        msg = str(exc).lower()
        if "email" in msg or "unique" in msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Duplicate registration: an institution with this email already exists.",
            )
        raise HTTPException(status_code=400, detail="Could not create institution. Check input data.")
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error while creating institution.")

    return {
        "detail": "Institution registered successfully as DRAFT.",
        "school_id": school.id,
        "institution_verification_status": school.institution_verification_status,
        "confirms_educational_institution": school.confirms_educational_institution,
        "confirms_contact_information": school.confirms_contact_information,
        "created_by_agent_profile_id": agent_profile.id,
    }


# ---------------------------------------------------------------------------
# Phase 4: AGENT — List Own Institutions
# ---------------------------------------------------------------------------

@router.get(
    "/institutions/",
    summary="Phase 4 — Agent lists own institutions",
    description="Returns all institutions created by the authenticated Agent.",
)
def agent_list_institutions(
    status_filter: Optional[str] = Query(None, description="Filter by verification status: DRAFT, PENDING, APPROVED, REJECTED"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.AGENT)),
):
    agent_profile, _config = _resolve_agent_for_phase4(current_user, db)

    q = db.query(School).filter(School.created_by_agent_profile_id == agent_profile.id)
    if status_filter:
        q = q.filter(School.institution_verification_status == status_filter.upper())
    q = q.order_by(School.created_at.desc())
    total = q.count()
    schools = q.offset(skip).limit(limit).all()

    return {
        "total": total,
        "items": [_serialize_school_for_agent(s) for s in schools],
    }


# ---------------------------------------------------------------------------
# Phase 4: AGENT — Get Institution Detail
# ---------------------------------------------------------------------------

@router.get(
    "/institutions/{school_id}",
    summary="Phase 4 — Agent views an institution detail",
)
def agent_get_institution(
    school_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.AGENT)),
):
    agent_profile, _config = _resolve_agent_for_phase4(current_user, db)
    school = _get_agent_school_or_403(school_id, agent_profile, db)
    return _serialize_school_for_agent(school)


# ---------------------------------------------------------------------------
# Phase 4: AGENT — Submit Institution for Verification (DRAFT → PENDING)
# ---------------------------------------------------------------------------

@router.post(
    "/institutions/submit",
    summary="Phase 4 — Agent submits institution for Admin verification",
    description=(
        "Records both agent confirmations and moves institution from DRAFT "
        "to PENDING. Once submitted the Agent cannot edit the school until it "
        "is reviewed. Duplicate submission is prevented."
    ),
)
def agent_submit_institution(
    data: AgentSchoolSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.AGENT)),
):
    agent_profile, config = _resolve_agent_for_phase4(current_user, db)
    school = _get_agent_school_or_403(data.school_id, agent_profile, db)
    if not config.idp_is_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The feature used to create this institution is no longer enabled.",
        )

    # Only DRAFT can be submitted
    if school.institution_verification_status != _IVS_DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Institution is in '{school.institution_verification_status}' status. "
                "Only DRAFT institutions can be submitted for verification."
            ),
        )

    now = datetime.now(timezone.utc)
    _apply_institution_submission_confirmations(school, data, now)
    school.institution_verification_status = _IVS_PENDING
    school.institution_submitted_at = now
    school.institution_submitted_by_agent_id = agent_profile.id

    try:
        db.commit()
        db.refresh(school)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error while submitting institution.")

    return {
        "detail": "Institution submitted for verification.",
        "school_id": school.id,
        "institution_verification_status": school.institution_verification_status,
        "institution_submitted_at": school.institution_submitted_at,
    }



# ---------------------------------------------------------------------------
# NOTE — Removed duplicate routes (now handled by existing /school/ endpoints)
# ---------------------------------------------------------------------------
# The following operations are now performed through the existing school APIs
# (updated to also accept UserRole.AGENT with ownership & editability guards):
#
#   PATCH /school/school-profile?school_id=SCH-xxx  — update profile (DRAFT only)
#   POST  /school/school-info/?school_id=SCH-xxx    — create school info
#   PUT   /school/school-info/{id}/                 — update school info
#   DELETE /school/school-info/{id}/                — delete school info
#   GET   /school/school-info/?school_id=SCH-xxx    — list school info (public)
#   POST  /school/class-fees/?school_id=SCH-xxx     — create class fee
#   PUT   /school/class-fees/{id}/                  — update class fee
#   DELETE /school/class-fees/{id}/                 — delete class fee
#   GET   /school/class-fees/?school_id=SCH-xxx     — list class fees (public)
#   POST  /school/faqs/select?school_id=SCH-xxx     — select FAQs (DRAFT only)
#   GET   /admin/faqs/?is_active=true               — browse FAQ catalogue
# ---------------------------------------------------------------------------



# ===========================================================================
# Phase 4 — Admin/SuperAdmin Institution Verification
# ===========================================================================

@router.get(
    "/admin/institutions/pending",
    summary="Phase 4 — Admin: list institutions pending verification",
)
def admin_list_pending_institutions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    agent_profile_id: Optional[int] = Query(None, description="Filter by agent profile ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    """Returns all agent-created institutions currently in PENDING status."""
    q = db.query(School).filter(
        School.institution_verification_status == _IVS_PENDING,
        School.created_by_agent_profile_id.isnot(None),
    )
    if agent_profile_id:
        q = q.filter(School.created_by_agent_profile_id == agent_profile_id)

    total = q.count()
    schools = q.order_by(School.institution_submitted_at.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "items": [
            {
                "school_id": s.id,
                "school_name": s.school_name,
                "school_email": s.school_email,
                "school_phone": s.school_phone,
                "district": s.district,
                "state": s.state,
                "institution_verification_status": s.institution_verification_status,
                "institution_submitted_at": s.institution_submitted_at,
                "created_by_role": s.created_by_role,
                "created_by_name": s.created_by_name,
                "created_by_agent_profile_id": s.created_by_agent_profile_id,
                "confirms_educational_institution": s.confirms_educational_institution,
                "confirms_contact_information": s.confirms_contact_information,
                "created_at": s.created_at,
            }
            for s in schools
        ],
    }


@router.get(
    "/admin/institutions/{school_id}",
    summary="Phase 4 — Admin: get complete institution registration",
)
def admin_get_institution_detail(
    school_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="Institution not found.")

    # Resolve agent details if applicable
    agent_info = None
    if school.created_by_agent_profile_id:
        ap = db.query(AgentProfile).filter(AgentProfile.id == school.created_by_agent_profile_id).first()
        if ap:
            agent_info = {
                "agent_profile_id": ap.id,
                "agent_id": ap.agent_id,
                "agent_name": f"{ap.first_name} {ap.last_name}".strip(),
                "agent_phone": ap.phone,
                "agent_email": ap.email,
            }

    return {
        "school_id": school.id,
        "school_name": school.school_name,
        "school_email": school.school_email,
        "school_phone": school.school_phone,
        "district": school.district,
        "state": school.state,
        "pin_code": school.pin_code,
        "country": school.country,
        "school_board": school.school_board.value if hasattr(school.school_board, "value") else school.school_board,
        "school_type": school.school_type.value if hasattr(school.school_type, "value") else school.school_type,
        "institution_categories": school.institution_categories,
        "principal_name": school.principal_name,
        # Confirmations
        "confirms_educational_institution": school.confirms_educational_institution,
        "confirms_contact_information": school.confirms_contact_information,
        "confirmation_educational_at": school.confirmation_educational_at,
        "confirmation_contact_at": school.confirmation_contact_at,
        # Lifecycle
        "institution_verification_status": school.institution_verification_status,
        "institution_submitted_at": school.institution_submitted_at,
        "institution_submitted_by_agent_id": school.institution_submitted_by_agent_id,
        "institution_verified_by": school.institution_verified_by,
        "institution_verified_at": school.institution_verified_at,
        "institution_rejection_reason": school.institution_rejection_reason,
        # Creator
        "created_by_role": school.created_by_role,
        "created_by_name": school.created_by_name,
        "created_by_user_id": school.created_by_user_id,
        "created_by_agent_profile_id": school.created_by_agent_profile_id,
        "agent_info": agent_info,
        "created_at": school.created_at,
    }


@router.patch(
    "/admin/institutions/{school_id}/approve",
    summary="Phase 4 — Admin: approve a PENDING institution & trigger Agent earning",
)
def admin_approve_institution(
    school_id: str,
    data: InstitutionApproveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    """
    Approves a PENDING institution.

    Security rules:
    - Only ADMIN / SUPERADMIN.
    - Institution must exist and be PENDING.
    - Creates exactly one AgentEarning (duplicate-safe via UNIQUE constraint).
    - Earning is at the rate configured at approval time.
    - If idp_is_enabled is False or rate is zero at approval time, logs it but
      does not create an earning.
    """
    school = db.query(School).filter(School.id == school_id).with_for_update().first()
    if not school:
        raise HTTPException(status_code=404, detail="Institution not found.")

    if school.institution_verification_status != _IVS_PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Institution is in '{school.institution_verification_status}' status. "
                "Only PENDING institutions can be approved."
            ),
        )

    # Prevent agent self-approval (extra guard)
    if school.created_by_user_id and school.created_by_user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An Agent cannot approve their own institution.",
        )

    now = datetime.now(timezone.utc)
    school.institution_verification_status = _IVS_APPROVED
    school.institution_verified_by = current_user.id
    school.institution_verified_at = now
    school.is_verified = True

    earning_created = False
    earning_id = None

    # ── Trigger Agent earning ────────────────────────────────────────────────
    if school.created_by_agent_profile_id:
        agent_profile = db.query(AgentProfile).filter(
            AgentProfile.id == school.created_by_agent_profile_id
        ).first()
        if agent_profile:
            config = db.query(AgentPaymentConfig).filter(
                AgentPaymentConfig.agent_profile_id == agent_profile.id
            ).first()

            if (
                config
                and config.idp_is_enabled
                and config.idp_rate
                and config.idp_rate > 0
            ):
                rate = _Decimal(str(config.idp_rate))
                earning = AgentEarning(
                    agent_profile_id=agent_profile.id,
                    earning_type=AgentEarningType.INSTITUTION_DIGITAL_PROFILE.value,
                    status=AgentEarningStatus.APPROVED.value,
                    reference_type="school",
                    reference_id=school.id,          # unique per school — prevents duplicates
                    applied_rate=rate,
                    amount=rate,
                    earning_date=now.date(),
                    description=(
                        f"Institution Digital Profile approved: {school.school_name} "
                        f"({school.id}) — Rate: {rate}"
                    ),
                    approved_at=now,
                    approved_by=current_user.id,
                )
                db.add(earning)
                try:
                    db.flush()  # flush to catch UNIQUE constraint before full commit
                    earning_id = earning.id
                    earning_created = True
                except IntegrityError:
                    # Duplicate earning — idempotent, do not raise
                    db.rollback()
                    db.add(school)
                    school.institution_verification_status = _IVS_APPROVED
                    school.institution_verified_by = current_user.id
                    school.institution_verified_at = now
                    school.is_verified = True
                    logger.warning(
                        "[Phase4] Duplicate earning prevented for school=%s agent=%s",
                        school.id, agent_profile.id,
                    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "uq_agent_earning_type_ref" in str(exc):
            # Earning already exists — school approval still goes through
            school_obj = db.query(School).filter(School.id == school_id).first()
            if school_obj:
                school_obj.institution_verification_status = _IVS_APPROVED
                school_obj.institution_verified_by = current_user.id
                school_obj.institution_verified_at = now
                school_obj.is_verified = True
                db.commit()
            return {
                "detail": "Institution approved. Earning already existed (idempotent).",
                "school_id": school_id,
                "institution_verification_status": _IVS_APPROVED,
                "earning_created": False,
            }
        raise HTTPException(status_code=500, detail=f"Database error during approval: {exc}")
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error while approving institution.")

    return {
        "detail": "Institution approved successfully.",
        "school_id": school_id,
        "institution_verification_status": _IVS_APPROVED,
        "institution_verified_at": now,
        "earning_created": earning_created,
        "earning_id": earning_id,
    }


@router.patch(
    "/admin/institutions/{school_id}/reject",
    summary="Phase 4 — Admin: reject a PENDING institution",
)
def admin_reject_institution(
    school_id: str,
    data: InstitutionRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    """
    Rejects a PENDING institution.

    - Requires a rejection_reason (min 5 chars).
    - No Agent earning is created.
    - Sets institution_verification_status = REJECTED.
    - Agent cannot bypass rejection by resubmitting the same record.
    """
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="Institution not found.")

    if school.institution_verification_status != _IVS_PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Institution is in '{school.institution_verification_status}' status. "
                "Only PENDING institutions can be rejected."
            ),
        )

    now = datetime.now(timezone.utc)
    school.institution_verification_status = _IVS_REJECTED
    school.institution_verified_by = current_user.id
    school.institution_verified_at = now
    school.institution_rejection_reason = data.rejection_reason.strip()

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error while rejecting institution.")

    return {
        "detail": "Institution rejected.",
        "school_id": school_id,
        "institution_verification_status": _IVS_REJECTED,
        "institution_rejection_reason": school.institution_rejection_reason,
        "institution_verified_at": now,
        "earning_created": False,
    }


@router.get(
    "/admin/institutions/",
    summary="Phase 4 — Admin: list all agent-created institutions with filters",
)
def admin_list_institutions(
    verification_status: Optional[str] = Query(None, description="DRAFT, PENDING, APPROVED, REJECTED"),
    agent_profile_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    q = db.query(School).filter(School.created_by_agent_profile_id.isnot(None))
    if verification_status:
        q = q.filter(School.institution_verification_status == verification_status.upper())
    if agent_profile_id:
        q = q.filter(School.created_by_agent_profile_id == agent_profile_id)

    total = q.count()
    schools = q.order_by(School.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "items": [
            {
                "school_id": s.id,
                "school_name": s.school_name,
                "school_email": s.school_email,
                "school_phone": s.school_phone,
                "district": s.district,
                "state": s.state,
                "institution_verification_status": s.institution_verification_status,
                "institution_submitted_at": s.institution_submitted_at,
                "institution_verified_at": s.institution_verified_at,
                "created_by_role": s.created_by_role,
                "created_by_name": s.created_by_name,
                "created_by_agent_profile_id": s.created_by_agent_profile_id,
                "created_at": s.created_at,
            }
            for s in schools
        ],
    }
