"""Agent Phase 3 — Payment Account, Earnings Summary, and Withdrawal Schemas"""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.agent_payment import PaymentMethod, WithdrawalStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UPI_RE = re.compile(r"^[\w.\-]{2,256}@[a-zA-Z]{2,64}$")
_IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")

MAX_ACCOUNT_LEN = 20
MAX_TRANSACTION_ID_LEN = 128
MAX_PROOF_SIZE = 5 * 1024 * 1024   # 5 MB
ALLOWED_PROOF_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
ALLOWED_PROOF_EXTS = {"jpg", "jpeg", "png", "webp"}


def _mask_account(number: str) -> str:
    """Returns XXXXXX1234 style masked account number."""
    if not number:
        return ""
    visible = number[-4:]
    return f"{'X' * (len(number) - 4)}{visible}" if len(number) > 4 else "X" * len(number)


# ---------------------------------------------------------------------------
# Payment Account — Write
# ---------------------------------------------------------------------------

class PaymentAccountRequest(BaseModel):
    account_holder_name: str = Field(..., min_length=2, max_length=255)
    payment_method: PaymentMethod

    # UPI fields
    upi_id: Optional[str] = None

    # Bank fields
    bank_account_number: Optional[str] = None
    confirm_bank_account_number: Optional[str] = None   # validation only; never stored
    ifsc_code: Optional[str] = None
    bank_name: Optional[str] = None
    branch_name: Optional[str] = None

    @field_validator("payment_method")
    @classmethod
    def validate_method(cls, v):
        if v not in (PaymentMethod.UPI, PaymentMethod.BANK_TRANSFER):
            raise ValueError("payment_method must be UPI or BANK_TRANSFER")
        return v

    @field_validator("upi_id")
    @classmethod
    def validate_upi(cls, v):
        if v is None:
            return v
        if not _UPI_RE.match(v):
            raise ValueError("Invalid UPI ID format (e.g. name@upi)")
        return v

    @field_validator("ifsc_code")
    @classmethod
    def validate_ifsc(cls, v):
        if v is None:
            return v
        if not _IFSC_RE.match(v.upper()):
            raise ValueError("Invalid IFSC code format (e.g. SBIN0001234)")
        return v.upper()

    @model_validator(mode="after")
    def validate_method_fields(self):
        if self.payment_method == PaymentMethod.UPI:
            if not self.upi_id:
                raise ValueError("upi_id is required for UPI payment method")
        elif self.payment_method == PaymentMethod.BANK_TRANSFER:
            missing = []
            if not self.bank_account_number:
                missing.append("bank_account_number")
            if not self.confirm_bank_account_number:
                missing.append("confirm_bank_account_number")
            if not self.ifsc_code:
                missing.append("ifsc_code")
            if not self.bank_name:
                missing.append("bank_name")
            if missing:
                raise ValueError(f"Missing required fields for BANK_TRANSFER: {', '.join(missing)}")
            if self.bank_account_number != self.confirm_bank_account_number:
                raise ValueError("bank_account_number and confirm_bank_account_number do not match")
            if len(self.bank_account_number) > MAX_ACCOUNT_LEN:
                raise ValueError(f"bank_account_number must not exceed {MAX_ACCOUNT_LEN} characters")
        return self


# ---------------------------------------------------------------------------
# Payment Account — Response
# ---------------------------------------------------------------------------

class PaymentAccountResponse(BaseModel):
    id: int
    agent_profile_id: int
    account_holder_name: str
    payment_method: str
    upi_id: Optional[str] = None
    bank_account_masked: Optional[str] = None   # XXXXXX1234
    ifsc_code: Optional[str] = None
    bank_name: Optional[str] = None
    branch_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Earnings Summary
# ---------------------------------------------------------------------------

class EarningsCategoryBreakdown(BaseModel):
    earning_type: str
    total_approved: Decimal
    total_pending: Decimal
    total_rejected: Decimal
    count: int


class EarningsSummaryResponse(BaseModel):
    total_approved_earnings: Decimal
    total_pending_earnings: Decimal
    total_rejected_earnings: Decimal
    total_withdrawal_requested: Decimal   # PENDING + APPROVED withdrawals
    total_reserved_amount: Decimal        # same as withdrawal_requested (amount held)
    total_paid_amount: Decimal            # successfully paid withdrawals
    available_balance: Decimal            # approved_earnings - reserved - paid
    currency: str = "INR"
    breakdown: list[EarningsCategoryBreakdown] = []
    last_updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Earnings History
# ---------------------------------------------------------------------------

class EarningHistoryItem(BaseModel):
    id: int
    earning_type: str
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    description: Optional[str] = None
    applied_rate: Decimal
    amount: Decimal
    status: str
    earning_date: Optional[date] = None
    created_at: datetime
    approved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class WithdrawalHistoryItem(BaseModel):
    id: int
    requested_amount: Decimal
    status: str
    agent_remarks: Optional[str] = None
    payment_method: Optional[str] = None
    bank_account_masked: Optional[str] = None
    upi_id: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    transaction_id: Optional[str] = None
    transaction_date: Optional[date] = None
    actual_paid_amount: Optional[Decimal] = None
    admin_remarks: Optional[str] = None
    rejection_reason: Optional[str] = None
    paid_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Withdrawal Request
# ---------------------------------------------------------------------------

class WithdrawalCreateRequest(BaseModel):
    amount: Decimal = Field(..., decimal_places=2)
    remarks: Optional[str] = Field(None, max_length=500)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError("amount must be greater than zero")
        return v


class WithdrawalResponse(BaseModel):
    id: int
    agent_profile_id: int
    requested_amount: Decimal
    status: str
    agent_remarks: Optional[str] = None
    payment_method_snapshot: Optional[str] = None
    upi_id_snapshot: Optional[str] = None
    bank_account_masked_snapshot: Optional[str] = None
    ifsc_snapshot: Optional[str] = None
    bank_name_snapshot: Optional[str] = None
    account_holder_name_snapshot: Optional[str] = None
    admin_remarks: Optional[str] = None
    rejection_reason: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    transaction_id: Optional[str] = None
    transaction_date: Optional[date] = None
    actual_paid_amount: Optional[Decimal] = None
    paid_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Admin Actions
# ---------------------------------------------------------------------------

class ApproveWithdrawalRequest(BaseModel):
    admin_remarks: Optional[str] = Field(None, max_length=500)


class RejectWithdrawalRequest(BaseModel):
    rejection_reason: str = Field(..., min_length=5, max_length=500)


# ---------------------------------------------------------------------------
# Withdrawal History (audit)
# ---------------------------------------------------------------------------

class WithdrawalAuditItem(BaseModel):
    id: int
    from_status: Optional[str] = None
    to_status: str
    action: str
    actor_user_id: Optional[int] = None
    remarks: Optional[str] = None
    transaction_id: Optional[str] = None
    transaction_date: Optional[date] = None
    actual_paid_amount: Optional[Decimal] = None
    created_at: datetime

    model_config = {"from_attributes": True}
