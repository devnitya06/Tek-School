from pydantic import BaseModel, EmailStr, field_validator, Field
from typing import Optional, Literal, List, Dict, Any
from decimal import Decimal
from datetime import datetime, time
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


class EmployeePaymentCreate(BaseModel):
    """Payment structure for teacher and staff creation"""
    monthly_in_hand_salary: float = Field(default=0.0, ge=0, description="Monthly in-hand salary amount")
    allowance: float = Field(default=0.0, ge=0, description="Allowance amount")
    bonus: float = Field(default=0.0, ge=0, description="Bonus amount")
    other_allowances: float = Field(default=0.0, ge=0, description="Other allowances amount")
    incentive_plan: float = Field(default=0.0, ge=0, description="Incentive plan amount")
    health_care_insurance: float = Field(default=0.0, ge=0, description="Health care insurance amount")
    skill_development: float = Field(default=0.0, ge=0, description="Skill development amount")

class StaffCreateRequest(StaffBase):
    password: str
    employee_type: Optional[Literal["full_time", "part_time"]] = None
    annual_salary: Optional[Decimal] = None
    emergency_leave: Optional[int] = None
    casual_leave: Optional[int] = None
    immidiate_boss: Optional[str] = None
    super_boss: Optional[str] = None
    mark_in_time: Optional[time] = None
    mark_out_time: Optional[time] = None
    employee_grade: Optional[str] = None
    is_active_hr_service: Optional[bool] = None
    hiring_for_board: Optional[str] = None
    teaching_language: Optional[Dict[str, Any]] = None
    subjects: Optional[str] = None
    assigned_class: Optional[str] = None
    assigned_subjects: Optional[Dict[str, Any]] = None
    permissions: Optional[List[StaffPermissionType]] = None
    payment: Optional[EmployeePaymentCreate] = None  # Optional payment structure

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
    immidiate_boss: Optional[str] = None
    super_boss: Optional[str] = None
    mark_in_time: Optional[time] = None
    mark_out_time: Optional[time] = None
    employee_grade: Optional[str] = None
    is_active_hr_service: Optional[bool] = None
    hiring_for_board: Optional[str] = None
    teaching_language: Optional[Dict[str, Any]] = None
    subjects: Optional[str] = None
    assigned_class: Optional[str] = None
    assigned_subjects: Optional[Dict[str, Any]] = None
    payment: Optional[EmployeePaymentCreate] = None  # Optional payment structure update

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
    school_id: Optional[str] = None
    employee_type: Optional[str] = None
    annual_salary: Optional[Decimal] = None
    emergency_leave: Optional[int] = None
    casual_leave: Optional[int] = None
    immidiate_boss: Optional[str] = None
    super_boss: Optional[str] = None
    mark_in_time: Optional[time] = None
    mark_out_time: Optional[time] = None
    employee_grade: Optional[str] = None
    is_active_hr_service: Optional[bool] = None
    hiring_for_board: Optional[str] = None
    teaching_language: Optional[Dict[str, Any]] = None
    subjects: Optional[str] = None
    assigned_class: Optional[str] = None
    assigned_subjects: Optional[Dict[str, Any]] = None
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }


class StaffResponseWithCompensation(StaffResponse):
    """Same as StaffResponse plus employee_compensation when linked from designation template."""

    employee_compensation: Optional[Dict[str, Any]] = None


class DesignationCompensationTemplateUpsert(BaseModel):
    designation: str = Field(..., min_length=1, max_length=255)
    basic_salary: Optional[Decimal] = None
    hra: Optional[Decimal] = None
    special_allowance: Optional[Decimal] = None
    travel_allowance: Optional[Decimal] = None
    medical_allowance: Optional[Decimal] = None
    employee_pf_contribution: Optional[Decimal] = None
    additional_benefits: bool = Field(
        default=False,
        description="Whether extra structured benefits (see extra_benefits) apply.",
    )
    extra_benefits: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Optional JSON object for custom benefits (e.g. insurance name, gym, meal allowance). "
            "Copied to staff EmployeeCompensation when designation matches. Keys/values are free-form."
        ),
    )
    employee_grade: Optional[str] = None
    max_salary: Optional[Decimal] = None
    emergency_leave: Optional[int] = None
    casual_leave: Optional[int] = None


class DesignationCompensationTemplateBulkCreate(BaseModel):
    """Create many designation templates in one request (school must not already have that designation)."""

    templates: List[DesignationCompensationTemplateUpsert] = Field(
        ...,
        min_length=1,
        description="Each item is one designation + its compensation fields.",
    )


class DesignationCompensationTemplatePatch(BaseModel):
    """Partial update: identify template by current designation; only sent fields are updated."""

    designation: str = Field(..., min_length=1, max_length=255, description="Existing template designation key.")
    basic_salary: Optional[Decimal] = None
    hra: Optional[Decimal] = None
    special_allowance: Optional[Decimal] = None
    travel_allowance: Optional[Decimal] = None
    medical_allowance: Optional[Decimal] = None
    employee_pf_contribution: Optional[Decimal] = None
    additional_benefits: Optional[bool] = None
    extra_benefits: Optional[Dict[str, Any]] = None
    employee_grade: Optional[str] = None
    max_salary: Optional[Decimal] = None
    emergency_leave: Optional[int] = None
    casual_leave: Optional[int] = None


class DesignationCompensationTemplateBulkPatch(BaseModel):
    """Partially update many templates in one request (each item: designation + fields to change)."""

    updates: List[DesignationCompensationTemplatePatch] = Field(
        ...,
        min_length=1,
        description="Each entry targets one existing template by designation.",
    )


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

