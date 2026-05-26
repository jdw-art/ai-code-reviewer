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
        changed_file_actions: list[InvestigationAction] = []
        test_actions_by_path: dict[str, list[InvestigationAction]] = {}
        for changed_file in analysis.files:
            priority = 10 if changed_file.risk_tags else 20
            changed_file_action = InvestigationAction(
                action_type="read_changed_file",
                path=changed_file.path,
                ref=task.effective_ref,
                reason="Read changed file context for the PR head ref.",
                priority=priority,
            )
            changed_file_actions.append(changed_file_action)
            if not changed_file.is_test:
                test_actions_by_path[changed_file.path] = []
                for candidate in self._test_candidates(changed_file.path)[: self.budget.max_test_files]:
                    test_actions_by_path[changed_file.path].append(
                        InvestigationAction(
                            action_type="find_related_test",
                            path=candidate,
                            ref=task.effective_ref,
                            reason=f"Check whether related tests cover {changed_file.path}.",
                            priority=40,
                        )
                    )

        changed_file_actions.sort(key=lambda item: (item.priority, item.path))

        selected_actions = changed_file_actions[: self.budget.max_context_files]
        if (
            test_actions_by_path
            and self.budget.max_context_files > 1
            and len(changed_file_actions) >= self.budget.max_context_files
        ):
            retained_changed_file_actions = selected_actions
            reserved_changed_file_action, reserved_test_action = self._first_test_action_for_changed_files(
                retained_changed_file_actions,
                test_actions_by_path,
            )
            if reserved_changed_file_action and reserved_test_action:
                retained_without_reserved = [
                    action for action in retained_changed_file_actions if action.path != reserved_changed_file_action.path
                ]
                selected_actions = [reserved_changed_file_action] + retained_without_reserved[: self.budget.max_context_files - 2]
                selected_actions.append(reserved_test_action)
        else:
            remaining_slots = self.budget.max_context_files - len(selected_actions)
            test_actions = [
                test_action
                for changed_file_action in changed_file_actions
                for test_action in test_actions_by_path.get(changed_file_action.path, [])
            ]
            selected_actions.extend(test_actions[:remaining_slots])

        return InvestigationPlan(actions=selected_actions, budget=self.budget)

    def _first_test_action_for_changed_files(
        self,
        changed_file_actions: list[InvestigationAction],
        test_actions_by_path: dict[str, list[InvestigationAction]],
    ) -> tuple[InvestigationAction | None, InvestigationAction | None]:
        for changed_file_action in changed_file_actions:
            test_actions = test_actions_by_path.get(changed_file_action.path, [])
            if test_actions:
                return changed_file_action, test_actions[0]
        return None, None

    def _test_candidates(self, path: str) -> list[str]:
        directory, filename = os.path.split(path)
        stem, ext = os.path.splitext(filename)
        candidates = [
            f"tests/test_{stem}{ext}",
            f"{directory}/test_{stem}{ext}" if directory else f"test_{stem}{ext}",
            f"{directory}/{stem}_test{ext}" if directory else f"{stem}_test{ext}",
        ]
        return [candidate.replace("//", "/") for candidate in candidates]
