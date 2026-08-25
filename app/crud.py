from sqlalchemy.orm import Session
from models import Job as JobModel


def get_all_jobs(db: Session, limit: int = 20, offset: int = 0):
    return db.query(JobModel).offset(offset).limit(limit).all()


def get_job_by_id(db: Session, job_id: int):
    return db.query(JobModel).filter(JobModel.id == job_id).first()


def create_job_from_normalized(db: Session, job_data: dict):
    new_job = JobModel(
        source_id=job_data["source_id"],
        title=job_data["title"],
        company=job_data["company"],
        salary=job_data["salary"],
        url=job_data["url"],
        description=job_data.get("description", ""),  # <-- Save description to DB
    )
    db.add(new_job)
    return new_job


def search_jobs(db: Session, keyword: str, limit: int = 10):
    return (
        db.query(JobModel)
        .filter(
            (JobModel.title.ilike(f"%{keyword}%")) |
            (JobModel.company.ilike(f"%{keyword}%"))
        )
        .limit(limit)
        .all()
    )


def get_job_by_source_id(db: Session, source_id: str):
    return db.query(JobModel).filter(JobModel.source_id == source_id).first()


def create_job(db: Session, source_id: str, title: str, company: str, salary: int, url: str, description: str = ""):
    new_job = JobModel(
        source_id=source_id,
        title=title,
        company=company,
        salary=salary,
        url=url,
        description=description,  # <-- Added description here as well
    )
    db.add(new_job)
    return new_job


def get_existing_source_ids(db: Session, source_ids: list):
    rows = db.query(JobModel.source_id).filter(JobModel.source_id.in_(source_ids)).all()
    return {row[0] for row in rows}