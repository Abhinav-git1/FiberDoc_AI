"""Alembic environment: uses the app's engine (DATABASE_URL from backend/.env) and its models for autogenerate."""
from logging.config import fileConfig

from alembic import context

from app.db import models  # noqa: F401  (registers every table on Base.metadata)
from app.db.session import Base, engine

config = context.config

# Configure logging only for the `alembic` command line; inside the app (init_db) keep uvicorn's logging.
if config.config_file_name and not config.attributes.get("from_app"):
    fileConfig(config.config_file_name)


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("Offline (--sql) mode is not set up; run against a database.")
run_migrations_online()
