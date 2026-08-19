from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.placement import PlacementStatus


class PlacementPartnerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    school_id: str
    company_logo: Optional[str] = None
    company_name: str
    website: str
    placement_year: int
    campus_month: Optional[int] = Field(None, ge=1, le=12)
    about_company: Optional[str] = None
    hiring_criteria: Optional[str] = None
    what_they_give: Optional[str] = None
    no_of_placement: int = 0
    status: PlacementStatus
    created_at: datetime
    updated_at: datetime


class PlacementPartnerListItem(BaseModel):
    id: int
    company_name: str
    placement_year: int
    no_of_placement: int
    created_at: datetime
    status: PlacementStatus


class PlacementAchieverResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    school_id: str
    student_logo: Optional[str] = None
    student_name: str
    gender: str
    class_name: str
    section_roll_no: Optional[str] = None
    company_id: int
    company_name: str
    designation: str
    salary_package_lpa: str
    placement_year: int
    about_student: Optional[str] = None
    file: Optional[str] = None
    status: PlacementStatus
    created_at: datetime
    updated_at: datetime


class PlacementAchieverListItem(BaseModel):
    id: int
    student_name: str
    class_name: str
    company_name: str
    placement_year: int
    salary_package_lpa: str
    created_at: datetime
    status: PlacementStatus


class PlacementPage(BaseModel):
    page: int
    per_page: int
    total_count: int
    total_pages: int
    items: list