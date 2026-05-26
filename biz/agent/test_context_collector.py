from unittest import TestCase, main
from unittest.mock import patch

from biz.agent.context_collector import ContextCollector
from biz.agent.task import ContextBudget, FileReadResult, InvestigationAction, InvestigationPlan


class FakeReader:
    def __init__(self, files):
        self.files = files

    def read_file(self, path, ref):
        if path not in self.files:
            return FileReadResult(path=path, ref=ref, ok=False, error="missing")
        if isinstance(self.files[path], FileReadResult):
            return self.files[path]
        return FileReadResult(path=path, ref=ref, ok=True, content=self.files[path])


class TestContextCollector(TestCase):
    def test_collects_success_and_warning(self):
        plan = InvestigationPlan(
            actions=[
                InvestigationAction("read_changed_file", "src/app.py", "abc123", "changed file", 10),
                InvestigationAction("find_related_test", "tests/test_app.py", "abc123", "related test", 40),
            ],
            budget=ContextBudget(max_context_files=5, max_file_chars=100),
        )

        contexts, warnings = ContextCollector().collect(plan, FakeReader({"src/app.py": "print('hello')"}))

        self.assertEqual(len(contexts), 2)
        self.assertIsNone(contexts[0].error)
        self.assertEqual(contexts[1].error, "missing")
        self.assertIn("Failed to read tests/test_app.py: missing", warnings)

    def test_truncates_large_content(self):
        plan = InvestigationPlan(
            actions=[InvestigationAction("read_changed_file", "src/app.py", "abc123", "changed file", 10)],
            budget=ContextBudget(max_context_files=5, max_file_chars=4),
        )

        contexts, warnings = ContextCollector().collect(plan, FakeReader({"src/app.py": "abcdef"}))

        self.assertEqual(contexts[0].content, "abcd")
        self.assertTrue(contexts[0].truncated)
        self.assertIn("Truncated src/app.py to 4 characters", warnings)

    def test_does_not_warn_when_only_reader_truncated(self):
        plan = InvestigationPlan(
            actions=[InvestigationAction("read_changed_file", "src/app.py", "abc123", "changed file", 10)],
            budget=ContextBudget(max_context_files=5, max_file_chars=100),
        )

        contexts, warnings = ContextCollector().collect(
            plan,
            FakeReader({"src/app.py": FileReadResult(path="src/app.py", ref="abc123", ok=True, content="abcd", truncated=True)}),
        )

        self.assertTrue(contexts[0].truncated)
        self.assertNotIn("Truncated src/app.py to 100 characters", warnings)

    def test_limits_context_files_and_warns_about_skipped_actions(self):
        plan = InvestigationPlan(
            actions=[
                InvestigationAction("read_changed_file", "src/app.py", "abc123", "changed file", 10),
                InvestigationAction("find_related_test", "tests/test_app.py", "abc123", "related test", 40),
                InvestigationAction("read_import", "src/lib.py", "abc123", "import", 50),
            ],
            budget=ContextBudget(max_context_files=2, max_file_chars=100),
        )

        contexts, warnings = ContextCollector().collect(
            plan,
            FakeReader({"src/app.py": "app", "tests/test_app.py": "test", "src/lib.py": "lib"}),
        )

        self.assertEqual([context.path for context in contexts], ["src/app.py", "tests/test_app.py"])
        self.assertIn("Skipped 1 context actions due to max_context_files=2", warnings)

    def test_reader_truncation_warning_is_distinct_from_collector_char_warning(self):
        plan = InvestigationPlan(
            actions=[InvestigationAction("read_changed_file", "src/app.py", "abc123", "changed file", 10)],
            budget=ContextBudget(max_context_files=5, max_file_chars=100),
        )

        contexts, warnings = ContextCollector().collect(
            plan,
            FakeReader({"src/app.py": FileReadResult(path="src/app.py", ref="abc123", ok=True, content="abcd", truncated=True)}),
        )

        self.assertTrue(contexts[0].truncated)
        self.assertIn("Reader returned truncated content for src/app.py", warnings)
        self.assertNotIn("Truncated src/app.py to 100 characters", warnings)

    def test_truncates_to_fit_max_context_tokens(self):
        plan = InvestigationPlan(
            actions=[
                InvestigationAction("read_changed_file", "src/app.py", "abc123", "changed file", 10),
                InvestigationAction("find_related_test", "tests/test_app.py", "abc123", "related test", 40),
                InvestigationAction("read_import", "src/lib.py", "abc123", "import", 50),
            ],
            budget=ContextBudget(max_context_files=5, max_file_chars=100, max_context_tokens=3),
        )

        def fake_count_tokens(text):
            return len(text)

        def fake_truncate_text_by_tokens(text, max_tokens):
            return text[:max_tokens]

        with patch("biz.agent.context_collector.count_tokens", side_effect=fake_count_tokens), patch(
            "biz.agent.context_collector.truncate_text_by_tokens",
            side_effect=fake_truncate_text_by_tokens,
        ):
            contexts, warnings = ContextCollector().collect(
                plan,
                FakeReader({"src/app.py": "ab", "tests/test_app.py": "cdef", "src/lib.py": "gh"}),
            )

        self.assertEqual(contexts[0].content, "ab")
        self.assertFalse(contexts[0].truncated)
        self.assertEqual(contexts[1].content, "c")
        self.assertTrue(contexts[1].truncated)
        self.assertEqual(contexts[2].content, "")
        self.assertTrue(contexts[2].truncated)
        self.assertIn("Truncated tests/test_app.py to fit max_context_tokens=3", warnings)
        self.assertIn("Truncated src/lib.py to fit max_context_tokens=3", warnings)

    def test_defensively_trims_when_token_truncation_still_exceeds_budget(self):
        plan = InvestigationPlan(
            actions=[
                InvestigationAction("read_changed_file", "src/app.py", "abc123", "changed file", 10),
                InvestigationAction("find_related_test", "tests/test_app.py", "abc123", "related test", 40),
            ],
            budget=ContextBudget(max_context_files=5, max_file_chars=100, max_context_tokens=5),
        )

        def fake_count_tokens(text):
            if text == "abc":
                return 3
            if text == "mixed":
                return 8
            return len(text)

        def fake_truncate_text_by_tokens(text, max_tokens):
            return "mixed"

        with patch("biz.agent.context_collector.count_tokens", side_effect=fake_count_tokens), patch(
            "biz.agent.context_collector.truncate_text_by_tokens",
            side_effect=fake_truncate_text_by_tokens,
        ):
            contexts, warnings = ContextCollector().collect(
                plan,
                FakeReader({"src/app.py": "abc", "tests/test_app.py": "0123456789"}),
            )

        self.assertEqual(contexts[0].content, "abc")
        self.assertEqual(contexts[1].content, "mi")
        self.assertTrue(contexts[1].truncated)
        self.assertIn("Truncated tests/test_app.py to fit max_context_tokens=5", warnings)


if __name__ == "__main__":
    main()
