from sqlalchemy import Column, Integer, ForeignKey,String,DateTime,event,Text
from sqlalchemy.orm import relationship
from app.db.session import Base
from sqlalchemy.sql import func
from app.models.school import SchoolBoard,SchoolMedium
from enum import Enum
from sqlalchemy import Enum as SQLEnum
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