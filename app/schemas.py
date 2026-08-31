from typing import Optional
from pydantic import BaseModel

class JobBase(BaseModel):
    source_id: str
    title: str
    company: str
    url: str
    salary: Optional[int] = None
    salary_currency: Optional[str] = None
    salary_period: Optional[str] = None
    description: Optional[str] = None

class JobResponse(JobBase):
    id: int

    class Config:
        from_attributes = True