import time
import random
from abc import ABC, abstractmethod
from typing import List, Dict, Any


class NormalizedJob:
    """Standard shape every scraper must convert its data into."""
    def __init__(self, source_id: str, title: str, company: str, url: str,
                 salary: int = 0, description: str = ""):
        self.source_id = source_id
        self.title = title
        self.company = company
        self.url = url
        self.salary = salary
        self.description = description

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "company": self.company,
            "url": self.url,
            "salary": self.salary,
            "description": self.description,
        }


class BaseScraper(ABC):
    source_name: str = "unknown"
    max_retries: int = 3
    retry_delay: int = 2
    min_request_delay: float = 1.0  # minimum seconds between requests

    @abstractmethod
    def fetch(self) -> Any:
        pass

    @abstractmethod
    def parse(self, raw_data: Any) -> List[NormalizedJob]:
        pass

    def _polite_delay(self):
        delay = self.min_request_delay + random.uniform(0, 0.5)
        time.sleep(delay)

    def fetch_with_retry(self) -> Any:
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                self._polite_delay()
                return self.fetch()
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
        raise last_error

    def run(self) -> List[NormalizedJob]:
        raw_data = self.fetch_with_retry()
        return self.parse(raw_data)