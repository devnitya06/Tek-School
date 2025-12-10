from sqlalchemy import Column, Integer, ForeignKey,String,DateTime,event
from sqlalchemy.orm import relationship
from app.db.session import Base
from sqlalchemy.sql import func
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