from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


BACKEND_DIR = Path(__file__).resolve().parents[2]
BASELINE = "0001"


def alembic_config():
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["from_app"] = True  # env.py: keep the app's logging setup
    return cfg


def init_db() -> None:
    """Bring the database to the latest schema by running the Alembic migrations in migrations/versions/."""
    from alembic import command

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # Look only in the schema we write to: with no schema given, Postgres reflection also sees tables
        # further down the search_path (e.g. public), which would misread a fresh schema as an old database.
        insp, schema = inspect(conn), conn.execute(text("SELECT current_schema()")).scalar()
        pre_alembic = insp.has_table("documents", schema=schema) and not insp.has_table("alembic_version", schema=schema)
        if pre_alembic:
            _upgrade_pre_alembic(conn)
    cfg = alembic_config()
    if pre_alembic:
        command.stamp(cfg, BASELINE)  # its tables already exist; record that it is at the baseline
    command.upgrade(cfg, "head")


def _upgrade_pre_alembic(conn) -> None:
    """One-time handover for a database created before Alembic (2026-11-14): bring it to the 0001 baseline
    with the ALTERs that used to run at every startup. All idempotent. Remove once no such database is left."""
    conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS sha256 VARCHAR(64)"))
    conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS stored_path VARCHAR"))
    for col in ("source_name", "section", "jurisdiction", "standard_family", "version", "effective_date"):
        conn.execute(text(f"ALTER TABLE rules ADD COLUMN IF NOT EXISTS {col} VARCHAR"))
    conn.execute(text("ALTER TABLE rules ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'approved'"))
    conn.execute(text("UPDATE rules SET status = 'approved' WHERE status IS NULL"))
    conn.execute(text("ALTER TABLE rules ALTER COLUMN status SET NOT NULL"))  # as in the model and 0001
    for col, typ in (("status", "VARCHAR"), ("evidence", "JSON"), ("source_pages_checked", "JSON"),
                     ("recommended_action", "TEXT"), ("needs_human_review", "BOOLEAN"), ("retrieval", "JSON")):
        conn.execute(text(f"ALTER TABLE findings ADD COLUMN IF NOT EXISTS {col} {typ}"))
    # 2026-11-12: rename the first status values to the blueprint's four.
    conn.execute(text("UPDATE findings SET status = 'passed' WHERE status = 'compliant'"))
    conn.execute(text("UPDATE findings SET status = 'needs_review' WHERE status = 'unverified'"))
    conn.execute(text("UPDATE findings SET status = CASE WHEN evidence::text = '[]' THEN 'missing_evidence' "
                      "ELSE 'failed' END WHERE status = 'non_compliant'"))


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db
