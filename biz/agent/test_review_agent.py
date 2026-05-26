from unittest import TestCase, main

from biz.agent.review_agent import ReviewAgent
from biz.agent.task import FileReadResult, ReviewTask


class FakeReader:
    def read_file(self, path, ref):
        return FileReadResult(path=path, ref=ref, ok=True, content="def validate_token():\n    return True")


class FakeReviewer:
    def __init__(self, text):
        self.text = text

    def review_evidence(self, evidence):
        self.evidence = evidence
        return self.text


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
        self.assertEqual(result.investigated_files, ["src/auth.py"])
        self.assertEqual(result.agent_trace["mode"], "context_investigation")
        self.assertIn("src/auth.py", reviewer.evidence)


if __name__ == "__main__":
    main()
