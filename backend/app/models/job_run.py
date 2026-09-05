"""Persistent execution history for scheduled and manual jobs."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    desc,
)
from sqlalchemy.orm import relationship

from app.core.timezone import utc_now
from app.db.database import Base


class DailyJobRun(Base):
    __tablename__ = "daily_job_runs"

    id = Column(Integer, primary_key=True)
    job_name = Column(String(80), nullable=False)
    trigger_source = Column(String(20), nullable=False)
    target_date = Column(Date, nullable=False)
    timezone_name = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    finished_at = Column(DateTime(timezone=True))
    initiated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    summaries_created = Column(Integer)
    alerts_created = Column(Integer)
    error_message = Column(Text)

    initiator = relationship("User")

    __table_args__ = (
        CheckConstraint(
            "trigger_source IN ('scheduled', 'manual')",
            name="ck_daily_job_runs_trigger_source",
        ),
        CheckConstraint(
            "status IN ('running', 'success', 'failed')",
            name="ck_daily_job_runs_status",
        ),
        Index("idx_daily_job_runs_started", desc("started_at")),
        Index("idx_daily_job_runs_job_target", "job_name", "target_date"),
        Index("idx_daily_job_runs_status", "status"),
    )
