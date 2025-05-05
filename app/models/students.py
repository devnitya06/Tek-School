from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.db.session import Base

class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    student_name = Column(String, nullable=False)
    student_age = Column(Integer)
    student_class = Column(String)

    user = relationship("User", backref="student_profile")
