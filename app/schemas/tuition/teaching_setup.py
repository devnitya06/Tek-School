from datetime import date, datetime, time
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl


class TeachingSetupCreate(BaseModel):
    teaching_mode: str
    lesson_plan_id: str
    batch_id: Optional[str] = None
    batch_title: Optional[str] = None
    batch_start_date: Optional[date] = None
    batch_end_date: Optional[date] = None
    tuition_from_time: Optional[time] = None
    tuition_to_time: Optional[time] = None
    tuition_days: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    subjects: List[str] = Field(default_factory=list)
    material_update_days: List[str] = Field(default_factory=list)
    upload_from_time: Optional[time] = None
    upload_to_time: Optional[time] = None
    monthly_tuition_fee: Optional[float] = None
    monthly_tuition_discount: Optional[float] = None
    premium_study_material_fee: Optional[float] = None
    premium_study_material_discount: Optional[float] = None
    maximum_students: Optional[int] = 200
    meeting_provider: Optional[str] = None
    meeting_link: Optional[HttpUrl] = None
    online_teaching_ability: Optional[bool] = None
    stable_internet_connection: Optional[bool] = None
    camera_available: Optional[bool] = None
    silent_place_without_background_noise: Optional[bool] = None
    laptop_desktop_pc: Optional[bool] = None
    headphone_whiteboard: Optional[bool] = None
    status: Optional[str] = "ACTIVE"


class TeachingSetupUpdate(BaseModel):
    teaching_mode: Optional[str] = None
    lesson_plan_id: Optional[str] = None
    batch_id: Optional[str] = None
    batch_title: Optional[str] = None
    batch_start_date: Optional[date] = None
    batch_end_date: Optional[date] = None
    tuition_from_time: Optional[time] = None
    tuition_to_time: Optional[time] = None
    tuition_days: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    subjects: Optional[List[str]] = None
    material_update_days: Optional[List[str]] = None
    upload_from_time: Optional[time] = None
    upload_to_time: Optional[time] = None
    monthly_tuition_fee: Optional[float] = None
    monthly_tuition_discount: Optional[float] = None
    premium_study_material_fee: Optional[float] = None
    premium_study_material_discount: Optional[float] = None
    maximum_students: Optional[int] = None
    meeting_provider: Optional[str] = None
    meeting_link: Optional[HttpUrl] = None
    online_teaching_ability: Optional[bool] = None
    stable_internet_connection: Optional[bool] = None
    camera_available: Optional[bool] = None
    silent_place_without_background_noise: Optional[bool] = None
    laptop_desktop_pc: Optional[bool] = None
    headphone_whiteboard: Optional[bool] = None
    status: Optional[str] = None


class TeachingSetupStatusUpdate(BaseModel):
    status: str


class TeachingSetupCreateResponse(BaseModel):
    message: str
    teaching_setup_id: str


class TeachingSetupSummaryResponse(BaseModel):
    id: str
    lesson_plan_id: Optional[str] = None
    batch_id: Optional[str] = None
    lesson_plan_title: Optional[str] = None
    batch_name: Optional[str] = None
    subject_name: Optional[str] = None
    teaching_mode: str
    monthly_tuition_fee: float
    monthly_tuition_discount: float
    final_tuition_fee: float
    premium_study_material_fee: float
    premium_study_material_discount: float
    final_premium_fee: float
    joined_students_count: int
    maximum_students: int
    available_seats: int
    average_rating: float
    total_reviews: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TeachingSetupDetailResponse(BaseModel):
    id: str
    lesson_plan_id: Optional[str] = None
    batch_id: Optional[str] = None
    lesson_plan_title: Optional[str] = None
    batch_name: Optional[str] = None
    subject_name: Optional[str] = None
    teaching_mode: str
    batch_title: Optional[str] = None
    batch_start_date: Optional[date] = None
    batch_end_date: Optional[date] = None
    tuition_from_time: Optional[time] = None
    tuition_to_time: Optional[time] = None
    tuition_days: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    subjects: List[str] = Field(default_factory=list)
    material_update_days: List[str] = Field(default_factory=list)
    upload_from_time: Optional[time] = None
    upload_to_time: Optional[time] = None
    monthly_tuition_fee: float
    monthly_tuition_discount: float
    final_tuition_fee: float
    premium_study_material_fee: float
    premium_study_material_discount: float
    final_premium_fee: float
    joined_students_count: int
    maximum_students: int
    available_seats: int
    average_rating: float
    total_reviews: int
    meeting_provider: Optional[str] = None
    meeting_link: Optional[str] = None
    online_teaching_ability: Optional[bool] = None
    stable_internet_connection: Optional[bool] = None
    camera_available: Optional[bool] = None
    silent_place_without_background_noise: Optional[bool] = None
    laptop_desktop_pc: Optional[bool] = None
    headphone_whiteboard: Optional[bool] = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TeachingSetupListResponse(BaseModel):
    items: List[TeachingSetupSummaryResponse] = Field(default_factory=list)
    total: int
