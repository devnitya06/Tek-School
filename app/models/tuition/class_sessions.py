from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from app.db.session import Base


class TuitionTeachingSetupClassSession(Base):
    __tablename__ = "tuition_teaching_setup_class_sessions"

    __table_args__ = (
        UniqueConstraint("teaching_setup_id", "session_date", name="uq_tuition_class_session_setup_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    teaching_setup_id = Column(String, ForeignKey("tuition_teaching_setups.id"), nullable=False)
    session_date = Column(Date, nullable=False)
    status = Column(String(30), nullable=False, default="IN_PROGRESS")
    notes = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<TuitionTeachingSetupClassSession {self.teaching_setup_id}:{self.session_date}>"
