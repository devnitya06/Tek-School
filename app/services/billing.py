"""
Billing service: pricing calculations, wallet operations, inquiry billing.

Design principles:
- All money uses Decimal (never float).
- Wallet deductions happen inside a single DB transaction with row-level locking.
- Viewer numbering is atomic (SELECT … FOR UPDATE on wallet row).
- Historical prices are never recalculated after first view.
- Razorpay-ready: recharge creates PENDING transaction; wallet is only credited
  after confirmed payment. Future integration only needs to add:
    1. create_razorpay_order() call in recharge_wallet()
    2. POST /school/wallet/recharge/verify + POST /webhooks/payment/razorpay
       that call confirm_wallet_recharge() below.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.billing import (
    BusinessInquirySchool,
    DigitalProfilePriceConfig,
    SchoolWallet,
    WalletRechargeBonus,
    WalletRechargeConfig,
    WalletTransaction,
    WalletTransactionStatus,
    WalletTransactionType,
)
from app.models.school import BusinessInquiry, School


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _get_school(user_id: int, db: Session) -> School:
    school = db.query(School).filter(School.user_id == user_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School profile not found.")
    return school


# ---------------------------------------------------------------------------
# Price Configuration
# ---------------------------------------------------------------------------

def calculate_applicable_price(
    viewer_number: int,
    config: DigitalProfilePriceConfig,
) -> Decimal:
    """
    Viewer 1-2   → first_two_viewer_price
    Viewer 3-7   → next_five_viewer_price
    Viewer 8+    → all_other_viewer_price
    """
    if viewer_number <= 2:
        return Decimal(str(config.first_two_viewer_price))
    if viewer_number <= 7:
        return Decimal(str(config.next_five_viewer_price))
    return Decimal(str(config.all_other_viewer_price))


def get_price_config_for_school(school: School, db: Session) -> Optional[DigitalProfilePriceConfig]:
    """
    Find the best matching pricing config for a school.
    Matching order:
      1. Exact match on school_board → education_associate
      2. Fall back to first available config
    """
    # Map school board to education associate for best-effort matching
    board_to_associate = {
        "cbse": "SCHOOL_EDUCATIONS",
        "icse": "SCHOOL_EDUCATIONS",
        "cisce": "SCHOOL_EDUCATIONS",
        "stateboard": "SCHOOL_EDUCATIONS",
        "cambridge": "SCHOOL_EDUCATIONS",
        "ib": "SCHOOL_EDUCATIONS",
        "nios": "SCHOOL_EDUCATIONS",
        "pre_board_education": "SCHOOL_EDUCATIONS",
        "other": "SCHOOL_EDUCATIONS",
        "higher_education": "HIGHER_EDUCATION",
        "professional_education": "PROFESSIONAL_EDUCATION",
        "medical_pharma": "MEDICAL_PHARMA",
        "university": "UNIVERSITY",
        "training_coaching": "TRAINING_COACHING",
        "creative_training": "CREATIVE_TRAINING",
    }

    school_board_val = None
    if school.school_board:
        board_str = str(school.school_board)
        # SchoolBoard is a TypeDecorator — extract value string
        if hasattr(school.school_board, "value"):
            board_str = school.school_board.value
        school_board_val = board_str.lower()

    associate = board_to_associate.get(school_board_val or "") if school_board_val else None

    if associate:
        config = (
            db.query(DigitalProfilePriceConfig)
            .filter(DigitalProfilePriceConfig.education_associate == associate)
            .order_by(DigitalProfilePriceConfig.updated_at.desc())
            .first()
        )
        if config:
            return config

    # Fall back to any available config
    return db.query(DigitalProfilePriceConfig).order_by(DigitalProfilePriceConfig.updated_at.desc()).first()


# ---------------------------------------------------------------------------
# Wallet — Get or Create
# ---------------------------------------------------------------------------

def get_or_create_wallet(school_id: str, db: Session) -> SchoolWallet:
    """Return the wallet for a school; create with 0 balance if missing."""
    wallet = db.query(SchoolWallet).filter(SchoolWallet.school_id == school_id).first()
    if not wallet:
        wallet = SchoolWallet(school_id=school_id, balance=Decimal("0.00"), currency="INR")
        db.add(wallet)
        db.flush()
    return wallet


# ---------------------------------------------------------------------------
# Recharge Configuration
# ---------------------------------------------------------------------------

def get_active_recharge_config(db: Session) -> Optional[WalletRechargeConfig]:
    """Return the first (and only) recharge config row."""
    return db.query(WalletRechargeConfig).order_by(WalletRechargeConfig.id).first()


def calculate_recharge_bonus(amount: Decimal, config: WalletRechargeConfig) -> Tuple[Decimal, Decimal]:
    """
    Returns (bonus_percentage, bonus_amount) for the given recharge amount.
    Matches the slab whose recharge_amount == requested amount exactly.
    If no match, bonus is 0.
    """
    bonus_pct = Decimal("0.00")
    for slab in config.bonus_configs:
        if Decimal(str(slab.recharge_amount)) == amount:
            bonus_pct = Decimal(str(slab.bonus_percentage))
            break
    bonus_amount = (amount * bonus_pct / Decimal("100")).quantize(Decimal("0.01"))
    return bonus_pct, bonus_amount


# ---------------------------------------------------------------------------
# Wallet Recharge (PENDING — Razorpay not yet integrated)
# ---------------------------------------------------------------------------

def initiate_wallet_recharge(
    school_id: str,
    amount: Decimal,
    db: Session,
    current_user_id: int,
) -> WalletTransaction:
    """
    Create a PENDING recharge transaction.
    Does NOT credit the wallet — wallet is only credited after payment confirmation.

    Future Razorpay integration:
      - After creating txn, call razorpay_client.order.create() here.
      - Save payment_provider="RAZORPAY", payment_order_id=order["id"].
      - Return the Razorpay order details to the frontend.
    """
    config = get_active_recharge_config(db)
    if not config:
        raise HTTPException(status_code=404, detail="Recharge configuration not found.")

    min_amt = Decimal(str(config.min_recharge_amount))
    max_amt = Decimal(str(config.max_recharge_amount))

    if amount < min_amt or amount > max_amt:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_RECHARGE_AMOUNT",
                "message": f"Recharge amount must be between ₹{min_amt} and ₹{max_amt}.",
                "min_amount": float(min_amt),
                "max_amount": float(max_amt),
            },
        )

    bonus_pct, bonus_amount = calculate_recharge_bonus(amount, config)
    total_credit = (amount + bonus_amount).quantize(Decimal("0.01"))

    txn = WalletTransaction(
        school_id=school_id,
        transaction_type=WalletTransactionType.RECHARGE.value,
        transaction_status=WalletTransactionStatus.PENDING.value,
        amount=amount,
        bonus_amount=bonus_amount,
        total_credit=total_credit,
        currency="INR",
        description=f"Wallet recharge request for ₹{amount}",
        # Razorpay fields — null until integrated
        payment_provider=None,
        payment_order_id=None,
        payment_payment_id=None,
        payment_signature=None,
    )
    db.add(txn)
    db.flush()
    return txn, bonus_pct


def confirm_wallet_recharge(
    transaction_id: int,
    db: Session,
    payment_provider: Optional[str] = None,
    payment_payment_id: Optional[str] = None,
    payment_signature: Optional[str] = None,
) -> WalletTransaction:
    """
    Confirm a PENDING recharge and credit the wallet.
    Call this from the Razorpay webhook / verify endpoint.

    Guards against double-credit:
    - Uses SELECT … FOR UPDATE on the transaction row.
    - Validates PENDING → SUCCESS transition only.
    """
    # Lock the transaction row
    txn = (
        db.query(WalletTransaction)
        .filter(WalletTransaction.id == transaction_id)
        .with_for_update()
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    if txn.transaction_status != WalletTransactionStatus.PENDING.value:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "INVALID_TRANSACTION_STATE",
                "message": f"Transaction is already in state '{txn.transaction_status}'. Cannot re-confirm.",
            },
        )

    # Lock and update wallet
    wallet = (
        db.query(SchoolWallet)
        .filter(SchoolWallet.school_id == txn.school_id)
        .with_for_update()
        .first()
    )
    if not wallet:
        wallet = SchoolWallet(school_id=txn.school_id, balance=Decimal("0.00"), currency="INR")
        db.add(wallet)
        db.flush()

    balance_before = Decimal(str(wallet.balance))
    balance_after = (balance_before + Decimal(str(txn.total_credit))).quantize(Decimal("0.01"))

    wallet.balance = balance_after

    txn.transaction_status = WalletTransactionStatus.SUCCESS.value
    txn.balance_before = balance_before
    txn.balance_after = balance_after
    if payment_provider:
        txn.payment_provider = payment_provider
    if payment_payment_id:
        txn.payment_payment_id = payment_payment_id
    if payment_signature:
        txn.payment_signature = payment_signature

    db.flush()
    return txn


# ---------------------------------------------------------------------------
# Business Inquiry School Junction — Seed rows
# ---------------------------------------------------------------------------

def seed_inquiry_school_rows(inquiry_id: int, school_ids: list, db: Session) -> None:
    """
    Create one BusinessInquirySchool row per school_id for a new BusinessInquiry.
    Idempotent: skips if row already exists (shouldn't happen in practice).
    """
    for sid in school_ids:
        existing = (
            db.query(BusinessInquirySchool)
            .filter(
                BusinessInquirySchool.business_inquiry_id == inquiry_id,
                BusinessInquirySchool.school_id == sid,
            )
            .first()
        )
        if not existing:
            row = BusinessInquirySchool(
                business_inquiry_id=inquiry_id,
                school_id=sid,
                is_seen=False,
                amount_deducted=Decimal("0.00"),
            )
            db.add(row)


# ---------------------------------------------------------------------------
# Business Inquiry Viewer Count (per school)
# ---------------------------------------------------------------------------

def get_school_viewer_count(school_id: str, db: Session) -> int:
    """
    Count total successfully-charged inquiry views for this school.
    This determines the viewer_number for the NEXT view.
    Only counts is_seen=True rows (successfully charged).
    """
    count = (
        db.query(func.count(BusinessInquirySchool.id))
        .filter(
            BusinessInquirySchool.school_id == school_id,
            BusinessInquirySchool.is_seen == True,  # noqa: E712
        )
        .scalar()
    )
    return count or 0


# ---------------------------------------------------------------------------
# Business Inquiry — Calculate applicable price
# ---------------------------------------------------------------------------

def calculate_inquiry_view_price(
    school_id: str,
    school: School,
    db: Session,
) -> Tuple[int, Decimal, Optional[DigitalProfilePriceConfig]]:
    """
    Returns (next_viewer_number, applicable_price, config_used).
    Does NOT deduct anything.
    """
    config = get_price_config_for_school(school, db)
    if not config:
        # No config found — charge 0 (free access)
        viewer_count = get_school_viewer_count(school_id, db)
        return viewer_count + 1, Decimal("0.00"), None

    viewer_count = get_school_viewer_count(school_id, db)
    next_viewer_number = viewer_count + 1
    price = calculate_applicable_price(next_viewer_number, config)
    return next_viewer_number, price, config


# ---------------------------------------------------------------------------
# Business Inquiry — Atomic View + Deduction
# ---------------------------------------------------------------------------

def view_business_inquiry(
    inquiry_id: int,
    school_id: str,
    school: School,
    db: Session,
) -> Tuple[BusinessInquiry, BusinessInquirySchool]:
    """
    Atomic flow:
      1. Find inquiry + validate school membership.
      2. Find/get BusinessInquirySchool junction row.
      3. If already seen → return stored data, no charge.
      4. Lock wallet row (FOR UPDATE).
      5. Determine viewer number + price.
      6. Check balance — raise 402 if insufficient.
      7. Deduct wallet.
      8. Create WalletTransaction (SUCCESS, INQUIRY_DEDUCTION).
      9. Update BusinessInquirySchool: is_seen=True, viewer_number, price_per_view, etc.
     10. Commit is handled by the caller.
    """
    # Step 1: Fetch inquiry
    inquiry = (
        db.query(BusinessInquiry)
        .filter(
            BusinessInquiry.id == inquiry_id,
            BusinessInquiry.school_ids.contains([school_id]),
        )
        .first()
    )
    if not inquiry:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "BUSINESS_INQUIRY_NOT_FOUND",
                "message": "Business inquiry not found or you do not have access.",
            },
        )

    # Step 2: Junction row
    junction = (
        db.query(BusinessInquirySchool)
        .filter(
            BusinessInquirySchool.business_inquiry_id == inquiry_id,
            BusinessInquirySchool.school_id == school_id,
        )
        .first()
    )
    if not junction:
        # Auto-create if missing (e.g. inquiry pre-dates the feature)
        junction = BusinessInquirySchool(
            business_inquiry_id=inquiry_id,
            school_id=school_id,
            is_seen=False,
            amount_deducted=Decimal("0.00"),
        )
        db.add(junction)
        db.flush()

    # Step 3: Already seen — no charge
    if junction.is_seen:
        return inquiry, junction

    # Step 4: Lock wallet
    wallet = (
        db.query(SchoolWallet)
        .filter(SchoolWallet.school_id == school_id)
        .with_for_update()
        .first()
    )
    if not wallet:
        wallet = SchoolWallet(school_id=school_id, balance=Decimal("0.00"), currency="INR")
        db.add(wallet)
        db.flush()
        # Re-lock
        wallet = (
            db.query(SchoolWallet)
            .filter(SchoolWallet.school_id == school_id)
            .with_for_update()
            .first()
        )

    # Step 5: Viewer number and price
    # Use FOR UPDATE on the junction aggregate to prevent race conditions
    seen_count = (
        db.query(func.count(BusinessInquirySchool.id))
        .filter(
            BusinessInquirySchool.school_id == school_id,
            BusinessInquirySchool.is_seen == True,  # noqa: E712
        )
        .with_for_update()
        .scalar()
    ) or 0
    next_viewer_number = seen_count + 1

    config = get_price_config_for_school(school, db)
    if config:
        price = calculate_applicable_price(next_viewer_number, config)
    else:
        price = Decimal("0.00")

    # Step 6: Check balance
    balance = Decimal(str(wallet.balance))
    if balance < price:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "INSUFFICIENT_WALLET_BALANCE",
                "message": "Insufficient wallet balance to view this business inquiry.",
                "required_amount": float(price),
                "wallet_balance": float(balance),
                "shortfall_amount": float(price - balance),
            },
        )

    # Step 7: Deduct wallet
    balance_before = balance
    balance_after = (balance - price).quantize(Decimal("0.01"))
    wallet.balance = balance_after

    # Step 8: Wallet transaction
    txn = WalletTransaction(
        school_id=school_id,
        transaction_type=WalletTransactionType.INQUIRY_DEDUCTION.value,
        transaction_status=WalletTransactionStatus.SUCCESS.value,
        amount=-price,           # negative = debit
        bonus_amount=Decimal("0.00"),
        total_credit=-price,
        balance_before=balance_before,
        balance_after=balance_after,
        currency="INR",
        reference_type="BUSINESS_INQUIRY",
        reference_id=str(inquiry_id),
        description=f"View charge for Business Inquiry #{inquiry_id}",
    )
    db.add(txn)
    db.flush()

    # Step 9: Update junction row
    junction.is_seen = True
    junction.seen_at = _now_utc()
    junction.viewer_number = next_viewer_number
    junction.price_per_view = price
    junction.amount_deducted = price
    junction.wallet_transaction_id = txn.id

    db.flush()
    return inquiry, junction
