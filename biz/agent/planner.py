import os

from biz.agent.task import ContextBudget, DiffAnalysis, InvestigationAction, InvestigationPlan, ReviewTask


class InvestigationPlanner:
    def __init__(self, budget: ContextBudget | None = None):
        self.budget = budget or ContextBudget(
            max_context_files=int(os.getenv("AGENT_MAX_CONTEXT_FILES", 5)),
            max_context_tokens=int(os.getenv("AGENT_MAX_CONTEXT_TOKENS", 12000)),
            max_file_chars=int(os.getenv("AGENT_MAX_FILE_CHARS", 30000)),
            max_import_files=int(os.getenv("AGENT_MAX_IMPORT_FILES", 2)),
            max_test_files=int(os.getenv("AGENT_MAX_TEST_FILES", 2)),
        )

    def create_plan(self, task: ReviewTask, analysis: DiffAnalysis) -> InvestigationPlan:
        actions: list[InvestigationAction] = []
        for changed_file in analysis.files:
            priority = 10 if changed_file.risk_tags else 20
            actions.append(
                InvestigationAction(
                    action_type="read_changed_file",
                    path=changed_file.path,
                    ref=task.effective_ref,
                    reason="Read changed file context for the PR head ref.",
                    priority=priority,
                )
            )
            if not changed_file.is_test:
                for candidate in self._test_candidates(changed_file.path)[: self.budget.max_test_files]:
                    actions.append(
                        InvestigationAction(
                            action_type="find_related_test",
                            path=candidate,
                            ref=task.effective_ref,
                            reason=f"Check whether related tests cover {changed_file.path}.",
                            priority=40,
                        )
                    )

        actions.sort(key=lambda item: (item.priority, item.path))
        return InvestigationPlan(actions=actions[: self.budget.max_context_files], budget=self.budget)

    def _test_candidates(self, path: str) -> list[str]:
        directory, filename = os.path.split(path)
        stem, ext = os.path.splitext(filename)
        candidates = [
            f"tests/test_{stem}{ext}",
            f"{directory}/test_{stem}{ext}" if directory else f"test_{stem}{ext}",
            f"{directory}/{stem}_test{ext}" if directory else f"{stem}_test{ext}",
        ]
        return [candidate.replace("//", "/") for candidate in candidates]
