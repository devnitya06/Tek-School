from sqlalchemy import Column, Integer, String, ForeignKey,Table,Time,UniqueConstraint
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
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.id:
            self.id = f"SCH-{str(uuid.uuid4().int)[:6]}"
            
class_mandatory_subjects = Table(
    "class_mandatory_subjects",
    Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id")),
    Column("subject_id", Integer, ForeignKey("mandatory_subjects.id")),
    Column("school_id", Integer, ForeignKey("schools.id"))
)

class_optional_subjects = Table(
    "class_optional_subjects",
    Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id")),
    Column("subject_id", Integer, ForeignKey("optional_subjects.id")),
    Column("school_id", Integer, ForeignKey("schools.id"))
)

class_extra_curricular = Table(
    "class_extra_curricular",
    Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id")),
    Column("activity_id", Integer, ForeignKey("extra_curricular_activities.id")),
    Column("school_id", Integer, ForeignKey("schools.id"))
)

class_assigned_teachers = Table(
    "class_assigned_teachers",
    Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id")),
    Column("teacher_id", Integer, ForeignKey("teachers.id")),
    Column("school_id", Integer, ForeignKey("schools.id"))
)
class_section = Table(
    "class_section",
    Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id")),
    Column("section_id", Integer, ForeignKey("sections.id")),
    Column("school_id", Integer, ForeignKey("schools.id"))
)

class Section(Base):
    __tablename__ = "sections"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50))
    school_id = Column(Integer, ForeignKey("schools.id"))
    
    school = relationship("School", back_populates="mandatory_subjects")
    classes = relationship("Class", secondary="class_section", back_populates="class_section")

# Subject Models
class MandatorySubject(Base):
    __tablename__ = "mandatory_subjects"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    school_id = Column(Integer, ForeignKey("schools.id"))
    
    school = relationship("School", back_populates="mandatory_subjects")
    classes = relationship("Class", secondary=class_mandatory_subjects, back_populates="mandatory_subjects")

class OptionalSubject(Base):
    __tablename__ = "optional_subjects"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    school_id = Column(Integer, ForeignKey("schools.id"))
    
    school = relationship("School", back_populates="optional_subjects")
    classes = relationship("Class", secondary=class_optional_subjects, back_populates="optional_subjects")

# Extra Curricular Activity Model
class ExtraCurricularActivity(Base):
    __tablename__ = "extra_curricular_activities"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    school_id = Column(Integer, ForeignKey("schools.id"))
    
    school = relationship("School", back_populates="extra_curricular_activities")
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
    
    # Many-to-many relationships
    mandatory_subjects = relationship(
        "MandatorySubject", 
        secondary=class_mandatory_subjects,
        back_populates="classes"
    )
    optional_subjects = relationship(
        "OptionalSubject", 
        secondary=class_optional_subjects,
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
    class_section = relationship(
        "Class", 
        secondary=class_section,
        back_populates="classes"
    )
    
    # Unique constraint to prevent duplicate class names within a school
    __table_args__ = (
        UniqueConstraint('name', 'school_id', name='uq_class_name_school'),
    )            
            
# class_mandatory_subjects = Table(
#     'class_mandatory_subjects',
#     Base.metadata,
#     Column('class_id', Integer, ForeignKey('classes.id')),
#     Column('subject_id', Integer, ForeignKey('subjects.id'))
# )

# class_optional_subjects = Table(
#     'class_optional_subjects',
#     Base.metadata,
#     Column('class_id', Integer, ForeignKey('classes.id')),
#     Column('subject_id', Integer, ForeignKey('subjects.id'))
# )

# class_extra_curriculums = Table(
#     'class_extra_curriculums',
#     Base.metadata,
#     Column('class_id', Integer, ForeignKey('classes.id')),
#     Column('extra_id', Integer, ForeignKey('extra_curriculums.id'))
# )                  
# class_teachers = Table(
#     'class_teachers',
#     Base.metadata,
#     Column('class_id', Integer, ForeignKey('classes.id')),
#     Column('teacher_id', String, ForeignKey('teachers.id'))
# )                  

# class Subject(Base):
#     __tablename__ = 'subjects'

#     id = Column(Integer, primary_key=True)
#     name = Column(String, unique=True, nullable=False)


# class ExtraCurriculum(Base):
#     __tablename__ = 'extra_curriculums'

#     id = Column(Integer, primary_key=True)
#     name = Column(String, unique=True, nullable=False)

# class Class(Base):
#     __tablename__ = 'classes'

#     id = Column(Integer, primary_key=True, index=True)
#     class_name = Column(String, nullable=False)      # e.g., "10th"
#     section = Column(String, nullable=False)         # e.g., "A", "B"

#     start_time = Column(Time, nullable=True)
#     end_time = Column(Time, nullable=True)

#     assigned_teachers = relationship("Teacher",secondary=class_teachers)
#     mandatory_subjects = relationship("Subject", secondary=class_mandatory_subjects)
#     optional_subjects = relationship("Subject", secondary=class_optional_subjects)
#     extra_curriculums = relationship("ExtraCurriculum", secondary=class_extra_curriculums)