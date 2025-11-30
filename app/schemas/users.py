from datetime import datetime
from pydantic import BaseModel, EmailStr,field_validator
from typing import Optional
from enum import Enum

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserRole(str,Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    SCHOOL = "school"
    TEACHER = "teacher"
    STUDENT  = "student" 
    
# Base schema for user-related actions
class UserBase(BaseModel):
    # name: str
    # location: Optional[str] = None
    # phone: Optional[str] = None
    # website: Optional[str] = None
    # email: EmailStr

    name: Optional[str] = None 
    location: Optional[str] = None
    phone: str
    website: Optional[str] = None
    email: EmailStr

    first_name: Optional[str] = None
    last_name: Optional[str] = None

# Schema used when creating a new user (no password, role is handled later)
class UserCreate(UserBase):
    pass
    
class SignupResponse(BaseModel):
    detail: str
    user_id: int    

class ResendOtpRequest(BaseModel):
    email: EmailStr
class ForgotPasswordRequest(BaseModel):
    email: EmailStr
# Output schema for the User model (including role, timestamps, etc.)
class UserResponse(UserBase):
    id: int
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {
        "from_attributes": True 
    }

# Token schema for token-related actions
class TokenBase(BaseModel):
    token: str
    expires_at: datetime

class TokenCreate(TokenBase):
    user_id: int

class Token(TokenBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    role: str
    detail: str

# OTP schema for OTP-related actions
class OtpCreate(BaseModel):
    email: EmailStr
    
# OTP verification schema
class OtpVerify(BaseModel):
    email: EmailStr
    otp: str        

# Output schema for OTPs
class OtpResponse(BaseModel):
    id: int
    email: EmailStr
    otp: str
    created_at: datetime
    expires_at: datetime

    model_config = {
        "from_attributes": True 
    }

# Template schema for template-related actions
class TemplateBase(BaseModel):
    name: str
    subject: str
    context: str
    body: str


class TemplateCreate(TemplateBase):
    pass


class TemplateUpdate(TemplateBase):
    pass


# Output schema for the Template model (including timestamps)
class TemplateResponse(TemplateBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True 
    }             