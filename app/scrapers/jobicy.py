import requests
from typing import List, Any
from .base import BaseScraper, NormalizedJob


class JobicyScraper(BaseScraper):
    source_name = "jobicy"

    def fetch(self) -> Any:
        url = "https://jobicy.com/api/v2/remote-jobs?count=50"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()

    def parse(self, raw_data: Any) -> List[NormalizedJob]:
        jobs_data = raw_data.get("jobs", [])
        normalized_jobs = []

        for job in jobs_data:
            job_id = job.get("id")
            if not job_id:
                continue

            normalized_jobs.append(
                NormalizedJob(
                    source_id=f"jobicy_{job_id}",
                    title=job.get("jobTitle", "Unknown"),
                    company=job.get("companyName", "Unknown"),
                    url=job.get("url", ""),
                    salary=0,
                    description=job.get("jobExcerpt", ""),
                )
            )

        return normalized_jobs