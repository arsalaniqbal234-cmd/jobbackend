import logging
from apscheduler.schedulers.background import BackgroundScheduler
from database import SessionLocal
from app.routers.jobs import _scrape_all  # Updated import

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()

def scheduled_scrape_job():
    logger.info("Executing scheduled scrape job...")
    db = SessionLocal()
    try:
        results = _scrape_all(db)
        logger.info(f"Scrape job completed: {results}")
    except Exception as e:
        logger.error(f"Scheduled scrape job failed: {e}")
    finally:
        db.close()

def start_scheduler():
    scheduler.add_job(
        scheduled_scrape_job,
        'interval',
        hours=6,
        id='scrape_all_job',
        replace_existing=True
    )
    scheduler.start()
    logger.info("APScheduler started: Scraper set to run every 6 hours.")