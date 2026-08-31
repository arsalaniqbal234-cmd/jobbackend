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
        decoded_html = html.unescape(raw_html)
        soup = BeautifulSoup(decoded_html, "html.parser")
        return soup.get_text(separator="\n", strip=True)

    def parse(self, raw_data: Any) -> List[NormalizedJob]:
        jobs_data = raw_data[1:]  # skip legal notice item
        normalized_jobs = []

        for job in jobs_data:
            raw_id = job.get("id")
            if not raw_id:
                continue

            salary_min = job.get("salary_min", 0)
            salary_max = job.get("salary_max", 0)
            real_salary = salary_max if salary_max else salary_min

            # RemoteOK reports USD salaries on an annual basis
            salary = int(real_salary) if real_salary > 0 else None
            salary_currency = "USD" if salary else None
            salary_period = "annual" if salary else None

            raw_description = job.get("description", "")
            clean_description = self._clean_description(raw_description)

            normalized_jobs.append(
                NormalizedJob(
                    source_id=f"remoteok_{raw_id}",
                    title=job.get("position", "Unknown"),
                    company=job.get("company", "Unknown"),
                    url=job.get("url", ""),
                    salary=salary,
                    salary_currency=salary_currency,
                    salary_period=salary_period,
                    description=clean_description,
                )
            )

        return normalized_jobs