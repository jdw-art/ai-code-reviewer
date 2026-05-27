import os
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from biz.agent.task import AgentReviewResult


class TestGithubAgentWorker(TestCase):
    def setUp(self):
        self.previous_agent_review_enabled = os.environ.get("AGENT_REVIEW_ENABLED")
        os.environ["AGENT_REVIEW_ENABLED"] = "1"

    def tearDown(self):
        if self.previous_agent_review_enabled is None:
            os.environ.pop("AGENT_REVIEW_ENABLED", None)
        else:
            os.environ["AGENT_REVIEW_ENABLED"] = self.previous_agent_review_enabled

    def _webhook_data(self):
        return {
            "action": "opened",
            "repository": {"name": "repo", "full_name": "owner/repo"},
            "pull_request": {
                "number": 1,
                "head": {"sha": "abc123", "ref": "feature"},
                "base": {"ref": "main"},
                "user": {"login": "octocat"},
                "html_url": "https://github.com/owner/repo/pull/1",
            },
        }

    def _handler(self):
        handler = MagicMock()
        handler.action = "opened"
        handler.get_pull_request_changes.return_value = [
            {"new_path": "src/app.py", "diff": "+print('hello')", "additions": 1, "deletions": 0}
        ]
        handler.get_pull_request_commits.return_value = [{"message": "Add app"}]
        return handler

    @patch("biz.queue.worker.event_manager")
    @patch("biz.queue.worker.GitHubFileReader")
    @patch("biz.queue.worker.ReviewAgent")
    @patch("biz.queue.worker.GithubPullRequestHandler")
    @patch("biz.queue.worker.ReviewService.check_mr_last_commit_id_exists", return_value=False)
    def test_github_pr_uses_agent_when_enabled(
        self,
        _check_exists,
        handler_cls,
        agent_cls,
        reader_cls,
        event_manager,
    ):
        webhook_data = self._webhook_data()
        handler = self._handler()
        handler_cls.return_value = handler
        agent_cls.return_value.review.return_value = AgentReviewResult(
            review_text="Risk level: low\nNo numeric score in this text.",
            score=88,
            risk_level="low",
            investigated_files=["src/app.py"],
            investigation_summary="Checked src/app.py.",
            warnings=[],
            agent_trace={"mode": "context_investigation"},
        )

        from biz.queue.worker import handle_github_pull_request_event

        handle_github_pull_request_event(webhook_data, "token", "https://github.com", "github_com")

        reader_cls.assert_called_once()
        agent_cls.return_value.review.assert_called_once()
        handler.add_pull_request_notes.assert_called_once()
        event_manager["merge_request_reviewed"].send.assert_called_once()
        entity = event_manager["merge_request_reviewed"].send.call_args.args[0]
        self.assertEqual(entity.score, 88)
        self.assertIn("context_investigation", entity.agent_trace)

    @patch("biz.queue.worker.event_manager")
    @patch("biz.queue.worker.CodeReviewer")
    @patch("biz.queue.worker.GitHubFileReader")
    @patch("biz.queue.worker.ReviewAgent")
    @patch("biz.queue.worker.GithubPullRequestHandler")
    @patch("biz.queue.worker.ReviewService.check_mr_last_commit_id_exists", return_value=False)
    def test_github_pr_uses_classic_reviewer_when_agent_disabled(
        self,
        _check_exists,
        handler_cls,
        agent_cls,
        reader_cls,
        code_reviewer_cls,
        event_manager,
    ):
        os.environ["AGENT_REVIEW_ENABLED"] = "0"
        webhook_data = self._webhook_data()
        handler = self._handler()
        handler_cls.return_value = handler
        code_reviewer_cls.return_value.review_and_strip_code.return_value = "Classic review\n总分: 76分"
        code_reviewer_cls.parse_review_score.return_value = 76

        from biz.queue.worker import handle_github_pull_request_event

        handle_github_pull_request_event(webhook_data, "token", "https://github.com", "github_com")

        reader_cls.assert_not_called()
        agent_cls.assert_not_called()
        code_reviewer_cls.return_value.review_and_strip_code.assert_called_once()
        event_manager["merge_request_reviewed"].send.assert_called_once()
        entity = event_manager["merge_request_reviewed"].send.call_args.args[0]
        self.assertEqual(entity.score, 76)
        self.assertEqual(entity.review_result, "Classic review\n总分: 76分")

    @patch("biz.queue.worker.event_manager")
    @patch("biz.queue.worker.CodeReviewer")
    @patch("biz.queue.worker.GitHubFileReader")
    @patch("biz.queue.worker.ReviewAgent")
    @patch("biz.queue.worker.GithubPullRequestHandler")
    @patch("biz.queue.worker.ReviewService.check_mr_last_commit_id_exists", return_value=False)
    def test_github_pr_falls_back_to_classic_reviewer_when_agent_raises(
        self,
        _check_exists,
        handler_cls,
        agent_cls,
        reader_cls,
        code_reviewer_cls,
        event_manager,
    ):
        webhook_data = self._webhook_data()
        handler = self._handler()
        handler_cls.return_value = handler
        agent_cls.return_value.review.side_effect = RuntimeError("agent unavailable")
        code_reviewer_cls.return_value.review_and_strip_code.return_value = "Classic fallback\n总分: 64分"
        code_reviewer_cls.parse_review_score.return_value = 64

        from biz.queue.worker import handle_github_pull_request_event

        handle_github_pull_request_event(webhook_data, "token", "https://github.com", "github_com")

        reader_cls.assert_called_once()
        agent_cls.return_value.review.assert_called_once()
        code_reviewer_cls.return_value.review_and_strip_code.assert_called_once()
        event_manager["merge_request_reviewed"].send.assert_called_once()
        entity = event_manager["merge_request_reviewed"].send.call_args.args[0]
        self.assertEqual(entity.score, 64)
        self.assertEqual(entity.agent_trace, "")


if __name__ == "__main__":
    main()
