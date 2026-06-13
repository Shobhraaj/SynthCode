from __future__ import annotations

from pydantic import BaseModel, Field


class FileInput(BaseModel):
    path: str
    language: str
    content: str


class FileScore(BaseModel):
    path: str
    score: float = Field(..., ge=0, le=1)
    chunks_analyzed: int = Field(default=0, ge=0)


class PredictRequest(BaseModel):
    files: list[FileInput]


class PredictResponse(BaseModel):
    scores: list[FileScore]
    model_version: str
    inference_time_ms: int = 0

