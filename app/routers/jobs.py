from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
import requests
import os

from database import get_db
from app import crud
from app import schemas
from app.scrapers import AVAILABLE_SCRAPERS

router = APIRouter()


@router.get("/search", response_model=list[schemas.JobResponse])
async def search(
    keyword: str,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    return crud.search_jobs(db, keyword, limit)


@router.post("/scrape/{source}")
async def scrape_jobs(
    source: str,
    db: Session = Depends(get_db),
    x_api_key: str = Header(None)
):
    if x_api_key != os.getenv("SCRAPE_SECRET_KEY"):
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing API key"
        )

    if source not in AVAILABLE_SCRAPERS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown source '{source}'. Available: {list(AVAILABLE_SCRAPERS.keys())}"
        )

    scraper_class = AVAILABLE_SCRAPERS[source]
    scraper = scraper_class()

    try:
        normalized_jobs = scraper.run()
    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=504,
            detail=f"{source} took too long to respond"
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch jobs from {source}: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to parse jobs from {source}: {str(e)}"
        )

    added_count = 0
    skipped_count = 0

    try:
        for job in normalized_jobs:
            existing = crud.get_job_by_source_id(db, job.source_id)

            if existing:
                skipped_count += 1
                continue

            crud.create_job_from_normalized(db, job.to_dict())
            added_count += 1

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database error while saving jobs: {str(e)}"
        )

    return {
        "source": source,
        "message": f"{added_count} new jobs added, {skipped_count} duplicates skipped"
    }


@router.get("/jobs", response_model=list[schemas.JobResponse])
async def get_jobs(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    return crud.get_all_jobs(db, limit=limit, offset=offset)


@router.get("/jobs/{job_id}", response_model=schemas.JobResponse)
async def get_job(
    job_id: int,
    db: Session = Depends(get_db)
):
    job = crud.get_job_by_id(db, job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found"
        )

    return job