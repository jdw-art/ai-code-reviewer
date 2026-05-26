from biz.agent.task import CollectedContext, InvestigationPlan
from biz.agent.tools.file_reader import PlatformFileReader


class ContextCollector:
    def collect(self, plan: InvestigationPlan, file_reader: PlatformFileReader) -> tuple[list[CollectedContext], list[str]]:
        contexts: list[CollectedContext] = []
        warnings: list[str] = []

        for action in plan.actions:
            result = file_reader.read_file(action.path, action.ref)
            if not result.ok:
                warning = f"Failed to read {action.path}: {result.error}"
                warnings.append(warning)
                contexts.append(
                    CollectedContext(
                        path=action.path,
                        ref=action.ref,
                        reason=action.reason,
                        content="",
                        truncated=False,
                        error=result.error,
                    )
                )
                continue

            content = result.content
            truncated = result.truncated
            if len(content) > plan.budget.max_file_chars:
                content = content[: plan.budget.max_file_chars]
                truncated = True

            if truncated:
                warnings.append(f"Truncated {action.path} to {plan.budget.max_file_chars} characters")

            contexts.append(
                CollectedContext(
                    path=action.path,
                    ref=action.ref,
                    reason=action.reason,
                    content=content,
                    truncated=truncated,
                    error=None,
                )
            )

        return contexts, warnings
