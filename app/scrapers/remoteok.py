import requests

from app.scrapers.base import BaseScraper


class RemoteOKScraper(BaseScraper):
    source_name = "remoteok"

    def fetch(self):
        response = requests.get("https://remoteok.com/api", headers={"User-Agent": "Rozgar/0.8"}, timeout=10)
        response.raise_for_status()
        return response.json()

    def parse(self, raw_data):
        if not isinstance(raw_data, list):
            raise ValueError("Unexpected RemoteOK response")
        records = []
        for job in raw_data:
            if not isinstance(job, dict) or not job.get("id"):
                continue
            try:
                salary = int(float(job.get("salary_max") or job.get("salary_min") or 0))
                salary = salary if salary > 0 else None
            except (TypeError, ValueError, OverflowError):
                salary = None
            records.append({
                "source_id": f"remoteok_{job['id']}", "title": job.get("position", ""),
                "company": job.get("company", ""), "url": job.get("url", ""),
                "salary": salary, "salary_currency": "USD" if salary else None,
                "salary_period": "annual" if salary else None,
                "description": job.get("description") or "", "location": job.get("location") or None,
                "is_remote": True, "raw_data": job,
            })
        return self.normalize(records)
