from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://fiberdoc:fiberdoc@localhost:5432/fiberdoc"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_embed_model: str = "gemini-embedding-001"
    embed_dim: int = 768
    # Backup models, comma-separated, tried in order when the main one is overloaded (503), too slow (504 / timeout)
    # or out of quota (429). Empty = no fallback. Each model has its own free-tier daily quota (20 requests on
    # 2026-11-19), so three backups give about four times the free capacity without billing (the owner's choice).
    # A different model generation runs on separate capacity, so it is usually free when the main one is busy.
    gemini_fallback_model: str = "gemini-3.7-flash,gemini-3.5-flash,gemini-3.1-flash-lite"
    gemini_timeout_s: int = 30  # per HTTP request; without it a stalled call leaves a document 'processing' forever
    # Total time for one Gemini call, retries and model switches included. Past it the rule becomes 'needs review'
    # (a person checks it) instead of the upload waiting minutes on an overloaded model.
    gemini_call_budget_s: int = 60
    cors_origins: str = "http://localhost:5173"
    max_upload_mb: int = 25
    upload_dir: str = "data/uploads"  # originals are kept here, under <project_id>/
    app_url: str = "http://localhost:5173"  # the frontend; used for links in webhook payloads (emails)
    webhook_timeout_s: int = 10


# LangGraph/LangSmith read LANGSMITH_* from the real environment, which pydantic-settings does not populate.
# override=False: variables already set in the shell win over .env.
load_dotenv(override=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
