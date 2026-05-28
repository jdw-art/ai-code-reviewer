import re
from copy import deepcopy
from typing import Any

from biz.agent.deep_review.task import ProjectDeepReviewSessionSnapshot
from biz.utils.code_reviewer import ProjectDeepReviewReviewer


class _SnapshotProjectReviewTools:
    """基于 session 摘要快照构造的最小可用项目工具。"""

    def __init__(self, baseline_snapshot: dict[str, Any]):
        self.baseline_snapshot = baseline_snapshot if isinstance(baseline_snapshot, dict) else {}

    def list_project_review_logs(self) -> list[dict[str, Any]]:
        """返回摘要中可用的 baseline review 简表。"""
        reviews = self.baseline_snapshot.get("baseline_reviews", [])
        result: list[dict[str, Any]] = []
        for review in reviews:
            if not isinstance(review, dict):
                continue
            result.append(
                {
                    "id": review.get("id"),
                    "project_id": review.get("project_id", ""),
                    "project_name": review.get("project_name", ""),
                    "url": review.get("url", ""),
                    "score": review.get("score", 0),
                    "risk_level": review.get("risk_level", "medium"),
                    "review_profile": review.get("review_profile", ""),
                }
            )
        return result

    def read_review_log(self, review_log_id: int) -> dict[str, Any] | None:
        """读取摘要里的单条 review 信息。"""
        for review in self.baseline_snapshot.get("baseline_reviews", []):
            if isinstance(review, dict) and review.get("id") == review_log_id:
                return deepcopy(review)
        return None

    def read_review_trace(self, review_log_id: int) -> dict[str, Any]:
        """摘要快照不包含原始 trace，统一返回空字典。"""
        return {}

    def group_reviews_by_module(self) -> list[dict[str, Any]]:
        """返回摘要里已有的热点模块聚合。"""
        groups = self.baseline_snapshot.get("hot_modules", [])
        return deepcopy(groups) if isinstance(groups, list) else []

    def group_reviews_by_risk_theme(self) -> list[dict[str, Any]]:
        """返回摘要里已有的重复问题聚合。"""
        groups = self.baseline_snapshot.get("repeated_issue_patterns", [])
        return deepcopy(groups) if isinstance(groups, list) else []


