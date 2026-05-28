import asyncio

import pytest

from backend.app.config import Settings
from backend.app.models.schemas import AnalysisResult
from backend.app.services.github_fetcher import FileContent, RepoMeta
from backend.app.services.heuristic import HeuristicResult
from backend.app.services.inference_client import InferenceServiceError, MLFileScore
from backend.app.services.pipeline import AnalysisPipeline
from backend.app.services.sampler import TreeEntry


def test_ml_or_heuristic_falls_back_when_inference_disabled():
    pipeline = AnalysisPipeline(Settings(INFERENCE_ENABLED=False))
    files = [FileContent(path="src/a.py", language="Python", size_bytes=10, content="x", sha="1")]
    heuristics = [HeuristicResult(0.6, 0.6, 0.6, 0.6, 0.6, 0.6, composite=0.6)]

    scores = asyncio.run(pipeline._ml_or_heuristic(files, heuristics))

    assert scores == [MLFileScore(path="src/a.py", score=0.6, chunks_analyzed=1)]


def test_ml_or_heuristic_falls_back_on_inference_error():
    class BrokenInference:
        async def predict_batch(self, _files):
            raise InferenceServiceError("offline")

    pipeline = AnalysisPipeline(Settings(INFERENCE_ENABLED=True))
    pipeline.inference = BrokenInference()
    files = [FileContent(path="src/a.py", language="Python", size_bytes=10, content="x", sha="1")]
    heuristics = [HeuristicResult(0.2, 0.2, 0.2, 0.2, 0.2, 0.2, composite=0.2)]

    scores = asyncio.run(pipeline._ml_or_heuristic(files, heuristics))

    assert scores == [MLFileScore(path="src/a.py", score=0.2, chunks_analyzed=1)]


def test_analyze_repo_uses_default_branch_and_reports_progress():
    progress_updates = []
    pipeline = AnalysisPipeline(Settings(INFERENCE_ENABLED=False))

    class StubFetcher:
        async def validate_repo(self, owner, repo):
            assert owner == "openai"
            assert repo == "demo"
            return RepoMeta(owner=owner, repo=repo, default_branch="dev", private=False, pushed_at=None)

        async def fetch_tree(self, owner, repo, branch):
            assert branch == "dev"
            return [TreeEntry(path="src/a.py", type="blob", size=350, sha="tree-sha")]

        async def fetch_files_batch(self, owner, repo, paths, branch):
            assert paths == ["src/a.py"]
            assert branch == "dev"
            return [FileContent(path="src/a.py", language="Python", size_bytes=350, content="print(1)", sha="file-sha")]

    class StubSampler:
        def sample(self, tree, max_files):
            assert len(tree) == 1
            assert max_files == pipeline.settings.MAX_FILES_PER_REPO
            return tree

    class StubHeuristics:
        def analyze_file(self, content, language):
            assert content == "print(1)"
            assert language == "Python"
            return HeuristicResult(0.3, 0.3, 0.3, 0.3, 0.3, 0.3, composite=0.3)

    class StubScorer:
        def score_repo(self, owner, repo, branch, files, ml_scores, heuristic_scores, commit_sha):
            assert branch == "dev"
            assert commit_sha == "tree-sha"
            assert len(files) == 1
            assert ml_scores == [MLFileScore(path="src/a.py", score=0.3, chunks_analyzed=1)]
            assert heuristic_scores[0].composite == 0.3
            return AnalysisResult(
                owner=owner,
                repo=repo,
                branch=branch,
                overall_score=0.3,
                label="mixed",
                files_analyzed=1,
                file_scores=[],
                scanned_at="2026-01-01T00:00:00Z",
                model_version="phase2-heuristic-ensemble-v1",
                expires_at="2026-01-08T00:00:00Z",
            )

    pipeline.fetcher = StubFetcher()
    pipeline.sampler = StubSampler()
    pipeline.heuristics = StubHeuristics()
    pipeline.scorer = StubScorer()

    async def progress(percent, message):
        progress_updates.append((percent, message))

    result = asyncio.run(pipeline.analyze_repo("openai", "demo", "", progress=progress))

    assert result.branch == "dev"
    assert [p for p, _ in progress_updates] == [10, 25, 45, 65, 80, 92]


def test_analyze_repo_raises_when_sampling_empty():
    pipeline = AnalysisPipeline(Settings(INFERENCE_ENABLED=False))

    class StubFetcher:
        async def validate_repo(self, owner, repo):
            return RepoMeta(owner=owner, repo=repo, default_branch="main", private=False, pushed_at=None)

        async def fetch_tree(self, owner, repo, branch):
            return []

    class EmptySampler:
        def sample(self, tree, max_files):
            return []

    pipeline.fetcher = StubFetcher()
    pipeline.sampler = EmptySampler()

    with pytest.raises(ValueError, match="No supported source files"):
        asyncio.run(pipeline.analyze_repo("openai", "demo", "main"))
