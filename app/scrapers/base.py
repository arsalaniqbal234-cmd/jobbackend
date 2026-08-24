from abc import ABC, abstractmethod
from typing import List, Dict, Any


class NormalizedJob:
    """
    Standard shape every scraper must convert its data into,
    regardless of which site it came from.
    """
    def __init__(
        self, 
        source_id: str, 
        title: str, 
        company: str, 
        url: str, 
        salary: int = 0, 
        description: str = ""  # <-- Added description parameter
    ):
        self.source_id = source_id
        self.title = title
        self.company = company
        self.url = url
        self.salary = salary
        self.description = description  # <-- Assigned to instance

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "company": self.company,
            "url": self.url,
            "salary": self.salary,
            "description": self.description,  # <-- Included in dict output
        }


class BaseScraper(ABC):
    source_name: str = "unknown"

    @abstractmethod
    def fetch(self) -> Any:
        pass

    @abstractmethod
    def parse(self, raw_data: Any) -> List[NormalizedJob]:
        pass

    def run(self) -> List[NormalizedJob]:
        raw_data = self.fetch()
        return self.parse(raw_data)