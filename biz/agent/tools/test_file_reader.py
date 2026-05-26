import base64
from unittest import TestCase, main
from unittest.mock import Mock, patch

from biz.agent.tools.file_reader import GitHubFileReader


class TestGitHubFileReader(TestCase):
    @patch("biz.agent.tools.file_reader.requests.get")
    def test_reads_and_decodes_file(self, mock_get):
        encoded = base64.b64encode(b"print('hello')\n").decode("utf-8")
        mock_get.return_value = Mock(status_code=200, json=lambda: {"content": encoded, "encoding": "base64"})

        reader = GitHubFileReader(repo_full_name="owner/repo", token="token")
        result = reader.read_file("src/app.py", "abc123")

        self.assertTrue(result.ok)
        self.assertEqual(result.content, "print('hello')\n")
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], "https://api.github.com/repos/owner/repo/contents/src/app.py")
        self.assertEqual(kwargs["params"], {"ref": "abc123"})

    @patch("biz.agent.tools.file_reader.requests.get")
    def test_returns_error_for_missing_file(self, mock_get):
        mock_get.return_value = Mock(status_code=404, text="not found")

        reader = GitHubFileReader(repo_full_name="owner/repo", token="token")
        result = reader.read_file("missing.py", "abc123")

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "GitHub file read failed: 404 not found")


if __name__ == "__main__":
    main()
