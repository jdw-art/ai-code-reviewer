from unittest import TestCase, main

from biz.agent.planner import InvestigationPlanner
from biz.agent.task import ChangedFile, ContextBudget, DiffAnalysis, ReviewTask


class TestInvestigationPlanner(TestCase):
    def _task(self):
        return ReviewTask(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            source_branch="feature/login",
            target_branch="main",
            change_ref="abc123",
            author="octocat",
            url="https://github.com/owner/repo/pull/1",
            commits=[],
            changes=[],
            access_token="token",
            platform_url="https://github.com",
        )

    def test_plans_changed_file_and_test_candidates(self):
        analysis = DiffAnalysis(
            files=[
                ChangedFile(
                    path="biz/service/review_service.py",
                    language="python",
                    additions=10,
                    deletions=1,
                    is_test=False,
                    is_config=False,
                )
            ],
            total_additions=10,
            total_deletions=1,
        )

        plan = InvestigationPlanner(ContextBudget(max_context_files=5)).create_plan(self._task(), analysis)
        action_pairs = [(action.action_type, action.path) for action in plan.actions]

        self.assertIn(("read_changed_file", "biz/service/review_service.py"), action_pairs)
        self.assertIn(("find_related_test", "tests/test_review_service.py"), action_pairs)
        self.assertIn(("find_related_test", "biz/service/test_review_service.py"), action_pairs)

    def test_respects_max_context_files(self):
        analysis = DiffAnalysis(
            files=[
                ChangedFile("test_a.py", "python", 1, 0, True, False),
                ChangedFile("test_b.py", "python", 1, 0, True, False),
                ChangedFile("test_c.py", "python", 1, 0, True, False),
            ],
            total_additions=3,
            total_deletions=0,
        )

        plan = InvestigationPlanner(ContextBudget(max_context_files=2)).create_plan(self._task(), analysis)

        self.assertEqual(len(plan.actions), 2)
        self.assertEqual([action.action_type for action in plan.actions], ["read_changed_file", "read_changed_file"])

    def test_preserves_related_test_when_changed_files_fill_budget(self):
        analysis = DiffAnalysis(
            files=[
                ChangedFile("a.py", "python", 1, 0, False, False),
                ChangedFile("b.py", "python", 1, 0, False, False),
                ChangedFile("c.py", "python", 1, 0, False, False),
            ],
            total_additions=3,
            total_deletions=0,
        )

        plan = InvestigationPlanner(ContextBudget(max_context_files=2)).create_plan(self._task(), analysis)
        action_types = [action.action_type for action in plan.actions]

        self.assertEqual(len(plan.actions), 2)
        self.assertIn("read_changed_file", action_types)
        self.assertEqual(action_types.count("find_related_test"), 1)

    def test_reserved_related_test_matches_retained_changed_file(self):
        analysis = DiffAnalysis(
            files=[
                ChangedFile("z_risky.py", "python", 1, 0, False, False, risk_tags=["security"]),
                ChangedFile("a_low.py", "python", 1, 0, False, False),
            ],
            total_additions=2,
            total_deletions=0,
        )

        plan = InvestigationPlanner(ContextBudget(max_context_files=2)).create_plan(self._task(), analysis)
        action_pairs = [(action.action_type, action.path) for action in plan.actions]

        self.assertIn(("read_changed_file", "z_risky.py"), action_pairs)
        self.assertIn(("find_related_test", "tests/test_z_risky.py"), action_pairs)
        self.assertNotIn(("find_related_test", "tests/test_a_low.py"), action_pairs)


if __name__ == "__main__":
    main()
