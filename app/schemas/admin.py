from pydantic import BaseModel, Field
from typing import List,Optional,Union
from app.models.school import SchoolBoard,SchoolMedium
from app.models.admin import ExamType,QuestionType,SetType,PlanDuration
from datetime import datetime,date,time
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
class AdminExamBase(BaseModel):
    name: str
    school_class_subject_id: int
    exam_type: ExamType
    question_type: QuestionType
    passing_mark: int
    repeat: int = 0
    duration: int
    exam_validity: Optional[datetime] = None
    description: Optional[str] = None


class AdminExamCreate(AdminExamBase):
    pass
class AdminExamUpdate(BaseModel):
    name: Optional[str] = None
    exam_type: Optional[ExamType] = None
    passing_mark: Optional[int] = None
    repeat: Optional[bool] = None
    duration: Optional[int] = None
    exam_validity: Optional[date] = None
    description: Optional[str] = None

class ExamQuestionPayload(BaseModel):
    que_type: QuestionType
    question: str
    image: Optional[str] = None

    # Short / MCQ fields
    option_a: Optional[str] = None
    option_b: Optional[str] = None
    option_c: Optional[str] = None
    option_d: Optional[str] = None
    correct_option: Optional[List[str]] = None

    # Long / Descriptive fields
    descriptive_answer: Optional[str] = None
    answer_keys: Optional[List[str]] = None


class ExamQuestionPayloadList(BaseModel):
    questions: List[ExamQuestionPayload]

class QuestionSetCreate(BaseModel):
    board: str
    class_name: str
    set: SetType
    description: Optional[str] = None

class QuestionCreate(BaseModel):
    subject_id: int
    year: int
    question: str
    probability_ratio: float
    teacher_verified_count: int

class BulkQuestionCreate(BaseModel):
    questions: List[QuestionCreate]
class QuestionUpdate(BaseModel):
    subject_id: Optional[int] = None
    year: Optional[int] = None
    probability_ratio: Optional[int] = None
    no_of_teacher_verified: Optional[int] = None
    question: Optional[str] = None

class StudentAnswer(BaseModel):
    question_id: int
    selected_option: Union[str, List[str]]


class StudentExamSubmitRequest(BaseModel):
    answers: List[StudentAnswer]

class RechargePlanCreate(BaseModel):
    class_name: str = Field(..., min_length=1)
    duration: PlanDuration
    amount: int = Field(..., gt=0)

class RechargePlanResponse(BaseModel):
    id: int
    class_name: str
    duration: PlanDuration
    amount: int
    validity_days: int
    is_active: bool
    model_config = {
        "from_attributes": True
    }
class RechargePlanListResponse(BaseModel):
    id: int
    class_name: str
    duration: PlanDuration
    amount: int
    validity_days: int

    model_config = {
        "from_attributes": True
    }

class StudentPurchaseRequest(BaseModel):
    duration: PlanDuration
class StudentPurchaseResponse(BaseModel):
    subscription_id: int
    payment_id: int
    amount: int
    currency: str = "INR"
    status: str
