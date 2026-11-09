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
    cors_origins: str = "http://localhost:5173"
    max_upload_mb: int = 25
    upload_dir: str = "data/uploads"  # originals are kept here, under <project_id>/


# LangGraph/LangSmith read LANGSMITH_* from the real environment, which pydantic-settings does not populate.
# override=False: variables already set in the shell win over .env.
load_dotenv(override=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
