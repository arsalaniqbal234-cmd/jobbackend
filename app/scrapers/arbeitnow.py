import requests
from typing import List, Any
from .base import BaseScraper, NormalizedJob


class ArbeitnowScraper(BaseScraper):
    source_name = "arbeitnow"

    def fetch(self) -> Any:
        url = "https://www.arbeitnow.com/api/job-board-api"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()

    def parse(self, raw_data: Any) -> List[NormalizedJob]:
        jobs_data = raw_data.get("data", [])
        normalized_jobs = []

        for job in jobs_data:
            slug = job.get("slug")
            if not slug:
                continue

            normalized_jobs.append(
                NormalizedJob(
                    source_id=f"arbeitnow_{slug}",
                    title=job.get("title", "Unknown"),
                    company=job.get("company_name", "Unknown"),
                    url=job.get("url", ""),
                    salary=0,
                    description=job.get("description", ""),
                )
            )

        return normalized_jobs