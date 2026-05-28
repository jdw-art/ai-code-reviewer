import json

from biz.agent.task import CollectedContext, DiffAnalysis, ReviewTask


def _sanitize_fenced_content(content: str) -> str:
    """打散证据中的 Markdown 代码围栏，避免破坏外层 prompt 结构。"""
    return content.replace("```", "` ` `")


def _json_data(value: object) -> str:
    """将不可信元数据编码成 JSON 字符串，降低 prompt 注入风险。"""
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


class EvidenceBuilder:
    """把任务、diff、上下文和 warning 组装成 LLM 可审查的结构化证据。"""

    def build(
        self,
        task: ReviewTask,
        analysis: DiffAnalysis,
        contexts: list[CollectedContext],
        warnings: list[str],
    ) -> str:
        """生成完整 evidence 文本；这里的所有输入都按不可信数据处理。"""
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
        """整理提交信息，提交内容可能包含恶意指令，因此逐条 JSON 编码。"""
        messages = [commit.get("message", "").strip() for commit in commits if commit.get("message")]
        return "\n".join(f"- {_json_data(message)}" for message in messages) if messages else "- No commit messages provided."

    def _diff_summary(self, analysis: DiffAnalysis) -> str:
        """输出 diff 汇总，帮助模型先建立文件级风险地图。"""
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
        """输出原始 diff 片段，路径和 diff 内容都需要隔离为证据。"""
        lines = []
        for index, change in enumerate(changes, start=1):
            lines.append(f"## Changed File {index}")
            lines.append(f"- Path: {_json_data(change.get('new_path') or change.get('old_path'))}")
            lines.append("```diff")
            lines.append(_sanitize_fenced_content(change.get("diff", "")))
            lines.append("```")
        return "\n".join(lines)

    def _contexts(self, contexts: list[CollectedContext]) -> str:
        """输出已读取的上下文文件，并保留读取失败和截断信息。"""
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
        """输出调查阶段的证据缺口，提醒模型不要在缺失上下文时编造事实。"""
        return "\n".join(f"- {_json_data(warning)}" for warning in warnings) if warnings else "- No investigation warnings."
