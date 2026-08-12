from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class NewsSubmissionCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    images: Optional[List[str]] = None
    full_name: Optional[str] = None
    phone_no: Optional[str] = None
    email_id: Optional[str] = None
    location: Optional[str] = None


class NewsSubmissionVerifyRequest(BaseModel):
    news_id: int
    otp_code: str = Field(..., min_length=4, max_length=10)


class NewsSubmissionUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    full_name: Optional[str] = None
    phone_no: Optional[str] = None
    email_id: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = None
    remark: Optional[str] = None


class NewsRemarkRequest(BaseModel):
    status: Optional[str] = None
    remark: Optional[str] = None


class NewsSubmissionResponse(BaseModel):
    id: int
    school_id: str
    title: str
    description: Optional[str] = None
    images: Optional[List[str]] = None
    user_type: Optional[str] = None
    full_name: Optional[str] = None
    phone_no: Optional[str] = None
    email_id: Optional[str] = None
    location: Optional[str] = None
    status: str
    remark: Optional[str] = None
    is_verified: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
