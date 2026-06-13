from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.config import Settings
from backend.app.models.schemas import AnalysisResult, FileScore, RepoLabel
from backend.app.services.github_fetcher import FileContent
from backend.app.services.heuristic import HeuristicResult
from backend.app.services.inference_client import MLFileScore
from backend.app.services.heuristic import SIGNAL_WEIGHTS


class EnsembleScorer:
    ML_WEIGHT = 0.70
    HEURISTIC_WEIGHT = 0.30
    ML_WEIGHT_NO_CHUNKS = 0.20
    HEURISTIC_WEIGHT_NO_CHUNKS = 0.80
    CHUNKS_FOR_FULL_COVERAGE = 3
    MIN_COVERAGE_NO_CHUNKS = 0.15
    AGREEMENT_WEIGHT = 0.75
    COVERAGE_WEIGHT = 0.25

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
            ml_meta = ml_by_path.get(file.path, MLFileScore(path=file.path, score=heuristic.composite))
            ml_score = clamp(ml_meta.score)
            ml_weight, heuristic_weight = self._weights_for_file(ml_meta.chunks_analyzed)
            score = clamp((ml_weight * ml_score) + (heuristic_weight * heuristic.composite))
            confidence = self._file_confidence(ml_score, heuristic.composite, ml_meta.chunks_analyzed)
            top_signals = top_signal_names(heuristic)
            file_scores.append(
                FileScore(
                    path=file.path,
                    score=score,
                    language=file.language,
                    size_bytes=file.size_bytes,
                    ml_score=ml_score,
                    heuristic_score=heuristic.composite,
                    confidence=confidence,
                    top_signals=top_signals,
                )
            )

        overall = weighted_mean(file_scores)
        confidence = weighted_confidence(file_scores)
        explanation = build_repo_explanation(file_scores)
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
            confidence=confidence,
            explanation=explanation,
            expires_at=scanned_at + timedelta(days=self.settings.CACHE_TTL_DB_DAYS),
            scanned_commit_sha=scanned_commit_sha,
        )

    def _weights_for_file(self, chunks_analyzed: int) -> tuple[float, float]:
        if chunks_analyzed <= 0:
            return self.ML_WEIGHT_NO_CHUNKS, self.HEURISTIC_WEIGHT_NO_CHUNKS
        return self.ML_WEIGHT, self.HEURISTIC_WEIGHT

    def _file_confidence(self, ml_score: float, heuristic_score: float, chunks_analyzed: int) -> float:
        agreement = 1.0 - abs(ml_score - heuristic_score)
        coverage = (
            min(1.0, max(0.0, chunks_analyzed / self.CHUNKS_FOR_FULL_COVERAGE))
            if chunks_analyzed > 0
            else self.MIN_COVERAGE_NO_CHUNKS
        )
        return clamp((agreement * self.AGREEMENT_WEIGHT) + (coverage * self.COVERAGE_WEIGHT))


def weighted_mean(scores: list[FileScore]) -> float:
    if not scores:
        return 0.0
    total_weight = sum(max(1, score.size_bytes) for score in scores)
    return clamp(sum(score.score * max(1, score.size_bytes) for score in scores) / total_weight)


def weighted_confidence(scores: list[FileScore]) -> float:
    if not scores:
        return 0.0
    total_weight = sum(max(1, score.size_bytes) for score in scores)
    return clamp(sum(score.confidence * max(1, score.size_bytes) for score in scores) / total_weight)


def label_for_score(score: float) -> RepoLabel:
    if score > 0.5:
        return "AI-coded"
    if score >= 0.3:
        return "mixed"
    return "human"


def clamp(value: float) -> float:
    return round(min(1.0, max(0.0, value)), 4)


def top_signal_names(heuristic: HeuristicResult, limit: int = 3) -> list[str]:
    signal_values = heuristic.asdict()
    weighted = []
    for name, weight in SIGNAL_WEIGHTS.items():
        weighted.append((signal_values.get(name, 0.0) * weight, name))
    weighted.sort(reverse=True)
    return [name for _, name in weighted[:limit]]


def build_repo_explanation(file_scores: list[FileScore]) -> list[str]:
    if not file_scores:
        return []
    counts: dict[str, int] = {}
    for file in file_scores:
        for signal in file.top_signals:
            counts[signal] = counts.get(signal, 0) + 1
    top = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:3]
    return [f"{name} appeared in {count} high-impact files" for name, count in top]
