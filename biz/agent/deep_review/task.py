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
class ProjectDeepReviewSessionSnapshot:
    """项目级会话的固定输入快照。"""

    session_id: int
    platform: str
    project_id: str
    project_name: str
    profile_name: str
    review_log_ids: list[int] = field(default_factory=list)
    baseline_snapshot: dict[str, Any] = field(default_factory=dict)
    session_summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectDeepReviewRunTrace:
    """项目级单次运行的轻量追踪对象。"""

    session_id: int
    user_message_id: int
    profile_name: str
    round_count: int
    stop_reason: str
    rounds: list[dict[str, Any]] = field(default_factory=list)
    tool_outputs: list[dict[str, Any]] = field(default_factory=list)
    final_summary: dict[str, Any] = field(default_factory=dict)


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
