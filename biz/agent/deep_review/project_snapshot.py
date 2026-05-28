import json

from biz.agent.deep_review.task import ProjectReviewLogSummary
from biz.agent.review_comment_parser import parse_baseline_review


def _normalize_agent_trace(agent_trace: str | dict | None) -> dict:
    if isinstance(agent_trace, dict):
        return agent_trace
    if not agent_trace:
        return {}
    try:
        payload = json.loads(agent_trace)
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_module_name(path: str) -> str:
    normalized = (path or "").strip().lstrip("/")
    if not normalized:
        return "unknown"
    return normalized.split("/", 1)[0]


def _sort_counter_items(counter: dict[str, int], key_name: str) -> list[dict]:
    return [
        {key_name: name, "count": count}
        for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def build_project_snapshot(rows: list[dict]) -> dict:
    repeated_issue_counter: dict[str, int] = {}
    module_counter: dict[str, int] = {}
    baseline_reviews: list[dict] = []

    for row in rows:
        parsed = parse_baseline_review(row.get("review_result", ""))
        trace = _normalize_agent_trace(row.get("agent_trace"))
        investigated_items = trace.get("investigated_files", [])
        investigated_files: list[str] = []

        for issue in parsed["confirmed_issues"]:
            repeated_issue_counter[issue] = repeated_issue_counter.get(issue, 0) + 1

        for item in investigated_items:
            path = item.get("path", "") if isinstance(item, dict) else ""
            if not path:
                continue
            investigated_files.append(path)
            module = _extract_module_name(path)
            module_counter[module] = module_counter.get(module, 0) + 1

        summary = ProjectReviewLogSummary(
            id=row.get("id", 0),
            project_id=row.get("project_id", ""),
            project_name=row.get("project_name", ""),
            url=row.get("url", ""),
            score=row.get("score", parsed["total_score"]),
            risk_level=row.get("risk_level") or parsed["risk_level"],
            review_profile=row.get("review_profile", ""),
            confirmed_issues=parsed["confirmed_issues"],
            potential_risks=parsed["potential_risks"],
            investigation_summary=parsed["investigation_summary"],
            investigated_files=investigated_files,
        )
        baseline_reviews.append(summary.__dict__)

    return {
        "review_count": len(rows),
        "baseline_reviews": baseline_reviews,
        "repeated_issue_patterns": _sort_counter_items(repeated_issue_counter, "title"),
        "hot_modules": _sort_counter_items(module_counter, "module"),
    }
