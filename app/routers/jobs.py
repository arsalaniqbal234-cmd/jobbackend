import hmac
import os
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app import cache, crud, schemas
from app.auth import verify_api_key
from app.pipeline import scrape_all, scrape_source
from app.scrapers import AVAILABLE_SCRAPERS
from database import get_db

router = APIRouter()


def parameters(
    keyword: str = Query("", max_length=200), company: str | None = Query(None, max_length=200),
    location: str | None = Query(None, max_length=200),
    min_salary: int | None = Query(None, ge=0, le=1000000000),
    salary_only: bool = False, remote_only: bool = False,
    salary_currency: str = Query("USD", pattern="^[A-Z]{3}$"),
    salary_period: str = Query("annual", pattern="^(annual|monthly|hourly)$"),
    limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0, le=100000),
    before_id: int | None = Query(None, ge=1),
):
    return locals()


@router.get("/search", response_model=list[schemas.JobResponse])
@router.get("/jobs", response_model=list[schemas.JobResponse])
def get_jobs(response: Response, params: dict = Depends(parameters), db: Session = Depends(get_db)):
    start = time.perf_counter()
    def load():
        filters = {k: v for k, v in params.items() if k not in {"limit", "offset", "before_id"}}
        query = crud.job_query(db, **filters)
        if params["before_id"] is not None:
            from app.models import Job
            query = query.filter(Job.id < params["before_id"])
        from app.models import Job
        rows = query.order_by(Job.id.desc()).offset(params["offset"]).limit(params["limit"]).all()
        return [schemas.JobResponse.model_validate(row).model_dump(mode="json") for row in rows]
    result, cache_status = cache.get_or_load(params, load)
    response.headers["X-Cache"] = cache_status
    response.headers["Server-Timing"] = f'jobs;dur={(time.perf_counter()-start)*1000:.2f}'
    return result


@router.get("/jobs/{job_id}", response_model=schemas.JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = crud.get_job_by_id(db, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/scrape/{source}")
def scrape_jobs(source: str, _: None = Depends(verify_api_key)):
    if source not in AVAILABLE_SCRAPERS:
        raise HTTPException(404, "Unknown source")
    return scrape_source(source)


@router.post("/scrape-all")
def scrape_all_sources(_: None = Depends(verify_api_key)):
    return {"results": scrape_all()}


@router.post("/cron/scrape-all")
def cron_scrape_all(authorization: str | None = Header(None)):
    secret = os.getenv("CRON_SECRET")
    if not secret or not authorization or not hmac.compare_digest(
        authorization.encode(), ("Bearer " + secret).encode()
    ):
        raise HTTPException(401, "Unauthorized")
    return {"results": scrape_all()}
