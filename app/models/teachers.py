from sqlalchemy import Column, Integer, String, ForeignKey, Time, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from app.db.session import Base
from enum import Enum
import uuid
from datetime import time

# Define Python Enum for teacher_type
class TeacherTypeEnum(str, Enum):
    full_time = "full_time"
    part_time = "part_time"

class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(String, primary_key=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    highest_qualification = Column(String, nullable=False)
    university = Column(String, nullable=False)
    phone = Column(String(10), nullable=False)
    email = Column(String, unique=True, nullable=False)
    teacher_in_classes = Column(ARRAY(String), nullable=False)  # ["5th", "7th"]
    subjects = Column(ARRAY(String), nullable=False)            # ["Math", "Sci"]
    start_duty = Column(Time, nullable=False)                   # 10:30 AM
    end_duty = Column(Time, nullable=False)                    # 5:00 PM
    teacher_type = Column(SQLEnum(TeacherTypeEnum), nullable=False)
    present_in = Column(ARRAY(String), nullable=False)          # ["Mon", "Wed", "Fri"]

    # Foreign keys
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Nullable until account is created

    # Relationships
    school = relationship("School", back_populates="teachers")
    user = relationship("User", back_populates="teacher_profile")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.id:
            self.id = f"TCH-{str(uuid.uuid4().int)[:6]}"