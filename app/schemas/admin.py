from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Union
from app.models.school import SchoolBoard, SchoolMedium
from app.models.admin import ExamType, QuestionType, SetType, PlanDuration
from datetime import datetime, date, time


# FAQ Schemas
class FAQCreate(BaseModel):
    question: str = Field(..., min_length=1, description="FAQ question")
    answer: str = Field(..., min_length=1, description="FAQ answer")
    is_active: Optional[bool] = Field(True, description="Whether the FAQ is active")


class FAQUpdate(BaseModel):
    question: Optional[str] = Field(None, min_length=1, description="FAQ question")
    answer: Optional[str] = Field(None, min_length=1, description="FAQ answer")
    is_active: Optional[bool] = Field(None, description="Whether the FAQ is active")


class FAQResponse(BaseModel):
    id: int
    question: str
    answer: str
    created_by: int
    created_at: datetime
    updated_at: Optional[datetime]
    is_active: bool

    class Config:
        from_attributes = True


class SchoolFAQSelect(BaseModel):
    faq_ids: List[int] = Field(
        ..., description="List of FAQ IDs to assign to the school"
    )


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


class SchoolClassSubjectUpdate(BaseModel):
    school_board: Optional[SchoolBoard] = None
    school_medium: Optional[SchoolMedium] = None
    class_name: Optional[str] = None
    subject: Optional[str] = None


class ChapterQnABase(BaseModel):
    id: int | None = None
    question: str
    answer: str


class ChapterContentBase(BaseModel):
    id: int | None = None
    url: str


class ChapterKeyPointBase(BaseModel):
    point: str


class ChapterCreate(BaseModel):
    title: str
    description: Optional[str] = None
    # Business rule: Original book content is mandatory for chapters
    original_book_content: str
    summarized_content: Optional[str] = None
    videos: Optional[List[ChapterContentBase]] = []
    images: Optional[List[ChapterContentBase]] = []
    pdfs: Optional[List[ChapterContentBase]] = []
    qnas: Optional[List[ChapterQnABase]] = []
    keypoints: List[ChapterKeyPointBase] = []


class ChapterUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    videos: Optional[List[ChapterContentBase]] = None
    images: Optional[List[ChapterContentBase]] = None
    pdfs: Optional[List[ChapterContentBase]] = None
    qnas: Optional[List[ChapterQnABase]] = None
    keypoints: Optional[List[ChapterKeyPointBase]] = None


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
    class_id: int
    duration: PlanDuration
    amount: int = Field(..., gt=0)


class RechargePlanResponse(BaseModel):
    id: int
    class_id: int
    duration: PlanDuration
    amount: int
    validity_days: int
    is_active: bool
    model_config = {"from_attributes": True}


class SchoolClassMiniResponse(BaseModel):
    id: int
    class_name: str
    model_config = {"from_attributes": True}


class RechargePlanListResponse(BaseModel):
    id: int
    duration: PlanDuration
    amount: int
    validity_days: int
    school_class_subject: SchoolClassMiniResponse

    model_config = {"from_attributes": True}


class StudentPurchaseRequest(BaseModel):
    duration: PlanDuration


class StudentPurchaseResponse(BaseModel):
    subscription_id: int
    payment_id: int
    amount: int
    currency: str = "INR"
    status: str


class AccountConfigurationCreate(BaseModel):
    name: str
    value: int


class AccountConfigurationUpdate(BaseModel):
    value: int


class AccountConfigurationResponse(BaseModel):
    id: int
    name: str
    value: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaymentConfigurationCreate(BaseModel):
    class_id: int

    monthly_amount: int
    monthly_discount: int

    quarterly_amount: int
    quarterly_discount: int

    half_yearly_amount: int
    half_yearly_discount: int

    yearly_amount: int
    yearly_discount: int


class PaymentConfigurationUpdate(BaseModel):
    monthly_amount: int
    monthly_discount: int

    quarterly_amount: int
    quarterly_discount: int

    half_yearly_amount: int
    half_yearly_discount: int

    yearly_amount: int
    yearly_discount: int


class PaymentConfigurationResponse(BaseModel):
    id: int
    class_id: int

    monthly_amount: int
    monthly_discount: int
    quarterly_amount: int
    quarterly_discount: int
    half_yearly_amount: int
    half_yearly_discount: int
    yearly_amount: int
    yearly_discount: int

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# Exam and Question Bank


class MarksConfig(BaseModel):
    mcq: int = 2
    short: int = 2
    long: int = 10


class QuestionBankCreate(BaseModel):
    board: SchoolBoard
    medium: SchoolMedium
    school_class_subject_id: int
    subject_id: int


class OptionCreate(BaseModel):
    option_text: str
    is_correct: bool = False


class AnswerCreate(BaseModel):
    answer_text: str


class KeyPointCreate(BaseModel):
    key_point: str


class QuestionCreate(BaseModel):
    question_type: QuestionType
    question_text: str

    options: list[OptionCreate] | None = None
    answer: AnswerCreate | None = None
    key_points: list[KeyPointCreate] | None = None


class QuestionCountSchema(BaseModel):
    total: int
    mcq: int
    short: int
    long: int


class ChapterOut(BaseModel):
    id: int
    name: str


class QuestionBankListOut(BaseModel):
    id: int

    school_board: SchoolBoard
    school_medium: SchoolMedium
    class_name: str
    subject: str

    chapter: ChapterOut

    marks_config: dict
    question_counts: QuestionCountSchema

    created_at: datetime


class OptionCreate(BaseModel):
    option_text: str
    is_correct: bool = False


class AnswerCreate(BaseModel):
    answer_text: str


class KeyPointCreate(BaseModel):
    key_point: str


class QuestionCreate(BaseModel):
    chapter_id: Optional[int] = None
    question_type: QuestionType
    marks: int
    question_text: str
    image: Optional[str] = None
    source: Optional[str] = None

    options: Optional[List[OptionCreate]] = None
    answer: Optional[AnswerCreate] = None
    key_points: Optional[List[KeyPointCreate]] = None


class QuestionBulkCreate(BaseModel):
    questions: list[QuestionCreate]


class QuestionBankListResponse(BaseModel):
    id: int
    board: Optional[str]
    medium: Optional[str]

    class_name: Optional[str]
    class_id: Optional[int]
    subject_name: Optional[str]
    subject_id: Optional[int]
    mcq_count: int
    short_count: int
    long_count: int
    total_questions: int

    created_by: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class QuestionBankDetailResponse(BaseModel):
    id: int
    board: Optional[str]
    medium: Optional[str]

    class_name: Optional[str]
    subject_name: Optional[str]

    mcq_count: int
    short_count: int
    long_count: int
    total_questions: int

    created_by: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class QuestionBankUpdate(BaseModel):
    board: Optional[SchoolBoard] = None
    medium: Optional[SchoolMedium] = None
    school_class_subject_id: Optional[int] = None
    subject_id: Optional[int] = None


class HolidayMasterBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    type: str = Field(..., min_length=2, max_length=100)
    date: date
    description: Optional[str] = Field(None, max_length=500)

    @field_validator("name", "type")
    @classmethod
    def strip_values(cls, v: str):
        return v.strip()


class HolidayMasterCreate(HolidayMasterBase):
    pass


class HolidayMasterUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    type: Optional[str] = Field(None, min_length=2, max_length=100)
    date: Optional[date] = None
    description: Optional[str] = Field(None, max_length=500)

    @field_validator("name", "type")
    @classmethod
    def strip_values(cls, v):
        if v:
            return v.strip()
        return v


class HolidayMasterResponse(HolidayMasterBase):
    id: int
    file: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str