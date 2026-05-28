import json

from biz.agent.deep_review.project_snapshot import build_project_snapshot


class ProjectReviewLogTools:
    """围绕 baseline review 日志提供项目级只读聚合能力。"""

    def __init__(self, review_rows: list[dict]):
        self.review_rows = review_rows
        self.snapshot = build_project_snapshot(review_rows)

    def list_project_review_logs(self) -> list[dict]:
        reviews = []
        for item in self.snapshot["baseline_reviews"]:
            reviews.append(
                {
                    "id": item["id"],
                    "project_id": item["project_id"],
                    "project_name": item["project_name"],
                    "url": item["url"],
                    "score": item["score"],
                    "risk_level": item["risk_level"],
                    "review_profile": item["review_profile"],
                }
            )
        return reviews

    def read_review_log(self, review_log_id: int) -> dict | None:
        for row in self.review_rows:
            if row.get("id") == review_log_id:
                return row
        return None

    @staticmethod
    def _normalize_agent_trace(agent_trace: dict | str | None) -> dict:
        """对持久化 trace 做最小规范化，保留原始字段结构。"""
        if isinstance(agent_trace, dict):
            return agent_trace
        if not agent_trace:
            return {}
        try:
            payload = json.loads(agent_trace)
        except (TypeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def read_review_trace(self, review_log_id: int) -> dict:
        review = self.read_review_log(review_log_id)
        if review is None:
            return {}
        return self._normalize_agent_trace(review.get("agent_trace"))

    def group_reviews_by_module(self) -> list[dict]:
        return self.snapshot["hot_modules"]

    def group_reviews_by_risk_theme(self) -> list[dict]:
        return self.snapshot["repeated_issue_patterns"]
