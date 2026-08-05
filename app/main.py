from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import requests
import os

from database import engine, get_db, Base
from models import Job as JobModel


app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://jobsi-ten.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


Base.metadata.create_all(bind=engine)


@app.get("/search")
async def search(keyword: str, limit: int = 10, db: Session = Depends(get_db)):
    results = (
        db.query(JobModel)
        .filter(
            (JobModel.title.ilike(f"%{keyword}%")) |
            (JobModel.company.ilike(f"%{keyword}%"))
        )
        .limit(limit)
        .all()
    )
    return results

@app.get("/")
def home():
    return{"message":"job backend api"}


    


@app.post("/scrape")
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

            existing = db.query(JobModel).filter(JobModel.source_id == source_id).first()

            if existing:
                skipped_count += 1
                continue

            new_job = JobModel(
                source_id=source_id,
                title=title,
                company=company,
                salary=real_salary,
                url=job_url
            )
            db.add(new_job)
            added_count += 1

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while saving jobs: {str(e)}")

    return {
        "message": f"{added_count} new jobs added, {skipped_count} duplicates skipped"
    }


@app.get("/jobs")
async def get_jobs(db: Session = Depends(get_db)):
    jobs = db.query(JobModel).all()
    return jobs


@app.get("/jobs/{job_id}")
async def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(JobModel).filter(JobModel.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job