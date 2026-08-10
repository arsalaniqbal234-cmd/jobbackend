from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
import requests
import os

from database import get_db
from app import crud 
from app import schemas

router = APIRouter()


@router.get("/search", response_model=list[schemas.JobResponse])
async def search(keyword: str, limit: int = 10, db: Session = Depends(get_db)):
    return crud.search_jobs(db, keyword, limit)


@router.post("/scrape")
async def scrape_jobs(
    db: Session = Depends(get_db),
    x_api_key: str = Header(None)
):
    if x_api_key != os.getenv("SCRAPE_SECRET_KEY"):
        raise HTTPException(status_code=403, detail="Invalid or missing API key")

    url = "https://remoteok.com/api"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="RemoteOK took too long to respond")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch jobs from RemoteOK: {str(e)}")
    except ValueError:
        raise HTTPException(status_code=502, detail="RemoteOK returned invalid data")

    if not isinstance(data, list) or len(data) < 2:
        raise HTTPException(status_code=502, detail="Unexpected response format from RemoteOK")

    jobs_data = data[1:]

    added_count = 0
    skipped_count = 0

    try:
        for job in jobs_data:
            source_id = str(job.get("id"))
            title = job.get("position", "Unknown")
            company = job.get("company", "Unknown")
            job_url = job.get("url", "")
            salary_min = job.get("salary_min", 0)
            salary_max = job.get("salary_max", 0)
            real_salary = salary_max if salary_max else salary_min

            existing = crud.get_job_by_source_id(db, source_id)

            if existing:
                skipped_count += 1
                continue

            crud.create_job(db, source_id, title, company, real_salary, job_url)
            added_count += 1

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while saving jobs: {str(e)}")

    return {
        "message": f"{added_count} new jobs added, {skipped_count} duplicates skipped"
    }


@router.get("/jobs", response_model=list[schemas.JobResponse])
async def get_jobs(db: Session = Depends(get_db)):
    return crud.get_all_jobs(db)


@router.get("/jobs/{job_id}", response_model=schemas.JobResponse)
async def get_job(job_id: int, db: Session = Depends(get_db)):
    job = crud.get_job_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job