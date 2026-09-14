import random
import time
from abc import ABC, abstractmethod
from typing import Any

import requests
from pydantic import BaseModel, Field, HttpUrl, ValidationError, field_validator


class NormalizedJob(BaseModel):
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    url: HttpUrl
    salary: int | None = Field(default=None, ge=0, le=2147483647)
    salary_currency: str | None = None
    salary_period: str | None = None
    description: str = ""
    location: str | None = None
    is_remote: bool = False
    raw_data: dict = Field(default_factory=dict)

    @field_validator("title", "company")
    @classmethod
    def clean_text(cls, value):
        value = " ".join(value.split())
        if not value:
            raise ValueError("Empty job field")
        return value

    def to_dict(self):
        return self.model_dump(mode="json")


class BaseScraper(ABC):
    source_name = "unknown"
    max_retries = 3
    retry_delay = 2
    min_request_delay = 1.0

    @abstractmethod
    def fetch(self) -> Any:
        pass

    @abstractmethod
    def parse(self, raw_data: Any) -> list[NormalizedJob]:
        pass

    def normalize(self, records):
        result = []
        for record in records:
            try:
                result.append(NormalizedJob(**record))
            except ValidationError:
                # One malformed entry must not discard all other valid jobs.
                continue
        return result

    def fetch_with_retry(self):
        for attempt in range(self.max_retries):
            time.sleep(self.min_request_delay + random.uniform(0, 0.5))
            try:
                return self.fetch()
            except requests.RequestException as error:
                response = error.response
                retryable = response is None or response.status_code == 429 or response.status_code >= 500
                if not retryable or attempt == self.max_retries - 1:
                    raise
                delay = self.retry_delay * (2 ** attempt)
                if response is not None:
                    try:
                        delay = max(delay, min(60, float(response.headers.get("Retry-After", "0"))))
                    except ValueError:
                        pass
                time.sleep(delay)
        raise RuntimeError("Scraper retries exhausted")

    def run(self):
        return self.parse(self.fetch_with_retry())
