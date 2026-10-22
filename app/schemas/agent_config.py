"""Agent Phase 2 — Payment Configuration Schemas"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, field_validator


def _validate_rate(v: Decimal) -> Decimal:
    if v < 0:
        raise ValueError("Rate must be zero or positive")
    return v


# ------------------------------------------------------------------
# Activity sub-schemas
# ------------------------------------------------------------------

class ActivityConfig(BaseModel):
    """Standard activity with a single flat rate."""
    is_enabled: bool
    rate: Decimal = Field(..., decimal_places=2)

    @field_validator("rate")
    @classmethod
    def rate_positive(cls, v):
        return _validate_rate(v)


class StipendConfig(BaseModel):
    """Monthly stipend rate."""
    is_enabled: bool
    monthly_rate: Decimal = Field(..., decimal_places=2)

    @field_validator("monthly_rate")
    @classmethod
    def rate_positive(cls, v):
        return _validate_rate(v)


# ------------------------------------------------------------------
# Write request (POST and PUT share the same structure)
# ------------------------------------------------------------------

class AgentConfigRequest(BaseModel):
    institution_digital_profile: ActivityConfig
    monthly_stipend: StipendConfig
    physical_verification: ActivityConfig
    online_demonstration: ActivityConfig
    offline_demonstration: ActivityConfig
    other_activities: ActivityConfig
    initial_bonus: Decimal = Field(..., decimal_places=2)

    @field_validator("initial_bonus")
    @classmethod
    def bonus_positive(cls, v):
        return _validate_rate(v)


# ------------------------------------------------------------------
# Response schemas
# ------------------------------------------------------------------

class ActivityConfigResponse(BaseModel):
    is_enabled: bool
    rate: Decimal

    model_config = {"from_attributes": True}


class StipendConfigResponse(BaseModel):
    is_enabled: bool
    monthly_rate: Decimal
    effective_from: Optional[date] = None

    model_config = {"from_attributes": True}


class AgentConfigResponse(BaseModel):
    agent_profile_id: int
    agent_id: str
    institution_digital_profile: ActivityConfigResponse
    monthly_stipend: StipendConfigResponse
    physical_verification: ActivityConfigResponse
    online_demonstration: ActivityConfigResponse
    offline_demonstration: ActivityConfigResponse
    other_activities: ActivityConfigResponse
    initial_bonus: Decimal
    is_bonus_withdrawn: bool
    effective_from: datetime
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------
# Earning response
# ------------------------------------------------------------------

class AgentEarningResponse(BaseModel):
    id: int
    agent_profile_id: int
    earning_type: str
    status: str
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    applied_rate: Decimal
    amount: Decimal
    earning_date: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime
    approved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
