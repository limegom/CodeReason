from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "CodeReason API"
    api_prefix: str = "/api"
    database_url: str = "sqlite:///./codereason.db"
    demo_mode: bool = False
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6"
    internal_worker_token: str | None = None
    upload_max_file_bytes: int = 256 * 1024
    upload_max_batch_files: int = 100


@lru_cache
def get_settings() -> Settings:
    origins = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    )
    return Settings(
        app_name=os.getenv("APP_NAME", "CodeReason API"),
        api_prefix=os.getenv("API_PREFIX", "/api"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./codereason.db"),
        demo_mode=_as_bool(os.getenv("DEMO_MODE")),
        cors_origins=origins,
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.6"),
        internal_worker_token=os.getenv("INTERNAL_WORKER_TOKEN") or None,
        upload_max_file_bytes=max(int(os.getenv("UPLOAD_MAX_FILE_BYTES", str(256 * 1024))), 1),
        upload_max_batch_files=max(int(os.getenv("UPLOAD_MAX_BATCH_FILES", "100")), 1),
    )
