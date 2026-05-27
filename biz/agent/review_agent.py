from typing import Protocol

from biz.agent.context_collector import ContextCollector
from biz.agent.diff_analyzer import DiffAnalyzer
from biz.agent.evidence_builder import EvidenceBuilder
from biz.agent.planner import InvestigationPlanner
from biz.agent.task import AgentReviewResult, ReviewTask
from biz.agent.tools.file_reader import PlatformFileReader
from biz.utils.code_reviewer import CodeReviewer


class EvidenceReviewer(Protocol):
    """基于结构化 evidence 生成审查结果的模型接口。"""

    def review_evidence(self, evidence: str) -> str:
        ...


class ClassicReviewer(Protocol):
    """旧版 diff-only reviewer 接口，用作 Agent 失败时的兜底。"""

    def review_and_strip_code(self, changes_text: str, commits_text: str = "") -> str:
        ...


class ReviewAgent:
    """调查型代码审查编排器，负责串联分析、规划、上下文收集和模型审查。"""

    def __init__(
        self,
        file_reader: PlatformFileReader,
        reviewer: EvidenceReviewer | None = None,
        analyzer: DiffAnalyzer | None = None,
        planner: InvestigationPlanner | None = None,
        collector: ContextCollector | None = None,
        evidence_builder: EvidenceBuilder | None = None,
        fallback_reviewer: ClassicReviewer | None = None,
    ):
        self.file_reader = file_reader
        self.reviewer = reviewer
        self.analyzer = analyzer or DiffAnalyzer()
        self.planner = planner or InvestigationPlanner()
        self.collector = collector or ContextCollector()
        self.evidence_builder = evidence_builder or EvidenceBuilder()
        self.fallback_reviewer = fallback_reviewer

    def review(self, task: ReviewTask) -> AgentReviewResult:
        """执行一次完整 Agent 审查；内部异常会降级到旧版审查器。"""
        try:
            analysis = self.analyzer.analyze(task.changes)
            plan = self.planner.create_plan(task, analysis)
            contexts, warnings = self.collector.collect(plan, self.file_reader)
            evidence = self.evidence_builder.build(task, analysis, contexts, warnings)
            reviewer = self.reviewer or self._default_reviewer(task)
            review_text = reviewer.review_evidence(evidence)
            score = CodeReviewer.parse_review_score(review_text)
            risk_level = self._parse_risk_level(review_text)
            # trace 只记录成功读取的文件元数据，不保存文件内容，避免落库过大或泄露上下文。
            successful_contexts = [context for context in contexts if context.error is None]
            investigated_files = [context.path for context in successful_contexts]
            investigation_summary = self._summary(investigated_files, warnings)
            return AgentReviewResult(
                review_text=review_text,
                score=score,
                risk_level=risk_level,
                investigated_files=investigated_files,
                investigation_summary=investigation_summary,
                warnings=warnings,
                review_mode=task.review_mode,
                review_profile=task.review_profile,
                agent_trace={
                    "mode": "context_investigation",
                    "risk_level": risk_level,
                    "review_profile": task.review_profile,
                    "review_mode": task.review_mode,
                    "investigated_files": [
                        {"path": context.path, "reason": context.reason, "truncated": context.truncated}
                        for context in successful_contexts
                    ],
                    "warnings": warnings,
                    "budget": {
                        "max_context_files": plan.budget.max_context_files,
                        "used_context_files": len(successful_contexts),
                    },
                },
            )
        except Exception as exc:
            return self._classic_fallback(task, exc)

    def _default_reviewer(self, task: ReviewTask) -> EvidenceReviewer:
        """延迟加载 Agent reviewer，避免未安装可选模型 SDK 时影响普通导入。"""
        from biz.utils.code_reviewer import AgentCodeReviewer

        return AgentCodeReviewer(review_profile=task.review_profile, repo_full_name=task.project_id)

    def _parse_risk_level(self, review_text: str) -> str:
        """从模型输出中解析风险等级，缺失时使用 medium 保守兜底。"""
        return CodeReviewer.parse_risk_level(review_text)

    def _summary(self, investigated_files: list[str], warnings: list[str]) -> str:
        """生成简短调查摘要，用于结果对象和后续可观测信息。"""
        checked = ", ".join(investigated_files) if investigated_files else "no context files"
        if warnings:
            return f"Checked {checked}. Warnings: {'; '.join(warnings)}"
        return f"Checked {checked}."

    def _classic_fallback(self, task: ReviewTask, exc: Exception) -> AgentReviewResult:
        """Agent 编排失败时回到旧版审查，保证 webhook 仍能给出评论。"""
        reviewer = self.fallback_reviewer or CodeReviewer(
            review_profile=task.review_profile,
            repo_full_name=task.project_id,
        )
        commits_text = ";".join(commit.get("message", "").strip() for commit in task.commits)
        review_text = reviewer.review_and_strip_code(str(task.changes), commits_text)
        score = CodeReviewer.parse_review_score(review_text)
        risk_level = self._parse_risk_level(review_text)
        warnings = [f"Agent review failed, used classic fallback: {type(exc).__name__}"]
        return AgentReviewResult(
            review_text=review_text,
            score=score,
            risk_level=risk_level,
            investigated_files=[],
            investigation_summary=self._summary([], warnings),
            warnings=warnings,
            review_mode=task.review_mode,
            review_profile=task.review_profile,
            agent_trace={
                "mode": "classic_fallback",
                "risk_level": risk_level,
                "review_profile": task.review_profile,
                "review_mode": task.review_mode,
                "investigated_files": [],
                "warnings": warnings,
            },
        )
