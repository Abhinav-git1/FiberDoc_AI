from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    from app.db import models  # noqa: F401  (register tables)

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    # No Alembic yet: create_all will not add columns to an existing table, so add new ones here (idempotent).
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS sha256 VARCHAR(64)"))
        conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS stored_path VARCHAR"))


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db
