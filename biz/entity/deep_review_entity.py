from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProjectDeepReviewSessionEntity:
    platform: str
    project_id: str
    project_name: str
    profile_name: str
    time_range_start: int
    time_range_end: int
    included_review_log_ids: list[int]
    baseline_snapshot: dict[str, Any]
    created_by: str
    working_memory: dict[str, Any] = field(default_factory=dict)
    session_summary: dict[str, Any] = field(default_factory=dict)
    status: str = "active"


@dataclass
class ProjectDeepReviewMessageEntity:
    session_id: int
    role: str
    content: str


@dataclass
class ProjectDeepReviewRunEntity:
    session_id: int
    user_message_id: int
    profile_name: str
    round_count: int
    stop_reason: str
    result_markdown: str
    trace_json: dict[str, Any]
