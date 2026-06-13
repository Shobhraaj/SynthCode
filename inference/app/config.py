from __future__ import annotations

import os
from functools import lru_cache

try:
    from pydantic_settings import BaseSettings
except ImportError:  # pragma: no cover
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


class InferenceSettings(BaseSettings):
    MODEL_PATH: str = "./ml/weights/codebert-ai-detector"
    MODEL_DEVICE: str = "cuda"
    MAX_BATCH_SIZE: int = 16
    MAX_TOKENS: int = 512
    CHUNK_OVERLAP: int = 64
    WARMUP_ON_STARTUP: bool = False
    MODEL_VERSION: str = "heuristic-inference-stub-v1"

    class Config:
        env_file = ".env.inference"


@lru_cache
def get_settings() -> InferenceSettings:
    return InferenceSettings()

