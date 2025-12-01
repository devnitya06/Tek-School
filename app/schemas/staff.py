from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, Literal, List, Dict, Any
from decimal import Decimal
from datetime import datetime
from app.models.staff import StaffPermissionType, ActionType, ResourceType


class StaffBase(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    designation: Optional[str] = None

    @field_validator("phone")
    def validate_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if not value.isdigit():
            raise ValueError("Phone must contain digits only")
        if len(value) != 10:
            raise ValueError("Phone must be exactly 10 digits")
        return value


class StaffCreateRequest(StaffBase):
    password: str
    employee_type: Optional[Literal["full_time", "part_time"]] = None
    annual_salary: Optional[Decimal] = None
    emergency_leave: Optional[int] = None
    casual_leave: Optional[int] = None
    permissions: Optional[List[StaffPermissionType]] = None

    @field_validator("password")
    def validate_password(cls, value: str) -> str:
        if not value:
            raise ValueError("Password is required")
        if len(value) < 6:
            raise ValueError("Password must be at least 6 characters long")
        return value


class StaffUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    designation: Optional[str] = None
    employee_type: Optional[Literal["full_time", "part_time"]] = None
    annual_salary: Optional[Decimal] = None
    emergency_leave: Optional[int] = None
    casual_leave: Optional[int] = None

    @field_validator("phone")
    def validate_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if not value.isdigit():
            raise ValueError("Phone must contain digits only")
        if len(value) != 10:
            raise ValueError("Phone must be exactly 10 digits")
        return value


class StaffResponse(StaffBase):
    id: str
    school_id: str
    employee_type: Optional[str] = None
    annual_salary: Optional[Decimal] = None
    emergency_leave: Optional[int] = None
    casual_leave: Optional[int] = None
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }


class StaffPermissionAssignRequest(BaseModel):
    permissions: List[StaffPermissionType]


class StaffPermissionResponse(BaseModel):
    permissions: List[str]
    staff_id: str
    staff_name: str

    model_config = {
        "from_attributes": True
    }


class ActivityLogResponse(BaseModel):
    id: int
    user_id: int
    user_name: Optional[str] = None
    user_role: str
    school_id: str
    action_type: str
    resource_type: str
    resource_id: Optional[str] = None
    description: Optional[str] = None
    action_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = {
        "from_attributes": True
    }

