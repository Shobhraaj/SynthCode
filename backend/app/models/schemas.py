from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


RepoLabel = Literal["human", "mixed", "AI-coded"]
JobState = Literal["queued", "processing", "completed", "failed", "timeout"]


class AnalyzeRequest(BaseModel):
    owner: str = Field(..., min_length=1, max_length=120)
    repo: str = Field(..., min_length=1, max_length=120)
    branch: str = Field(default="main", min_length=1, max_length=180)
    force_rescan: bool = False
    client_id: str | None = None


class FileScore(BaseModel):
    path: str
    score: float = Field(..., ge=0, le=1)
    language: str
    size_bytes: int = Field(default=0, ge=0)
    ml_score: float | None = Field(default=None, ge=0, le=1)
    heuristic_score: float | None = Field(default=None, ge=0, le=1)


class AnalysisResult(BaseModel):
    owner: str
    repo: str
    branch: str
    overall_score: float = Field(..., ge=0, le=1)
    label: RepoLabel
    files_analyzed: int
    file_scores: list[FileScore]
    scanned_at: datetime
    model_version: str
    expires_at: datetime
    scanned_commit_sha: str | None = None


class AnalyzeResponse(BaseModel):
    job_id: str
    status: JobState
    result_url: str | None = None
    result: AnalysisResult | None = None


class JobStatus(BaseModel):
    job_id: str
    status: JobState
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    result_url: str | None = None
    result: AnalysisResult | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    model_version: str
    inference_enabled: bool

