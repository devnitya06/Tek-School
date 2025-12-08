from sqlalchemy import Column, Integer, ForeignKey,String,DateTime,event,Text,Boolean,ARRAY,JSON,Float,UniqueConstraint
from sqlalchemy.orm import relationship
from app.db.session import Base
from sqlalchemy.sql import func
from app.models.school import SchoolBoard,SchoolMedium
from enum import Enum
from sqlalchemy import Enum as SQLEnum
import uuid
from datetime import datetime


class ExamType(str, Enum):
    mock = "mock"
    rank = "rank"


class QuestionType(str, Enum):
    short = "short"
    long = "long"


class AdminExamStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
class StudentExamStatus(str, Enum):
    pass_ = "pass"
    fail = "fail"
class SetType(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    ALL = "ALL"

class AdminExam(Base):
    __tablename__ = "admin_exams"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)

    school_class_subject_id = Column(Integer, ForeignKey("school_classes_subjects.id"), nullable=False)
    class_name = Column(String, nullable=False)
    subject = Column(String, nullable=False)

    exam_type = Column(SQLEnum(ExamType), nullable=False)
    question_type = Column(SQLEnum(QuestionType), nullable=False)
    passing_mark = Column(Integer, nullable=False)
    repeat = Column(Integer,default=0)
    duration = Column(Integer, nullable=False)
    exam_validity = Column(DateTime, nullable=True)
    description = Column(String, nullable=True)
    no_students_appeared = Column(Integer, default=0)
    status = Column(SQLEnum(AdminExamStatus), default=AdminExamStatus.ACTIVE, nullable=False)

    school_class_subject = relationship("SchoolClassSubject", back_populates="admin_exams")
    admin_exam_bank = relationship("AdminExamBank", back_populates="exam", cascade="all, delete")
    student_admin_exam_data = relationship("StudentAdminExamData", back_populates="exam", cascade="all, delete")

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.id:
            self.id = f"AEXM-{str(uuid.uuid4().int)[:6]}"


class AdminExamBank(Base):
    __tablename__ = "admin_exam_bank"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(String, ForeignKey("admin_exams.id", ondelete="CASCADE"))

    question = Column(Text, nullable=False)
    que_type = Column(SQLEnum(QuestionType), nullable=False)
    image = Column(String, nullable=True)

    # MCQ Fields
    option_a = Column(String(200), nullable=True)
    option_b = Column(String(200), nullable=True)
    option_c = Column(String(200), nullable=True)
    option_d = Column(String(200), nullable=True)
    correct_option = Column(ARRAY(String), nullable=True)

    # Descriptive Fields
    descriptive_answer = Column(Text, nullable=True)
    answer_keys = Column(ARRAY(String), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    exam = relationship("AdminExam", back_populates="admin_exam_bank")

class StudentAdminExamData(Base):
    __tablename__ = "student_admin_exam_data"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    exam_id = Column(String, ForeignKey("admin_exams.id", ondelete="CASCADE"), nullable=False)

    attempt_no = Column(Integer, default=1)
    answers = Column(JSON, nullable=False)
    result = Column(Float, nullable=True)
    status = Column(SQLEnum(StudentExamStatus), nullable=True)
    appeared_count = Column(Integer, default=0)
    class_rank = Column(Integer, nullable=True)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())

    student = relationship("Student", back_populates="admin_exam_data")

    exam = relationship("AdminExam", back_populates="student_admin_exam_data")

class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)

    user = relationship("User", back_populates="admin_profile")
    
