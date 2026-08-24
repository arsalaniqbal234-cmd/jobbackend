from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class JobResponse(BaseModel):
    id: int
    source_id: Optional[str]
    title: str
    company: str
    salary: int
    url: Optional[str]
    description: Optional[str] = None  # <-- Added optional description
    scraped_at: Optional[datetime]

    class Config:
        from_attributes = True