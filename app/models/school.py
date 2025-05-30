from sqlalchemy import Column, Integer, String, ForeignKey,Table,Time,UniqueConstraint,Date
from sqlalchemy.orm import relationship
from app.db.session import Base
import uuid
from enum import Enum
from sqlalchemy import Enum as SQLEnum

class SchoolType(str, Enum):
    PVT = "private"
    GOVT = "government"
    SEMI_GOVT = "semi-government"
    INTERNATIONAL = "international"

class SchoolMedium(str, Enum):
    ENGLISH = "english"
    HINDI = "hindi"
    BILINGUAL = "bilingual"
    OTHER = "other"

class SchoolBoard(str, Enum):
    CBSE = "cbse"
    ICSE = "icse"
    STATE = "stateboard"
    IB = "ib"
    OTHER = "other"
class School(Base):
    __tablename__ = "schools"

    id = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    # School Information
    school_name = Column(String, nullable=False)
    school_type = Column(SQLEnum(SchoolType), nullable=True)
    school_medium = Column(SQLEnum(SchoolMedium), nullable=True)
    school_board = Column(SQLEnum(SchoolBoard), nullable=True)
    establishment_year = Column(Integer, nullable=True)
    
    # Address Information
    profile_pic_url = Column(String, nullable=True)
    banner_pic_url = Column(String, nullable=True)
    pin_code = Column(String(10), nullable=True)
    block_division = Column(String)
    district = Column(String, nullable=True)
    state = Column(String, nullable=True)
    country = Column(String, nullable=False, default="India")
    
    # Contact Information
    school_email = Column(String, nullable=False)
    school_phone = Column(String(15), nullable=False)
    school_alt_phone = Column(String(15))
    school_website = Column(String)
    
    # Principal Information
    principal_name = Column(String, nullable=True)
    principal_designation = Column(String)
    principal_email = Column(String)
    principal_phone = Column(String(15))

    user = relationship("User", backref="school")
    teachers = relationship("Teacher", back_populates="school", cascade="all, delete-orphan")
    classes = relationship("Class", back_populates="school")
    subjects = relationship("Subject", back_populates="school")
    extra_activities = relationship("ExtraCurricularActivity", back_populates="school")
    sections = relationship("Section", back_populates="school")
    transports = relationship("Transport", back_populates="school")
    students = relationship("Student", back_populates="school")
    timetable_days = relationship("TimetableDay", back_populates="school", cascade="all, delete")
    timetable_periods = relationship("TimetablePeriod", back_populates="school", cascade="all, delete")

    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.id:
            self.id = f"SCH-{str(uuid.uuid4().int)[:6]}"
            
class_subjects = Table(
    "class_subjects",
    Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id")),
    Column("subject_id", Integer, ForeignKey("subjects.id")),
    Column("school_id", String, ForeignKey("schools.id"))
)



class_extra_curricular = Table(
    "class_extra_curricular",
    Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id")),
    Column("activity_id", Integer, ForeignKey("extra_curricular_activities.id")),
    Column("school_id", String, ForeignKey("schools.id"))
)

class_assigned_teachers = Table(
    "class_assigned_teachers",
    Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id")),
    Column("teacher_id", String, ForeignKey("teachers.id")),
    Column("school_id", String, ForeignKey("schools.id"))
)
class_section = Table(
    "class_section",
    Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id")),
    Column("section_id", Integer, ForeignKey("sections.id")),
    Column("school_id", String, ForeignKey("schools.id"))
)

class Section(Base):
    __tablename__ = "sections"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50))
    school_id = Column(String, ForeignKey("schools.id"))
    
    school = relationship("School", back_populates="sections")
    classes = relationship("Class", secondary=class_section, back_populates="sections")
    students = relationship("Student", back_populates="section")
    attendances = relationship("Attendance", back_populates="section")


# Subject Models
class Subject(Base):
    __tablename__ = "subjects"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    school_id = Column(String, ForeignKey("schools.id"))
    
    school = relationship("School", back_populates="subjects")
    classes = relationship("Class", secondary=class_subjects, back_populates="subjects")
    attendances = relationship("Attendance", back_populates="subject")

class class_optional_subjects(Base):
    __tablename__ = 'class_optional_subjects'
    
    class_id = Column(Integer, ForeignKey('classes.id', ondelete="CASCADE"), primary_key=True)
    subject_id = Column(Integer, ForeignKey('subjects.id', ondelete="CASCADE"), primary_key=True)
class ExtraCurricularActivity(Base):
    __tablename__ = "extra_curricular_activities"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    school_id = Column(String, ForeignKey("schools.id"))
    
    school = relationship("School", back_populates="extra_activities")
    classes = relationship("Class", secondary=class_extra_curricular, back_populates="extra_curricular_activities")

