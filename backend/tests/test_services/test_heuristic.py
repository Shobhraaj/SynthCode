from backend.app.services.heuristic import HeuristicAnalyzer


def test_heuristic_analyzer_returns_normalized_scores():
    content = """
import os
import sys

def process_data(value):
    # Validate input
    if value is None:
        raise ValueError("value is required")
    try:
        return str(value).strip()
    except Exception:
        return None
"""

    result = HeuristicAnalyzer().analyze_file(content, "Python")

    assert 0 <= result.composite <= 1
    assert 0 <= result.boilerplate_ratio <= 1

