from __future__ import annotations

import os
from functools import lru_cache

try:
    from pydantic_settings import BaseSettings
except ImportError:  # pragma: no cover - keeps source importable before deps install
    from pydantic import BaseModel

    class BaseSettings(BaseModel):
        def __init__(self, **data):
            env_data = {
                name: os.getenv(name, field.default)
                for name, field in self.model_fields.items()
                if os.getenv(name) is not None
            }
            env_data.update(data)
            super().__init__(**env_data)


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    API_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql+asyncpg://synthcode:dev_password@db:5432/synthcode"
    REDIS_URL: str = "redis://redis:6379/0"

    GITHUB_TOKEN: str = ""
    GITHUB_API_BASE: str = "https://api.github.com"
    GITHUB_LOW_RATE_REMAINING: int = 100

    INFERENCE_SERVICE_URL: str = "http://inference:8001"
    INFERENCE_TIMEOUT: int = 30
    INFERENCE_MAX_RETRIES: int = 2
    INFERENCE_ENABLED: bool = False

    RATE_LIMIT_ANON: int = 5
    RATE_LIMIT_AUTH: int = 20
    RATE_LIMIT_WINDOW: int = 3600

    MAX_FILES_PER_REPO: int = 30
    MIN_FILE_BYTES: int = 200
    MAX_FILE_BYTES: int = 100 * 1024
    CACHE_TTL_REDIS: int = 3600
    CACHE_TTL_DB_DAYS: int = 7
    MODEL_VERSION: str = "phase2-heuristic-ensemble-v1"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()

