"""School settlement ledger: cash (offline) vs bank account; signed amounts (credits +, debits -)."""

from __future__ import annotations

from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.school import BankAccount, SchoolSettlementTransaction

SETTLEMENT_CASH = "cash_offline"
SETTLEMENT_BANK = "bank_account"

# Student fee UI may send a default bank_account_id even when payment_method is cash;
# settlement must follow payment_method so /school/bank-accounts/ cash bucket matches reality.
_STUDENT_FEE_CASH_METHODS = frozenset({"cash_offline", "cash"})


def resolve_student_fee_settlement_bank_account_id(
    payment_method: Optional[str],
    bank_account_id: Optional[int],
) -> Optional[int]:
    """
    Bank account id for school settlement inflow (student fees).
    Returns None to credit the virtual cash_offline bucket.
    """
    pm = (payment_method or "").strip().lower()
    if pm in _STUDENT_FEE_CASH_METHODS:
        return None
    return bank_account_id


def resolve_inflow_channel(bank_account_id: Optional[int]) -> Tuple[str, Optional[int]]:
    """Money received by school: bank row if student/school chose an account, else cash."""
    if bank_account_id:
        return SETTLEMENT_BANK, bank_account_id
    return SETTLEMENT_CASH, None


def ensure_bank_account_for_school(
    db: Session, school_id: str, bank_account_id: int
) -> BankAccount:
    acc = (
        db.query(BankAccount)
        .filter(BankAccount.id == bank_account_id, BankAccount.school_id == school_id)
        .first()
    )
    if not acc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid bank_account_id for this school.",
        )
    return acc


def record_settlement_entry(
    db: Session,
    *,
    school_id: str,
    settlement_channel: str,
    bank_account_id: Optional[int],
    signed_amount: float,
    direction: str,
    category: str,
    source_reference: str,
    description: Optional[str],
    recorded_by_user_id: Optional[int],
) -> SchoolSettlementTransaction:
    """
    Append one ledger row. `signed_amount` is negative for outflows (e.g. salary -10000),
    positive for inflows (e.g. fee +10000). `direction` is 'in' or 'out' for reporting.
    """
    if settlement_channel not in (SETTLEMENT_CASH, SETTLEMENT_BANK):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="settlement_channel must be 'cash_offline' or 'bank_account'.",
        )
    if settlement_channel == SETTLEMENT_BANK:
        if not bank_account_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="bank_account_id is required when settlement_channel is 'bank_account'.",
            )
        ensure_bank_account_for_school(db, school_id, bank_account_id)
    else:
        bank_account_id = None

    row = SchoolSettlementTransaction(
        school_id=school_id,
        settlement_channel=settlement_channel,
        bank_account_id=bank_account_id,
        amount=float(signed_amount),
        direction=direction,
        category=category,
        source_reference=source_reference,
        description=description,
        recorded_by_user_id=recorded_by_user_id,
    )
    db.add(row)
    return row


def validate_school_payout_settlement(
    *,
    settlement_channel: str,
    bank_account_id: Optional[int],
) -> Tuple[str, Optional[int]]:
    """School paying staff/teacher: must choose cash or bank; bank requires account id."""
    if settlement_channel not in (SETTLEMENT_CASH, SETTLEMENT_BANK):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="settlement_channel must be 'cash_offline' or 'bank_account'.",
        )
    if settlement_channel == SETTLEMENT_BANK:
        if not bank_account_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="bank_account_id is required when paying from a bank account.",
            )
        return SETTLEMENT_BANK, bank_account_id
    if bank_account_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="bank_account_id must be omitted when settlement_channel is 'cash_offline'.",
        )
    return SETTLEMENT_CASH, None


def record_school_salary_payout(
    db: Session,
    *,
    school_id: str,
    settlement_channel: str,
    bank_account_id: Optional[int],
    gross_payout_amount: float,
    category: str,
    source_reference: str,
    description: Optional[str],
    recorded_by_user_id: Optional[int],
) -> SchoolSettlementTransaction:
    """Debit school ledger (negative amount) for salary paid to teacher or staff."""
    ch, bid = validate_school_payout_settlement(
        settlement_channel=settlement_channel, bank_account_id=bank_account_id
    )
    signed = -abs(float(gross_payout_amount))
    return record_settlement_entry(
        db,
        school_id=school_id,
        settlement_channel=ch,
        bank_account_id=bid,
        signed_amount=signed,
        direction="out",
        category=category,
        source_reference=source_reference,
        description=description,
        recorded_by_user_id=recorded_by_user_id,
    )


def record_student_fee_credit(
    db: Session,
    *,
    school_id: str,
    bank_account_id: Optional[int],
    credited_amount: float,
    source_reference: str,
    description: Optional[str],
    recorded_by_user_id: Optional[int],
) -> SchoolSettlementTransaction:
    """Credit school ledger when a student fee is recognised (verified or direct entry)."""
    ch, bid = resolve_inflow_channel(bank_account_id)
    if ch == SETTLEMENT_BANK and bid is not None:
        ensure_bank_account_for_school(db, school_id, bid)
    signed = abs(float(credited_amount))
    return record_settlement_entry(
        db,
        school_id=school_id,
        settlement_channel=ch,
        bank_account_id=bid,
        signed_amount=signed,
        direction="in",
        category="student_fee",
        source_reference=source_reference,
        description=description,
        recorded_by_user_id=recorded_by_user_id,
    )