class ProjectDeepReviewAgent:
    """执行项目级两轮闭环问答。"""

    MAX_ROUNDS = 2
    MAX_GITHUB_PRS = 1

    def __init__(
        self,
        session_snapshot: ProjectDeepReviewSessionSnapshot,
        project_tools: Any | None = None,
        github_tools: Any | None = None,
        reviewer: Any | None = None,
        working_memory: dict[str, Any] | None = None,
        session_summary: dict[str, Any] | None = None,
    ):
        self.session_snapshot = session_snapshot
        self.project_tools = project_tools or _SnapshotProjectReviewTools(session_snapshot.baseline_snapshot)
        self.github_tools = github_tools
        self.reviewer = reviewer or ProjectDeepReviewReviewer(
            review_profile=session_snapshot.profile_name,
            repo_full_name=session_snapshot.project_id,
        )
        self.working_memory = deepcopy(working_memory or {})
        self.session_summary = deepcopy(session_summary or session_snapshot.session_summary)

    @classmethod
    def from_session(
        cls,
        session: dict[str, Any],
        project_tools: Any | None = None,
        github_tools: Any | None = None,
        reviewer: Any | None = None,
    ) -> "ProjectDeepReviewAgent":
        """仅基于 session 中已持久化的摘要结构做轻量 hydrate。"""
        baseline_snapshot = session.get("baseline_snapshot")
        working_memory = session.get("working_memory")
        session_summary = session.get("session_summary")

        normalized_snapshot = baseline_snapshot if isinstance(baseline_snapshot, dict) else {}
        normalized_working_memory = working_memory if isinstance(working_memory, dict) else {}
        normalized_session_summary = session_summary if isinstance(session_summary, dict) else {}

        snapshot = ProjectDeepReviewSessionSnapshot(
            session_id=session.get("id") or session.get("session_id") or 0,
            platform=session.get("platform", ""),
            project_id=session.get("project_id", ""),
            project_name=session.get("project_name", ""),
            profile_name=session.get("profile_name", "default_review"),
            review_log_ids=list(session.get("included_review_log_ids") or []),
            baseline_snapshot=deepcopy(normalized_snapshot),
            session_summary=deepcopy(normalized_session_summary),
        )
        return cls(
            session_snapshot=snapshot,
            project_tools=project_tools or _SnapshotProjectReviewTools(normalized_snapshot),
            github_tools=github_tools,
            reviewer=reviewer,
            working_memory=deepcopy(normalized_working_memory),
            session_summary=deepcopy(normalized_session_summary),
        )

    def answer(self, question: str, user_message_id: int = 0) -> dict[str, Any]:
        """围绕一个项目问题执行至多两轮调查并返回结果。"""
        trace = {
            "session_id": self.session_snapshot.session_id,
            "user_message_id": user_message_id,
            "profile_name": self.session_snapshot.profile_name,
            "round_count": 0,
            "stop_reason": "",
            "rounds": [],
            "tool_outputs": [],
            "final_summary": {},
        }

        baseline_context = self._collect_baseline_context(question, trace)
        round_count = 1
        github_context: dict[str, Any] = {}

        if self.github_tools is not None:
            github_context = self._collect_github_context(baseline_context, trace)
            round_count = self.MAX_ROUNDS

        stop_reason = "round_limit" if round_count >= self.MAX_ROUNDS else "baseline_only"
        evidence_text = self._build_evidence_text(question, baseline_context, github_context)
        result_markdown = self._review_project(question, evidence_text)
        updated_working_memory = self._update_working_memory(
            question=question,
            baseline_context=baseline_context,
            github_context=github_context,
            round_count=round_count,
            stop_reason=stop_reason,
        )
        updated_session_summary = self._update_session_summary(
            question=question,
            baseline_context=baseline_context,
            round_count=round_count,
            stop_reason=stop_reason,
        )

        trace["round_count"] = round_count
        trace["stop_reason"] = stop_reason
        trace["final_summary"] = {
            "question": question,
            "baseline_review_count": baseline_context.get("review_count", 0),
            "github_pr_numbers": github_context.get("pr_numbers", []),
        }

        self.working_memory = deepcopy(updated_working_memory)
        self.session_summary = deepcopy(updated_session_summary)
        self.session_snapshot.session_summary = deepcopy(updated_session_summary)

        return {
            "result_markdown": result_markdown,
            "round_count": round_count,
            "stop_reason": stop_reason,
            "trace": trace,
            "updated_working_memory": updated_working_memory,
            "updated_session_summary": updated_session_summary,
        }

    def _review_project(self, question: str, evidence_text: str) -> str:
        """兼容真实 reviewer 与测试替身。"""
        if hasattr(self.reviewer, "review_project"):
            return self.reviewer.review_project(question, evidence_text)
        return self.reviewer.review_evidence(evidence_text)

    def _collect_baseline_context(self, question: str, trace: dict[str, Any]) -> dict[str, Any]:
        """第一轮：从项目摘要快照聚合 baseline 线索。"""
        review_logs = deepcopy(self.project_tools.list_project_review_logs())
        risk_themes = deepcopy(self.project_tools.group_reviews_by_risk_theme())
        hot_modules = deepcopy(self.project_tools.group_reviews_by_module())
        context = {
            "question": question,
            "review_count": len(review_logs),
            "review_logs": review_logs,
            "risk_themes": risk_themes,
            "hot_modules": hot_modules,
        }
        trace["rounds"].append(
            {
                "round": 1,
                "source": "project_tools",
                "question": question,
                "review_count": len(review_logs),
            }
        )
        trace["tool_outputs"].extend(
            [
                {"tool": "list_project_review_logs", "payload": self._summarize_review_logs(review_logs)},
                {"tool": "group_reviews_by_risk_theme", "payload": risk_themes[:5]},
                {"tool": "group_reviews_by_module", "payload": hot_modules[:5]},
            ]
        )
        return context

    def _collect_github_context(self, baseline_context: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
        """第二轮：基于 baseline 线索补充 GitHub 证据。"""
        pr_numbers = self._extract_pr_numbers(baseline_context.get("review_logs", []))[: self.MAX_GITHUB_PRS]
        github_context: dict[str, Any] = {"pr_numbers": pr_numbers, "pull_requests": []}
        round_trace = {"round": 2, "source": "github_tools", "pr_numbers": pr_numbers}

        if not pr_numbers:
            round_trace["note"] = "baseline 摘要中没有可继续追踪的 PR 编号。"
            trace["rounds"].append(round_trace)
            return github_context

        pr_number = pr_numbers[0]
        metadata = self._safe_tool_call("read_pr_metadata", pr_number, trace=trace, default={})
        diff_files = self._safe_tool_call("read_pr_diff", pr_number, trace=trace, default=[])

        primary_file = self._extract_primary_file(diff_files)
        head_ref = self._extract_head_ref(metadata)
        related_tests: list[dict[str, Any]] = []
        local_imports: list[dict[str, Any]] = []

        if primary_file and head_ref and hasattr(self.github_tools, "read_related_test"):
            related_tests = self._safe_tool_call(
                "read_related_test",
                primary_file,
                head_ref,
                trace=trace,
                default=[],
            )
        if primary_file and head_ref and hasattr(self.github_tools, "read_local_import"):
            local_imports = self._safe_tool_call(
                "read_local_import",
                primary_file,
                head_ref,
                trace=trace,
                default=[],
            )

        github_context["pull_requests"].append(
            {
                "number": pr_number,
                "title": metadata.get("title", ""),
                "state": metadata.get("state", ""),
                "head_ref": head_ref,
                "changed_files": [item.get("filename", "") for item in diff_files if isinstance(item, dict)],
                "related_tests": related_tests,
                "local_imports": local_imports,
            }
        )
        round_trace["primary_pr"] = pr_number
        round_trace["primary_file"] = primary_file
        trace["rounds"].append(round_trace)
        return github_context

    def _safe_tool_call(
        self,
        tool_name: str,
        *args: Any,
        trace: dict[str, Any],
        default: Any,
    ) -> Any:
        """读取工具结果并记录到 trace，失败时保守返回默认值。"""
        try:
            tool_method = getattr(self.github_tools, tool_name)
            payload = tool_method(*args)
        except Exception as exc:
            payload = default
            trace["tool_outputs"].append(
                {
                    "tool": tool_name,
                    "payload": self._sanitize_tool_payload(tool_name, default),
                    "warning": f"{type(exc).__name__}: {exc}",
                }
            )
            return payload

        trace["tool_outputs"].append({"tool": tool_name, "payload": self._sanitize_tool_payload(tool_name, payload)})
        return payload

    @staticmethod
    def _extract_pr_numbers(review_logs: list[dict[str, Any]]) -> list[int]:
        """从 baseline review URL 中提取 PR 编号。"""
        pr_numbers: list[int] = []
        seen: set[int] = set()
        for review in review_logs:
            if not isinstance(review, dict):
                continue
            url = review.get("url", "")
            match = re.search(r"/pull/(\d+)", url)
            if not match:
                continue
            pr_number = int(match.group(1))
            if pr_number in seen:
                continue
            seen.add(pr_number)
            pr_numbers.append(pr_number)
        return pr_numbers

    @staticmethod
    def _extract_primary_file(diff_files: list[dict[str, Any]]) -> str:
        """选择第二轮调查的首个主文件。"""
        for item in diff_files:
            if isinstance(item, dict) and item.get("filename"):
                return item["filename"]
        return ""

    @staticmethod
    def _extract_head_ref(metadata: dict[str, Any]) -> str:
        """优先取 head.ref，缺失时用 HEAD 兜底。"""
        head = metadata.get("head")
        if isinstance(head, dict) and head.get("ref"):
            return head["ref"]
        return "HEAD"

    def _build_evidence_text(
        self,
        question: str,
        baseline_context: dict[str, Any],
        github_context: dict[str, Any],
    ) -> str:
        """组装项目级 reviewer 所需证据文本。"""
        baseline_lines = [
            f"用户问题：{question}",
            "",
            "第一轮：baseline 摘要线索",
            f"- 纳入的 baseline review 数量：{baseline_context.get('review_count', 0)}",
        ]
        for item in baseline_context.get("risk_themes", [])[:5]:
            baseline_lines.append(f"- 重复问题：{item.get('title', '')}（{item.get('count', 0)}次）")
        for item in baseline_context.get("hot_modules", [])[:5]:
            baseline_lines.append(f"- 热点模块：{item.get('module', '')}（{item.get('count', 0)}次）")
        for review in baseline_context.get("review_logs", [])[:5]:
            baseline_lines.append(
                "- 历史 review："
                f"id={review.get('id')}，risk={review.get('risk_level')}，score={review.get('score')}，url={review.get('url')}"
            )

        github_lines = ["", "第二轮：GitHub 补充调查"]
        pull_requests = github_context.get("pull_requests", [])
        if not pull_requests:
            github_lines.append("- 当前没有可补充的 GitHub 原始证据。")
        for item in pull_requests:
            github_lines.append(
                f"- PR #{item.get('number')}：{item.get('title', '')}，state={item.get('state', '')}，ref={item.get('head_ref', '')}"
            )
            changed_files = item.get("changed_files", [])
            if changed_files:
                github_lines.append(f"- 变更文件：{', '.join(changed_files)}")
            related_tests = [test.get("path", "") for test in item.get("related_tests", []) if isinstance(test, dict)]
            if related_tests:
                github_lines.append(f"- 相关测试：{', '.join(related_tests)}")
            local_imports = [imp.get("line", "") for imp in item.get("local_imports", []) if isinstance(imp, dict)]
            if local_imports:
                github_lines.append(f"- 本地导入：{' ; '.join(local_imports)}")

        memory_lines = ["", "当前工作记忆摘要"]
        for item in self._summarize_findings(self.working_memory.get("confirmed_findings")):
            memory_lines.append(f"- 已确认线索：{item}")
        for item in self._ensure_list(self.working_memory.get("open_questions"))[:5]:
            memory_lines.append(f"- 待确认问题：{item}")

        summary_lines = ["", "当前会话摘要"]
        summary_lines.append(f"- 已提问次数：{self.session_summary.get('question_count', 0)}")
        summary_lines.append(f"- 最近问题：{self.session_summary.get('last_question', '')}")
        return "\n".join(baseline_lines + github_lines + memory_lines + summary_lines)

    def _update_working_memory(
        self,
        question: str,
        baseline_context: dict[str, Any],
        github_context: dict[str, Any],
        round_count: int,
        stop_reason: str,
    ) -> dict[str, Any]:
        """更新工作记忆，保留原对象中的已有信息。"""
        updated = deepcopy(self.working_memory)
        updated["hot_modules"] = deepcopy(baseline_context.get("hot_modules", []))
        updated["repeated_issue_patterns"] = deepcopy(baseline_context.get("risk_themes", []))
        updated["last_question"] = question
        updated["last_round_count"] = round_count
        updated["last_stop_reason"] = stop_reason

        confirmed_findings = self._ensure_list(updated.get("confirmed_findings"))
        top_risk = baseline_context.get("risk_themes", [])[:1]
        if top_risk:
            confirmed_findings = self._append_unique_finding(
                confirmed_findings,
                {
                    "source": "baseline",
                    "title": top_risk[0].get("title", ""),
                    "count": top_risk[0].get("count", 0),
                },
            )
        if github_context.get("pull_requests"):
            primary_pr = github_context["pull_requests"][0]
            confirmed_findings = self._append_unique_finding(
                confirmed_findings,
                {
                    "source": "github",
                    "title": primary_pr.get("title", ""),
                    "pr_number": primary_pr.get("number"),
                },
            )
        updated["confirmed_findings"] = confirmed_findings[-10:]

        open_questions = self._ensure_list(updated.get("open_questions"))
        if github_context.get("pull_requests"):
            primary_pr = github_context["pull_requests"][0]
            if not primary_pr.get("related_tests"):
                open_questions = self._append_unique(open_questions, "需要确认核心回归测试是否已经补齐")
        updated["open_questions"] = open_questions
        return updated

    def _update_session_summary(
        self,
        question: str,
        baseline_context: dict[str, Any],
        round_count: int,
        stop_reason: str,
    ) -> dict[str, Any]:
        """更新会话摘要，供后续多轮问答复用。"""
        updated = deepcopy(self.session_summary)
        question_count = updated.get("question_count", 0)
        updated["question_count"] = question_count + 1 if isinstance(question_count, int) else 1
        recent_questions = self._ensure_list(updated.get("recent_questions"))
        recent_questions.append(question)
        updated["recent_questions"] = recent_questions[-5:]
        updated["last_question"] = question
        updated["last_round_count"] = round_count
        updated["last_stop_reason"] = stop_reason
        updated["last_review_count"] = baseline_context.get("review_count", 0)
        updated["last_hot_modules"] = deepcopy(baseline_context.get("hot_modules", [])[:3])
        updated["last_repeated_issue_patterns"] = deepcopy(baseline_context.get("risk_themes", [])[:3])
        return updated

    @staticmethod
    def _ensure_list(value: Any) -> list[Any]:
        """把可选字段规范成列表。"""
        return deepcopy(value) if isinstance(value, list) else []

    @staticmethod
    def _append_unique(items: list[str], item: str) -> list[str]:
        """避免在问题列表中重复追加同一条内容。"""
        if item not in items:
            items.append(item)
        return items

    @staticmethod
    def _append_unique_finding(items: list[dict[str, Any]], item: dict[str, Any]) -> list[dict[str, Any]]:
        """按来源和主题去重，避免多轮会话不断重复追加同一条结论。"""
        fingerprint = (
            item.get("source", ""),
            item.get("title", ""),
            item.get("pr_number", ""),
        )
        for existing in items:
            existing_fingerprint = (
                existing.get("source", ""),
                existing.get("title", ""),
                existing.get("pr_number", ""),
            )
            if existing_fingerprint == fingerprint:
                return items
        items.append(item)
        return items

    @staticmethod
    def _summarize_review_logs(review_logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """trace 中只保留 review 摘要，不落完整原始内容。"""
        summary = []
        for item in review_logs[:5]:
            if not isinstance(item, dict):
                continue
            summary.append(
                {
                    "id": item.get("id"),
                    "url": item.get("url", ""),
                    "score": item.get("score", 0),
                    "risk_level": item.get("risk_level", ""),
                }
            )
        return summary

    @staticmethod
    def _sanitize_tool_payload(tool_name: str, payload: Any) -> Any:
        """把工具输出压成轻量摘要，避免把源码和 patch 直接持久化到 trace。"""
        if tool_name == "read_pr_metadata" and isinstance(payload, dict):
            head = payload.get("head", {})
            return {
                "number": payload.get("number"),
                "title": payload.get("title", ""),
                "state": payload.get("state", ""),
                "head_ref": head.get("ref", "") if isinstance(head, dict) else "",
            }
        if tool_name == "read_pr_diff" and isinstance(payload, list):
            files = []
            for item in payload[:20]:
                if not isinstance(item, dict):
                    continue
                files.append(
                    {
                        "filename": item.get("filename", ""),
                        "status": item.get("status", ""),
                    }
                )
            return {"count": len(payload), "files": files}
        if tool_name == "read_related_test" and isinstance(payload, list):
            files = []
            for item in payload[:10]:
                if not isinstance(item, dict):
                    continue
                files.append(
                    {
                        "path": item.get("path", ""),
                        "ref": item.get("ref", ""),
                        "truncated": item.get("truncated", False),
                    }
                )
            return {"count": len(payload), "files": files}
        if tool_name == "read_local_import" and isinstance(payload, list):
            return {"count": len(payload)}
        return payload

    @staticmethod
    def _summarize_findings(findings: Any) -> list[str]:
        """把工作记忆中的 finding 压成短文本，避免下一轮 prompt 持续膨胀。"""
        result = []
        for item in findings if isinstance(findings, list) else []:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "")
            source = item.get("source", "")
            if title:
                result.append(f"{source}:{title}".strip(":"))
        return result[:5]
