from sqlalchemy.orm import Session
from app.models import Job as JobModel


def get_all_jobs(db: Session, limit: int = 20, offset: int = 0, company: str = None):
    query = db.query(JobModel)
    if company:
        query = query.filter(JobModel.company.ilike(f"%{company}%"))
    return query.order_by(JobModel.id.desc()).offset(offset).limit(limit).all()

def get_job_by_id(db: Session, job_id: int):
    return db.query(JobModel).filter(JobModel.id == job_id).first()


def create_job_from_normalized(db: Session, job_data: dict):
    new_job = JobModel(
        source_id=job_data["source_id"],
        title=job_data["title"],
        company=job_data["company"],
        salary=job_data.get("salary"),
        salary_currency=job_data.get("salary_currency"),  # Added
        salary_period=job_data.get("salary_period"),      # Added
        url=job_data["url"],
        description=job_data.get("description", ""),
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


from sqlalchemy.dialects.postgresql import insert as pg_insert


def upsert_jobs(db: Session, jobs_data: list):
    """
    Postgres-specific upsert (uses sqlalchemy.dialects.postgresql).
    Will not work on SQLite or other databases — fine since production
    runs on Postgres (Neon), but keep this in mind if the DB ever changes.
    """
    if not jobs_data:
        return 0

    stmt = pg_insert(JobModel).values(jobs_data)
    stmt = stmt.on_conflict_do_nothing(index_elements=["source_id"])
    result = db.execute(stmt)
    return result.rowcount


def get_existing_source_ids(db: Session, source_ids: list):
    rows = db.query(JobModel.source_id).filter(JobModel.source_id.in_(source_ids)).all()
    return {row[0] for row in rows}