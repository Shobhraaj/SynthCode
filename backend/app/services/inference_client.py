from __future__ import annotations

import asyncio
from dataclasses import dataclass

from backend.app.config import Settings
from backend.app.services.github_fetcher import FileContent


class InferenceServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class MLFileScore:
    path: str
    score: float
    chunks_analyzed: int = 0


class InferenceClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.INFERENCE_SERVICE_URL.rstrip("/")
        self.timeout = settings.INFERENCE_TIMEOUT
        self.max_retries = settings.INFERENCE_MAX_RETRIES

    async def predict_batch(self, files: list[FileContent]) -> list[MLFileScore]:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise InferenceServiceError("Install httpx to use inference integration") from exc

        payload = {
            "files": [
                {"path": file.path, "language": file.language, "content": file.content}
                for file in files
            ]
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await client.post(f"{self.base_url}/predict/batch", json=payload)
                    response.raise_for_status()
                    data = response.json()
                    return [
                        MLFileScore(
                            path=item["path"],
                            score=float(item["score"]),
                            chunks_analyzed=int(item.get("chunks_analyzed") or 0),
                        )
                        for item in data.get("scores", [])
                    ]
                except (httpx.ConnectError, httpx.ReadTimeout, httpx.HTTPStatusError) as exc:
                    if attempt == self.max_retries:
                        raise InferenceServiceError(f"GPU service unreachable: {exc}") from exc
                    await asyncio.sleep(2**attempt)

        return []

    async def health_check(self) -> bool:
        try:
            import httpx
        except ImportError:  # pragma: no cover
            return False
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{self.base_url}/health")
            return response.status_code == 200

