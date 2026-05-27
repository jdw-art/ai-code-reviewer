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

    def read_review_trace(self, review_log_id: int) -> dict:
        review = self.read_review_log(review_log_id)
        if review is None:
            return {}
        for item in self.snapshot["baseline_reviews"]:
            if item["id"] == review_log_id:
                return {
                    "confirmed_issues": item["confirmed_issues"],
                    "potential_risks": item["potential_risks"],
                    "investigation_summary": item["investigation_summary"],
                    "investigated_files": item["investigated_files"],
                }
        return {}

    def group_reviews_by_module(self) -> list[dict]:
        return self.snapshot["hot_modules"]

    def group_reviews_by_risk_theme(self) -> list[dict]:
        return self.snapshot["repeated_issue_patterns"]
