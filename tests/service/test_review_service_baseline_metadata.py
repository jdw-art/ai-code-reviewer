import importlib
import os
import sys
import tempfile
from unittest import TestCase, main


class TestReviewServiceBaselineMetadata(TestCase):
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

    def test_insert_and_query_baseline_metadata(self):
        entity = self.MergeRequestReviewEntity(
            project_name="repo",
            project_id="owner/repo",
            platform="github",
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
            review_mode="baseline_review",
            review_profile="security_review",
            risk_level="high",
        )

        self.ReviewService.insert_mr_review_log(entity)
        df = self.ReviewService.get_mr_review_logs(include_agent_trace=True, include_review_metadata=True)

        self.assertEqual(df.iloc[0]["platform"], "github")
        self.assertEqual(df.iloc[0]["project_id"], "owner/repo")
        self.assertEqual(df.iloc[0]["review_profile"], "security_review")
        self.assertEqual(df.iloc[0]["risk_level"], "high")

    def test_check_mr_last_commit_id_exists_scopes_by_platform_and_project_id(self):
        github_entity = self.MergeRequestReviewEntity(
            project_name="repo",
            project_id="owner/repo",
            platform="github",
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
        )
        gitlab_entity = self.MergeRequestReviewEntity(
            project_name="repo",
            project_id="group/repo",
            platform="gitlab",
            author="octocat",
            source_branch="feature",
            target_branch="main",
            updated_at=2,
            commits=[{"message": "Add feature"}],
            score=88,
            url="https://gitlab.example.com/group/repo/-/merge_requests/1",
            review_result="总分: 88分",
            url_slug="gitlab_example",
            webhook_data={},
            additions=1,
            deletions=0,
            last_commit_id="abc123",
        )

        self.ReviewService.insert_mr_review_log(github_entity)
        self.ReviewService.insert_mr_review_log(gitlab_entity)

        self.assertTrue(
            self.ReviewService.check_mr_last_commit_id_exists(
                "github", "owner/repo", "repo", "feature", "main", "abc123"
            )
        )
        self.assertTrue(
            self.ReviewService.check_mr_last_commit_id_exists(
                "gitlab", "group/repo", "repo", "feature", "main", "abc123"
            )
        )
        self.assertFalse(
            self.ReviewService.check_mr_last_commit_id_exists(
                "github", "fork/repo", "repo", "feature", "main", "abc123"
            )
        )


if __name__ == "__main__":
    main()
