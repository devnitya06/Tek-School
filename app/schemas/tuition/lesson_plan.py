from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class LessonPlanCreate(BaseModel):
    board: str = Field(..., description="Board identifier (e.g. 'CBSE', 'ICSE')", example="cbse")
    class_name: str = Field(
        ...,
        description="Class name (e.g. 'Standard 2').",
        example="Standard 2",
    )
    subject_name: str = Field(
        ...,
        description="Subject name (e.g. 'Mathematics').",
        example="Mathematics",
    )
    batch_names: List[str] = Field(
        default_factory=list,
        description="List of batch names to associate (e.g. ['A', 'B']). Max 3, no duplicates.",
        example=["A"],
    )
    title: Optional[str] = Field(None, description="Title of the lesson plan.", example="Chapter 1 – Motion")

    model_config = {
        "json_schema_extra": {
            "example": {
                "board": "cbse",
                "class_name": "Standard 2",
                "subject_name": "Mathematics",
                "batch_names": ["A"],
                "title": "Chapter 1 – Motion",
            }
        }
    }


class LessonPlanUpdate(BaseModel):
    title: Optional[str] = Field(None, description="Updated lesson plan title.", example="Chapter 2 – Force")
    board: Optional[str] = Field(None, description="Updated board identifier.", example="ICSE")
    class_name: Optional[str] = Field(None, description="Updated class name (e.g. 'Standard 2').", example="Standard 2")
    subject_name: Optional[str] = Field(None, description="Updated subject name (e.g. 'Physics').", example="Physics")
    batch_names: Optional[List[str]] = Field(None, description="Replace batch names (max 3, no duplicates).", example=["B"])
    remarks: Optional[str] = Field(None, description="Optional teacher remarks.", example="Revised after review")
    status: Optional[str] = Field(None, description="Lesson plan status: 'active' or 'inactive'.", example="active")


class LessonCreate(BaseModel):
    lesson_title: str = Field(..., description="Title of the lesson.", example="Introduction to Motion")
    lesson_objective: Optional[str] = Field(
        None,
        description="Learning objective for this lesson.",
        example="Students will understand the concept of displacement and velocity.",
    )


class LessonUpdate(BaseModel):
    lesson_title: Optional[str] = Field(None, description="Updated lesson title.", example="Advanced Motion")
    lesson_objective: Optional[str] = Field(None, description="Updated learning objective.", example="Understand acceleration.")


class TopicCreate(BaseModel):
    topic_title: str = Field(..., description="Title of the topic.", example="Speed vs Velocity")
    topic_content: Optional[str] = Field(None, description="Detailed content for the topic.", example="Speed is scalar...")
    reference_video_link: Optional[str] = Field(None, description="Reference video URL.", example="https://youtube.com/...")


class TopicBulkCreate(BaseModel):
    topics: List[TopicCreate] = Field(..., description="List of topics to create in bulk.")


class TopicUpdate(BaseModel):
    topic_title: Optional[str] = Field(None, description="Updated topic title.", example="Velocity and Acceleration")
    topic_content: Optional[str] = Field(None, description="Updated topic content.")
    reference_video_link: Optional[str] = Field(None, description="Updated reference video URL.")


class TopicReorderItem(BaseModel):
    topic_id: str = Field(..., description="ID of the topic to reorder.", example="TOP12345678")
    display_order: int = Field(..., description="New display order (1-based).", example=2)


class TopicReorderRequest(BaseModel):
    topics: List[TopicReorderItem] = Field(..., description="Ordered list of topic IDs with their new positions.")


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
    id: str = Field(..., description="Unique lesson plan ID.")
    title: Optional[str] = Field(None, description="Title of the lesson plan.")
    board: str = Field(..., description="Board identifier (e.g. 'CBSE', 'ICSE').")
    class_name: str = Field(..., description="Class name resolved from the teaching configuration.")
    subject_name: str = Field(..., description="Subject name resolved from the teaching configuration.")
    batch_ids: list[str] = Field(default_factory=list, description="List of batch IDs linked to this lesson plan.")

    class BatchInfo(BaseModel):
        id: str = Field(..., description="Batch ID.")
        batch_name: str = Field(..., description="Human-readable batch name.")

        model_config = {"from_attributes": True}

    batches: list[BatchInfo] = Field(default_factory=list, description="Full batch details for each linked batch.")
    lessons: list[LessonSummaryResponse] = Field(default_factory=list, description="Lessons within this plan (non-deleted, ordered).")
    status: str = Field(..., description="Lesson plan status: 'active' or 'inactive'.")
    remarks: Optional[str] = Field(None, description="Optional teacher remarks.")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LessonPlanCreateResponse(BaseModel):
    message: str = Field(..., description="Human-readable result message.", example="Lesson plan created successfully.")
    lesson_plan_id: str = Field(..., description="ID of the created lesson plan.", example="LPABCD1234")
    status: str = Field(..., description="Status of the new lesson plan.", example="active")
