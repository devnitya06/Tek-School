"""
Pydantic schemas for Billing, Wallet, and Digital Profile Price Configuration.
"""
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums (mirror models/billing.py — kept separate for Pydantic serialization)
# ---------------------------------------------------------------------------

class EducationAssociate(str, Enum):
    SCHOOL_EDUCATIONS = "SCHOOL_EDUCATIONS"
    HIGHER_EDUCATION = "HIGHER_EDUCATION"
    PROFESSIONAL_EDUCATION = "PROFESSIONAL_EDUCATION"
    MEDICAL_PHARMA = "MEDICAL_PHARMA"
    UNIVERSITY = "UNIVERSITY"
    TRAINING_COACHING = "TRAINING_COACHING"
    CREATIVE_TRAINING = "CREATIVE_TRAINING"


class WalletTransactionType(str, Enum):
    RECHARGE = "RECHARGE"
    INQUIRY_DEDUCTION = "INQUIRY_DEDUCTION"
    BONUS = "BONUS"
    REFUND = "REFUND"
    ADJUSTMENT = "ADJUSTMENT"


class WalletTransactionStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


# ---------------------------------------------------------------------------
# Digital Profile Price Configuration
# ---------------------------------------------------------------------------

class PriceConfigCreate(BaseModel):
    education_associate: EducationAssociate
    education_offered: List[str] = Field(..., min_length=1)
    first_two_viewer_price: Decimal = Field(..., ge=0)
    next_five_viewer_price: Decimal = Field(..., ge=0)
    all_other_viewer_price: Decimal = Field(..., ge=0)

    @field_validator("education_offered")
    @classmethod
    def education_offered_not_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("education_offered must not be empty")
        cleaned = [x.strip() for x in v if x.strip()]
        if not cleaned:
            raise ValueError("education_offered must contain at least one non-empty value")
        return cleaned


class PriceConfigUpdate(BaseModel):
    education_associate: Optional[EducationAssociate] = None
    education_offered: Optional[List[str]] = None
    first_two_viewer_price: Optional[Decimal] = Field(None, ge=0)
    next_five_viewer_price: Optional[Decimal] = Field(None, ge=0)
    all_other_viewer_price: Optional[Decimal] = Field(None, ge=0)

    @field_validator("education_offered")
    @classmethod
    def education_offered_not_empty(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is not None:
            cleaned = [x.strip() for x in v if x.strip()]
            if not cleaned:
                raise ValueError("education_offered must contain at least one non-empty value")
            return cleaned
        return v


class PriceConfigResponse(BaseModel):
    id: int
    education_associate: str
    education_offered: List[str]
    first_two_viewer_price: Decimal
    next_five_viewer_price: Decimal
    all_other_viewer_price: Decimal
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PriceConfigListResponse(BaseModel):
    items: List[PriceConfigResponse]
    total: int


# ---------------------------------------------------------------------------
# Recharge Configuration
# ---------------------------------------------------------------------------

class RechargeBonusItem(BaseModel):
    recharge_amount: Decimal = Field(..., ge=0)
    bonus_percentage: Decimal = Field(..., ge=0)


class RechargeConfigUpdate(BaseModel):
    min_recharge_amount: Decimal = Field(..., ge=0)
    max_recharge_amount: Decimal = Field(..., ge=0)
    bonus_configs: List[RechargeBonusItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_min_max(self) -> "RechargeConfigUpdate":
        if self.max_recharge_amount < self.min_recharge_amount:
            raise ValueError("max_recharge_amount must be >= min_recharge_amount")
        return self

    @field_validator("bonus_configs")
    @classmethod
    def no_duplicate_amounts(cls, v: List[RechargeBonusItem]) -> List[RechargeBonusItem]:
        amounts = [item.recharge_amount for item in v]
        if len(amounts) != len(set(amounts)):
            raise ValueError("Duplicate recharge_amount values are not allowed in bonus_configs")
        return v


class RechargeBonusResponse(BaseModel):
    recharge_amount: Decimal
    bonus_percentage: Decimal

    model_config = {"from_attributes": True}


class RechargeConfigResponse(BaseModel):
    id: int
    min_recharge_amount: Decimal
    max_recharge_amount: Decimal
    bonus_configs: List[RechargeBonusResponse] = []
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# School Wallet
# ---------------------------------------------------------------------------

class WalletResponse(BaseModel):
    school_id: str
    balance: Decimal
    currency: str
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AdminWalletResponse(BaseModel):
    school_id: str
    balance: Decimal
    total_recharged: Decimal
    total_bonus: Decimal
    total_inquiry_deduction: Decimal
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Wallet Recharge
# ---------------------------------------------------------------------------

class RechargeRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, description="Recharge amount in INR")


class RechargeResponse(BaseModel):
    transaction_id: int
    requested_amount: Decimal
    bonus_percentage: Decimal
    bonus_amount: Decimal
    total_credit: Decimal
    payment_status: str
    payment_provider: Optional[str] = None
    payment_order_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Wallet Transaction
# ---------------------------------------------------------------------------

class WalletTransactionResponse(BaseModel):
    transaction_id: int
    school_id: Optional[str] = None
    transaction_type: str
    transaction_status: str
    paid_amount: Decimal     # base amount (positive for recharge, 0 for deductions from school view)
    bonus_amount: Decimal
    amount: Decimal          # net amount (positive credit or negative debit)
    balance_before: Optional[Decimal] = None
    balance_after: Optional[Decimal] = None
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    description: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class WalletTransactionListResponse(BaseModel):
    items: List[WalletTransactionResponse]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Business Inquiry View Price
# ---------------------------------------------------------------------------

class InquiryViewPriceResponse(BaseModel):
    inquiry_id: int
    is_seen: bool
    viewer_number: int           # next viewer number if unseen; historical if seen
    applicable_price: Decimal
    wallet_balance: Decimal
    can_view: bool


# ---------------------------------------------------------------------------
# Business Inquiry Billing Extension (added to existing response)
# ---------------------------------------------------------------------------

class BusinessInquiryBillingInfo(BaseModel):
    """Per-school billing info attached to each BusinessInquiry list/detail item."""
    is_seen: bool = False
    seen_at: Optional[datetime] = None
    viewer_number: Optional[int] = None
    view_price: Optional[Decimal] = None    # current applicable price (if unseen) or historical
    amount_deducted: Decimal = Decimal("0.00")
    remark: Optional[str] = None
    remark_status: Optional[str] = None

    model_config = {"from_attributes": True}
