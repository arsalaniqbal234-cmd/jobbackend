import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app import cache
from app.alerts import delivery_counts
from app.auth import admin_user
from app.config import integer_env
from app.models import Job, ScrapeRun
from app.scrapers import AVAILABLE_SCRAPERS
from database import get_db

router = APIRouter()


@router.get("/health/live")
def live():
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        # Check application schema as well as connectivity.
        db.query(Job.id).limit(1).all()
        database_status = "ok"
    except Exception:
        db.rollback()
        database_status = "unavailable"
    redis_status = "disabled"
    if cache.client() is not None:
        try:
            redis_status = "ok" if cache.client().ping() else "unavailable"
        except Exception:
            redis_status = "unavailable"
    status = "ok" if database_status == "ok" and redis_status in ("ok", "disabled") else "degraded"
    return JSONResponse(
        status_code=200 if database_status == "ok" else 503,
        content={"status": status, "database": database_status, "cache": redis_status},
    )


@router.get("/health")
def pipeline_health(db: Session = Depends(get_db), _: str = Depends(admin_user)):
    moment = datetime.now(timezone.utc)
    stale_after = timedelta(hours=integer_env("SCRAPE_INTERVAL_HOURS", 6) * 2)
    sources = []
    for name in AVAILABLE_SCRAPERS:
        latest = db.query(ScrapeRun).filter_by(source=name).order_by(ScrapeRun.id.desc()).first()
        success = db.query(ScrapeRun).filter_by(source=name, status="ok").order_by(ScrapeRun.id.desc()).first()
        status = latest.status if latest else "never_run"
        if latest and latest.status == "running" and moment - latest.started_at > timedelta(minutes=15):
            status = "stalled"
        elif status == "ok" and moment - latest.finished_at > stale_after:
            status = "stale"
        sources.append({
            "source": name, "status": status,
            "last_started_at": latest.started_at.isoformat() if latest else None,
            "last_success_at": success.finished_at.isoformat() if success else None,
            "duration_ms": latest.duration_ms if latest else None,
            "fetched": latest.fetched if latest else 0, "added": latest.added if latest else 0,
            "skipped": latest.skipped if latest else 0,
            "error_code": latest.error_code if latest else None,
        })
    total = db.query(func.count(Job.id)).scalar()
    counts = delivery_counts(db)
    return {
        "generated_at": moment.isoformat(), "sources": sources, "total_jobs": total,
        "alerts": {"configured": bool(os.getenv("RESEND_API_KEY") and os.getenv("SENDER_EMAIL")),
                   "counts": counts},
        "monitoring": {"sentry_configured": bool(os.getenv("SENTRY_DSN")),
                       "redis_configured": cache.client() is not None},
    }
