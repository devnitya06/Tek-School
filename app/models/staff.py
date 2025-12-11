from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Numeric, Table, Enum as SQLEnum, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from enum import Enum as PyEnum

from app.db.session import Base

import uuid


class StaffPermissionType(str, PyEnum):
    TEACHER = "teacher"
    STUDENTS = "students"
    CLASS_AND_TIMETABLE = "class_and_timetable"
    EXAMS = "exams"
    TRANSPORT = "transport"
    PAYMENTS = "payments"
    LEAVE_REQUEST = "leave_request"
    HELP_DESK = "help_desk"


# Many-to-many relationship table for Staff and Permissions
staff_permissions = Table(
    "staff_permissions",
    Base.metadata,
    Column("staff_id", String, ForeignKey("staff.id", ondelete="CASCADE"), primary_key=True),
    Column("permission", SQLEnum(StaffPermissionType), primary_key=True),
    Column("granted_at", DateTime, server_default=func.now()),
    Column("granted_by", Integer, ForeignKey("users.id"), nullable=True)  # School user who granted it
)


class Staff(Base):
    __tablename__ = "staff"

    id = Column(String, primary_key=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    phone = Column(String(15), nullable=True)
    designation = Column(String, nullable=True)
    employee_type = Column(String, nullable=True)  # "full_time" or "part_time"
    annual_salary = Column(Numeric(12, 2), nullable=True)
    emergency_leave = Column(Integer, nullable=True, default=0)
    casual_leave = Column(Integer, nullable=True, default=0)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    school = relationship("School", back_populates="staff_members")
    user = relationship("User", back_populates="staff_profile")
    attendances = relationship("Attendance", back_populates="staff")
    leave_requests = relationship("LeaveRequest", back_populates="staff", cascade="all, delete")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.id:
            self.id = f"STF-{str(uuid.uuid4().int)[:6]}"


class ActionType(str, PyEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    APPROVE = "approve"
    DECLINE = "decline"


class ResourceType(str, PyEnum):
    STUDENT = "student"
    TEACHER = "teacher"
    LEAVE_REQUEST = "leave_request"
    CLASS = "class"
    TRANSPORT = "transport"


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)  # User who performed the action
    user_role = Column(String, nullable=False)  # Role of the user (school, staff, teacher, etc.)
    school_id = Column(String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    action_type = Column(SQLEnum(ActionType), nullable=False)  # create, update, delete, approve, decline
    resource_type = Column(SQLEnum(ResourceType), nullable=False)  # student, teacher, leave_request, class, transport
    resource_id = Column(String, nullable=True)  # ID of the resource that was acted upon
    description = Column(Text, nullable=True)  # Human-readable description
    action_metadata = Column(JSON, nullable=True)  # Additional data about the action
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="activity_logs")
    school = relationship("School", backref="activity_logs")

