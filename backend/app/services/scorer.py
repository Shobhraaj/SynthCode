from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.config import Settings
from backend.app.models.schemas import AnalysisResult, FileScore, RepoLabel
from backend.app.services.github_fetcher import FileContent
from backend.app.services.heuristic import HeuristicResult
from backend.app.services.inference_client import MLFileScore


class EnsembleScorer:
    ML_WEIGHT = 0.70
    HEURISTIC_WEIGHT = 0.30

    def __init__(self, settings: Settings):
        self.settings = settings

    def score_repo(
        self,
        owner: str,
        repo: str,
        branch: str,
        files: list[FileContent],
        ml_scores: list[MLFileScore],
        heuristic_scores: list[HeuristicResult],
        scanned_commit_sha: str | None = None,
    ) -> AnalysisResult:
        scanned_at = datetime.now(timezone.utc)
        ml_by_path = {score.path: score for score in ml_scores}
        file_scores: list[FileScore] = []

        for file, heuristic in zip(files, heuristic_scores):
            ml_score = ml_by_path.get(file.path, MLFileScore(path=file.path, score=heuristic.composite)).score
            score = clamp((self.ML_WEIGHT * ml_score) + (self.HEURISTIC_WEIGHT * heuristic.composite))
            file_scores.append(
                FileScore(
                    path=file.path,
                    score=score,
                    language=file.language,
                    size_bytes=file.size_bytes,
                    ml_score=clamp(ml_score),
                    heuristic_score=heuristic.composite,
                )
            )

        overall = weighted_mean(file_scores)
        return AnalysisResult(
            owner=owner,
            repo=repo,
            branch=branch,
            overall_score=overall,
            label=label_for_score(overall),
            files_analyzed=len(file_scores),
            file_scores=file_scores,
            scanned_at=scanned_at,
            model_version=self.settings.MODEL_VERSION,
            expires_at=scanned_at + timedelta(days=self.settings.CACHE_TTL_DB_DAYS),
            scanned_commit_sha=scanned_commit_sha,
        )


def weighted_mean(scores: list[FileScore]) -> float:
    if not scores:
        return 0.0
    total_weight = sum(max(1, score.size_bytes) for score in scores)
    return clamp(sum(score.score * max(1, score.size_bytes) for score in scores) / total_weight)


def label_for_score(score: float) -> RepoLabel:
    if score > 0.5:
        return "AI-coded"
    if score >= 0.3:
        return "mixed"
    return "human"


def clamp(value: float) -> float:
    return round(min(1.0, max(0.0, value)), 4)

