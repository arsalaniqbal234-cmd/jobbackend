import os
from datetime import datetime, timedelta, timezone
from html import escape

import requests
from sqlalchemy import exists, func
from sqlalchemy.dialects.postgresql import insert

from app import crud
from app.config import integer_env
from app.locks import pipeline_lock
from app.models import AlertDelivery, Job, SavedSearch
from app.observability import report_failure


def now():
    return datetime.now(timezone.utc)


def email_payload(search, job):
    salary = "Not specified"
    if job.salary:
        salary = f"{job.salary_currency or ''} {job.salary:,} / {job.salary_period or 'unspecified period'}"
    url = escape(job.url, quote=True)
    title, company, keyword = map(escape, (job.title, job.company, search.keywords))
    site = escape(os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/"), quote=True)
    return {
        "from": os.getenv("SENDER_EMAIL", ""),
        "to": [search.email],
        "subject": f"New job matching {search.keywords}",
        "html": f'<h2>New job on Rozgar</h2><p>Your search: {keyword}</p>'
                f'<h3><a href="{url}">{title}</a></h3><p>{company} — {escape(salary)}</p>'
                f'<p><a href="{site}/saved-searches">Manage or stop these alerts</a></p>',
    }


def queue_alerts(db):
    count = 0
    searches = db.query(SavedSearch).filter(SavedSearch.is_active.is_(True)).yield_per(100)
    for search in searches:
        if not search.keywords or not search.email:
            continue
        filters = search.filters or {}
        query = crud.job_query(
            db, keyword=search.keywords, location=search.location, min_salary=search.min_salary,
            **{k: v for k, v in filters.items() if k in {
                "salary_only", "remote_only", "salary_currency", "salary_period"}},
        )
        jobs = query.filter(
            Job.created_at >= search.created_at,
            ~exists().where(AlertDelivery.search_id == search.id, AlertDelivery.job_id == Job.id),
        ).order_by(Job.id).limit(100).all()
        for job in jobs:
            result = db.execute(insert(AlertDelivery).values(
                search_id=search.id, job_id=job.id, status="pending",
                payload=email_payload(search, job), attempts=0,
            ).on_conflict_do_nothing())
            count += result.rowcount
    db.commit()
    return count


def deliver_pending(db):
    sent = 0
    cooldown = timedelta(minutes=integer_env("ALERT_MIN_INTERVAL_MINUTES", 60))
    candidates = db.query(AlertDelivery.id).join(SavedSearch).filter(
        SavedSearch.is_active.is_(True),
        (SavedSearch.last_notified_at.is_(None)) | (SavedSearch.last_notified_at <= now() - cooldown),
        AlertDelivery.status.in_(["pending", "retry"]),
        (AlertDelivery.next_attempt_at.is_(None)) | (AlertDelivery.next_attempt_at <= now()),
    ).order_by(AlertDelivery.id).limit(500).all()
    for (delivery_id,) in candidates:
        delivery = db.get(AlertDelivery, delivery_id)
        search = db.get(SavedSearch, delivery.search_id)
        db.refresh(search)
        if not search.is_active or (search.last_notified_at and now() - search.last_notified_at < cooldown):
            continue
        if delivery.first_attempt_at and now() - delivery.first_attempt_at >= timedelta(hours=23):
            # Provider keys expire at 24h. Never blindly retry an ambiguous old send.
            delivery.status = "needs_review"
            db.commit()
            continue
        delivery.first_attempt_at = delivery.first_attempt_at or now()
        delivery.attempts += 1
        delivery.status = "retry"
        delivery.next_attempt_at = now() + timedelta(minutes=min(60, 2 ** min(delivery.attempts, 6)))
        db.commit()  # Durable payload + first attempt before any external side effect.
        try:
            response = requests.post(
                "https://api.resend.com/emails", json=delivery.payload,
                headers={"Authorization": "Bearer " + os.environ["RESEND_API_KEY"],
                         "Idempotency-Key": f"rozgar-alert-{delivery.id}"},
                timeout=(5, 15),
            )
            response.raise_for_status()
            provider_id = response.json().get("id")
            if not provider_id:
                raise ValueError("Missing delivery identifier")
        except (requests.RequestException, ValueError) as error:
            report_failure("alerts", error)
            if isinstance(error, requests.HTTPError) and error.response is not None:
                if 400 <= error.response.status_code < 500 and error.response.status_code not in (408, 409, 429):
                    delivery.status = "failed"
                    db.commit()
            continue
        delivery.status = "sent"
        delivery.sent_at = now()
        delivery.provider_id = provider_id
        search.last_notified_at = now()
        db.commit()
        sent += 1
    return sent


def run_alert_engine(db):
    if not os.getenv("RESEND_API_KEY") or not os.getenv("SENDER_EMAIL"):
        return {"status": "disabled", "queued": 0, "sent": 0}
    with pipeline_lock("alerts") as acquired:
        if not acquired:
            return {"status": "busy", "queued": 0, "sent": 0}
        queued = queue_alerts(db)
        sent = deliver_pending(db)
        return {"status": "ok", "queued": queued, "sent": sent}


def delivery_counts(db):
    return dict(db.query(AlertDelivery.status, func.count(AlertDelivery.id)).group_by(AlertDelivery.status).all())
