import os

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

# Never fall back to the application's DATABASE_URL or send real notifications.
TEST_URL = os.getenv("TEST_DATABASE_URL", "postgresql://rozgar:rozgar_test_only@127.0.0.1:55432/rozgar_test")
url = make_url(TEST_URL)
if not url.database or not url.database.endswith("_test") or url.host not in {"localhost", "127.0.0.1", "postgres"}:
    raise RuntimeError("Tests require a local dedicated database with a name ending in _test")
os.environ["DATABASE_URL"] = TEST_URL
os.environ["REDIS_URL"] = os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:56379/15")
os.environ["SENTRY_DSN"] = ""
os.environ["RESEND_API_KEY"] = ""
os.environ["SENDER_EMAIL"] = ""
os.environ["CLERK_SECRET_KEY"] = ""
os.environ["CLERK_ISSUER"] = "https://clerk.example.test"
os.environ["CLERK_AUTHORIZED_PARTIES"] = "http://localhost:3000"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app import cache  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrate():
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE alert_deliveries, job_sources, saved_searches, scrape_runs, jobs RESTART IDENTITY CASCADE"))
    app.dependency_overrides.clear()
    cache.client.cache_clear()
    cache._failure_until = 0
    cache.client().flushdb()  # Explicit test Redis database 15.
    import requests
    def forbidden(*args, **kwargs):
        raise AssertionError("External requests must be mocked in tests")
    monkeypatch.setattr(requests, "get", forbidden)
    monkeypatch.setattr(requests, "post", forbidden)
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client
