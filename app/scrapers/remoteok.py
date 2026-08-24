import html
import requests
from typing import List, Any
from bs4 import BeautifulSoup
from app.scrapers.base import BaseScraper, NormalizedJob


class RemoteOKScraper(BaseScraper):
    source_name = "remoteok"

    def fetch(self) -> Any:
        url = "https://remoteok.com/api"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()

    def _clean_description(self, raw_html: str) -> str:
        if not raw_html:
            return ""
        # 1. Unescape Unicode entities (e.g., \u003C -> <)
        decoded_html = html.unescape(raw_html)
        # 2. Parse and strip HTML tags
        soup = BeautifulSoup(decoded_html, "html.parser")
        return soup.get_text(separator="\n", strip=True)

    def parse(self, raw_data: Any) -> List[NormalizedJob]:
        jobs_data = raw_data[1:]  # skip legal notice item[cite: 1]
        normalized_jobs = []

        for job in jobs_data:
            raw_id = job.get("id")
            if not raw_id:
                continue

            salary_min = job.get("salary_min", 0)
            salary_max = job.get("salary_max", 0)
            real_salary = salary_max if salary_max else salary_min

            # Strip HTML tags & unicode entities from description
            raw_description = job.get("description", "")
            clean_description = self._clean_description(raw_description)

            normalized_jobs.append(
                NormalizedJob(
                    source_id=f"remoteok_{raw_id}",
                    title=job.get("position", "Unknown"),
                    company=job.get("company", "Unknown"),
                    url=job.get("url", ""),
                    salary=real_salary,
                    description=clean_description,
                )
            )

        return normalized_jobs