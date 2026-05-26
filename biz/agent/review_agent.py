import re
from typing import Protocol

from biz.agent.context_collector import ContextCollector
from biz.agent.diff_analyzer import DiffAnalyzer
from biz.agent.evidence_builder import EvidenceBuilder
from biz.agent.planner import InvestigationPlanner
from biz.agent.task import AgentReviewResult, ReviewTask
from biz.agent.tools.file_reader import PlatformFileReader
from biz.utils.code_reviewer import CodeReviewer


class EvidenceReviewer(Protocol):
    def review_evidence(self, evidence: str) -> str:
        ...


class ReviewAgent:
    def __init__(
        self,
        file_reader: PlatformFileReader,
        reviewer: EvidenceReviewer | None = None,
        analyzer: DiffAnalyzer | None = None,
        planner: InvestigationPlanner | None = None,
        collector: ContextCollector | None = None,
        evidence_builder: EvidenceBuilder | None = None,
    ):
        self.file_reader = file_reader
        self.reviewer = reviewer or self._default_reviewer()
        self.analyzer = analyzer or DiffAnalyzer()
        self.planner = planner or InvestigationPlanner()
        self.collector = collector or ContextCollector()
        self.evidence_builder = evidence_builder or EvidenceBuilder()

    def review(self, task: ReviewTask) -> AgentReviewResult:
        analysis = self.analyzer.analyze(task.changes)
        plan = self.planner.create_plan(task, analysis)
        contexts, warnings = self.collector.collect(plan, self.file_reader)
        evidence = self.evidence_builder.build(task, analysis, contexts, warnings)
        review_text = self.reviewer.review_evidence(evidence)
        score = CodeReviewer.parse_review_score(review_text)
        risk_level = self._parse_risk_level(review_text)
        changed_paths = {file.path for file in analysis.files}
        successful_contexts = [context for context in contexts if context.error is None]
        investigated_files = [context.path for context in successful_contexts if context.path in changed_paths]
        investigation_summary = self._summary(investigated_files, warnings)
        return AgentReviewResult(
            review_text=review_text,
            score=score,
            risk_level=risk_level,
            investigated_files=investigated_files,
            investigation_summary=investigation_summary,
            warnings=warnings,
            agent_trace={
                "mode": "context_investigation",
                "risk_level": risk_level,
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

    def _default_reviewer(self) -> EvidenceReviewer:
        from biz.utils.code_reviewer import AgentCodeReviewer

        return AgentCodeReviewer()

    def _parse_risk_level(self, review_text: str) -> str:
        match = re.search(r"risk level[:：]\s*(low|medium|high)", review_text, flags=re.IGNORECASE)
        return match.group(1).lower() if match else "medium"

    def _summary(self, investigated_files: list[str], warnings: list[str]) -> str:
        checked = ", ".join(investigated_files) if investigated_files else "no context files"
        if warnings:
            return f"Checked {checked}. Warnings: {'; '.join(warnings)}"
        return f"Checked {checked}."
