from __future__ import annotations

import asyncio

from backend.app.config import get_settings
from backend.app.services.pipeline import AnalysisPipeline
from backend.app.workers.celery_app import celery_app


if celery_app:

    @celery_app.task(bind=True, max_retries=2, soft_time_limit=120)
    def analyze_repo(self, owner: str, repo: str, branch: str = "main", job_id: str | None = None):
        async def run():
            pipeline = AnalysisPipeline(get_settings())
            return await pipeline.analyze_repo(owner, repo, branch)

        result = asyncio.run(run())
        return result.model_dump(mode="json")

