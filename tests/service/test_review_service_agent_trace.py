import importlib
import os
import sys
import tempfile
from unittest import TestCase, main


class TestReviewServiceAgentTrace(TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        self.original_review_db_file = os.environ.get("REVIEW_DB_FILE")
        self.module_name = "biz.service.review_service"
        self.original_review_service_module = sys.modules.pop(self.module_name, None)
        self.service_package = importlib.import_module("biz.service")
        self.had_review_service_attr = hasattr(self.service_package, "review_service")
        self.original_review_service_attr = getattr(self.service_package, "review_service", None)
        if self.had_review_service_attr:
            delattr(self.service_package, "review_service")

        os.environ["REVIEW_DB_FILE"] = self.tmp.name
        review_service_module = importlib.import_module(self.module_name)
        review_entity_module = importlib.import_module("biz.entity.review_entity")
        self.ReviewService = review_service_module.ReviewService
        self.MergeRequestReviewEntity = review_entity_module.MergeRequestReviewEntity

    def tearDown(self):
        sys.modules.pop(self.module_name, None)
        if self.original_review_service_module is not None:
            sys.modules[self.module_name] = self.original_review_service_module
        if self.had_review_service_attr:
            setattr(self.service_package, "review_service", self.original_review_service_attr)
        elif hasattr(self.service_package, "review_service"):
            delattr(self.service_package, "review_service")

        if self.original_review_db_file is None:
            os.environ.pop("REVIEW_DB_FILE", None)
        else:
            os.environ["REVIEW_DB_FILE"] = self.original_review_db_file
        os.unlink(self.tmp.name)

    def test_insert_mr_review_log_stores_agent_trace(self):
        entity = self.MergeRequestReviewEntity(
            project_name="repo",
            author="octocat",
            source_branch="feature",
            target_branch="main",
            updated_at=1,
            commits=[{"message": "Add feature"}],
            score=90,
            url="https://github.com/owner/repo/pull/1",
            review_result="总分: 90分",
            url_slug="github_com",
            webhook_data={},
            additions=1,
            deletions=0,
            last_commit_id="abc123",
            agent_trace='{"mode": "context_investigation"}',
        )

        self.ReviewService.insert_mr_review_log(entity)
        df = self.ReviewService.get_mr_review_logs(include_agent_trace=True)

        self.assertEqual(df.iloc[0]["agent_trace"], '{"mode": "context_investigation"}')

    def test_get_mr_review_logs_only_returns_agent_trace_when_requested(self):
        entity = self.MergeRequestReviewEntity(
            project_name="repo",
            author="octocat",
            source_branch="feature",
            target_branch="main",
            updated_at=1,
            commits=[{"message": "Add feature"}],
            score=90,
            url="https://github.com/owner/repo/pull/1",
            review_result="总分: 90分",
            url_slug="github_com",
            webhook_data={},
            additions=1,
            deletions=0,
            last_commit_id="abc123",
            agent_trace='{"mode": "context_investigation"}',
        )

        self.ReviewService.insert_mr_review_log(entity)
        default_df = self.ReviewService.get_mr_review_logs()
        trace_df = self.ReviewService.get_mr_review_logs(include_agent_trace=True)

        self.assertNotIn("agent_trace", default_df.columns)
        self.assertIn("agent_trace", trace_df.columns)


if __name__ == "__main__":
    main()
