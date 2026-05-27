from unittest import TestCase, main

from biz.agent.task import (
    AgentReviewResult,
    ChangedFile,
    CollectedContext,
    ContextBudget,
    DiffAnalysis,
    FileReadResult,
    InvestigationAction,
    InvestigationPlan,
    ReviewTask,
)


class TestAgentTaskTypes(TestCase):
    def test_review_task_defaults_change_ref_to_source_branch(self):
        task = ReviewTask(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            source_branch="feature/login",
            target_branch="main",
            change_ref="",
            author="octocat",
            url="https://github.com/owner/repo/pull/1",
            commits=[],
            changes=[],
            access_token="token",
            platform_url="https://github.com",
        )

        self.assertEqual(task.effective_ref, "feature/login")

    def test_review_task_prefers_explicit_change_ref(self):
        task = ReviewTask(
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

        self.assertEqual(task.effective_ref, "abc123")

    def test_review_task_repr_omits_access_token(self):
        task = ReviewTask(
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
            access_token="super-secret-token",
            platform_url="https://github.com",
        )

        self.assertNotIn("super-secret-token", repr(task))

    def test_agent_trace_is_serializable_shape(self):
        result = AgentReviewResult(
            review_text="总分: 90分",
            score=90,
            risk_level="medium",
            investigated_files=["src/app.py"],
            investigation_summary="Checked changed file context.",
            warnings=[],
            agent_trace={"mode": "context_investigation"},
        )

        self.assertEqual(result.agent_trace["mode"], "context_investigation")


if __name__ == "__main__":
    main()
