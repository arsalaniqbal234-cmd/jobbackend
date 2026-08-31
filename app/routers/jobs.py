import hmac
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import crud, schemas
from app.scrapers import AVAILABLE_SCRAPERS
from database import get_db

router = APIRouter()


def verify_api_key(x_api_key: str = Header(None)):
    expected_key = os.getenv("SCRAPE_SECRET_KEY")
    if not expected_key:
        raise HTTPException(
            status_code=500, detail="Server misconfiguration: scrape key not set"
        )
    if not x_api_key or not hmac.compare_digest(x_api_key, expected_key):
        raise HTTPException(status_code=403, detail="Invalid or missing API key")


def _run_single_scraper(source_name: str, scraper_class):
    """Runs fetch+parse for one source. No DB access here — that happens

    back on the main thread to avoid sharing one DB session across threads.
    """
    scraper = scraper_class()
    try:
        normalized_jobs = scraper.run()
        return source_name, [job.to_dict() for job in normalized_jobs], None
    except Exception as e:
        return source_name, None, str(e)


@router.get("/search", response_model=list[schemas.JobResponse])
def search(keyword: str, limit: int = 10, db: Session = Depends(get_db)):
    return crud.search_jobs(db, keyword, limit)


@router.get("/health")
def check_all_sources_health(_: None = Depends(verify_api_key)):
    results = {}
    all_healthy = True

    for source_name, scraper_class in AVAILABLE_SCRAPERS.items():
        scraper = scraper_class()
        try:
            scraper.fetch()
            results[source_name] = "healthy"
        except Exception:
            results[source_name] = "unhealthy"
            all_healthy = False

    status_code = 200 if all_healthy else 503
    return JSONResponse(status_code=status_code, content={"sources": results})


@router.get("/health/{source}")
def check_source_health(source: str, _: None = Depends(verify_api_key)):
    if source not in AVAILABLE_SCRAPERS:
        raise HTTPException(status_code=404, detail=f"Unknown source '{source}'")

    scraper_class = AVAILABLE_SCRAPERS[source]
    scraper = scraper_class()

    try:
        scraper.fetch()
        return {"source": source, "status": "healthy"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"source": source, "status": "unhealthy"},
        )


@router.post("/scrape/{source}")
def scrape_jobs(
    source: str, db: Session = Depends(get_db), _: None = Depends(verify_api_key)
):
    if source not in AVAILABLE_SCRAPERS:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown source '{source}'. Available:"
                f" {list(AVAILABLE_SCRAPERS.keys())}"
            ),
        )

    scraper_class = AVAILABLE_SCRAPERS[source]
    scraper = scraper_class()

    try:
        normalized_jobs = scraper.run()
    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=504, detail=f"{source} took too long to respond"
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=502, detail=f"Failed to fetch jobs from {source}: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Failed to parse jobs from {source}: {str(e)}"
        )

    try:
        jobs_data = [job.to_dict() for job in normalized_jobs]
        added_count = crud.upsert_jobs(db, jobs_data)
        db.commit()
        skipped_count = len(jobs_data) - added_count
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Database error while saving jobs: {str(e)}"
        )

    return {
        "source": source,
        "message": (
            f"{added_count} new jobs added, {skipped_count} duplicates skipped"
        ),
    }


@router.post("/cron/scrape-all")
def cron_scrape_all(
    db: Session = Depends(get_db), authorization: str = Header(None)
):
    cron_secret = os.getenv("CRON_SECRET")
    expected_header = f"Bearer {cron_secret}" if cron_secret else None

    if not cron_secret or not authorization or not hmac.compare_digest(authorization, expected_header):
        raise HTTPException(status_code=401, detail="Unauthorized")

    results = {}

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(_run_single_scraper, name, cls): name
            for name, cls in AVAILABLE_SCRAPERS.items()
        }

        for future in as_completed(futures):
            source_name, jobs_data, error = future.result()

            if error:
                results[source_name] = {"error": error}
                continue

            try:
                added = crud.upsert_jobs(db, jobs_data)
                db.commit()
                skipped = len(jobs_data) - added
                results[source_name] = {"added": added, "skipped": skipped}
            except Exception as e:
                db.rollback()
                results[source_name] = {"error": str(e)}

    return {"results": results}


@router.post("/scrape-all")
def scrape_all_sources(
    db: Session = Depends(get_db), _: None = Depends(verify_api_key)
):
    results = {}

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(_run_single_scraper, name, cls): name
            for name, cls in AVAILABLE_SCRAPERS.items()
        }

        for future in as_completed(futures):
            source_name, jobs_data, error = future.result()

            if error:
                results[source_name] = {"error": error}
                continue

            try:
                added = crud.upsert_jobs(db, jobs_data)
                db.commit()
                skipped = len(jobs_data) - added
                results[source_name] = {"added": added, "skipped": skipped}
            except Exception as e:
                db.rollback()
                results[source_name] = {"error": str(e)}

    return {"results": results}


@router.get("/jobs", response_model=list[schemas.JobResponse])
def get_jobs(
    limit: int = 20,
    offset: int = 0,
    company: str = None,
    db: Session = Depends(get_db)
):
    return crud.get_all_jobs(db, limit=limit, offset=offset, company=company)


@router.get("/jobs/{job_id}", response_model=schemas.JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = crud.get_job_by_id(db, job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return job