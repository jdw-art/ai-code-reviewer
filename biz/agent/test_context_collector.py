from unittest import TestCase, main

from biz.agent.context_collector import ContextCollector
from biz.agent.task import ContextBudget, FileReadResult, InvestigationAction, InvestigationPlan


class FakeReader:
    def __init__(self, files):
        self.files = files

    def read_file(self, path, ref):
        if path not in self.files:
            return FileReadResult(path=path, ref=ref, ok=False, error="missing")
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


if __name__ == "__main__":
    main()
