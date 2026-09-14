import hashlib
import json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import func, or_
from sqlalchemy.dialects.postgresql import insert

from app.models import Job, JobSource, SavedSearch


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"ref", "source", "fbclid", "gclid"}]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", urlencode(sorted(query)), ""))


def fingerprint(url: str) -> str:
    return hashlib.sha256(canonical_url(url).encode()).hexdigest()


def job_query(db, keyword="", company=None, location=None, min_salary=None,
              salary_only=False, remote_only=False, salary_currency="USD", salary_period="annual"):
    query = db.query(Job)
    # autoescape makes % and _ literal input, not user-controlled SQL wildcards.
    if keyword and keyword.strip():
        query = query.filter(or_(Job.title.icontains(keyword.strip(), autoescape=True),
                                 Job.company.icontains(keyword.strip(), autoescape=True)))
    if company:
        query = query.filter(Job.company.icontains(company.strip(), autoescape=True))
    if location:
        query = query.filter(Job.location.icontains(location.strip(), autoescape=True))
    if min_salary is not None and min_salary > 0:
        query = query.filter(Job.salary >= min_salary, Job.salary_currency == salary_currency,
                             Job.salary_period == salary_period)
    if salary_only:
        query = query.filter(Job.salary > 0)
    if remote_only:
        query = query.filter(Job.is_remote.is_(True))
    return query


def get_job_by_id(db, job_id):
    return db.get(Job, job_id)


def upsert_jobs(db, jobs_data):
    added = 0
    for record in jobs_data:
        data = dict(record)
        raw = data.pop("raw_data", {})
        source = data.pop("source", data["source_id"].split("_", 1)[0])
        data["fingerprint"] = fingerprint(data["url"])
        job_id = db.execute(insert(Job).values(**data).on_conflict_do_nothing().returning(Job.id)).scalar()
        if job_id is not None:
            added += 1
        else:
            job_id = db.query(Job.id).filter(or_(Job.source_id == data["source_id"],
                                                Job.fingerprint == data["fingerprint"])).scalar()
        db.execute(insert(JobSource).values(source_id=data["source_id"], job_id=job_id,
                                            source=source, raw_data=raw).on_conflict_do_update(
            index_elements=["source_id"],
            set_={"raw_data": raw, "fetched_at": func.now()},
        ))
    return added  # The pipeline owns the transaction.


def create_saved_search(db, search, user_id, email):
    payload = search.model_dump()
    payload["keywords"] = payload["keywords"].casefold()
    if payload["location"]:
        payload["location"] = payload["location"].casefold()
    signature = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    # Lock this user's creation quota and deduplication across concurrent requests.
    from sqlalchemy import text
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": "saved:" + user_id})
    existing = db.query(SavedSearch).filter_by(user_id=user_id, signature=signature).first()
    if existing:
        if not existing.is_active:
            from datetime import datetime, timezone
            existing.created_at = datetime.now(timezone.utc)
        existing.is_active = True
        existing.email = email
        db.commit()
        db.refresh(existing)
        return existing
    if db.query(SavedSearch).filter_by(user_id=user_id, is_active=True).count() >= 20:
        from fastapi import HTTPException
        raise HTTPException(409, "You can save up to 20 searches; delete one first")
    item = SavedSearch(**payload, user_id=user_id, email=email, signature=signature)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def get_saved_searches_by_user(db, user_id):
    return db.query(SavedSearch).filter_by(user_id=user_id, is_active=True).order_by(SavedSearch.id.desc()).all()


def delete_saved_search(db, search_id, user_id):
    item = db.query(SavedSearch).filter_by(id=search_id, user_id=user_id, is_active=True).first()
    if not item:
        return False
    # Soft delete preserves delivery history and prevents resend on reactivation.
    item.is_active = False
    db.commit()
    return True
