from pydantic import BaseModel
from typing import List,Optional
from app.models.school import SchoolBoard,SchoolMedium
# Reuse previously defined base schemas
class AccountConfigurationBase(BaseModel):
    name: str
    value: int

class CreditConfigurationBase(BaseModel):
    standard_name: str
    monthly_credit: int
    margin_up_to: int

# Wrapper schema for POST request
class ConfigurationCreateSchema(BaseModel):
    account_configurations: List[AccountConfigurationBase]
    credit_configurations: List[CreditConfigurationBase]

class SchoolClassSubjectBase(BaseModel):
    school_board: Optional[SchoolBoard]
    school_medium: Optional[SchoolMedium]
    class_name: Optional[str]
    subject: Optional[str]

class ChapterQnABase(BaseModel):
    id: int | None = None
    question: str
    answer: str

class ChapterContentBase(BaseModel):
    id: int | None = None
    url: str

class ChapterCreate(BaseModel):
    title: str
    description: Optional[str] = None
    videos: Optional[List[ChapterContentBase]] = []
    images: Optional[List[ChapterContentBase]] = []
    pdfs: Optional[List[ChapterContentBase]] = []
    qnas: Optional[List[ChapterQnABase]] = []
class ChapterUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    videos: Optional[List[ChapterContentBase]] = []
    images: Optional[List[ChapterContentBase]] = []
    pdfs: Optional[List[ChapterContentBase]] = []
    qnas: Optional[List[ChapterQnABase]] = []