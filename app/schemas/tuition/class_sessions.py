from datetime import date, datetime, time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ClassSessionStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    LIVE = "LIVE"
    DONE = "DONE"
    NOT_DONE = "NOT_DONE"


class TeachingSetupClassSessionCreate(BaseModel):
    session_date: date
    notes: Optional[str] = None


class TeachingSetupClassSessionUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


class TeachingSetupClassSessionResponse(BaseModel):
    id: int
    teaching_setup_id: str
    session_date: date
    status: str
    notes: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TeachingSetupClassSessionListResponse(BaseModel):
    items: list[TeachingSetupClassSessionResponse] = Field(default_factory=list)
    total: int


class ClassSessionResponse(BaseModel):
    teaching_setup_id: str
    class_date: date
    weekday: str
    scheduled_start_time: time
    scheduled_end_time: time
    status: ClassSessionStatus
    reason: Optional[str] = None
    started_at: Optional[datetime] = None
    is_clickable: bool
    meeting_link: Optional[str] = None


class ClassSessionListResponse(BaseModel):
    teaching_setup_id: str
    sessions: list[ClassSessionResponse] = Field(default_factory=list)


class ClassSessionStartResponse(BaseModel):
    message: str
    session: ClassSessionResponse


class ClassSessionUpdate(BaseModel):
    status: ClassSessionStatus
    reason: Optional[str] = None
