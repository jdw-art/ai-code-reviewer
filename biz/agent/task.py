from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReviewTask:
    """一次代码审查任务的统一输入，屏蔽不同平台 webhook 字段差异。"""

    platform: str
    project_id: str
    project_name: str
    source_branch: str
    target_branch: str
    change_ref: str
    author: str
    url: str
    commits: list[dict[str, Any]]
    changes: list[dict[str, Any]]
    access_token: str = field(repr=False)
    platform_url: str
    review_mode: str = "baseline_review"
    review_profile: str = "default_review"

    @property
    def effective_ref(self) -> str:
        """返回读取上下文时使用的 ref，优先使用 PR head commit。"""
        return self.change_ref or self.source_branch


@dataclass
class ChangedFile:
    """单个变更文件的轻量分析结果。"""

    path: str
    language: str
    additions: int
    deletions: int
    is_test: bool
    is_config: bool
    risk_tags: list[str] = field(default_factory=list)
    changed_symbols: list[str] = field(default_factory=list)


@dataclass
class DiffAnalysis:
    """整次 PR diff 的汇总信息，供调查规划器决定读取范围。"""

    files: list[ChangedFile]
    total_additions: int
    total_deletions: int
    risk_hints: list[str] = field(default_factory=list)


@dataclass
class ContextBudget:
    """Agent 调查阶段的上下文预算，避免一次 PR 消耗过多 token 或 API 调用。"""

    max_context_files: int = 5
    max_context_tokens: int = 12000
    max_file_chars: int = 30000
    max_import_files: int = 2
    max_test_files: int = 2


@dataclass
class InvestigationAction:
    """一次上下文读取动作，例如读取变更文件或候选测试文件。"""

    action_type: str
    path: str
    ref: str
    reason: str
    priority: int


@dataclass
class InvestigationPlan:
    """按优先级裁剪后的调查计划。"""

    actions: list[InvestigationAction]
    budget: ContextBudget


@dataclass
class FileReadResult:
    """平台文件读取结果，错误和截断状态会进入 agent_trace。"""

    path: str
    ref: str
    content: str = ""
    ok: bool = False
    truncated: bool = False
    error: str | None = None


@dataclass
class CollectedContext:
    """已收集的文件上下文，包含读取原因和失败信息。"""

    path: str
    ref: str
    reason: str
    content: str
    truncated: bool = False
    error: str | None = None


@dataclass
class AgentReviewResult:
    """Agent 审查的最终结果，既用于评论回写，也用于持久化追踪。"""

    review_text: str
    score: int
    risk_level: str
    investigated_files: list[str]
    investigation_summary: str
    warnings: list[str]
    review_mode: str = "baseline_review"
    review_profile: str = "default_review"
    agent_trace: dict[str, Any] = field(default_factory=dict)
