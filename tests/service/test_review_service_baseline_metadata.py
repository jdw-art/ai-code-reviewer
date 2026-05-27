import importlib
import os
import sqlite3
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

    def _execute_sql(self, statements):
        with sqlite3.connect(self.tmp.name) as conn:
            cursor = conn.cursor()
            for statement in statements:
                cursor.execute(statement)
            conn.commit()

    def _fetch_mr_row(self):
        with sqlite3.connect(self.tmp.name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM mr_review_log LIMIT 1")
            return cursor.fetchone()

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

    def test_get_mr_review_logs_includes_dashboard_metadata_when_requested(self):
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
            review_result="## 已确认问题\n- 示例问题",
            url_slug="github_com",
            webhook_data={},
            additions=1,
            deletions=0,
            last_commit_id="abc123",
        )

        self.ReviewService.insert_mr_review_log(entity)
        df = self.ReviewService.get_mr_review_logs(include_review_metadata=True)

        self.assertEqual(
            list(df.columns[:5]),
            ["platform", "project_id", "review_mode", "review_profile", "risk_level"],
        )
        self.assertIn("review_result", df.columns)

    def test_insert_mr_review_log_keeps_missing_metadata_empty(self):
        entity = self.MergeRequestReviewEntity(
            project_name="repo",
            author="octocat",
            source_branch="feature",
            target_branch="main",
            updated_at=1,
            commits=[{"message": "Add feature"}],
            score=90,
            url="https://github.com/owner/repo/pull/1",
            review_result="## 已确认问题\n- 示例问题",
            url_slug="github_com",
            webhook_data={},
            additions=1,
            deletions=0,
            last_commit_id="abc123",
        )

        self.ReviewService.insert_mr_review_log(entity)
        df = self.ReviewService.get_mr_review_logs(include_review_metadata=True)

        self.assertEqual(df.iloc[0]["platform"], "")
        self.assertEqual(df.iloc[0]["project_id"], "")
        self.assertEqual(df.iloc[0]["review_mode"], "")
        self.assertEqual(df.iloc[0]["review_profile"], "")
        self.assertEqual(df.iloc[0]["risk_level"], "")

    def test_get_mr_review_logs_keeps_empty_metadata_values(self):
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
            review_result="## 已确认问题\n- 示例问题",
            url_slug="github_com",
            webhook_data={},
            additions=1,
            deletions=0,
            last_commit_id="abc123",
            review_mode="",
            review_profile=None,
            risk_level="",
        )

        self.ReviewService.insert_mr_review_log(entity)
        df = self.ReviewService.get_mr_review_logs(include_review_metadata=True)

        self.assertEqual(df.iloc[0]["review_mode"], "")
        self.assertTrue(df.iloc[0]["review_profile"] is None)
        self.assertEqual(df.iloc[0]["risk_level"], "")

    def test_init_db_keeps_legacy_rows_as_empty_metadata(self):
        self._execute_sql([
            "DROP TABLE IF EXISTS mr_review_log",
            """
            CREATE TABLE mr_review_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT,
                author TEXT,
                source_branch TEXT,
                target_branch TEXT,
                updated_at INTEGER,
                commit_messages TEXT,
                score INTEGER,
                url TEXT,
                review_result TEXT
            )
            """,
            """
            INSERT INTO mr_review_log (
                project_name, author, source_branch, target_branch, updated_at,
                commit_messages, score, url, review_result
            ) VALUES (
                'legacy-repo', 'octocat', 'feature', 'main', 1,
                '["legacy commit"]', 80, 'https://example.com/mr/1', '历史评论'
            )
            """,
        ])

        self.ReviewService.init_db()

        row = self._fetch_mr_row()
        self.assertEqual(row["platform"], "")
        self.assertEqual(row["project_id"], "")
        self.assertEqual(row["review_mode"], "")
        self.assertEqual(row["review_profile"], "")
        self.assertEqual(row["risk_level"], "")

    def test_init_db_clears_pseudo_default_metadata_from_previous_migration(self):
        self._execute_sql([
            "DROP TABLE IF EXISTS mr_review_log",
            """
            CREATE TABLE mr_review_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT DEFAULT 'github',
                project_id TEXT DEFAULT '',
                project_name TEXT,
                author TEXT,
                source_branch TEXT,
                target_branch TEXT,
                updated_at INTEGER,
                commit_messages TEXT,
                score INTEGER,
                url TEXT,
                review_result TEXT,
                additions INTEGER DEFAULT 0,
                deletions INTEGER DEFAULT 0,
                last_commit_id TEXT DEFAULT '',
                agent_trace TEXT DEFAULT '',
                review_mode TEXT DEFAULT 'baseline_review',
                review_profile TEXT DEFAULT 'default_review',
                risk_level TEXT DEFAULT 'medium'
            )
            """,
            """
            INSERT INTO mr_review_log (
                project_name, author, source_branch, target_branch, updated_at,
                commit_messages, score, url, review_result
            ) VALUES (
                'legacy-repo', 'octocat', 'feature', 'main', 1,
                '["legacy commit"]', 80, 'https://example.com/mr/1', '历史评论'
            )
            """,
        ])

        self.ReviewService.init_db()

        row = self._fetch_mr_row()
        self.assertEqual(row["platform"], "")
        self.assertEqual(row["project_id"], "")
        self.assertEqual(row["review_mode"], "")
        self.assertEqual(row["review_profile"], "")
        self.assertEqual(row["risk_level"], "")

    def test_init_db_clears_pseudo_default_metadata_even_with_commit_and_trace(self):
        self._execute_sql([
            "DROP TABLE IF EXISTS mr_review_log",
            """
            CREATE TABLE mr_review_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT DEFAULT 'github',
                project_id TEXT DEFAULT '',
                project_name TEXT,
                author TEXT,
                source_branch TEXT,
                target_branch TEXT,
                updated_at INTEGER,
                commit_messages TEXT,
                score INTEGER,
                url TEXT,
                review_result TEXT,
                additions INTEGER DEFAULT 0,
                deletions INTEGER DEFAULT 0,
                last_commit_id TEXT DEFAULT '',
                agent_trace TEXT DEFAULT '',
                review_mode TEXT DEFAULT 'baseline_review',
                review_profile TEXT DEFAULT 'default_review',
                risk_level TEXT DEFAULT 'medium'
            )
            """,
            """
            INSERT INTO mr_review_log (
                platform, project_id, project_name, author, source_branch, target_branch, updated_at,
                commit_messages, score, url, review_result, additions, deletions, last_commit_id,
                agent_trace, review_mode, review_profile, risk_level
            ) VALUES (
                'github', '', 'legacy-repo', 'octocat', 'feature', 'main', 1,
                '["legacy commit"]', 80, 'https://example.com/mr/1', '历史评论', 0, 0, 'abc123',
                '{"mode":"context_investigation"}', 'baseline_review', 'default_review', 'medium'
            )
            """,
        ])

        self.ReviewService.init_db()

        row = self._fetch_mr_row()
        self.assertEqual(row["platform"], "")
        self.assertEqual(row["project_id"], "")
        self.assertEqual(row["review_mode"], "")
        self.assertEqual(row["review_profile"], "")
        self.assertEqual(row["risk_level"], "")
        self.assertEqual(row["last_commit_id"], "abc123")
        self.assertEqual(row["agent_trace"], '{"mode":"context_investigation"}')

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
