from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import jwt
import pytest
import requests
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import inspect

from app import alerts, auth, cache, crud, pipeline
from app.models import AlertDelivery, Job, JobSource, SavedSearch, ScrapeRun
from app.schemas import SavedSearchCreate
from app.scrapers.arbeitnow import ArbeitnowScraper
from app.scrapers.remoteok import RemoteOKScraper
from app.scrapers.base import BaseScraper, NormalizedJob
from database import engine


def job(db, title="Python engineer", **kwargs):
    item = Job(source_id=kwargs.pop("source_id", "remoteok_1"), title=title, company="Example",
               url="https://example.com/jobs/1", salary=100000, salary_currency="USD",
               salary_period="annual", is_remote=True, **kwargs)
    db.add(item)
    db.commit()
    return item


def search(db, **kwargs):
    item = SavedSearch(user_id=kwargs.pop("user_id", "user_a"), email="person@example.com",
                       keywords="python", created_at=datetime.now(timezone.utc) - timedelta(hours=1),
                       filters={}, **kwargs)
    db.add(item)
    db.commit()
    return item


def signed_in(client, user="user_a"):
    from app.main import app
    app.dependency_overrides[auth.current_user] = lambda: user


def test_migration_matches_required_columns():
    expected = {"keywords", "location", "filters", "is_active", "signature"}
    assert expected <= {item["name"] for item in inspect(engine).get_columns("saved_searches")}
    assert {"alert_deliveries", "scrape_runs", "job_sources"} <= set(inspect(engine).get_table_names())


def test_saved_search_requires_authentication(client):
    assert client.get("/saved-searches/").status_code == 401
    assert client.post("/saved-searches/", json={"keywords": "python"}).status_code == 401
    assert client.delete("/saved-searches/1").status_code == 401
    assert client.get("/health").status_code == 401


