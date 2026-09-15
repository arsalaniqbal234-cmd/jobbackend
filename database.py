import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app import config  # noqa: F401 -- load the backend's environment first

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required; see Backend/.env.example")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    # Neon pooler endpoints reject PostgreSQL startup `options`. Query limits
    # belong at the database/role level when a transaction pooler is in use.
    connect_args={"connect_timeout": 5}
    if DATABASE_URL.startswith("postgresql") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    with SessionLocal() as db:
        yield db
