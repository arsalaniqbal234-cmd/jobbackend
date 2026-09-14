from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.alerts import run_alert_engine
from app.config import integer_env
from app.observability import report_failure
from app.pipeline import scrape_source
from app.scrapers import AVAILABLE_SCRAPERS
from database import SessionLocal

scheduler = BackgroundScheduler(timezone="UTC")


def alert_tick():
    with SessionLocal() as db:
        try:
            run_alert_engine(db)
        except Exception as error:
            db.rollback()
            report_failure("alert_worker", error)


def start_scheduler():
    for source in AVAILABLE_SCRAPERS:
        scheduler.add_job(
            scrape_source, "interval", args=[source], hours=integer_env("SCRAPE_INTERVAL_HOURS", 6),
            id="scrape_" + source, replace_existing=True, max_instances=1, coalesce=True,
            misfire_grace_time=300, next_run_time=datetime.now(timezone.utc),
        )
    scheduler.add_job(alert_tick, "interval", seconds=60, id="alerts",
                      replace_existing=True, max_instances=1, coalesce=True)
    scheduler.start()
