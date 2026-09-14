import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from app import cache, crud
from app.alerts import run_alert_engine
from app.locks import pipeline_lock
from app.models import ScrapeRun
from app.observability import report_failure
from app.scrapers import AVAILABLE_SCRAPERS
from database import SessionLocal


def scrape_source(source):
    with pipeline_lock("scrape:" + source) as acquired:
        if not acquired:
            return {"status": "busy", "added": 0, "skipped": 0}
        with SessionLocal() as db:
            # A prior process may have died after recording its start.
            db.query(ScrapeRun).filter_by(source=source, status="running").update(
                {"status": "failed", "error_code": "InterruptedRun"})
            run = ScrapeRun(source=source, status="running")
            db.add(run)
            db.commit()
            db.refresh(run)
            run_id = run.id
            start = time.perf_counter()
            try:
                records = [job.to_dict() for job in AVAILABLE_SCRAPERS[source]().run()]
                if not records:
                    raise ValueError("Source returned no usable jobs")
                added = crud.upsert_jobs(db, records)
                run.status, run.fetched, run.added = "ok", len(records), added
                run.skipped = len(records) - added
                run.finished_at = datetime.now(timezone.utc)
                run.duration_ms = (time.perf_counter() - start) * 1000
                db.commit()
                cache.invalidate_jobs()
                result = {"status": "ok", "added": added, "skipped": run.skipped}
            except Exception as error:
                db.rollback()
                report_failure("scraper." + source, error)
                run = db.get(ScrapeRun, run_id)
                run.status, run.error_code = "failed", type(error).__name__
                run.finished_at = datetime.now(timezone.utc)
                run.duration_ms = (time.perf_counter() - start) * 1000
                db.commit()
                result = {"status": "failed", "error": type(error).__name__}
            # Keep bounded history; this does not touch job or delivery records.
            db.query(ScrapeRun).filter(ScrapeRun.started_at < datetime.now(timezone.utc) - timedelta(days=30)).delete()
            db.commit()
            try:
                result["alerts"] = run_alert_engine(db)
            except Exception as error:
                db.rollback()
                report_failure("alerts", error)
                result["alerts"] = {"status": "failed"}
            return result


def scrape_all():
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(scrape_source, AVAILABLE_SCRAPERS))
    return dict(zip(AVAILABLE_SCRAPERS, results))
