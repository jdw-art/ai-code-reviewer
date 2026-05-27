from unittest import TestCase, main
from unittest.mock import patch

from biz.utils import code_reviewer
from biz.agent.review_agent import ReviewAgent
from biz.agent.task import CollectedContext, FileReadResult, ReviewTask


class FakeReader:
    def read_file(self, path, ref):
        return FileReadResult(path=path, ref=ref, ok=True, content="def validate_token():\n    return True")


class FakeReviewer:
    def __init__(self, text):
        self.text = text

    def review_evidence(self, evidence):
        self.evidence = evidence
        return self.text


class FakeCollector:
    def collect(self, plan, file_reader):
        return (
            [
                CollectedContext(
                    path="src/auth.py",
                    ref="abc123",
                    reason="Read changed file context for the PR head ref.",
                    content="def validate_token():\n    return True",
                ),
                CollectedContext(
                    path="tests/test_auth.py",
                    ref="abc123",
                    reason="Check whether related tests cover src/auth.py.",
                    content="def test_validate_token():\n    assert validate_token()",
                ),
            ],
            [],
        )


class RaisingAnalyzer:
    def analyze(self, changes):
        raise RuntimeError("prompt-bearing details should not leak")


class FakeFallbackReviewer:
    def review_and_strip_code(self, changes_text, commits_text=""):
        self.changes_text = changes_text
        self.commits_text = commits_text
        return "## Review\nRisk level: high\n总分: 61分"


class TestReviewAgent(TestCase):
    def _task(self):
        return ReviewTask(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            source_branch="feature/login",
            target_branch="main",
            change_ref="abc123",
            author="octocat",
            url="https://github.com/owner/repo/pull/1",
            commits=[{"message": "Add login validation"}],
            changes=[
                {
                    "new_path": "src/auth.py",
                    "diff": "+def validate_token():\n+    return True",
                    "additions": 2,
                    "deletions": 0,
                }
            ],
            access_token="token",
            platform_url="https://github.com",
        )

    def test_returns_agent_result_with_trace(self):
        reviewer = FakeReviewer("## Review\nRisk level: medium\n总分: 88分")
        result = ReviewAgent(file_reader=FakeReader(), reviewer=reviewer).review(self._task())

        self.assertEqual(result.score, 88)
        self.assertEqual(result.risk_level, "medium")
        self.assertEqual(result.investigated_files, ["src/auth.py", "tests/test_auth.py", "src/test_auth.py"])
        self.assertEqual(result.agent_trace["mode"], "context_investigation")
        self.assertIn("src/auth.py", reviewer.evidence)

    def test_investigated_files_include_related_successful_contexts(self):
        reviewer = FakeReviewer("## Review\nRisk level: medium\n总分: 88分")
        result = ReviewAgent(file_reader=FakeReader(), reviewer=reviewer, collector=FakeCollector()).review(self._task())

        self.assertEqual(result.investigated_files, ["src/auth.py", "tests/test_auth.py"])
        self.assertEqual(
            [item["path"] for item in result.agent_trace["investigated_files"]],
            ["src/auth.py", "tests/test_auth.py"],
        )

    def test_falls_back_to_classic_review_when_agent_orchestration_fails(self):
        fallback_reviewer = FakeFallbackReviewer()
        result = ReviewAgent(
            file_reader=FakeReader(),
            reviewer=FakeReviewer("unused"),
            analyzer=RaisingAnalyzer(),
            fallback_reviewer=fallback_reviewer,
        ).review(self._task())

        self.assertEqual(result.review_text, "## Review\nRisk level: high\n总分: 61分")
        self.assertEqual(result.score, 61)
        self.assertEqual(result.risk_level, "high")
        self.assertEqual(result.investigated_files, [])
        self.assertEqual(result.agent_trace["mode"], "classic_fallback")
        self.assertIn("RuntimeError", result.warnings[0])
        self.assertNotIn("prompt-bearing details", result.warnings[0])
        self.assertEqual(fallback_reviewer.commits_text, "Add login validation")

    def test_uses_shared_review_score_parser(self):
        reviewer = FakeReviewer("## Review\nRisk level: low\nscore from unusual format")

        with patch.object(code_reviewer.CodeReviewer, "parse_review_score", return_value=77) as parse_score:
            result = ReviewAgent(file_reader=FakeReader(), reviewer=reviewer).review(self._task())

        parse_score.assert_called_once_with(reviewer.text)
        self.assertEqual(result.score, 77)


if __name__ == "__main__":
    main()
