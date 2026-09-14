from contextlib import contextmanager

from sqlalchemy import text

from database import engine


@contextmanager
def pipeline_lock(name: str):
    # A separate transaction holds the lock while work sessions commit results.
    # Transaction locks release even if the process dies; no stale lease cleanup.
    with engine.begin() as connection:
        acquired = connection.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtext(:name))"),
            {"name": "rozgar:" + name},
        ).scalar()
        yield bool(acquired)
