from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Time, Date
from sqlalchemy.orm import relationship
from app.db.session import Base

class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    gender = Column(String(10), nullable=False)
    dob = Column(Date, nullable=False)

    class_id = Column(Integer, ForeignKey("classes.id"))
    section_id = Column(Integer, ForeignKey("sections.id"))
    roll_no = Column(Integer, nullable=False)
    is_transport = Column(Boolean, default=True)

    driver_id = Column(Integer, ForeignKey("transports.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    school_id = Column(String, ForeignKey("schools.id"), nullable=True)

    # Relationships
    classes = relationship("Class", back_populates="students")
    section = relationship("Section",back_populates="students")
    driver = relationship("Transport", back_populates="students")
    user = relationship("User", back_populates="student_profile")
    school= relationship("School", back_populates="students")
    parent = relationship("Parent", back_populates="student", uselist=False)
    present_address = relationship("PresentAddress", back_populates="student", uselist=False)
    permanent_address = relationship("PermanentAddress", back_populates="student", uselist=False)
    attendances = relationship("Attendance", back_populates="student")

class Parent(Base):
    __tablename__ = "parents"

    id = Column(Integer, primary_key=True, index=True)
    parent_name = Column(String(100), nullable=False)
    relation = Column(String(50), nullable=False)
    phone = Column(String(15), nullable=False)
    email = Column(String(100), nullable=False, unique=True)
    occupation = Column(String(100), nullable=True)
    organization = Column(String(150), nullable=True)

    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, unique=True)

    student = relationship("Student", back_populates="parent")

class AddressMixin:
    enter_pin = Column(String(10), nullable=False)
    division = Column(String(100), nullable=True)
    district = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    country = Column(String(100), nullable=False)
    building = Column(String(150), nullable=True)
    house_no = Column(String(50), nullable=True)
    floor_name = Column(String(50), nullable=True)
    
class PresentAddress(Base, AddressMixin):
    __tablename__ = "present_addresses"

    id = Column(Integer, primary_key=True, index=True)
    is_this_permanent_as_well = Column(Boolean, default=False)

    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, unique=True)
    student = relationship("Student", back_populates="present_address")

class PermanentAddress(Base, AddressMixin):
    __tablename__ = "permanent_addresses"

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, unique=True)
    student = relationship("Student", back_populates="permanent_address")

