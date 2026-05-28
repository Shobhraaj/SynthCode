from backend.app.config import Settings
from backend.app.models.schemas import FileScore
from backend.app.services.github_fetcher import FileContent
from backend.app.services.heuristic import HeuristicResult
from backend.app.services.inference_client import MLFileScore
from backend.app.services.scorer import EnsembleScorer, clamp, label_for_score, weighted_mean


def test_ensemble_scorer_blends_scores_and_falls_back_to_heuristic():
    scorer = EnsembleScorer(Settings())
    files = [
        FileContent(path="src/a.py", language="Python", size_bytes=100, content="", sha="sha-a"),
        FileContent(path="src/b.py", language="Python", size_bytes=300, content="", sha="sha-b"),
    ]
    heuristics = [
        HeuristicResult(0.2, 0.2, 0.2, 0.2, 0.2, 0.2, composite=0.2),
        HeuristicResult(0.4, 0.4, 0.4, 0.4, 0.4, 0.4, composite=0.4),
    ]
    ml_scores = [MLFileScore(path="src/a.py", score=0.9, chunks_analyzed=2)]

    result = scorer.score_repo(
        owner="owner",
        repo="repo",
        branch="main",
        files=files,
        ml_scores=ml_scores,
        heuristic_scores=heuristics,
        scanned_commit_sha="commit-sha",
    )

    assert result.files_analyzed == 2
    assert result.file_scores[0].score == 0.69
    assert result.file_scores[0].ml_score == 0.9
    assert result.file_scores[1].score == 0.4
    assert result.file_scores[1].ml_score == 0.4
    assert result.overall_score == 0.4725
    assert result.label == "mixed"
    assert result.scanned_commit_sha == "commit-sha"


def test_weighted_mean_and_label_boundaries():
    assert weighted_mean([]) == 0.0
    scores = [
        FileScore(path="a", score=0.0, language="Python", size_bytes=0),
        FileScore(path="b", score=1.0, language="Python", size_bytes=0),
    ]
    assert weighted_mean(scores) == 0.5
    assert label_for_score(0.29) == "human"
    assert label_for_score(0.3) == "mixed"
    assert label_for_score(0.51) == "AI-coded"
    assert clamp(-2.0) == 0.0
    assert clamp(2.0) == 1.0
