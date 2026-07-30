from datetime import date, datetime, time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ClassSessionStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    LIVE = "LIVE"
    DONE = "DONE"
    NOT_DONE = "NOT_DONE"


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
