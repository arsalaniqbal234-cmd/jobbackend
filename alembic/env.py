import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app.models  # noqa: E402,F401
from database import Base, DATABASE_URL  # noqa: E402

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
target_metadata = Base.metadata

if context.is_offline_mode():
    raise RuntimeError("Week 7 reconciles existing schema; run migrations online against a backed-up database.")
elif config.attributes.get("connection") is not None:
    connection = config.attributes["connection"]
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True,
                      version_table_schema=connection.dialect.default_schema_name)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True,
                      version_table_schema=connection.dialect.default_schema_name)
        with context.begin_transaction():
            context.run_migrations()
