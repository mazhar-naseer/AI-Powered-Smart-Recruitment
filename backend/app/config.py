from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_name: str = "SmartHire API"
    environment: str = "development"
    secret_key: str = "development-only-change-me-please"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    database_url: str = "postgresql+psycopg://smarthire:smarthire@localhost:5432/smarthire"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout: int = 30
    resume_storage_path: Path = Path("../storage/resumes")
    max_resume_size_mb: int = 5
    frontend_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://localhost:8080",
    ]
    cookie_secure: bool = False
    log_level: str = "INFO"
    frontend_url: str = "http://localhost:5173"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "no-reply@smarthire.local"
    smtp_use_tls: bool = True
    email_verification_minutes: int = 30
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"
    gemini_enabled: bool = True
    gemini_weight: float = 0.35
    hybrid_disagreement_threshold: float = 25.0
    gemini_timeout_seconds: int = 30

    @field_validator("gemini_weight")
    @classmethod
    def valid_gemini_weight(cls, value: float) -> float:
        if not 0 <= value <= 0.5:
            raise ValueError("GEMINI_WEIGHT must be between 0 and 0.5")
        return value

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
