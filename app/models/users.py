from sqlalchemy import Column,Boolean,Integer, String, Enum,DateTime,ForeignKey,UniqueConstraint,Index
from app.db.session import Base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship,validates
from sqlalchemy.exc import IntegrityError
from app.schemas.users import UserRole
from datetime import datetime, timezone,timedelta

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    location = Column(String)
    phone = Column(String)
    website = Column(String)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True)
    role = Column(Enum(UserRole), nullable=False)
    created_at = Column(DateTime, default=func.now())
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    
    
    tokens = relationship("Token", back_populates="user",cascade="all,delete-orphan")
    otps = relationship("Otp", back_populates="user", cascade="all, delete-orphan")
    admin_profile = relationship("Admin", back_populates="user", uselist=False, cascade="all, delete-orphan")
    teacher_profile = relationship("Teacher", back_populates="user", uselist=False, cascade="all, delete-orphan")
    school_profile = relationship("School", back_populates="user", uselist=False, cascade="all, delete-orphan")
    student_profile = relationship("Student", back_populates="user", uselist=False, cascade="all, delete-orphan")
    
    # Add unique constraint for school name and location
    __table_args__ = (
        Index(
            'uq_school_name_location',
            'name',
            'location',
            unique=True,
            postgresql_where=(role == 'SCHOOL')  # conditional index
        ),
    )
    
    @validates('phone')
    def validate_phone(self, key, phone):
        if phone is not None and len(phone) != 10:
            raise ValueError("Phone number must be 10 digits")
        if not phone.isdigit():
            raise ValueError("Phone number must contain only digits")
        return phone
    
    def verify_password(self, password: str):
        from app.core.security import verify_password
        return verify_password(password, self.hashed_password)
    
class Token(Base):
    __tablename__ = "tokens"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    expires_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    
    user=relationship("User", back_populates="tokens")    

class Otp(Base):
    __tablename__ = "otps"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    otp = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime, default=lambda: datetime.now(timezone.utc) + timedelta(minutes=5))
    is_verified=Column(Boolean,default=False)
    
    user = relationship("User", back_populates="otps")
    
class Template(Base):
    __tablename__ = "templates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    context = Column(String, nullable=False)
    body = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    