from unittest import TestCase, main
from unittest.mock import MagicMock, patch


class TestMergeRequestWorkerMetadata(TestCase):
    def _gitlab_webhook_data(self):
        return {
            "object_kind": "merge_request",
            "project": {
                "id": 123,
                "name": "repo",
                "path_with_namespace": "group/repo",
            },
            "user": {"username": "octocat"},
            "object_attributes": {
                "iid": 1,
                "action": "open",
                "source_branch": "feature",
                "target_branch": "main",
                "url": "https://gitlab.example.com/group/repo/-/merge_requests/1",
                "target_project_id": 123,
                "last_commit": {"id": "abc123"},
            },
        }

    def _gitlab_handler(self):
        handler = MagicMock()
        handler.action = "open"
        handler.get_merge_request_changes.return_value = [
            {"new_path": "src/app.py", "diff": "+print('hello')", "additions": 1, "deletions": 0}
        ]
        handler.get_merge_request_commits.return_value = [{"message": "Add app"}]
        return handler

    def _gitea_webhook_data(self):
        return {
            "action": "opened",
            "repository": {
                "name": "repo",
                "full_name": "owner/repo",
            },
            "pull_request": {
                "number": 1,
                "head": {"sha": "abc123", "ref": "feature"},
                "base": {"ref": "main"},
                "user": {"login": "octocat"},
                "html_url": "https://gitea.example.com/owner/repo/pulls/1",
            },
        }

    def _gitea_handler(self):
        handler = MagicMock()
        handler.action = "opened"
        handler.get_pull_request_changes.return_value = [
            {"new_path": "src/app.py", "diff": "+print('hello')", "additions": 1, "deletions": 0}
        ]
        handler.get_pull_request_commits.return_value = [{"message": "Add app"}]
        return handler

    @patch("biz.queue.worker.event_manager")
    @patch("biz.queue.worker.CodeReviewer")
    @patch("biz.queue.worker.MergeRequestHandler")
    @patch("biz.queue.worker.ReviewService.check_mr_last_commit_id_exists", return_value=False)
    def test_gitlab_mr_persists_non_github_metadata(
        self,
        _check_exists,
        handler_cls,
        code_reviewer_cls,
        event_manager,
    ):
        webhook_data = self._gitlab_webhook_data()
        handler = self._gitlab_handler()
        handler_cls.return_value = handler
        code_reviewer_cls.return_value.review_and_strip_code.return_value = "Risk level: high\n总分: 82分"
        code_reviewer_cls.return_value.review_mode_name = "baseline_review"
        code_reviewer_cls.return_value.review_profile_name = "default_review"
        code_reviewer_cls.parse_review_score.return_value = 82
        code_reviewer_cls.parse_risk_level.return_value = "high"

        from biz.queue.worker import handle_merge_request_event

        handle_merge_request_event(webhook_data, "token", "https://gitlab.example.com", "gitlab_example")

        event_manager["merge_request_reviewed"].send.assert_called_once()
        entity = event_manager["merge_request_reviewed"].send.call_args.args[0]
        self.assertEqual(entity.platform, "gitlab")
        self.assertEqual(entity.project_id, "group/repo")
        self.assertEqual(entity.review_mode, "baseline_review")
        self.assertEqual(entity.review_profile, "default_review")
        self.assertEqual(entity.risk_level, "high")

    @patch("biz.queue.worker.event_manager")
    @patch("biz.queue.worker.CodeReviewer")
    @patch("biz.queue.worker.GiteaPullRequestHandler")
    @patch("biz.queue.worker.ReviewService.check_mr_last_commit_id_exists", return_value=False)
    def test_gitea_mr_persists_non_github_metadata(
        self,
        _check_exists,
        handler_cls,
        code_reviewer_cls,
        event_manager,
    ):
        webhook_data = self._gitea_webhook_data()
        handler = self._gitea_handler()
        handler_cls.return_value = handler
        code_reviewer_cls.return_value.review_and_strip_code.return_value = "Risk level: low\n总分: 78分"
        code_reviewer_cls.return_value.review_mode_name = "baseline_review"
        code_reviewer_cls.return_value.review_profile_name = "default_review"
        code_reviewer_cls.parse_review_score.return_value = 78
        code_reviewer_cls.parse_risk_level.return_value = "low"

        from biz.queue.worker import handle_gitea_pull_request_event

        handle_gitea_pull_request_event(webhook_data, "token", "https://gitea.example.com", "gitea_example")

        event_manager["merge_request_reviewed"].send.assert_called_once()
        entity = event_manager["merge_request_reviewed"].send.call_args.args[0]
        self.assertEqual(entity.platform, "gitea")
        self.assertEqual(entity.project_id, "owner/repo")
        self.assertEqual(entity.review_mode, "baseline_review")
        self.assertEqual(entity.review_profile, "default_review")
        self.assertEqual(entity.risk_level, "low")


if __name__ == "__main__":
    main()