class AccountConfiguration(Base):
    __tablename__ = "account_configuration"

    id = Column(Integer, primary_key=True, index=True)
    name= Column(String, nullable=False, unique=True)
    value=Column(Integer, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
class CreditConfiguration(Base):
    __tablename__ = "credit_configuration"

    id = Column(Integer, primary_key=True, index=True)
    standard_name = Column(String, nullable=False,unique=True)
    monthly_credit = Column(Integer, nullable=False)
    margin_up_to = Column(Integer, nullable=False)
    
    school_margins = relationship("SchoolMarginConfiguration", back_populates="credit_configuration")
    
class CreditMaster(Base):
    __tablename__ = "credit_master"
    id = Column(Integer, primary_key=True, index=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    self_added_credit = Column(Integer, nullable=True, default=0)
    earned_credit = Column(Integer, nullable=True, default=0)
    available_credit = Column(Integer, nullable=True, default=0)
    used_credit = Column(Integer, nullable=True, default=0)
    transfer_credit = Column(Integer, nullable=True, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    def calculate_available_credit(self):
        self.available_credit = (self.self_added_credit or 0) + (self.earned_credit or 0) - (self.used_credit or 0) - (self.transfer_credit or 0)

@event.listens_for(CreditMaster, "before_insert")
def calculate_available_before_insert(mapper, connection, target):
    target.calculate_available_credit()

@event.listens_for(CreditMaster, "before_update")
def calculate_available_before_update(mapper, connection, target):
    target.calculate_available_credit()

class SchoolClassSubject(Base):
    __tablename__ = "school_classes_subjects"

    id = Column(Integer, primary_key=True, index=True)
    school_board = Column(SQLEnum(SchoolBoard), nullable=True)
    school_medium = Column(SQLEnum(SchoolMedium), nullable=True)
    class_name = Column(String, nullable=True)
    subject = Column(String, nullable=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # ✅ Relationships
    chapters = relationship("Chapter", back_populates="school_class_subject", cascade="all, delete-orphan")
    admin_exams = relationship("AdminExam", back_populates="school_class_subject", cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint(
            "school_board", "school_medium", "class_name", "subject",
            name="uq_board_medium_class_subject"
        ),
    )

class Chapter(Base):
    __tablename__ = "chapters"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    school_class_subject_id = Column(Integer, ForeignKey("school_classes_subjects.id", ondelete="CASCADE"))

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # ✅ Relationships
    school_class_subject = relationship("SchoolClassSubject", back_populates="chapters")
    videos = relationship("ChapterVideo", back_populates="chapter", cascade="all, delete-orphan")
    images = relationship("ChapterImage", back_populates="chapter", cascade="all, delete-orphan")
    pdfs = relationship("ChapterPDF", back_populates="chapter", cascade="all, delete-orphan")
    qnas = relationship("ChapterQnA", back_populates="chapter", cascade="all, delete-orphan")
    student_progress = relationship("StudentChapterProgress", back_populates="chapter")



class ChapterVideo(Base):
    __tablename__ = "chapter_videos"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, nullable=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"))

    chapter = relationship("Chapter", back_populates="videos")


class ChapterImage(Base):
    __tablename__ = "chapter_images"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, nullable=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"))

    chapter = relationship("Chapter", back_populates="images")


class ChapterPDF(Base):
    __tablename__ = "chapter_pdfs"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, nullable=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"))

    chapter = relationship("Chapter", back_populates="pdfs")


class ChapterQnA(Base):
    __tablename__ = "chapter_qnas"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text, nullable=True)
    answer = Column(Text, nullable=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"))

    chapter = relationship("Chapter", back_populates="qnas")


class StudentChapterProgress(Base):
    __tablename__ = "student_chapter_progress"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"))
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"))
    last_read_at = Column(DateTime, default=func.now())

    student = relationship("Student", back_populates="chapter_progress")
    chapter = relationship("Chapter", back_populates="student_progress")    

class QuestionSet(Base):
    __tablename__ = "question_sets"

    id = Column(Integer, primary_key=True, index=True)
    board = Column(String(100), nullable=False)
    class_name= Column(String(50), nullable=False)
    set = Column(SQLEnum(SetType),default=SetType.A,nullable=False)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationship
    questions = relationship("QuestionSetBank", back_populates="question_set")

class QuestionSetBank(Base):
    __tablename__ = "question_set_bank"

    id = Column(Integer, primary_key=True, index=True)
    question_set_id = Column(Integer, ForeignKey("question_sets.id"))

    subject = Column(Integer, ForeignKey("school_classes_subjects.id"), nullable=False)
    year = Column(Integer, nullable=True)
    probability_ratio = Column(Integer, nullable=True)
    no_of_teacher_verified = Column(Integer, nullable=True)
    question = Column(Text, nullable=False)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationship
    question_set = relationship("QuestionSet", back_populates="questions")
    school_class_subject = relationship("SchoolClassSubject")