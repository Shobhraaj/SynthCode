from __future__ import annotations

from backend.app.config import Settings
from backend.app.models.schemas import AnalysisResult
from backend.app.services.github_fetcher import GitHubFetcher
from backend.app.services.heuristic import HeuristicAnalyzer
from backend.app.services.inference_client import InferenceClient, InferenceServiceError, MLFileScore
from backend.app.services.sampler import FileSampler
from backend.app.services.scorer import EnsembleScorer


class AnalysisPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.fetcher = GitHubFetcher(settings)
        self.sampler = FileSampler(settings.MIN_FILE_BYTES, settings.MAX_FILE_BYTES)
        self.heuristics = HeuristicAnalyzer()
        self.inference = InferenceClient(settings)
        self.scorer = EnsembleScorer(settings)

    async def analyze_repo(self, owner: str, repo: str, branch: str, progress=None) -> AnalysisResult:
        await self._progress(progress, 10, "Validating repository...")
        meta = await self.fetcher.validate_repo(owner, repo)
        effective_branch = branch or meta.default_branch

        await self._progress(progress, 25, "Fetching repository tree...")
        tree = await self.fetcher.fetch_tree(owner, repo, effective_branch)
        sampled = self.sampler.sample(tree, self.settings.MAX_FILES_PER_REPO)
        if not sampled:
            raise ValueError("No supported source files were found in this repository")

        await self._progress(progress, 45, "Fetching sampled file contents...")
        files = await self.fetcher.fetch_files_batch(owner, repo, [entry.path for entry in sampled], effective_branch)

        await self._progress(progress, 65, "Running heuristic analysis...")
        heuristic_scores = [self.heuristics.analyze_file(file.content, file.language) for file in files]

        await self._progress(progress, 80, "Running ML inference...")
        ml_scores = await self._ml_or_heuristic(files, heuristic_scores)

        await self._progress(progress, 92, "Combining signals...")
        commit_sha = sampled[0].sha if sampled else None
        return self.scorer.score_repo(owner, repo, effective_branch, files, ml_scores, heuristic_scores, commit_sha)

    async def _ml_or_heuristic(self, files, heuristic_scores) -> list[MLFileScore]:
        if self.settings.INFERENCE_ENABLED:
            try:
                return await self.inference.predict_batch(files)
            except InferenceServiceError:
                pass
        return [
            MLFileScore(path=file.path, score=heuristic.composite, chunks_analyzed=1)
            for file, heuristic in zip(files, heuristic_scores)
        ]

    async def _progress(self, callback, progress: int, message: str) -> None:
        if callback:
            await callback(progress, message)

