from sqlalchemy import Column,Boolean,Integer, String, Enum,DateTime,ForeignKey,UniqueConstraint,Index, TypeDecorator
from app.db.session import Base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship,validates
from sqlalchemy.exc import IntegrityError
from app.schemas.users import UserRole
from datetime import datetime, timezone,timedelta

class UserRoleEnum(TypeDecorator):
    """Custom type decorator to ensure enum values are used instead of names"""
    impl = String
    cache_ok = True
    
    def __init__(self):
        super().__init__(length=50)
    
    def process_bind_param(self, value, dialect):
        """Convert enum to its value when binding to database"""
        if value is None:
            return value
        if isinstance(value, UserRole):
            print(f'TypeDecorator: Converting enum {value} to value: {value.value}')
            return value.value  # Return "staff" not "STAFF"
        print(f'TypeDecorator: Received non-enum value: {value} (type: {type(value)})')
        return value
    
    def process_result_value(self, value, dialect):
        """Convert database value back to enum when reading"""
        if value is None:
            return value
        try:
            return UserRole(value)
        except ValueError:
            return value

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    location = Column(String)
    phone = Column(String)
    website = Column(String)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True)
    role = Column(UserRoleEnum(), nullable=False)
    created_at = Column(DateTime, default=func.now())
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    
    
    tokens = relationship("Token", back_populates="user",cascade="all,delete-orphan")
    otps = relationship("Otp", back_populates="user", cascade="all, delete-orphan")
    admin_profile = relationship("Admin", back_populates="user", uselist=False, cascade="all, delete-orphan")
    teacher_profile = relationship("Teacher", back_populates="user", uselist=False, cascade="all, delete-orphan")
    school_profile = relationship("School", back_populates="user", uselist=False, cascade="all, delete-orphan", overlaps="school")
    student_profile = relationship("Student", back_populates="user", uselist=False, cascade="all, delete-orphan")
    staff_profile = relationship("Staff", back_populates="user", uselist=False, cascade="all, delete-orphan")
    
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
    
    @validates('role')
    def validate_role(self, key, role):
        """Validate role - TypeDecorator will handle conversion to value"""
        if isinstance(role, UserRole):
            print(f'Role validator: received enum {role}, value is {role.value}')
            return role  # Return enum, TypeDecorator will convert to value
        if isinstance(role, str):
            # If it's already a string, convert to enum for validation
            try:
                enum_role = UserRole(role)
                print(f'Role validator: converted string "{role}" to enum {enum_role}, value is {enum_role.value}')
                return enum_role  # Return enum, TypeDecorator will convert to value
            except ValueError:
                valid_values = [e.value for e in UserRole]
                raise ValueError(f"Invalid role value '{role}'. Must be one of: {valid_values}")
        return role
    
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
    