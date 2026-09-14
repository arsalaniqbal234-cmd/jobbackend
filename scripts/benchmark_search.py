"""Reproducible local benchmark; refuses non-test databases and never scrapes."""
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
url = os.getenv("TEST_DATABASE_URL", "postgresql://rozgar:rozgar_test_only@127.0.0.1:55432/rozgar_test")
from sqlalchemy.engine import make_url  # noqa: E402

parsed = make_url(url)
if parsed.host not in {"localhost", "127.0.0.1", "postgres"} or not parsed.database.endswith("_test"):
    raise RuntimeError("Benchmark requires an isolated local *_test database")
os.environ["DATABASE_URL"] = url
os.environ["REDIS_URL"] = os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:56379/15")
os.environ["SENTRY_DSN"] = ""
os.environ["RESEND_API_KEY"] = ""
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.dialects.postgresql import insert  # noqa: E402
from app import cache  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Job  # noqa: E402
from database import SessionLocal  # noqa: E402

command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
size = 10000
with SessionLocal() as db:
    for start in range(0, size, 1000):
        db.execute(insert(Job).values([{
            "source_id": f"benchmark_{index}", "title": f"Benchmark Python Developer {index}",
            "company": "Benchmark Company", "url": f"https://example.com/benchmark/{index}",
            "salary": 100000, "salary_currency": "USD", "salary_period": "annual", "is_remote": True,
        } for index in range(start, start + 1000)]).on_conflict_do_nothing())
    db.commit()
    db.execute(text("ANALYZE jobs"))
    db.commit()

results = {}
with TestClient(app) as client:
    for kind in ("cold", "warm"):
        measurements = []
        hits = 0
        cache.invalidate_jobs()
        client.get("/jobs?keyword=Benchmark&limit=20")
        for _ in range(50):
            if kind == "cold":
                cache.invalidate_jobs()
            start = time.perf_counter()
            response = client.get("/jobs?keyword=Benchmark&limit=20")
            elapsed = (time.perf_counter() - start) * 1000
            assert response.status_code == 200 and len(response.json()) == 20
            hits += response.headers["x-cache"] == "HIT"
            measurements.append(elapsed)
        results[kind] = {
            "requests": len(measurements), "cache_hits": hits,
            "median_ms": round(statistics.median(measurements), 2),
            "p95_ms": round(sorted(measurements)[47], 2),
        }
print(json.dumps({"rows": size, "method": "FastAPI TestClient + local PostgreSQL/Redis; not public-network latency",
                  "results": results}, indent=2))
if results["warm"]["cache_hits"] != 50 or results["warm"]["p95_ms"] >= 1000:
    raise SystemExit("Sub-second cached-search acceptance check failed")
