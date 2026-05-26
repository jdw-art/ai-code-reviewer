from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReviewTask:
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

    @property
    def effective_ref(self) -> str:
        return self.change_ref or self.source_branch


@dataclass
class ChangedFile:
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
    files: list[ChangedFile]
    total_additions: int
    total_deletions: int
    risk_hints: list[str] = field(default_factory=list)


@dataclass
class ContextBudget:
    max_context_files: int = 5
    max_context_tokens: int = 12000
    max_file_chars: int = 30000
    max_import_files: int = 2
    max_test_files: int = 2


@dataclass
class InvestigationAction:
    action_type: str
    path: str
    ref: str
    reason: str
    priority: int


@dataclass
class InvestigationPlan:
    actions: list[InvestigationAction]
    budget: ContextBudget


@dataclass
class FileReadResult:
    path: str
    ref: str
    content: str = ""
    ok: bool = False
    truncated: bool = False
    error: str | None = None


@dataclass
class CollectedContext:
    path: str
    ref: str
    reason: str
    content: str
    truncated: bool = False
    error: str | None = None


@dataclass
class AgentReviewResult:
    review_text: str
    score: int
    risk_level: str
    investigated_files: list[str]
    investigation_summary: str
    warnings: list[str]
    agent_trace: dict[str, Any] = field(default_factory=dict)
