from unittest import TestCase, main

from biz.agent.evidence_builder import EvidenceBuilder
from biz.agent.task import ChangedFile, CollectedContext, DiffAnalysis, ReviewTask


class TestEvidenceBuilder(TestCase):
    def test_builds_evidence_with_diff_context_and_requirements(self):
        task = ReviewTask(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            source_branch="feature/login",
            target_branch="main",
            change_ref="abc123",
            author="octocat",
            url="https://github.com/owner/repo/pull/1",
            commits=[{"message": "Add login validation"}],
            changes=[{"new_path": "src/auth.py", "diff": "+def validate_token():\n+    return True"}],
            access_token="token",
            platform_url="https://github.com",
        )
        analysis = DiffAnalysis(
            files=[ChangedFile("src/auth.py", "python", 2, 0, False, False, ["security"], ["validate_token"])],
            total_additions=2,
            total_deletions=0,
            risk_hints=["security"],
        )
        contexts = [
            CollectedContext(
                path="src/auth.py",
                ref="abc123",
                reason="Read changed file context.",
                content="def validate_token():\n    return True",
            )
        ]

        evidence = EvidenceBuilder().build(task, analysis, contexts, ["related test file not found"])

        self.assertIn("# Commit Messages", evidence)
        self.assertIn("Add login validation", evidence)
        self.assertIn("Risk tags: security", evidence)
        self.assertIn("src/auth.py", evidence)
        self.assertIn("related test file not found", evidence)
        self.assertIn("总分: XX分", evidence)


if __name__ == "__main__":
    main()
