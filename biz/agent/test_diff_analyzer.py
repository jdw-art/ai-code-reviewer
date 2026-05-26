from unittest import TestCase, main

from biz.agent.diff_analyzer import DiffAnalyzer


class TestDiffAnalyzer(TestCase):
    def test_analyzes_python_service_change(self):
        changes = [
            {
                "new_path": "biz/service/review_service.py",
                "diff": "@@ -1,3 +1,7 @@\n+class ReviewService:\n+    def insert_log(self):\n+        pass\n",
                "additions": 3,
                "deletions": 0,
            }
        ]

        analysis = DiffAnalyzer().analyze(changes)

        self.assertEqual(analysis.total_additions, 3)
        self.assertEqual(analysis.total_deletions, 0)
        self.assertEqual(analysis.files[0].language, "python")
        self.assertFalse(analysis.files[0].is_test)
        self.assertIn("ReviewService", analysis.files[0].changed_symbols)
        self.assertIn("insert_log", analysis.files[0].changed_symbols)

    def test_marks_test_config_and_risk_tags(self):
        changes = [
            {
                "new_path": "tests/test_auth_config.py",
                "diff": "+def test_token_validation():\n+    pass\n",
                "additions": 2,
                "deletions": 0,
            },
            {
                "new_path": "deploy/docker-compose.yml",
                "diff": "+services:\n",
                "additions": 1,
                "deletions": 0,
            },
        ]

        analysis = DiffAnalyzer().analyze(changes)

        self.assertTrue(analysis.files[0].is_test)
        self.assertIn("security", analysis.files[0].risk_tags)
        self.assertTrue(analysis.files[1].is_config)
        self.assertIn("config", analysis.files[1].risk_tags)
        self.assertIn("security", analysis.risk_hints)
        self.assertIn("config", analysis.risk_hints)


if __name__ == "__main__":
    main()
