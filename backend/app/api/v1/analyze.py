from __future__ import annotations

import asyncio
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
        return AnalyzeResponse(job_id=job_id, status="completed", result_url=result_url(request.owner, request.repo, request.branch), result=cached)

    job_id = str(uuid.uuid4())
    JOBS[job_id] = JobStatus(job_id=job_id, status="queued", progress=0, message="Queued for analysis.")
    background_tasks.add_task(run_analysis_job, job_id, request, settings)
    return AnalyzeResponse(job_id=job_id, status="queued")


@router.get("/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str) -> JobStatus:
    status = JOBS.get(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return status


@router.get("/results/{owner}/{repo}", response_model=AnalysisResult)
async def get_results(owner: str, repo: str, branch: str = "main") -> AnalysisResult:
    result = RESULTS.get(result_key(owner, repo, branch))
    if not result or result.expires_at <= now_utc():
        raise HTTPException(status_code=404, detail="No cached analysis found")
    return result


async def run_analysis_job(job_id: str, request: AnalyzeRequest, settings: Settings) -> None:
    async def progress(percent: int, message: str) -> None:
        JOBS[job_id] = JOBS[job_id].model_copy(update={"status": "processing", "progress": percent, "message": message})

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
    except asyncio.TimeoutError as exc:
        JOBS[job_id] = JobStatus(job_id=job_id, status="timeout", progress=100, message="Analysis timed out.", error=str(exc))
    except Exception as exc:
        JOBS[job_id] = JobStatus(job_id=job_id, status="failed", progress=100, message="Analysis failed.", error=str(exc))


def result_key(owner: str, repo: str, branch: str) -> tuple[str, str, str]:
    return (owner.lower(), repo.lower(), branch or "main")


def result_url(owner: str, repo: str, branch: str) -> str:
    return f"/api/v1/results/{owner}/{repo}?branch={branch}"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)

