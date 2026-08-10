from sqlalchemy.orm import Session
from models import Job as JobModel


def get_all_jobs(db: Session):
    return db.query(JobModel).all()


def get_job_by_id(db: Session, job_id: int):
    return db.query(JobModel).filter(JobModel.id == job_id).first()


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


def create_job(db: Session, source_id: str, title: str, company: str, salary: int, url: str):
    new_job = JobModel(
        source_id=source_id,
        title=title,
        company=company,
        salary=salary,
        url=url
    )
    db.add(new_job)
    return new_job