from unittest import TestCase, main

from biz.agent.deep_review.tools.project_review_log_tools import ProjectReviewLogTools


class TestProjectReviewLogTools(TestCase):
    def setUp(self):
        self.rows = [
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
                "agent_trace": '{"investigated_files":[{"path":"backend/auth.py","reason":"Read changed file context for the PR head ref.","truncated":false}]}',
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
            {
                "id": 3,
                "project_id": "owner/repo",
                "project_name": "repo",
                "score": 90,
                "risk_level": "low",
                "review_profile": "default_review",
                "review_result": """已确认问题
- 日志字段命名不一致

待关注风险
- 缓存回收路径缺少回归测试

调查摘要
- 检查了 worker/cache.py

风险等级
low

总分: 90分
""",
                "agent_trace": '{"investigated_files":[{"path":"worker/cache.py","reason":"Read changed file context for the PR head ref.","truncated":false}]}',
                "url": "https://github.com/owner/repo/pull/3",
            },
        ]

    def test_list_project_review_logs_returns_brief_rows(self):
        tools = ProjectReviewLogTools(self.rows)

        briefs = tools.list_project_review_logs()

        self.assertEqual(briefs[0]["id"], 1)
        self.assertEqual(briefs[0]["score"], 72)
        self.assertEqual(briefs[0]["risk_level"], "high")

    def test_group_reviews_by_module(self):
        tools = ProjectReviewLogTools(self.rows)

        groups = tools.group_reviews_by_module()

        self.assertEqual(groups[0]["module"], "backend")
        self.assertEqual(groups[0]["count"], 2)

    def test_group_reviews_by_risk_theme(self):
        tools = ProjectReviewLogTools(self.rows)

        groups = tools.group_reviews_by_risk_theme()

        self.assertEqual(groups[0]["title"], "缺少鉴权")
        self.assertEqual(groups[0]["count"], 2)


if __name__ == "__main__":
    main()
