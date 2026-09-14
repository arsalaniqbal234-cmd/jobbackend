from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from database import Base


class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    url = Column(String, nullable=False)
    salary = Column(Integer)
    salary_currency = Column(String(3))
    salary_period = Column(String(10))
    description = Column(Text)
    location = Column(String)
    is_remote = Column(Boolean, nullable=False, default=False, server_default="false")
    fingerprint = Column(String(64), unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class JobSource(Base):
    __tablename__ = "job_sources"
    source_id = Column(String, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    source = Column(String, nullable=False)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SavedSearch(Base):
    __tablename__ = "saved_searches"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    email = Column(String, nullable=False)
    keywords = Column(String, nullable=True)
    location = Column(String)
    min_salary = Column(Integer)
    filters = Column(JSON)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_notified_at = Column(DateTime(timezone=True))
    signature = Column(String(64))
    __table_args__ = (UniqueConstraint("user_id", "signature", name="uq_saved_search_signature"),)


class AlertDelivery(Base):
    __tablename__ = "alert_deliveries"
    id = Column(Integer, primary_key=True)
    search_id = Column(Integer, ForeignKey("saved_searches.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    payload = Column(JSON, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    first_attempt_at = Column(DateTime(timezone=True))
    next_attempt_at = Column(DateTime(timezone=True))
    sent_at = Column(DateTime(timezone=True))
    provider_id = Column(String)
    __table_args__ = (UniqueConstraint("search_id", "job_id", name="uq_alert_search_job"),)


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"
    id = Column(Integer, primary_key=True)
    source = Column(String, nullable=False, index=True)
    status = Column(String(20), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True))
    duration_ms = Column(Float)
    fetched = Column(Integer, nullable=False, default=0)
    added = Column(Integer, nullable=False, default=0)
    skipped = Column(Integer, nullable=False, default=0)
    error_code = Column(String(100))
