"""
Demo Management System — Pydantic Schemas
"""
from datetime import date, time, datetime, timedelta
from typing import List, Optional, Any
from pydantic import BaseModel, EmailStr, Field, field_validator, AnyHttpUrl
import re

from app.demo.enums import DemoDay, DemoUserCategory, DemoStatus, DemoPreferredLanguage


# ─── Configuration Schemas ────────────────────────────────────────────────────

class DemoConfigurationCreate(BaseModel):
    start_time: str = Field(..., description="HH:MM format, e.g. '10:00'")
    end_time: str = Field(..., description="HH:MM format, e.g. '17:00'")
    user_limit: int = Field(..., gt=0, description="Max users per slot")
    demo_days: List[DemoDay] = Field(..., min_length=1)
    presented_by: str = Field(..., min_length=1, max_length=255)
    demonstration_link: str = Field(..., min_length=1, max_length=1024)
    is_active: bool = Field(True)

    @field_validator("demo_days")
    @classmethod
    def validate_demo_days(cls, v):
        if not v:
            raise ValueError("At least one demo day must be selected.")
        return v

    @field_validator("demonstration_link")
    @classmethod
    def validate_link(cls, v):
        if not v or not v.strip():
            raise ValueError("Demonstration link is required.")
        # Basic URL validation
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("Please provide a valid demonstration URL.")
        return v.strip()


class DemoConfigurationUpdate(DemoConfigurationCreate):
    pass


class DemoConfigurationStatusUpdate(BaseModel):
    is_active: bool


class DemoConfigurationResponse(BaseModel):
    id: int
    start_time: str
    end_time: str
    user_limit: int
    demo_days: List[str]
    presented_by: str
    demonstration_link: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def time_to_str(cls, v):
        if isinstance(v, time):
            return v.strftime("%H:%M")
        return v


# ─── Slot Schema ──────────────────────────────────────────────────────────────

class SlotInfo(BaseModel):
    config_id: int
    start_time: str
    end_time: str
    presented_by: str
    user_limit: int
    booked_count: int
    remaining: int
    is_available: bool


class AvailableSlotsResponse(BaseModel):
    date: str
    slots: List[SlotInfo]


# ─── OTP Schemas ──────────────────────────────────────────────────────────────

class DemoOtpRequest(BaseModel):
    email: EmailStr


class DemoOtpVerifyRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)


# ─── Public Access Schema ─────────────────────────────────────────────────────

class DemoAccessRequest(BaseModel):
    email: EmailStr
    access_code: str = Field(..., description="Exactly 6 digits")

    @field_validator("access_code")
    @classmethod
    def validate_access_code(cls, v):
        if not re.fullmatch(r"\d{6}", v):
            from app.demo.exceptions import DemoAPIException, DemoErrorCode
            raise ValueError("Access code must be exactly 6 digits.")
        return v


# ─── Demo Request Schemas (Public) ────────────────────────────────────────────

class DemoRequestCreate(BaseModel):
    """
    Fields accepted from the public user.
    end_time, presented_by, demonstration_link are derived from configuration.
    """
    email: EmailStr
    user_category: DemoUserCategory
    institution_name: str = Field(..., min_length=1, max_length=255)
    full_name: str = Field(..., min_length=1, max_length=255)
    designation: Optional[str] = Field(None, max_length=255)
    phone: str = Field(..., min_length=10, max_length=20)
    institution_address: Optional[str] = Field(None, max_length=1000)
    area_of_interest: Optional[List[str]] = None
    preferred_language: Optional[DemoPreferredLanguage] = Field(
        None, description="Preferred language: HINDI, ENGLISH, or STATE_LANGUAGE"
    )
    config_id: int
    demo_date: date
    start_time: str = Field(..., description="HH:MM format, e.g. '14:00'")

    @field_validator("demo_date")
    @classmethod
    def validate_demo_date(cls, v):
        today = date.today()
        max_date = today + timedelta(days=30)
        if v < today:
            raise ValueError("Demo date cannot be in the past. Please select today or a future date.")
        if v > max_date:
            raise ValueError("Demo date cannot be more than 30 days in the future.")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        cleaned = re.sub(r"[\s\-\+]", "", v)
        if not cleaned.isdigit() or len(cleaned) < 10:
            raise ValueError("Please provide a valid phone number.")
        return cleaned

    @field_validator("start_time")
    @classmethod
    def validate_start_time_format(cls, v):
        try:
            time.fromisoformat(v + ":00") if len(v) == 5 else time.fromisoformat(v)
        except ValueError:
            raise ValueError("Please provide a valid time.")
        return v


class DemoRequestPublicResponse(BaseModel):
    """Public response — does NOT include access_code."""
    id: int
    request_code: str
    email: str
    user_category: str
    institution_name: str
    full_name: str
    designation: Optional[str]
    phone: str
    institution_address: Optional[str]
    area_of_interest: Optional[List[str]]
    preferred_language: Optional[str]
    config_id: int
    demo_date: date
    start_time: str
    end_time: str
    presented_by: str
    demonstration_link: str
    status: str
    feedback_message: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    images: Optional[List["DemoImageResponse"]] = []

    model_config = {"from_attributes": True}

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def time_to_str(cls, v):
        if isinstance(v, time):
            return v.strftime("%H:%M")
        return v


class DemoRequestAdminResponse(DemoRequestPublicResponse):
    """Admin response — includes access_code."""
    access_code: Optional[str]


class DemoImageResponse(BaseModel):
    id: int
    image_url: str
    file_name: Optional[str]
    file_size: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


# Allow forward reference resolution
DemoRequestPublicResponse.model_rebuild()
DemoRequestAdminResponse.model_rebuild()


class DemoRequestListItem(BaseModel):
    id: int
    request_code: str
    email: str
    full_name: str
    phone: str
    user_category: str
    institution_name: str
    preferred_language: Optional[str]
    demo_date: date
    start_time: str
    end_time: str
    presented_by: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def time_to_str(cls, v):
        if isinstance(v, time):
            return v.strftime("%H:%M")
        return v


# ─── Admin Action Schemas ─────────────────────────────────────────────────────

class DemoStatusUpdate(BaseModel):
    status: DemoStatus


class DemoRescheduleRequest(BaseModel):
    """
    Admin reschedule — backend derives end_time, presented_by, demonstration_link
    from the config_id.
    """
    demo_date: date
    config_id: int
    start_time: str = Field(..., description="HH:MM format")

    @field_validator("demo_date")
    @classmethod
    def validate_demo_date(cls, v):
        today = date.today()
        max_date = today + timedelta(days=30)
        if v < today:
            raise ValueError("Demo date cannot be in the past. Please select today or a future date.")
        if v > max_date:
            raise ValueError("Demo date cannot be more than 30 days in the future.")
        return v

    @field_validator("start_time")
    @classmethod
    def validate_start_time_format(cls, v):
        try:
            time.fromisoformat(v + ":00") if len(v) == 5 else time.fromisoformat(v)
        except ValueError:
            raise ValueError("Please provide a valid time.")
        return v


class DemoFeedbackUpdate(BaseModel):
    feedback_message: str = Field(..., min_length=1, max_length=2000)
