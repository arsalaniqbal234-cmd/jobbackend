from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class JobResponse(BaseModel):
    id: int
    source_id: str
    title: str
    company: str
    url: str
    salary: Optional[int] = None
    salary_currency: Optional[str] = None
    salary_period: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    is_remote: bool = False
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class SearchFilters(BaseModel):
    salary_only: bool = False
    remote_only: bool = False
    salary_currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    salary_period: str = Field(default="annual", pattern="^(annual|monthly|hourly)$")
    model_config = ConfigDict(extra="forbid")


class SavedSearchCreate(BaseModel):
    keywords: str = Field(min_length=1, max_length=200)
    location: Optional[str] = Field(default=None, max_length=200)
    min_salary: Optional[int] = Field(default=None, ge=0, le=1000000000)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    model_config = ConfigDict(extra="forbid")

    @field_validator("keywords")
    @classmethod
    def clean_keywords(cls, value):
        value = " ".join(value.split())
        if not value:
            raise ValueError("Enter a search keyword")
        return value

    @field_validator("location")
    @classmethod
    def clean_location(cls, value):
        return " ".join(value.split()) or None if value else None


class SavedSearchResponse(BaseModel):
    id: int
    user_id: str
    email: EmailStr
    keywords: Optional[str] = None
    location: Optional[str] = None
    min_salary: Optional[int] = None
    filters: Optional[dict] = None
    is_active: bool
    created_at: datetime
    last_notified_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)
