import uuid

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from database import DATABASE_URL, engine


def test_upgrade_preserves_legacy_search_and_job():
    name = "migration_" + uuid.uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{name}"'))
    isolated = create_engine(DATABASE_URL, connect_args={"options": f"-csearch_path={name},public"})
    try:
        with isolated.begin() as connection:
            configuration = Config("alembic.ini")
            configuration.attributes["connection"] = connection
            command.upgrade(configuration, "62cbe6c55481")
            connection.execute(text(
                "INSERT INTO saved_searches (user_id, keyword, email, min_salary) "
                "VALUES ('user_legacy', 'python', 'old@example.com', 80000)"
            ))
            connection.execute(text(
                "INSERT INTO jobs (source_id, title, company, url) "
                "VALUES ('remoteok_legacy', 'Developer', 'Example', 'https://example.com/job')"
            ))
            command.upgrade(configuration, "head")
            saved = connection.execute(text("SELECT keywords, email, min_salary, is_active FROM saved_searches")).one()
            assert saved == ("python", "old@example.com", 80000, False)
            assert connection.execute(text("SELECT fingerprint FROM jobs")).scalar()
            assert "alert_deliveries" in inspect(connection).get_table_names()
    finally:
        isolated.dispose()
        with engine.begin() as connection:
            # The schema name is generated above, not read from input.
            connection.execute(text(f'DROP SCHEMA "{name}" CASCADE'))
