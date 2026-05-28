import importlib
import os
import sys
import tempfile
from unittest import TestCase, main


class TestReviewServiceReviewRows(TestCase):
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

    def _insert_review(self, project_name: str, updated_at: int, score: int, risk_level: str, review_profile: str):
        entity = self.MergeRequestReviewEntity(
            project_name=project_name,
            project_id=f"owner/{project_name}",
            platform="github",
            author="octocat",
            source_branch="feature",
            target_branch="main",
            updated_at=updated_at,
            commits=[{"message": f"update {project_name}"}],
            score=score,
            url=f"https://github.com/owner/{project_name}/pull/{updated_at}",
            review_result=f"已确认问题\n- {project_name} 风险\n\n风险等级\n{risk_level}\n\n总分: {score}分",
            url_slug="github_com",
            webhook_data={},
            additions=1,
            deletions=0,
            last_commit_id=f"commit-{updated_at}",
            agent_trace='{"mode":"context_investigation"}',
            review_mode="baseline_review",
            review_profile=review_profile,
            risk_level=risk_level,
        )
        self.ReviewService.insert_mr_review_log(entity)

    def test_get_mr_review_rows_by_ids_returns_raw_rows_in_requested_order(self):
        """按 id 批量回捞时应返回原始字段，并保持请求顺序。"""
        self._insert_review("repo-a", updated_at=1, score=81, risk_level="medium", review_profile="default_review")
        self._insert_review("repo-b", updated_at=2, score=72, risk_level="high", review_profile="security_review")

        rows = self.ReviewService.get_mr_review_rows_by_ids([2, 1, 999])

        self.assertEqual([row["id"] for row in rows], [2, 1])
        self.assertEqual(rows[0]["project_id"], "owner/repo-b")
        self.assertEqual(rows[0]["project_name"], "repo-b")
        self.assertEqual(rows[0]["score"], 72)
        self.assertEqual(rows[0]["risk_level"], "high")
        self.assertEqual(rows[0]["review_profile"], "security_review")
        self.assertIn("repo-b 风险", rows[0]["review_result"])
        self.assertEqual(rows[0]["agent_trace"], '{"mode":"context_investigation"}')
        self.assertEqual(rows[0]["url"], "https://github.com/owner/repo-b/pull/2")

    def test_get_mr_review_rows_returns_dashboard_creation_fields(self):
        """Dashboard 创建 Deep Review 会话时需要拿到 id 与 agent_trace。"""
        self._insert_review("repo-c", updated_at=3, score=66, risk_level="high", review_profile="security_review")

        rows = self.ReviewService.get_mr_review_rows(
            updated_at_gte=1,
            updated_at_lte=10,
            project_ids=["owner/repo-c"],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], 1)
        self.assertEqual(rows[0]["project_id"], "owner/repo-c")
        self.assertEqual(rows[0]["platform"], "github")
        self.assertEqual(rows[0]["agent_trace"], '{"mode":"context_investigation"}')


if __name__ == "__main__":
    main()
