from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProjectReviewHypothesis:
    """项目级调查中的单条假设。"""

    id: str
    title: str
    category: str
    priority: int
    status: str
    reason: str
    supporting_evidence: list[str] = field(default_factory=list)
    counter_evidence: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)


@dataclass
class ProjectDeepReviewWorkingMemory:
    """项目级会话的可变工作记忆。"""

    active_hypotheses: list[ProjectReviewHypothesis] = field(default_factory=list)
    confirmed_findings: list[dict[str, Any]] = field(default_factory=list)
    weak_signals: list[dict[str, Any]] = field(default_factory=list)
    hot_modules: list[dict[str, Any]] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    evidence_index: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ProjectReviewLogSummary:
    """单条 baseline 日志在项目快照中的简化视图。"""

    id: int
    project_id: str
    project_name: str
    url: str
    score: int
    risk_level: str
    review_profile: str
    confirmed_issues: list[str] = field(default_factory=list)
    potential_risks: list[str] = field(default_factory=list)
    investigation_summary: list[str] = field(default_factory=list)
    investigated_files: list[str] = field(default_factory=list)
