from unittest import TestCase, main

from biz.agent.deep_review.project_snapshot import build_project_snapshot


class TestProjectSnapshot(TestCase):
    def test_build_snapshot_groups_repeated_risk_themes(self):
        rows = [
            {
                "id": 1,
                "project_id": "owner/repo",
                "project_name": "repo",
                "score": 72,
                "risk_level": "high",
                "review_profile": "security_review",
                "review_result": """已确认问题
- 缺少鉴权

待关注风险
- 测试不足

调查摘要
- 检查了 backend/auth.py 与 tests/test_auth.py

风险等级
high

总分: 72分
""",
                "agent_trace": '{"investigated_files":[{"path":"backend/auth.py","reason":"Read changed file context for the PR head ref.","truncated":false},{"path":"tests/test_auth.py","reason":"Read candidate related test.","truncated":false}]}',
                "url": "https://github.com/owner/repo/pull/1",
            },
            {
                "id": 2,
                "project_id": "owner/repo",
                "project_name": "repo",
                "score": 80,
                "risk_level": "medium",
                "review_profile": "security_review",
                "review_result": """已确认问题
- 缺少鉴权

待关注风险
- 配置未校验

调查摘要
- 检查了 backend/tenant.py

风险等级
medium

总分: 80分
""",
                "agent_trace": '{"investigated_files":[{"path":"backend/tenant.py","reason":"Read changed file context for the PR head ref.","truncated":false}]}',
                "url": "https://github.com/owner/repo/pull/2",
            },
        ]

        snapshot = build_project_snapshot(rows)

        self.assertEqual(snapshot["review_count"], 2)
        self.assertEqual(snapshot["repeated_issue_patterns"][0]["title"], "缺少鉴权")
        self.assertEqual(snapshot["repeated_issue_patterns"][0]["count"], 2)
        self.assertEqual(snapshot["hot_modules"][0]["module"], "backend")
        self.assertEqual(snapshot["hot_modules"][0]["count"], 2)

    def test_build_snapshot_keeps_review_brief(self):
        rows = [
            {
                "id": 7,
                "project_id": "owner/repo",
                "project_name": "repo",
                "score": 88,
                "risk_level": "low",
                "review_profile": "default_review",
                "review_result": """已确认问题
- 日志字段命名不一致

风险等级
low

总分: 88分
""",
                "agent_trace": "{}",
                "url": "https://github.com/owner/repo/pull/7",
            }
        ]

        snapshot = build_project_snapshot(rows)
        brief = snapshot["baseline_reviews"][0]

        self.assertEqual(brief["id"], 7)
        self.assertEqual(brief["risk_level"], "low")
        self.assertEqual(brief["confirmed_issues"], ["日志字段命名不一致"])


if __name__ == "__main__":
    main()
