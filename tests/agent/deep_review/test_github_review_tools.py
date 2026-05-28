from unittest import TestCase, main
from unittest.mock import Mock, patch

from biz.agent.deep_review.tools.github_review_tools import GitHubDeepReviewTools


class TestGitHubDeepReviewTools(TestCase):
    @patch("biz.agent.deep_review.tools.github_review_tools.requests.get")
    def test_read_pr_metadata_returns_payload(self, mock_get):
        """成功读取 PR 元信息。"""
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {"title": "Add auth check", "state": "open"},
        )

        tools = GitHubDeepReviewTools("owner/repo", "token")
        payload = tools.read_pr_metadata(12)

        self.assertEqual(payload["title"], "Add auth check")
        self.assertEqual(payload["state"], "open")
        mock_get.assert_called_once()

    @patch("biz.agent.deep_review.tools.github_review_tools.requests.get")
    def test_read_pr_diff_returns_files(self, mock_get):
        """成功读取 PR diff 文件列表。"""
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [{"filename": "backend/auth.py", "patch": "@@ -1 +1 @@"}],
        )

        tools = GitHubDeepReviewTools("owner/repo", "token")
        payload = tools.read_pr_diff(12)

        self.assertEqual(payload[0]["filename"], "backend/auth.py")
        self.assertIn("patch", payload[0])
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"], {"page": 1, "per_page": 100})

    @patch("biz.agent.deep_review.tools.github_review_tools.requests.get")
    def test_read_pr_diff_paginates_until_last_page(self, mock_get):
        """大 PR 会继续拉取后续页面，避免文件列表被截断。"""
        first_page = [{"filename": f"backend/file_{index}.py"} for index in range(100)]
        second_page = [{"filename": "backend/final.py"}]
        mock_get.side_effect = [
            Mock(status_code=200, json=lambda: first_page),
            Mock(status_code=200, json=lambda: second_page),
        ]

        tools = GitHubDeepReviewTools("owner/repo", "token")
        payload = tools.read_pr_diff(12)

        self.assertEqual(len(payload), 101)
        self.assertEqual(payload[-1]["filename"], "backend/final.py")
        self.assertEqual(mock_get.call_count, 2)

    @patch("biz.agent.deep_review.tools.github_review_tools.GitHubFileReader.read_file")
    def test_read_repo_file_reuses_file_reader_result(self, mock_read_file):
        """仓库文件读取直接复用统一文件读取结果。"""
        mock_read_file.return_value = Mock(
            ok=True,
            path="backend/auth.py",
            ref="abc123",
            content="print('ok')\n",
            truncated=False,
            error=None,
        )

        tools = GitHubDeepReviewTools("owner/repo", "token")
        result = tools.read_repo_file("backend/auth.py", "abc123")

        self.assertEqual(result["path"], "backend/auth.py")
        self.assertEqual(result["content"], "print('ok')\n")
        mock_read_file.assert_called_once_with("backend/auth.py", "abc123")

    def test_read_related_test_prefers_tests_directory(self):
        """候选测试文件优先从 tests 目录推导。"""
        tools = GitHubDeepReviewTools("owner/repo", "token")

        candidates = tools._test_candidates("backend/auth.py")

        self.assertIn("tests/test_auth.py", candidates)
        self.assertIn("tests/auth_test.py", candidates)

    def test_read_related_test_keeps_nested_tests_directory_candidates(self):
        """候选测试路径会保留 tests 下的目录线索。"""
        tools = GitHubDeepReviewTools("owner/repo", "token")

        candidates = tools._test_candidates("biz/agent/deep_review/task.py")

        self.assertIn("tests/agent/deep_review/test_task.py", candidates)

    def test_read_local_import_extracts_relative_import_candidates(self):
        """相对导入会被提取为后续可继续调查的线索。"""
        tools = GitHubDeepReviewTools("owner/repo", "token")
        tools.read_repo_file = Mock(return_value={"content": "from .helpers import sanitize\nfrom .subpkg import client\n"})

        result = tools.read_local_import("backend/auth.py", "abc123")

        self.assertEqual(
            result,
            [
                {"line": "from .helpers import sanitize"},
                {"line": "from .subpkg import client"},
            ],
        )


if __name__ == "__main__":
    main()