def test_verified_jwt_and_rejected_claims(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    monkeypatch.setenv("CLERK_JWT_KEY", public.decode())
    moment = datetime.now(timezone.utc)
    claims = {"sub": "user_a", "iss": "https://clerk.example.test", "azp": "http://localhost:3000",
              "iat": moment, "nbf": moment, "exp": moment + timedelta(minutes=1)}
    def verify(data):
        token = jwt.encode(data, private, algorithm="RS256")
        return auth.current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    assert verify(claims) == "user_a"
    from fastapi import HTTPException
    for patch in ({"exp": moment - timedelta(hours=1)}, {"iss": "https://attacker.test"},
                  {"azp": "https://attacker.test"}, {"sts": "pending"}):
        with pytest.raises(HTTPException) as failure:
            verify({**claims, **patch})
        assert failure.value.status_code == 401
    with pytest.raises(HTTPException):
        auth.current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid"))


def test_saved_search_contract_ownership_and_dedup(client, db, monkeypatch):
    signed_in(client)
    monkeypatch.setattr("app.routers.saved_searches.verified_email", lambda _: "person@example.com")
    payload = {"keywords": " Python ", "min_salary": 80000, "filters": {"remote_only": True}}
    first = client.post("/saved-searches/", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["user_id"] == "user_a"
    assert client.post("/saved-searches/", json=payload).json()["id"] == first.json()["id"]
    assert client.post("/saved-searches/", json={**payload, "min_salary": 90000}).json()["id"] != first.json()["id"]
    assert client.post("/saved-searches/", json={**payload, "user_id": "user_b"}).status_code == 422
    signed_in(client, "user_b")
    assert client.get("/saved-searches/").json() == []
    assert client.delete("/saved-searches/" + str(first.json()["id"])).status_code == 404
    signed_in(client)
    assert client.delete("/saved-searches/" + str(first.json()["id"])).status_code == 204
    assert len(client.get("/saved-searches/").json()) == 1


def test_email_is_verified_at_provider(monkeypatch):
    monkeypatch.setenv("CLERK_SECRET_KEY", "test")
    response = Mock()
    response.json.return_value = {"primary_email_address_id": "email1", "email_addresses": [
        {"id": "email1", "email_address": "person@example.com", "verification": {"status": "unverified"}}]}
    monkeypatch.setattr(auth.requests, "get", lambda *a, **k: response)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as failure:
        auth.verified_email("user_a")
    assert failure.value.status_code == 403
    response.json.return_value["email_addresses"][0]["verification"]["status"] = "verified"
    assert auth.verified_email("user_a") == "person@example.com"


def test_filters_literal_search_and_pagination(client, db):
    job(db)
    job(db, title="Design 100% role", source_id="remoteok_2", location="Lahore")
    assert len(client.get("/search", params={"keyword": "%"}).json()) == 1
    assert len(client.get("/jobs", params={"min_salary": 110000}).json()) == 0
    assert len(client.get("/jobs", params={"location": "lahore"}).json()) == 1
    first = client.get("/jobs?limit=1").json()[0]
    second = client.get("/jobs", params={"limit": 1, "before_id": first["id"]}).json()[0]
    assert second["id"] < first["id"]
    for path in ("/jobs?limit=0", "/jobs?offset=-1", "/search?limit=101", "/jobs?min_salary=-1"):
        assert client.get(path).status_code == 422


def test_cache_hit_invalidation_and_outage(client, db, monkeypatch):
    job(db)
    assert client.get("/jobs").headers["x-cache"] == "MISS"
    assert client.get("/jobs").headers["x-cache"] == "HIT"
    job(db, source_id="remoteok_2")
    cache.invalidate_jobs()
    assert len(client.get("/jobs").json()) == 2
    monkeypatch.setattr(cache.client(), "get", Mock(side_effect=cache.redis.ConnectionError()))
    response = client.get("/jobs?keyword=Python")
    assert response.status_code == 200 and response.headers["x-cache"] == "BYPASS"


def test_cross_source_duplicate_and_raw_data(db):
    data = NormalizedJob(source_id="remoteok_1", title="Python", company="Example",
                         url="https://example.com/job?utm_source=one", raw_data={"original": True}).to_dict()
    assert crud.upsert_jobs(db, [data]) == 1
    db.commit()
    data["source_id"] = "jobicy_2"
    data["url"] = "https://example.com/job?utm_source=two"
    assert crud.upsert_jobs(db, [data]) == 0
    db.commit()
    assert db.query(Job).count() == 1
    assert db.query(JobSource).count() == 2
    assert db.query(JobSource).first().raw_data == {"original": True}


def test_alert_matching_freshness_and_no_duplicates(db, monkeypatch):
    saved = search(db, min_salary=80000, location="Lahore")
    old = job(db, source_id="old", created_at=datetime.now(timezone.utc) - timedelta(days=2), location="Lahore")
    matching = job(db, source_id="matching", location="Lahore")
    job(db, source_id="other-location", location="Berlin")
    assert alerts.queue_alerts(db) == 1
    assert alerts.queue_alerts(db) == 0
    assert db.query(AlertDelivery).one().job_id == matching.id
    assert db.query(AlertDelivery).one().job_id != old.id
    monkeypatch.setenv("RESEND_API_KEY", "test")
    response = Mock()
    response.json.return_value = {"id": "email_123"}
    sender = Mock(return_value=response)
    monkeypatch.setattr(alerts.requests, "post", sender)
    assert alerts.deliver_pending(db) == 1
    assert alerts.deliver_pending(db) == 0
    assert sender.call_count == 1
    assert db.get(SavedSearch, saved.id).last_notified_at is not None


def test_alert_retry_same_payload_and_key(db, monkeypatch):
    search(db)
    job(db)
    alerts.queue_alerts(db)
    monkeypatch.setenv("RESEND_API_KEY", "test")
    sender = Mock(side_effect=requests.Timeout())
    monkeypatch.setattr(alerts.requests, "post", sender)
    assert alerts.deliver_pending(db) == 0
    first_args = sender.call_args.kwargs
    delivery = db.query(AlertDelivery).one()
    delivery.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    response = Mock()
    response.json.return_value = {"id": "email1"}
    sender.side_effect = None
    sender.return_value = response
    assert alerts.deliver_pending(db) == 1
    assert sender.call_args.kwargs == first_args


def test_old_ambiguous_retry_requires_review(db, monkeypatch):
    search(db)
    job(db)
    alerts.queue_alerts(db)
    delivery = db.query(AlertDelivery).one()
    delivery.first_attempt_at = datetime.now(timezone.utc) - timedelta(hours=24)
    db.commit()
    monkeypatch.setenv("RESEND_API_KEY", "test")
    assert alerts.deliver_pending(db) == 0
    assert delivery.status == "needs_review"


def test_deleted_search_and_cooldown_stop_delivery(db, monkeypatch):
    saved = search(db)
    job(db)
    job(db, source_id="second")
    alerts.queue_alerts(db)
    monkeypatch.setenv("RESEND_API_KEY", "test")
    sender = Mock()
    sender.return_value.json.return_value = {"id": "email"}
    monkeypatch.setattr(alerts.requests, "post", sender)
    assert alerts.deliver_pending(db) == 1
    assert sender.call_count == 1
    saved.is_active = False
    saved.last_notified_at = None
    db.commit()
    assert alerts.deliver_pending(db) == 0


def test_scraper_retries_and_rejects_bad_rows(monkeypatch):
    scraper = RemoteOKScraper()
    monkeypatch.setattr("app.scrapers.base.time.sleep", lambda _: None)
    fetch = Mock(side_effect=[requests.Timeout(), [{"legal": "notice"}, {"id": 1, "position": "Python", "company": "Acme",
         "url": "https://example.com/job", "salary_max": "120000"},
        {"id": 2, "position": "", "company": "Acme", "url": "javascript:alert(1)"}]])
    monkeypatch.setattr(scraper, "fetch", fetch)
    result = scraper.run()
    assert fetch.call_count == 2 and len(result) == 1
    assert result[0].salary == 120000
    arbeitnow = ArbeitnowScraper().parse({"data": [{"slug": "one", "title": "Dev", "company_name": "Acme",
                                                 "url": "https://example.com", "remote": False}]})
    assert arbeitnow[0].is_remote is False


def test_source_failure_persisted_without_losing_other_source(db, monkeypatch):
    class Broken(BaseScraper):
        def fetch(self): raise ValueError("secret must not be exposed")
        def parse(self, data): return []
    monkeypatch.setitem(pipeline.AVAILABLE_SCRAPERS, "testbroken", Broken)
    result = pipeline.scrape_source("testbroken")
    assert result["status"] == "failed"
    run = db.query(ScrapeRun).filter_by(source="testbroken").one()
    assert run.status == "failed" and run.error_code == "ValueError"


def test_dashboard_authorization_and_stale_state(client, db, monkeypatch):
    signed_in(client)
    assert client.get("/health").status_code == 403
    monkeypatch.setenv("ADMIN_USER_IDS", "user_a")
    db.add(ScrapeRun(source="remoteok", status="ok", fetched=2, added=2, skipped=0,
                    finished_at=datetime.now(timezone.utc) - timedelta(days=2)))
    db.commit()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert next(source for source in response.json()["sources"] if source["source"] == "remoteok")["status"] == "stale"
    assert client.get("/health/ready").status_code == 200


def test_sentry_scrubs_sensitive_information():
    from app.observability import scrub_event
    event = {"user": {"email": "private"}, "request": {"headers": {"Authorization": "secret"}, "data": "private"},
             "breadcrumbs": [{"message": "private"}],
             "exception": {"values": [{"type": "Error", "value": "private", "stacktrace": {"frames": [{"vars": {"secret": "x"}}]}}]}}
    cleaned = scrub_event(event, {})
    assert "private" not in str(cleaned) and "secret" not in str(cleaned)


def test_empty_and_invalid_search_input(client):
    signed_in(client)
    assert client.post("/saved-searches/", json={"keywords": "   "}).status_code == 422
    assert client.post("/saved-searches/", json={"keywords": "python", "filters": {"unknown": True}}).status_code == 422
    assert SavedSearchCreate(keywords=" python ").keywords == "python"
