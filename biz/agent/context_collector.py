from biz.agent.task import CollectedContext, InvestigationPlan
from biz.agent.tools.file_reader import PlatformFileReader
from biz.utils.token_util import count_tokens, truncate_text_by_tokens


class ContextCollector:
    def collect(self, plan: InvestigationPlan, file_reader: PlatformFileReader) -> tuple[list[CollectedContext], list[str]]:
        contexts: list[CollectedContext] = []
        warnings: list[str] = []
        total_tokens = 0

        max_context_files = plan.budget.max_context_files
        actions = plan.actions[:max_context_files]
        skipped_actions = len(plan.actions) - len(actions)
        if skipped_actions > 0:
            warnings.append(f"Skipped {skipped_actions} context actions due to max_context_files={max_context_files}")

        for action in actions:
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
            if result.truncated:
                warnings.append(f"Reader returned truncated content for {action.path}")

            collector_truncated = False
            if len(content) > plan.budget.max_file_chars:
                content = content[: plan.budget.max_file_chars]
                truncated = True
                collector_truncated = True

            if collector_truncated:
                warnings.append(f"Truncated {action.path} to {plan.budget.max_file_chars} characters")

            content_tokens = count_tokens(content)
            remaining_tokens = plan.budget.max_context_tokens - total_tokens
            if content_tokens > remaining_tokens:
                if remaining_tokens <= 0:
                    content = ""
                else:
                    content = truncate_text_by_tokens(content, remaining_tokens)
                truncated = True
                warnings.append(f"Truncated {action.path} to fit max_context_tokens={plan.budget.max_context_tokens}")
                content_tokens = count_tokens(content)

            total_tokens += content_tokens

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
