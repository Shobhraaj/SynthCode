from __future__ import annotations

import hashlib
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


MODEL_VERSION = "heuristic-mvp-v1"
RESULT_TTL = timedelta(days=7)

app = FastAPI(
    title="SynthCode API",
    version="1.0.0",
    description="Local MVP backend for SynthCode repository analysis.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    owner: str = Field(..., min_length=1, max_length=120)
    repo: str = Field(..., min_length=1, max_length=120)
    branch: str = Field(default="main", min_length=1, max_length=180)
    force_rescan: bool = False


class FileScore(BaseModel):
    path: str
    score: float = Field(..., ge=0, le=1)
    language: str


class AnalysisResult(BaseModel):
    owner: str
    repo: str
    branch: str
    overall_score: float = Field(..., ge=0, le=1)
    label: Literal["human", "mixed", "AI-coded"]
    files_analyzed: int
    file_scores: list[FileScore]
    scanned_at: datetime
    model_version: str
    expires_at: datetime


class AnalyzeResponse(BaseModel):
    job_id: str
    status: Literal["completed"]
    result: AnalysisResult


class JobStatus(BaseModel):
    job_id: str
    status: Literal["completed", "failed"]
    result: AnalysisResult | None = None
    error: str | None = None


RESULTS: dict[tuple[str, str, str], AnalysisResult] = {}
JOBS: dict[str, JobStatus] = {}


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "synthcode-api",
        "model_version": MODEL_VERSION,
    }


@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
def analyze_repo(request: AnalyzeRequest) -> AnalyzeResponse:
    key = result_key(request.owner, request.repo, request.branch)
    cached = RESULTS.get(key)
    if cached and cached.expires_at > now_utc() and not request.force_rescan:
        job_id = create_completed_job(cached)
        return AnalyzeResponse(job_id=job_id, status="completed", result=cached)

    result = run_heuristic_analysis(request)
    RESULTS[key] = result
    job_id = create_completed_job(result)
    return AnalyzeResponse(job_id=job_id, status="completed", result=result)


@app.get("/api/v1/results/{owner}/{repo}", response_model=AnalysisResult)
def get_results(owner: str, repo: str, branch: str = "main") -> AnalysisResult:
    result = RESULTS.get(result_key(owner, repo, branch))
    if not result or result.expires_at <= now_utc():
        raise HTTPException(status_code=404, detail="No cached analysis found")
    return result


@app.get("/api/v1/status/{job_id}", response_model=JobStatus)
def get_status(job_id: str) -> JobStatus:
    status = JOBS.get(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return status


def run_heuristic_analysis(request: AnalyzeRequest) -> AnalysisResult:
    scanned_at = now_utc()
    file_scores = sample_file_scores(request.owner, request.repo, request.branch)
    ml_score = sum(file.score for file in file_scores) / len(file_scores)
    heuristic_score = repository_heuristic_score(request.owner, request.repo)
    overall_score = clamp((0.7 * ml_score) + (0.3 * heuristic_score))

    return AnalysisResult(
        owner=request.owner,
        repo=request.repo,
        branch=request.branch,
        overall_score=overall_score,
        label=label_for_score(overall_score),
        files_analyzed=len(file_scores),
        file_scores=file_scores,
        scanned_at=scanned_at,
        model_version=MODEL_VERSION,
        expires_at=scanned_at + RESULT_TTL,
    )


def sample_file_scores(owner: str, repo: str, branch: str) -> list[FileScore]:
    language_paths = [
        ("src/index.ts", "TypeScript"),
        ("src/components/App.tsx", "TypeScript"),
        ("src/lib/analyzer.ts", "TypeScript"),
        ("app/main.py", "Python"),
        ("app/services/scoring.py", "Python"),
        ("lib/cache.js", "JavaScript"),
        ("cmd/server.go", "Go"),
        ("src/main.rs", "Rust"),
        ("tests/test_analysis.py", "Python"),
        ("README.md", "Markdown"),
    ]

    base_seed = stable_int(f"{owner}/{repo}:{branch}")
    count = 6 + (base_seed % 7)
    selected = language_paths[:count]

    scores: list[FileScore] = []
    for index, (path, language) in enumerate(selected):
        path_seed = stable_int(f"{owner}/{repo}:{branch}:{path}")
        center = 0.18 + ((path_seed % 7000) / 10000)
        structure_signal = 0.08 * math.sin((path_seed % 360) * math.pi / 180)
        repo_signal = 0.06 if contains_aiish_terms(repo) else -0.02
        score = clamp(center + structure_signal + repo_signal)
        scores.append(FileScore(path=path, score=score, language=language))

    return scores


def repository_heuristic_score(owner: str, repo: str) -> float:
    joined = f"{owner}-{repo}".lower()
    entropy = shannon_entropy(joined)
    entropy_signal = clamp((entropy - 2.4) / 2.2)
    term_signal = 0.18 if contains_aiish_terms(joined) else 0.0
    boilerplate_signal = 0.08 if any(token in joined for token in ("starter", "template", "demo")) else 0.0
    name_length_signal = clamp((len(joined) - 10) / 28) * 0.12
    return clamp(0.24 + entropy_signal * 0.38 + term_signal + boilerplate_signal + name_length_signal)


def contains_aiish_terms(value: str) -> bool:
    terms = ("ai", "gpt", "llm", "copilot", "chat", "agent", "bot", "generated")
    lowered = value.lower()
    return any(term in lowered for term in terms)


def label_for_score(score: float) -> Literal["human", "mixed", "AI-coded"]:
    if score > 0.5:
        return "AI-coded"
    if score >= 0.3:
        return "mixed"
    return "human"


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {character: value.count(character) for character in set(value)}
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def create_completed_job(result: AnalysisResult) -> str:
    job_id = str(uuid.uuid4())
    JOBS[job_id] = JobStatus(job_id=job_id, status="completed", result=result)
    return job_id


def result_key(owner: str, repo: str, branch: str) -> tuple[str, str, str]:
    return (owner.lower(), repo.lower(), branch)


def stable_int(value: str) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def clamp(value: float, minimum: float = 0.03, maximum: float = 0.97) -> float:
    return round(min(maximum, max(minimum, value)), 4)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