# Class Model (main table)
class Class(Base):
    __tablename__ = "classes"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    start_time = Column(Time)
    end_time = Column(Time)
    school_id = Column(String, ForeignKey("schools.id"))
    
    # Relationships
    school = relationship("School", back_populates="classes")
    students = relationship("Student", back_populates="classes")
    
    # Many-to-many relationships
    subjects = relationship(
        "Subject", 
        secondary=class_subjects,
        back_populates="classes"
    )
    optional_subjects = relationship(
        "Subject",
        secondary="class_optional_subjects",
        back_populates="classes"
    )
    
    assigned_teachers = relationship(
        "Teacher", 
        secondary=class_assigned_teachers,
        back_populates="assigned_classes"
    )
    extra_curricular_activities = relationship(
        "ExtraCurricularActivity", 
        secondary=class_extra_curricular,
        back_populates="classes"
    )
    sections = relationship(
        "Section", 
        secondary=class_section,
        back_populates="classes"
    )
    attendances = relationship("Attendance", back_populates="class_")
    
    # Unique constraint to prevent duplicate class names within a school
    __table_args__ = (
        UniqueConstraint('name', 'school_id', name='uq_class_name_school'),
    )            
            
class Transport(Base):
    __tablename__ = "transports"

    id = Column(Integer, primary_key=True, index=True)
    vechicle_name = Column(String(50), nullable=False)
    vechicle_number = Column(String(50), nullable=False)
    driver_name = Column(String(100), nullable=False)
    phone_no = Column(String(20), nullable=False)
    duty_start_time = Column(Time, nullable=False)
    duty_end_time = Column(Time, nullable=False)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    pickup_stops = relationship("PickupStop", back_populates="transport", cascade="all, delete-orphan")
    drop_stops = relationship("DropStop", back_populates="transport", cascade="all, delete-orphan")

    # Relationship to students
    students = relationship("Student", back_populates="driver")
    school = relationship("School", back_populates="transports")
    
class PickupStop(Base):
    __tablename__ = "pickup_stops"

    id = Column(Integer, primary_key=True, index=True)
    transport_id = Column(Integer, ForeignKey("transports.id"), nullable=False)
    stop_name = Column(String(100), nullable=False)
    stop_time = Column(Time, nullable=False)

    transport = relationship("Transport", back_populates="pickup_stops")

class DropStop(Base):
    __tablename__ = "drop_stops"

    id = Column(Integer, primary_key=True, index=True)
    transport_id = Column(Integer, ForeignKey("transports.id"), nullable=False)
    stop_name = Column(String(100), nullable=False)
    stop_time = Column(Time, nullable=False)

    transport = relationship("Transport", back_populates="drop_stops")
    

class Attendance(Base):
    __tablename__ = "attendances"
    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(Integer, ForeignKey("students.id"), nullable=True)
    teachers_id = Column(String, ForeignKey("teachers.id"), nullable=True)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    date = Column(Date, nullable=False)
    status = Column(String(1), nullable=False)

    student = relationship("Student", back_populates="attendances")
    teacher = relationship("Teacher", back_populates="attendances")
    class_ = relationship("Class", back_populates="attendances")
    section = relationship("Section", back_populates="attendances")
    subject = relationship("Subject", back_populates="attendances")

    __table_args__ = (
        UniqueConstraint('student_id', 'subject_id', 'date', name='uq_student_attendance'),
        UniqueConstraint('teachers_id', 'subject_id', 'class_id', 'section_id', 'date', name='uq_teacher_attendance'),
    )

class WeekDay(Enum):
    MONDAY = "Monday"
    TUESDAY = "Tuesday"
    WEDNESDAY = "Wednesday"
    THURSDAY = "Thursday"
    FRIDAY = "Friday"
    SATURDAY = "Saturday"
class TimetableDay(Base):
    __tablename__ = "timetable_days"

    id = Column(Integer, primary_key=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    day = Column(SQLEnum(WeekDay, name="weekday"), nullable=False) 

    periods = relationship("TimetablePeriod", back_populates="day", cascade="all, delete-orphan")
    school = relationship("School", back_populates="timetable_days")    
    
class TimetablePeriod(Base):
    __tablename__ = "timetable_periods"

    id = Column(Integer, primary_key=True)
    day_id = Column(Integer, ForeignKey("timetable_days.id"), nullable=False)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    period_number = Column(Integer, nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    teacher_id = Column(String, ForeignKey("teachers.id"), nullable=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    day = relationship("TimetableDay", back_populates="periods")
    school = relationship("School", back_populates="timetable_periods")
    teacher = relationship("Teacher",back_populates="timetable_periods")    
    subject = relationship("Subject")