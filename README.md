# Rozgar backend

FastAPI, PostgreSQL, Redis, APScheduler, and resilient source adapters for the Rozgar
job platform.

## Local setup

1. Create and activate a Python 3.11 virtual environment.
2. Install `requirements-dev.txt` for development or `requirements.txt` for runtime.
3. Copy `.env.example` to `.env` and provide local credentials.
4. Run `alembic upgrade head`.
5. Start the API with `uvicorn app.main:app --reload`.
6. Start one scheduler process with `python -m app.run_scheduler`.

`GET /health/live` is the process liveness probe and `GET /health/ready` checks
PostgreSQL plus configured Redis. `GET /health` requires an authenticated Clerk user
listed in `ADMIN_USER_IDS` and returns pipeline and alert-delivery health.

## Verification

Run `ruff check app database.py alembic tests scripts`, `pytest -q`, and
`python scripts/benchmark_search.py`. The tests and benchmark require dedicated local
PostgreSQL and Redis services matching the test defaults. The test bootstrap refuses a
non-local database or a database whose name does not end in `_test`.

Production migration and alert rollback guidance lives in the monorepo's
`docs/week-7-runbook.md`. Back up PostgreSQL before migration; delivery history is kept
to prevent repeated email.
