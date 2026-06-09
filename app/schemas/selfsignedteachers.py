from datetime import datetime, date
from typing import Optional
from enum import Enum
from pydantic import BaseModel, EmailStr, Field


class VerificationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    BLOCKED = "blocked"
    REJECTED = "rejected"


class SelfSignedTeacherSignupRequest(BaseModel):
    first_name: str
    last_name: str
    phone: str
    email: EmailStr
    bio: Optional[str] = None
    profile_image: Optional[str] = None


class SelfSignedTeacherProfileUpdate(BaseModel):
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    gender: Optional[str] = None
    dob: Optional[date] = None
    qualification: Optional[str] = None
    university: Optional[str] = None
    institution_name: Optional[str] = None
    designation: Optional[str] = None
    institution_pin_code: Optional[str] = None
    landmark: Optional[str] = None
    joining_date: Optional[date] = None
    profile_image: Optional[str] = None
    bio: Optional[str] = None


class SelfSignedTeacherProfileResponse(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    gender: Optional[str] = None
    dob: Optional[date] = None
    phone: Optional[str]
    email: EmailStr
    qualification: Optional[str]
    university: Optional[str]
    institution_name: Optional[str]
    designation: Optional[str]
    institution_pin_code: Optional[str]
    division: Optional[str]
    district: Optional[str]
    state: Optional[str]
    landmark: Optional[str]
    joining_date: Optional[date]
    official_id_card: Optional[str]
    profile_status: str
    verification_status: VerificationStatus
    rejection_reason: Optional[str]
    blocked_reason: Optional[str]
    verified_by: Optional[int]
    verified_at: Optional[datetime]
    profile_completed: bool
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {
        "from_attributes": True
    }


class VerificationStatusResponse(BaseModel):
    verification_status: VerificationStatus
    profile_status: str
    profile_completed: bool
    rejection_reason: Optional[str] = None
    blocked_reason: Optional[str] = None
    verified_by: Optional[int] = None
    verified_at: Optional[datetime] = None


class SelfSignedTeacherStudentCreateRequest(BaseModel):
    """Schema for Self Sign Teacher creating a student"""
    first_name: str
    last_name: str
    email: EmailStr
    phone: str
    select_board: Optional[str] = None
    select_medium: Optional[str] = None
    select_class_id: Optional[int] = None
    school_name: Optional[str] = None
    school_location: Optional[str] = None
    profile_image: Optional[str] = None
    pin: Optional[int] = None
    division: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    plot: Optional[str] = None
    parent_name: Optional[str] = None
    relation: Optional[str] = None
    parent_phone: Optional[str] = None
    parent_email: Optional[EmailStr] = None
    occupation: Optional[str] = None


class SelfSignedTeacherStudentUpdateRequest(BaseModel):
    """Schema for updating a Self Sign Student profile"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    profile_image: Optional[str] = None
    select_board: Optional[str] = None
    select_medium: Optional[str] = None
    select_class_id: Optional[int] = None
    school_name: Optional[str] = None
    school_location: Optional[str] = None
    pin: Optional[int] = None
    division: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    plot: Optional[str] = None
    parent_name: Optional[str] = None
    relation: Optional[str] = None
    parent_phone: Optional[str] = None
    parent_email: Optional[EmailStr] = None
    occupation: Optional[str] = None


class SelfSignedTeacherStudentJoinRequest(BaseModel):
    invite_code: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: str
    select_board: Optional[str] = None
    select_medium: Optional[str] = None
    select_class_id: Optional[int] = None
    school_name: Optional[str] = None
    school_location: Optional[str] = None
    profile_image: Optional[str] = None


class SelfSignedTeacherStudentResponse(BaseModel):
    """Response schema for Self Sign Student created by teacher"""
    id: int
    user_id: int
    email: EmailStr
    first_name: str
    last_name: str
    phone: Optional[str] = None
    profile_image: Optional[str] = None
    select_board: Optional[str] = None
    select_medium: Optional[str] = None
    select_class_id: Optional[int] = None
    school_name: Optional[str] = None
    school_location: Optional[str] = None
    pin: Optional[int] = None
    division: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    plot: Optional[str] = None
    status: str
    status_expiry_date: Optional[datetime] = None
    parent_name: Optional[str] = None
    relation: Optional[str] = None
    parent_phone: Optional[str] = None
    parent_email: Optional[str] = None
    occupation: Optional[str] = None
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class SelfSignedTeacherStudentListResponse(BaseModel):
    """Response schema for listing Self Sign Students"""
    id: int
    email: EmailStr
    first_name: str
    last_name: str
    phone: Optional[str] = None
    status: str
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class AdminSelfSignedTeacherResponse(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str]
    qualification: Optional[str]
    university: Optional[str]
    institution_name: Optional[str]
    designation: Optional[str]
    institution_pin_code: Optional[str]
    division: Optional[str]
    district: Optional[str]
    state: Optional[str]
    landmark: Optional[str]
    joining_date: Optional[date]
    official_id_card: Optional[str]
    profile_status: str
    verification_status: VerificationStatus
    profile_completed: bool
    rejection_reason: Optional[str]
    blocked_reason: Optional[str]
    verified_by: Optional[int]
    verified_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {
        "from_attributes": True
    }


class VerificationActionRequest(BaseModel):
    reason: Optional[str] = Field(None, description="Reason for rejection/block/hold")
