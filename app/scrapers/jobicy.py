import requests

from app.scrapers.base import BaseScraper


class JobicyScraper(BaseScraper):
    source_name = "jobicy"

    def fetch(self):
        response = requests.get("https://jobicy.com/api/v2/remote-jobs?count=50",
                                headers={"User-Agent": "Rozgar/0.8"}, timeout=10)
        response.raise_for_status()
        return response.json()

    def parse(self, raw_data):
        if not isinstance(raw_data, dict) or not isinstance(raw_data.get("jobs"), list):
            raise ValueError("Unexpected Jobicy response")
        return self.normalize([{
            "source_id": f"jobicy_{job['id']}", "title": job.get("jobTitle", ""),
            "company": job.get("companyName", ""), "url": job.get("url", ""),
            "description": job.get("jobDescription") or job.get("jobExcerpt") or "",
            "location": job.get("jobGeo") or None, "is_remote": True, "raw_data": job,
        } for job in raw_data["jobs"] if isinstance(job, dict) and job.get("id")])
