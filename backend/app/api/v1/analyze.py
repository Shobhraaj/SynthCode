from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from backend.app.api.deps import settings_dep
from backend.app.config import Settings
from backend.app.models.schemas import AnalysisResult, AnalyzeRequest, AnalyzeResponse, JobStatus
from backend.app.services.pipeline import AnalysisPipeline

router = APIRouter(tags=["analysis"])

RESULTS: dict[tuple[str, str, str], AnalysisResult] = {}
JOBS: dict[str, JobStatus] = {}
RESULT_KEY_SEPARATOR = "|"
STATE_ROOT = (Path.cwd() / ".synthcode_state").resolve()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_repo(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(settings_dep),
) -> AnalyzeResponse:
    restore_state()
    key = result_key(request.owner, request.repo, request.branch)
    cached = RESULTS.get(key)
    if cached and cached.expires_at > now_utc() and not request.force_rescan:
        job_id = str(uuid.uuid4())
        JOBS[job_id] = JobStatus(
            job_id=job_id,
            status="completed",
            progress=100,
            message="Using cached analysis.",
            result_url=result_url(request.owner, request.repo, request.branch),
            result=cached,
        )
        persist_state(settings)
        return AnalyzeResponse(job_id=job_id, status="completed", result_url=result_url(request.owner, request.repo, request.branch), result=cached)

    job_id = str(uuid.uuid4())
    JOBS[job_id] = JobStatus(job_id=job_id, status="queued", progress=0, message="Queued for analysis.")
    prune_state(settings)
    persist_state(settings)
    background_tasks.add_task(run_analysis_job, job_id, request, settings)
    return AnalyzeResponse(job_id=job_id, status="queued")


@router.get("/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str) -> JobStatus:
    restore_state()
    status = JOBS.get(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return status


@router.get("/results/{owner}/{repo}", response_model=AnalysisResult)
async def get_results(owner: str, repo: str, branch: str = "main") -> AnalysisResult:
    restore_state()
    result = RESULTS.get(result_key(owner, repo, branch))
    if not result or result.expires_at <= now_utc():
        raise HTTPException(status_code=404, detail="No cached analysis found")
    return result


async def run_analysis_job(job_id: str, request: AnalyzeRequest, settings: Settings) -> None:
    async def progress(percent: int, message: str) -> None:
        JOBS[job_id] = JOBS[job_id].model_copy(update={"status": "processing", "progress": percent, "message": message})
        prune_state(settings)
        persist_state(settings)

    try:
        await progress(5, "Starting analysis...")
        result = await AnalysisPipeline(settings).analyze_repo(request.owner, request.repo, request.branch, progress)
        RESULTS[result_key(result.owner, result.repo, result.branch)] = result
        RESULTS[result_key(request.owner, request.repo, request.branch)] = result
        JOBS[job_id] = JobStatus(
            job_id=job_id,
            status="completed",
            progress=100,
            message="Analysis completed.",
            result_url=result_url(result.owner, result.repo, result.branch),
            result=result,
        )
        prune_state(settings)
        persist_state(settings)
    except asyncio.TimeoutError as exc:
        JOBS[job_id] = JobStatus(job_id=job_id, status="timeout", progress=100, message="Analysis timed out.", error=str(exc))
        prune_state(settings)
        persist_state(settings)
    except Exception as exc:
        JOBS[job_id] = JobStatus(job_id=job_id, status="failed", progress=100, message="Analysis failed.", error=str(exc))
        prune_state(settings)
        persist_state(settings)


def result_key(owner: str, repo: str, branch: str) -> tuple[str, str, str]:
    return (owner.lower(), repo.lower(), branch or "main")


def result_url(owner: str, repo: str, branch: str) -> str:
    return f"/api/v1/results/{owner}/{repo}?branch={branch}"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def state_file_path() -> str:
    return str((STATE_ROOT / "job_store.json").resolve())


def restore_state() -> None:
    path = Path(state_file_path()).resolve()
    if not path.is_relative_to(STATE_ROOT):
        return
    if not path.exists():
        return
    if RESULTS or JOBS:
        return
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        raw_results = payload.get("results", {})
        raw_jobs = payload.get("jobs", {})
        for key, value in raw_results.items():
            parts = key.split(RESULT_KEY_SEPARATOR, 2)
            if len(parts) != 3:
                continue
            owner, repo, branch = parts
            result = AnalysisResult.model_validate(value)
            if result.expires_at > now_utc():
                RESULTS[(owner, repo, branch)] = result
        for job_id, value in raw_jobs.items():
            JOBS[job_id] = JobStatus.model_validate(value)
    except (OSError, json.JSONDecodeError, ValueError):
        return


def prune_state(settings: Settings) -> None:
    now = now_utc()
    expired = [key for key, result in RESULTS.items() if result.expires_at <= now]
    for key in expired:
        RESULTS.pop(key, None)

    if len(RESULTS) > settings.RESULT_STORE_LIMIT:
        ordered = sorted(RESULTS.items(), key=lambda item: item[1].scanned_at, reverse=True)
        RESULTS.clear()
        RESULTS.update(dict(ordered[: settings.RESULT_STORE_LIMIT]))

    if len(JOBS) > settings.JOB_HISTORY_LIMIT:
        ordered_jobs = sorted(
            JOBS.items(),
            key=lambda item: getattr(item[1].result, "scanned_at", now) if item[1].result else now,
            reverse=True,
        )
        JOBS.clear()
        JOBS.update(dict(ordered_jobs[: settings.JOB_HISTORY_LIMIT]))


def persist_state(settings: Settings) -> None:
    path = state_file_path()
    try:
        safe_path = Path(path).resolve()
        if not safe_path.is_relative_to(STATE_ROOT):
            return
        os.makedirs(STATE_ROOT, exist_ok=True)
        payload = {
            "results": {
                f"{owner}{RESULT_KEY_SEPARATOR}{repo}{RESULT_KEY_SEPARATOR}{branch}": result.model_dump(mode="json")
                for (owner, repo, branch), result in RESULTS.items()
            },
            "jobs": {job_id: job.model_dump(mode="json") for job_id, job in JOBS.items()},
        }
        with safe_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle)
    except OSError:
        return
