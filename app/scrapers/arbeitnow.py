import requests

from app.scrapers.base import BaseScraper


class ArbeitnowScraper(BaseScraper):
    source_name = "arbeitnow"

    def fetch(self):
        response = requests.get("https://www.arbeitnow.com/api/job-board-api",
                                headers={"User-Agent": "Rozgar/0.8"}, timeout=10)
        response.raise_for_status()
        return response.json()

    def parse(self, raw_data):
        if not isinstance(raw_data, dict) or not isinstance(raw_data.get("data"), list):
            raise ValueError("Unexpected Arbeitnow response")
        return self.normalize([{
            "source_id": f"arbeitnow_{job['slug']}", "title": job.get("title", ""),
            "company": job.get("company_name", ""), "url": job.get("url", ""),
            "description": job.get("description") or "", "location": job.get("location") or None,
            "is_remote": job.get("remote") is True, "raw_data": job,
        } for job in raw_data["data"] if isinstance(job, dict) and job.get("slug")])
