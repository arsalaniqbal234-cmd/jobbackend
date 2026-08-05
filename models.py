from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from database import Base

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(String, unique=True, index=True)
    title = Column(String, index=True)
    company = Column(String)
    salary = Column(Integer)
    url = Column(String, nullable=True)
    scraped_at = Column(DateTime(timezone=True), server_default=func.now())