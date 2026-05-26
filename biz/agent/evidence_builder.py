import json

from biz.agent.task import CollectedContext, DiffAnalysis, ReviewTask


def _sanitize_fenced_content(content: str) -> str:
    return content.replace("```", "` ` `")


def _json_data(value: object) -> str:
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


class EvidenceBuilder:
    def build(
        self,
        task: ReviewTask,
        analysis: DiffAnalysis,
        contexts: list[CollectedContext],
        warnings: list[str],
    ) -> str:
        sections = [
            "# Task",
            "Review this GitHub pull request as an investigation-style code review Agent.",
            "",
            "# Pull Request",
            f"- Platform: {_json_data(task.platform)}",
            f"- Project: {_json_data(task.project_name)}",
            f"- Source branch: {_json_data(task.source_branch)}",
            f"- Target branch: {_json_data(task.target_branch)}",
            f"- Ref: {_json_data(task.effective_ref)}",
            f"- Author: {_json_data(task.author)}",
            f"- URL: {_json_data(task.url)}",
            "",
            "# Commit Messages",
            self._commit_messages(task.commits),
            "",
            "# Diff Summary",
            self._diff_summary(analysis),
            "",
            "# Code Diff",
            self._code_diff(task.changes),
            "",
            "# Investigation Context",
            self._contexts(contexts),
            "",
            "# Investigation Notes",
            self._warnings(warnings),
            "",
            "# Output Requirements",
            "Return Markdown with these sections:",
            "1. Key issues",
            "2. Potential risks",
            "3. Context investigation summary",
            "4. Recommendations",
            "5. Risk level: low, medium, or high",
            "6. Score in this exact parseable format: 总分: XX分",
            "Distinguish confirmed issues from potential risks. Mention when context is insufficient.",
        ]
        return "\n".join(sections)

    def _commit_messages(self, commits: list[dict]) -> str:
        messages = [commit.get("message", "").strip() for commit in commits if commit.get("message")]
        return "\n".join(f"- {_json_data(message)}" for message in messages) if messages else "- No commit messages provided."

    def _diff_summary(self, analysis: DiffAnalysis) -> str:
        lines = [
            f"- Total additions: {analysis.total_additions}",
            f"- Total deletions: {analysis.total_deletions}",
            f"- Risk hints: {_json_data(', '.join(analysis.risk_hints)) if analysis.risk_hints else 'none'}",
        ]
        for file in analysis.files:
            risk_tags = _json_data(", ".join(file.risk_tags)) if file.risk_tags else "none"
            symbols = _json_data(", ".join(file.changed_symbols)) if file.changed_symbols else "none"
            lines.append(
                f"- File: {_json_data(file.path)}; Language: {_json_data(file.language)}; +{file.additions}/-{file.deletions}; "
                f"Risk tags: {risk_tags}; Changed symbols: {symbols}"
            )
        return "\n".join(lines)

    def _code_diff(self, changes: list[dict]) -> str:
        lines = []
        for index, change in enumerate(changes, start=1):
            lines.append(f"## Changed File {index}")
            lines.append(f"- Path: {_json_data(change.get('new_path') or change.get('old_path'))}")
            lines.append("```diff")
            lines.append(_sanitize_fenced_content(change.get("diff", "")))
            lines.append("```")
        return "\n".join(lines)

    def _contexts(self, contexts: list[CollectedContext]) -> str:
        if not contexts:
            return "- No context files were collected."
        lines = []
        for index, context in enumerate(contexts, start=1):
            lines.extend([
                f"## Context {index}",
                f"- Path: {_json_data(context.path)}",
                f"- Ref: {_json_data(context.ref)}",
                f"- Reason: {_json_data(context.reason)}",
                f"- Truncated: {context.truncated}",
                f"- Error: {_json_data(context.error) if context.error else 'none'}",
                "```",
                _sanitize_fenced_content(context.content),
                "```",
            ])
        return "\n".join(lines)

    def _warnings(self, warnings: list[str]) -> str:
        return "\n".join(f"- {_json_data(warning)}" for warning in warnings) if warnings else "- No investigation warnings."
