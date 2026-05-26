import os
import tempfile
from unittest import TestCase, main

from biz.entity.review_entity import MergeRequestReviewEntity
from biz.service.review_service import ReviewService


class TestReviewServiceAgentTrace(TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        self.original_db = ReviewService.DB_FILE
        ReviewService.DB_FILE = self.tmp.name
        ReviewService.init_db()

    def tearDown(self):
        ReviewService.DB_FILE = self.original_db
        os.unlink(self.tmp.name)

    def test_insert_mr_review_log_stores_agent_trace(self):
        entity = MergeRequestReviewEntity(
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

        ReviewService.insert_mr_review_log(entity)
        df = ReviewService.get_mr_review_logs()

        self.assertEqual(df.iloc[0]["agent_trace"], '{"mode": "context_investigation"}')


if __name__ == "__main__":
    main()
