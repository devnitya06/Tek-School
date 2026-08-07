from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class LessonPlanCreate(BaseModel):
    board: str
    class_id: int
    subject_id: int
    batch_ids: List[str] = Field(default_factory=list)
    title: Optional[str] = None


class LessonPlanUpdate(BaseModel):
    title: Optional[str] = None
    board: Optional[str] = None
    class_id: Optional[int] = None
    subject_id: Optional[int] = None
    batch_ids: Optional[List[str]] = None
    remarks: Optional[str] = None
    status: Optional[str] = None


class LessonCreate(BaseModel):
    lesson_title: str
    lesson_objective: Optional[str] = None


class LessonUpdate(BaseModel):
    lesson_title: Optional[str] = None
    lesson_objective: Optional[str] = None


class TopicCreate(BaseModel):
    topic_title: str
    topic_content: Optional[str] = None
    reference_video_link: Optional[str] = None


class TopicBulkCreate(BaseModel):
    topics: List[TopicCreate]


class TopicUpdate(BaseModel):
    topic_title: Optional[str] = None
    topic_content: Optional[str] = None
    reference_video_link: Optional[str] = None


class TopicReorderItem(BaseModel):
    topic_id: str
    display_order: int


class TopicReorderRequest(BaseModel):
    topics: List[TopicReorderItem]


class TopicFileResponse(BaseModel):
    id: str
    file_name: str
    file_url: str
    file_type: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TopicResponse(BaseModel):
    id: str
    lesson_id: str
    topic_title: str
    topic_content: Optional[str] = None
    display_order: int
    reference_video_link: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LessonResponse(BaseModel):
    id: str
    lesson_plan_id: str
    lesson_title: str
    lesson_objective: Optional[str] = None
    display_order: int
    topics: list[TopicResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LessonSummaryResponse(BaseModel):
    id: str
    lesson_title: str
    lesson_objective: Optional[str] = None
    display_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LessonPlanResponse(BaseModel):
    id: str
    title: Optional[str] = None
    board: str
    class_id: int
    class_name: Optional[str] = None
    subject_id: int
    subject_name: Optional[str] = None
    batch_ids: list[str] = Field(default_factory=list)
    
    class BatchInfo(BaseModel):
        id: str
        batch_name: str

        model_config = {"from_attributes": True}

    batches: list[BatchInfo] = Field(default_factory=list)
    lessons: list[LessonSummaryResponse] = Field(default_factory=list)
    status: str
    remarks: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LessonPlanCreateResponse(BaseModel):
    message: str
    lesson_plan_id: str
    status: str
