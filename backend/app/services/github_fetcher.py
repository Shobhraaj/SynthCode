from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from time import time
from typing import Any

from backend.app.config import Settings
from backend.app.services.sampler import TreeEntry, infer_language


class GitHubServiceError(RuntimeError):
    pass


class RepoNotFoundError(GitHubServiceError):
    pass


@dataclass(frozen=True)
class RepoMeta:
    owner: str
    repo: str
    default_branch: str
    private: bool
    pushed_at: str | None


@dataclass(frozen=True)
class FileContent:
    path: str
    language: str
    size_bytes: int
    content: str
    sha: str


class GitHubFetcher:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def validate_repo(self, owner: str, repo: str) -> RepoMeta:
        data = await self._request_json("GET", f"/repos/{owner}/{repo}")
        if not isinstance(data, dict):
            raise GitHubServiceError("Unexpected repository metadata response")
        return RepoMeta(
            owner=data["owner"]["login"],
            repo=data["name"],
            default_branch=data.get("default_branch") or "main",
            private=bool(data.get("private", False)),
            pushed_at=data.get("pushed_at"),
        )

    async def fetch_tree(self, owner: str, repo: str, branch: str) -> list[TreeEntry]:
        data = await self._request_json(
            "GET",
            f"/repos/{owner}/{repo}/git/trees/{branch}",
            params={"recursive": "1"},
        )
        if not isinstance(data, dict) or "tree" not in data:
            raise GitHubServiceError("Unexpected repository tree response")
        return [
            TreeEntry(
                path=item.get("path", ""),
                type=item.get("type", ""),
                size=int(item.get("size") or 0),
                sha=item.get("sha", ""),
                url=item.get("url"),
            )
            for item in data["tree"]
            if item.get("path")
        ]

    async def fetch_file_content(self, owner: str, repo: str, path: str, branch: str = "main") -> FileContent:
        data = await self._request_json(
            "GET",
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": branch},
        )
        if not isinstance(data, dict) or data.get("type") != "file":
            raise GitHubServiceError(f"Unexpected file content response for {path}")
        encoded = data.get("content", "")
        content = base64.b64decode(encoded).decode("utf-8", errors="replace")
        return FileContent(
            path=data.get("path", path),
            language=infer_language(path),
            size_bytes=int(data.get("size") or len(content.encode("utf-8"))),
            content=content,
            sha=data.get("sha", ""),
        )

    async def fetch_files_batch(
        self,
        owner: str,
        repo: str,
        paths: list[str],
        branch: str = "main",
    ) -> list[FileContent]:
        tasks = [self.fetch_file_content(owner, repo, path, branch) for path in paths]
        return list(await asyncio.gather(*tasks))

    async def _request_json(self, method: str, path: str, params: dict[str, str] | None = None) -> Any:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise GitHubServiceError("Install httpx to use GitHub integration") from exc

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SynthCode",
        }
        if self.settings.GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {self.settings.GITHUB_TOKEN}"

        async with httpx.AsyncClient(
            base_url=self.settings.GITHUB_API_BASE,
            timeout=20,
            headers=headers,
        ) as client:
            response = await client.request(method, path, params=params)
            await self._respect_rate_limit(response)
            if response.status_code == 404:
                raise RepoNotFoundError("Repository was not found or is inaccessible")
            if response.status_code >= 400:
                raise GitHubServiceError(f"GitHub API returned {response.status_code}: {response.text[:200]}")
            return response.json()

    async def _respect_rate_limit(self, response) -> None:
        remaining = int(response.headers.get("X-RateLimit-Remaining") or 9999)
        if remaining == 0:
            reset = int(response.headers.get("X-RateLimit-Reset") or time())
            await asyncio.sleep(max(0, reset - int(time())))
        elif remaining < self.settings.GITHUB_LOW_RATE_REMAINING:
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                await asyncio.sleep(min(int(retry_after), 5))
            else:
                reset_header = response.headers.get("X-RateLimit-Reset")
                reset_dt = parsedate_to_datetime(reset_header).timestamp() if reset_header and not reset_header.isdigit() else None
                if reset_dt and reset_dt > time():
                    await asyncio.sleep(1)

