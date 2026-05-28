import unittest
from datetime import timedelta
from unittest.mock import patch

from fastapi import HTTPException

import main


class MainCoverageTests(unittest.TestCase):
    def setUp(self):
        main.RESULTS.clear()
        main.JOBS.clear()

    def test_health_payload(self):
        payload = main.health()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["service"], "synthcode-api")
        self.assertEqual(payload["model_version"], main.MODEL_VERSION)

    def test_analyze_repo_uses_cache_when_not_forced(self):
        request = main.AnalyzeRequest(owner="OpenAI", repo="DemoRepo", branch="main")
        first = main.analyze_repo(request)
        second = main.analyze_repo(request)

        self.assertEqual(first.result.scanned_at, second.result.scanned_at)
        self.assertEqual(first.result.overall_score, second.result.overall_score)
        self.assertNotEqual(first.job_id, second.job_id)

    def test_get_results_raises_for_missing_or_expired(self):
        with self.assertRaises(HTTPException) as missing:
            main.get_results("missing", "repo")
        self.assertEqual(missing.exception.status_code, 404)

        request = main.AnalyzeRequest(owner="owner", repo="repo", branch="main")
        response = main.analyze_repo(request)
        response.result.expires_at = response.result.scanned_at - timedelta(seconds=1)

        with self.assertRaises(HTTPException) as expired:
            main.get_results("owner", "repo")
        self.assertEqual(expired.exception.status_code, 404)

    def test_get_status_raises_for_unknown_job(self):
        with self.assertRaises(HTTPException) as unknown:
            main.get_status("unknown")
        self.assertEqual(unknown.exception.status_code, 404)

    def test_get_status_returns_created_job(self):
        request = main.AnalyzeRequest(owner="owner", repo="repo", branch="main")
        response = main.analyze_repo(request)
        status = main.get_status(response.job_id)
        self.assertEqual(status.status, "completed")
        self.assertIsNotNone(status.result)

    def test_result_key_normalizes_owner_and_repo(self):
        self.assertEqual(
            main.result_key("Owner", "Repo", "dev"),
            ("owner", "repo", "dev"),
        )

    def test_heuristic_helpers_boundary_behaviors(self):
        self.assertEqual(main.label_for_score(0.29), "human")
        self.assertEqual(main.label_for_score(0.30), "mixed")
        self.assertEqual(main.label_for_score(0.51), "AI-coded")
        self.assertTrue(main.contains_aiish_terms("my-copilot-template"))
        self.assertFalse(main.contains_aiish_terms("source-repository"))
        self.assertEqual(main.clamp(-1), 0.03)
        self.assertEqual(main.clamp(5), 0.97)
        self.assertEqual(main.clamp(0.456789), 0.4568)

    def test_sample_file_scores_are_deterministic(self):
        scores_one = main.sample_file_scores("owner", "repo", "main")
        scores_two = main.sample_file_scores("owner", "repo", "main")
        self.assertEqual(scores_one, scores_two)
        self.assertGreaterEqual(len(scores_one), 6)
        self.assertLessEqual(len(scores_one), 12)
        self.assertTrue(all(0 <= file.score <= 1 for file in scores_one))

    def test_force_rescan_runs_new_analysis(self):
        request = main.AnalyzeRequest(owner="owner", repo="repo", branch="main")
        base = main.analyze_repo(request)
        with patch("main.now_utc", return_value=base.result.scanned_at + timedelta(minutes=10)):
            forced = main.analyze_repo(main.AnalyzeRequest(owner="owner", repo="repo", branch="main", force_rescan=True))
        self.assertNotEqual(base.result.scanned_at, forced.result.scanned_at)


if __name__ == "__main__":
    unittest.main()
