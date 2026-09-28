"""
Wallet routes (school-facing and admin-facing).

School routes:
    GET  /school/wallet                    → own wallet balance
    POST /school/wallet/recharge           → initiate recharge (PENDING)
    GET  /school/wallet/transactions       → own transaction history

Admin routes:
    GET  /admin/wallet/transactions        → all transactions (with filters)
    GET  /admin/schools/{school_id}/wallet → school wallet summary

Recharge config:
    GET   /wallet/recharge-config  → ADMIN, SUPERADMIN, SCHOOL
    PATCH /wallet/recharge-config  → ADMIN, SUPERADMIN
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.billing import (
    SchoolWallet,
    WalletRechargeBonus,
    WalletRechargeConfig,
    WalletTransaction,
    WalletTransactionStatus,
    WalletTransactionType,
)
from app.models.school import School
from app.models.users import User
from app.schemas.billing import (
    AdminWalletResponse,
    RechargeConfigResponse,
    RechargeConfigUpdate,
    RechargeBonusResponse,
    RechargeRequest,
    RechargeResponse,
    WalletResponse,
    WalletTransactionListResponse,
    WalletTransactionResponse,
)
from app.schemas.users import UserRole
from app.services.billing import (
    confirm_wallet_recharge,
    get_active_recharge_config,
    get_or_create_wallet,
    initiate_wallet_recharge,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------


def _normalize_role(role):
    if isinstance(role, UserRole):
        return role
    try:
        return UserRole(str(role))
    except ValueError:
        return None


def _require_admin_or_superadmin(current_user: User = Depends(get_current_user)) -> User:
    if _normalize_role(current_user.role) not in (UserRole.ADMIN, UserRole.SUPERADMIN):
        raise HTTPException(status_code=403, detail="Only Admin or Super Admin can perform this action.")
    return current_user


def _require_school(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    if _normalize_role(current_user.role) != UserRole.SCHOOL:
        raise HTTPException(status_code=403, detail="Only School users can access this resource.")
    return current_user


def _require_admin_superadmin_or_school(
    current_user: User = Depends(get_current_user),
) -> User:
    if _normalize_role(current_user.role) not in (UserRole.ADMIN, UserRole.SUPERADMIN, UserRole.SCHOOL):
        raise HTTPException(status_code=403, detail="Access denied.")
    return current_user


def _get_school_for_user(current_user: User, db: Session) -> School:
    school = db.query(School).filter(School.user_id == current_user.id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School profile not found.")
    return school


# ---------------------------------------------------------------------------
# Recharge Configuration
# ---------------------------------------------------------------------------

@router.get(
    "/recharge-config",
    response_model=RechargeConfigResponse,
    summary="Get Wallet Recharge Configuration",
    tags=["Wallet Recharge Config"],
)
def get_recharge_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin_superadmin_or_school),
):
    """Get the current recharge limits and bonus slabs. Roles: ADMIN, SUPERADMIN, SCHOOL."""
    config = get_active_recharge_config(db)
    if not config:
        # Return defaults if not configured yet
        return RechargeConfigResponse(
            id=0,
            min_recharge_amount=Decimal("500.00"),
            max_recharge_amount=Decimal("20000.00"),
            bonus_configs=[],
        )
    return RechargeConfigResponse(
        id=config.id,
        min_recharge_amount=Decimal(str(config.min_recharge_amount)),
        max_recharge_amount=Decimal(str(config.max_recharge_amount)),
        bonus_configs=[
            RechargeBonusResponse(
                recharge_amount=Decimal(str(b.recharge_amount)),
                bonus_percentage=Decimal(str(b.bonus_percentage)),
            )
            for b in (config.bonus_configs or [])
        ],
        updated_at=config.updated_at,
    )


@router.patch(
    "/recharge-config",
    response_model=RechargeConfigResponse,
    summary="Update Wallet Recharge Configuration",
    tags=["Wallet Recharge Config"],
)
def update_recharge_config(
    payload: RechargeConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin_or_superadmin),
):
    """
    Update recharge limits and bonus slabs. Roles: ADMIN, SUPERADMIN.
    Bonus config rows are replaced atomically (delete + re-insert).
    """
    config = get_active_recharge_config(db)
    if not config:
        config = WalletRechargeConfig(created_by=current_user.id)
        db.add(config)
        db.flush()

    config.min_recharge_amount = payload.min_recharge_amount
    config.max_recharge_amount = payload.max_recharge_amount
    config.updated_by = current_user.id

    # Validate bonus amounts fall within range
    for slab in payload.bonus_configs:
        if slab.recharge_amount < payload.min_recharge_amount or slab.recharge_amount > payload.max_recharge_amount:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_RECHARGE_AMOUNT",
                    "message": f"Bonus recharge_amount {slab.recharge_amount} must be within "
                               f"[{payload.min_recharge_amount}, {payload.max_recharge_amount}].",
                },
            )

    # Replace bonus slabs
    db.query(WalletRechargeBonus).filter(
        WalletRechargeBonus.recharge_config_id == config.id
    ).delete()
    for slab in payload.bonus_configs:
        db.add(WalletRechargeBonus(
            recharge_config_id=config.id,
            recharge_amount=slab.recharge_amount,
            bonus_percentage=slab.bonus_percentage,
        ))

    db.commit()
    db.refresh(config)
    return RechargeConfigResponse(
        id=config.id,
        min_recharge_amount=Decimal(str(config.min_recharge_amount)),
        max_recharge_amount=Decimal(str(config.max_recharge_amount)),
        bonus_configs=[
            RechargeBonusResponse(
                recharge_amount=Decimal(str(b.recharge_amount)),
                bonus_percentage=Decimal(str(b.bonus_percentage)),
            )
            for b in (config.bonus_configs or [])
        ],
        updated_at=config.updated_at,
    )


# ---------------------------------------------------------------------------
# School Wallet
# ---------------------------------------------------------------------------

@router.get(
    "/school/wallet",
    response_model=WalletResponse,
    summary="Get School Wallet Balance",
    tags=["School Wallet"],
)
def get_school_wallet(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_school),
):
    """Get own wallet balance. Roles: SCHOOL."""
    school = _get_school_for_user(current_user, db)
    wallet = get_or_create_wallet(school.id, db)
    db.commit()
    return WalletResponse(
        school_id=wallet.school_id,
        balance=Decimal(str(wallet.balance)),
        currency=wallet.currency,
        updated_at=wallet.updated_at,
    )


@router.post(
    "/school/wallet/recharge",
    response_model=RechargeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate Wallet Recharge",
    tags=["School Wallet"],
)
def recharge_wallet(
    payload: RechargeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_school),
):
    """
    Initiate a wallet recharge. Creates a PENDING transaction.
    Wallet is NOT credited yet — awaiting payment confirmation (future Razorpay integration).

    Roles: SCHOOL.
    """
    school = _get_school_for_user(current_user, db)
    txn, bonus_pct = initiate_wallet_recharge(
        school_id=school.id,
        amount=payload.amount,
        db=db,
        current_user_id=current_user.id,
    )
    db.commit()
    db.refresh(txn)
    return RechargeResponse(
        transaction_id=txn.id,
        requested_amount=Decimal(str(txn.amount)),
        bonus_percentage=bonus_pct,
        bonus_amount=Decimal(str(txn.bonus_amount)),
        total_credit=Decimal(str(txn.total_credit)),
        payment_status=txn.transaction_status,
        payment_provider=txn.payment_provider,
        payment_order_id=txn.payment_order_id,
    )


@router.get(
    "/school/wallet/transactions",
    response_model=WalletTransactionListResponse,
    summary="School Wallet Transaction History",
    tags=["School Wallet"],
)
def get_school_wallet_transactions(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_school),
):
    """
    Get own wallet transaction history with pagination.
    Default: top 10 newest transactions.
    Roles: SCHOOL.
    """
    school = _get_school_for_user(current_user, db)
    q = db.query(WalletTransaction).filter(WalletTransaction.school_id == school.id)
    if date_from:
        q = q.filter(WalletTransaction.created_at >= date_from)
    if date_to:
        q = q.filter(WalletTransaction.created_at <= date_to)

    total = q.count()
    rows = q.order_by(WalletTransaction.created_at.desc()).offset(offset).limit(limit).all()

    items = [_txn_to_response(r) for r in rows]
    return WalletTransactionListResponse(items=items, total=total, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Admin Wallet APIs
# ---------------------------------------------------------------------------

@router.get(
    "/admin/wallet/transactions",
    response_model=WalletTransactionListResponse,
    summary="Admin: List All Wallet Transactions",
    tags=["Admin Wallet"],
)
def admin_list_wallet_transactions(
    school_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    transaction_type: Optional[str] = Query(None),
    transaction_status: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin_or_superadmin),
):
    """
    List all wallet transactions with optional filters.
    Roles: ADMIN, SUPERADMIN.
    """
    q = db.query(WalletTransaction)
    if school_id:
        q = q.filter(WalletTransaction.school_id == school_id)
    if date_from:
        q = q.filter(WalletTransaction.created_at >= date_from)
    if date_to:
        q = q.filter(WalletTransaction.created_at <= date_to)
    if transaction_type:
        q = q.filter(WalletTransaction.transaction_type == transaction_type.upper())
    if transaction_status:
        q = q.filter(WalletTransaction.transaction_status == transaction_status.upper())

    total = q.count()
    rows = q.order_by(WalletTransaction.created_at.desc()).offset(offset).limit(limit).all()
    items = [_txn_to_response(r, include_school_id=True) for r in rows]
    return WalletTransactionListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/admin/schools/{school_id}/wallet",
    response_model=AdminWalletResponse,
    summary="Admin: Get School Wallet Summary",
    tags=["Admin Wallet"],
)
def admin_get_school_wallet(
    school_id: str = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin_or_superadmin),
):
    """
    Get wallet details and aggregated stats for a specific school.
    Roles: ADMIN, SUPERADMIN.
    """
    wallet = db.query(SchoolWallet).filter(SchoolWallet.school_id == school_id).first()
    if not wallet:
        raise HTTPException(
            status_code=404,
            detail={"code": "WALLET_NOT_FOUND", "message": f"No wallet found for school {school_id}."},
        )

    # Aggregate stats from transaction ledger
    def _agg(txn_type: str, status_val: str = WalletTransactionStatus.SUCCESS.value):
        return db.query(
            func.coalesce(func.sum(WalletTransaction.amount), 0)
        ).filter(
            WalletTransaction.school_id == school_id,
            WalletTransaction.transaction_type == txn_type,
            WalletTransaction.transaction_status == status_val,
        ).scalar()

    total_recharged = Decimal(str(
        db.query(func.coalesce(func.sum(WalletTransaction.amount), 0))
        .filter(
            WalletTransaction.school_id == school_id,
            WalletTransaction.transaction_type == WalletTransactionType.RECHARGE.value,
            WalletTransaction.transaction_status == WalletTransactionStatus.SUCCESS.value,
        ).scalar()
    ))
    total_bonus = Decimal(str(
        db.query(func.coalesce(func.sum(WalletTransaction.bonus_amount), 0))
        .filter(
            WalletTransaction.school_id == school_id,
            WalletTransaction.transaction_status == WalletTransactionStatus.SUCCESS.value,
        ).scalar()
    ))
    total_inquiry_raw = db.query(
        func.coalesce(func.sum(WalletTransaction.amount), 0)
    ).filter(
        WalletTransaction.school_id == school_id,
        WalletTransaction.transaction_type == WalletTransactionType.INQUIRY_DEDUCTION.value,
        WalletTransaction.transaction_status == WalletTransactionStatus.SUCCESS.value,
    ).scalar()
    total_inquiry_deduction = abs(Decimal(str(total_inquiry_raw)))

    return AdminWalletResponse(
        school_id=school_id,
        balance=Decimal(str(wallet.balance)),
        total_recharged=total_recharged,
        total_bonus=total_bonus,
        total_inquiry_deduction=total_inquiry_deduction,
        updated_at=wallet.updated_at,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _txn_to_response(txn: WalletTransaction, include_school_id: bool = False) -> WalletTransactionResponse:
    amount = Decimal(str(txn.amount))
    bonus = Decimal(str(txn.bonus_amount))

    # paid_amount: for RECHARGE it's the base amount; for deductions it's 0
    if txn.transaction_type == WalletTransactionType.RECHARGE.value:
        paid_amount = abs(amount)
    else:
        paid_amount = Decimal("0.00")

    return WalletTransactionResponse(
        transaction_id=txn.id,
        school_id=txn.school_id if include_school_id else None,
        transaction_type=txn.transaction_type,
        transaction_status=txn.transaction_status,
        paid_amount=paid_amount,
        bonus_amount=bonus,
        amount=amount,
        balance_before=Decimal(str(txn.balance_before)) if txn.balance_before is not None else None,
        balance_after=Decimal(str(txn.balance_after)) if txn.balance_after is not None else None,
        reference_type=txn.reference_type,
        reference_id=txn.reference_id,
        description=txn.description,
        created_at=txn.created_at,
    )
