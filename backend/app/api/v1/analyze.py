from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from backend.app.api.deps import settings_dep
from backend.app.config import Settings
from backend.app.models.schemas import AnalysisResult, AnalyzeRequest, AnalyzeResponse, JobStatus
from backend.app.services.pipeline import AnalysisPipeline

router = APIRouter(tags=["analysis"])

RESULTS: dict[tuple[str, str, str], AnalysisResult] = {}
JOBS: dict[str, JobStatus] = {}


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_repo(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(settings_dep),
) -> AnalyzeResponse:
    restore_state(settings)
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
async def get_status(job_id: str, settings: Settings = Depends(settings_dep)) -> JobStatus:
    restore_state(settings)
    status = JOBS.get(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return status


@router.get("/results/{owner}/{repo}", response_model=AnalysisResult)
async def get_results(owner: str, repo: str, branch: str = "main", settings: Settings = Depends(settings_dep)) -> AnalysisResult:
    restore_state(settings)
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


def state_file_path(settings: Settings | None = None) -> str:
    if settings:
        return settings.JOB_RESULT_STORE_PATH
    return os.getenv("JOB_RESULT_STORE_PATH", "/tmp/synthcode_job_store.json")


def restore_state(settings: Settings | None = None) -> None:
    path = state_file_path(settings)
    if not path or not os.path.exists(path):
        return
    if RESULTS or JOBS:
        return
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        raw_results = payload.get("results", {})
        raw_jobs = payload.get("jobs", {})
        for key, value in raw_results.items():
            owner, repo, branch = key.split("|", 2)
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
    path = state_file_path(settings)
    if not path:
        return
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        payload = {
            "results": {
                f"{owner}|{repo}|{branch}": result.model_dump(mode="json")
                for (owner, repo, branch), result in RESULTS.items()
            },
            "jobs": {job_id: job.model_dump(mode="json") for job_id, job in JOBS.items()},
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
    except OSError:
        return
