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
            {
                "id": 4,
                "project_id": "owner/repo",
                "project_name": "repo",
                "score": 84,
                "risk_level": "medium",
                "review_profile": "default_review",
                "review_result": "总分: 84分",
                "agent_trace": {
                    "mode": "context_investigation",
                    "review_mode": "baseline_review",
                    "warnings": ["上下文截断"],
                    "investigated_files": [
                        {
                            "path": "service/user.py",
                            "reason": "Read related source file.",
                            "truncated": True,
                        }
                    ],
                },
                "url": "https://github.com/owner/repo/pull/4",
            },
            {
                "id": 5,
                "project_id": "owner/repo",
                "project_name": "repo",
                "score": 70,
                "risk_level": "medium",
                "review_profile": "default_review",
                "review_result": "总分: 70分",
                "agent_trace": "",
                "url": "https://github.com/owner/repo/pull/5",
            },
            {
                "id": 6,
                "project_id": "owner/repo",
                "project_name": "repo",
                "score": 65,
                "risk_level": "medium",
                "review_profile": "default_review",
                "review_result": "总分: 65分",
                "agent_trace": "{invalid-json",
                "url": "https://github.com/owner/repo/pull/6",
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

    def test_read_review_trace_returns_normalized_original_json_payload(self):
        tools = ProjectReviewLogTools(self.rows)

        trace = tools.read_review_trace(1)

        self.assertEqual(trace["investigated_files"][0]["path"], "backend/auth.py")
        self.assertEqual(trace["investigated_files"][0]["reason"], "Read changed file context for the PR head ref.")
        self.assertIs(trace["investigated_files"][0]["truncated"], False)

    def test_read_review_trace_preserves_original_dict_payload(self):
        tools = ProjectReviewLogTools(self.rows)

        trace = tools.read_review_trace(4)

        self.assertEqual(trace["mode"], "context_investigation")
        self.assertEqual(trace["review_mode"], "baseline_review")
        self.assertEqual(trace["warnings"], ["上下文截断"])
        self.assertEqual(trace["investigated_files"][0]["reason"], "Read related source file.")
        self.assertIs(trace["investigated_files"][0]["truncated"], True)

    def test_read_review_trace_returns_empty_dict_for_empty_value(self):
        tools = ProjectReviewLogTools(self.rows)

        trace = tools.read_review_trace(5)

        self.assertEqual(trace, {})

    def test_read_review_trace_returns_empty_dict_for_invalid_json(self):
        tools = ProjectReviewLogTools(self.rows)

        trace = tools.read_review_trace(6)

        self.assertEqual(trace, {})


if __name__ == "__main__":
    main()
