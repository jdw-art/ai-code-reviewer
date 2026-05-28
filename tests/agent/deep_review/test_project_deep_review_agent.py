from unittest import TestCase, main
from unittest.mock import patch

from biz.agent.deep_review.agent import ProjectDeepReviewAgent
from biz.utils.code_reviewer import ProjectDeepReviewReviewer


class StubProjectDeepReviewReviewer:
    """用于断言项目级 evidence 组装结果的假审查器。"""

    def __init__(self):
        self.last_question = ""
        self.last_evidence_text = ""

    def review_project(self, question: str, evidence_text: str) -> str:
        self.last_question = question
        self.last_evidence_text = evidence_text
        return """项目总体结论
- 近期风险主要集中在鉴权与测试回归。

阶段性高风险主题
- 多个 PR 重复出现租户鉴权缺失。

重复出现的问题模式
- 同类问题在 backend 模块重复暴露。

热点模块与影响范围
- backend 模块改动密集，涉及登录与租户链路。

证据与判断依据
- 结合 baseline 摘要与 GitHub 补充调查给出判断。

评分明细
- 功能稳定性：21/25
- 安全与数据风险控制：20/25
- 测试与验证充分性：21/25
- 架构治理情况：20/25

改进建议
- 优先补齐 backend/auth.py 对应回归测试。

风险等级
high

总分: 82分
"""


class StubGitHubDeepReviewTools:
    """模拟第二轮 GitHub 补充调查工具。"""

    def __init__(self):
        self.calls = []

    def read_pr_metadata(self, pr_number: int) -> dict:
        self.calls.append(("read_pr_metadata", pr_number))
        return {
            "number": pr_number,
            "title": "修复租户鉴权回归",
            "state": "open",
            "head": {"ref": "feature/auth-fix"},
        }

    def read_pr_diff(self, pr_number: int) -> list[dict]:
        self.calls.append(("read_pr_diff", pr_number))
        return [
            {"filename": "backend/auth.py", "status": "modified", "patch": "@@ -1 +1 @@\n+validate()"},
            {"filename": "backend/tenant.py", "status": "modified"},
        ]

    def read_related_test(self, path: str, ref: str) -> list[dict]:
        self.calls.append(("read_related_test", path, ref))
        return [
            {
                "path": "tests/backend/test_auth.py",
                "ref": ref,
                "content": "def test_auth_guard():\n    assert True\n",
                "truncated": False,
            }
        ]

    def read_local_import(self, path: str, ref: str) -> list[dict]:
        self.calls.append(("read_local_import", path, ref))
        return [{"line": "from .tenant import TenantGuard"}]


class TestProjectDeepReviewAgent(TestCase):
    def _build_session_payload(self) -> dict:
        """构造只包含摘要快照的 session 数据。"""
        return {
            "id": 12,
            "platform": "github",
            "project_id": "owner/repo",
            "project_name": "repo",
            "profile_name": "security_review",
            "included_review_log_ids": [101, 102],
            "baseline_snapshot": {
                "review_count": 2,
                "baseline_reviews": [
                    {
                        "id": 101,
                        "project_id": "owner/repo",
                        "project_name": "repo",
                        "url": "https://github.com/owner/repo/pull/17",
                        "score": 72,
                        "risk_level": "high",
                        "review_profile": "security_review",
                        "confirmed_issues": ["租户鉴权缺失"],
                        "potential_risks": ["回归测试不足"],
                    },
                    {
                        "id": 102,
                        "project_id": "owner/repo",
                        "project_name": "repo",
                        "url": "https://github.com/owner/repo/pull/18",
                        "score": 79,
                        "risk_level": "medium",
                        "review_profile": "security_review",
                        "confirmed_issues": ["权限边界校验缺失"],
                        "potential_risks": ["配置校验不完整"],
                    },
                ],
                "repeated_issue_patterns": [
                    {"title": "租户鉴权缺失", "count": 2},
                    {"title": "回归测试不足", "count": 1},
                ],
                "hot_modules": [
                    {"module": "backend", "count": 3},
                    {"module": "tests", "count": 1},
                ],
            },
            "working_memory": {
                "confirmed_findings": [{"title": "历史风险"}],
                "open_questions": ["需要确认 tenant 相关回归范围"],
            },
            "session_summary": {
                "question_count": 2,
                "recent_questions": ["上一个问题"],
            },
        }

    def test_from_session_only_hydrates_snapshot_summary_without_fabricating_trace(self):
        """from_session 只消费 session 中已有摘要，不伪造原始 trace。"""
        session_payload = self._build_session_payload()

        agent = ProjectDeepReviewAgent.from_session(
            session_payload,
            reviewer=StubProjectDeepReviewReviewer(),
        )

        self.assertEqual(agent.session_snapshot.session_id, 12)
        self.assertEqual(agent.session_snapshot.project_id, "owner/repo")
        self.assertEqual(agent.working_memory["open_questions"], ["需要确认 tenant 相关回归范围"])
        self.assertEqual(agent.session_summary["recent_questions"], ["上一个问题"])
        self.assertEqual(agent.project_tools.read_review_log(101)["url"], "https://github.com/owner/repo/pull/17")
        self.assertEqual(agent.project_tools.read_review_trace(101), {})

    def test_answer_runs_two_rounds_and_updates_trace_memory_and_summary(self):
        """answer 先聚合 baseline 摘要，再执行 GitHub 第二轮补充调查。"""
        reviewer = StubProjectDeepReviewReviewer()
        github_tools = StubGitHubDeepReviewTools()
        agent = ProjectDeepReviewAgent.from_session(
            self._build_session_payload(),
            github_tools=github_tools,
            reviewer=reviewer,
        )

        result = agent.answer("最近反复出现的高风险主题是什么？")

        self.assertEqual(result["round_count"], 2)
        self.assertEqual(result["stop_reason"], "round_limit")
        self.assertEqual(result["result_markdown"].splitlines()[0], "项目总体结论")
        self.assertEqual(result["trace"]["round_count"], 2)
        self.assertEqual(result["trace"]["rounds"][0]["source"], "project_tools")
        self.assertEqual(result["trace"]["rounds"][1]["source"], "github_tools")
        self.assertEqual(result["trace"]["tool_outputs"][0]["tool"], "list_project_review_logs")
        self.assertEqual(result["trace"]["tool_outputs"][-1]["tool"], "read_local_import")
        self.assertEqual(result["updated_working_memory"]["hot_modules"][0]["module"], "backend")
        self.assertEqual(result["updated_working_memory"]["repeated_issue_patterns"][0]["title"], "租户鉴权缺失")
        self.assertEqual(result["updated_working_memory"]["last_question"], "最近反复出现的高风险主题是什么？")
        self.assertEqual(result["updated_session_summary"]["question_count"], 3)
        self.assertEqual(result["updated_session_summary"]["last_question"], "最近反复出现的高风险主题是什么？")
        self.assertEqual(reviewer.last_question, "最近反复出现的高风险主题是什么？")
        self.assertIn("第一轮：baseline 摘要线索", reviewer.last_evidence_text)
        self.assertIn("第二轮：GitHub 补充调查", reviewer.last_evidence_text)
        self.assertEqual(
            github_tools.calls,
            [
                ("read_pr_metadata", 17),
                ("read_pr_diff", 17),
                ("read_related_test", "backend/auth.py", "feature/auth-fix"),
                ("read_local_import", "backend/auth.py", "feature/auth-fix"),
            ],
        )
        read_pr_diff_payload = result["trace"]["tool_outputs"][4]["payload"]
        self.assertEqual(read_pr_diff_payload["count"], 2)
        self.assertNotIn("patch", read_pr_diff_payload["files"][0])
        read_related_test_payload = result["trace"]["tool_outputs"][5]["payload"]
        self.assertEqual(read_related_test_payload["files"][0]["path"], "tests/backend/test_auth.py")
        self.assertNotIn("content", read_related_test_payload["files"][0])

    def test_answer_keeps_working_memory_compact_across_repeated_questions(self):
        """重复问答不会无限堆叠相同 finding，也不会让摘要无限增长。"""
        reviewer = StubProjectDeepReviewReviewer()
        github_tools = StubGitHubDeepReviewTools()
        agent = ProjectDeepReviewAgent.from_session(
            self._build_session_payload(),
            github_tools=github_tools,
            reviewer=reviewer,
        )

        first_result = agent.answer("最近反复出现的高风险主题是什么？")
        second_result = agent.answer("最近反复出现的高风险主题是什么？")

        self.assertEqual(len(first_result["updated_working_memory"]["confirmed_findings"]), 3)
        self.assertEqual(len(second_result["updated_working_memory"]["confirmed_findings"]), 3)
        self.assertEqual(second_result["updated_session_summary"]["question_count"], 4)

    @patch("biz.utils.code_reviewer.Factory")
    def test_project_reviewer_uses_project_prompt_profile_and_chinese_contract(self, factory_cls):
        """项目级 reviewer 应走 project mode，并使用中文输出契约。"""
        factory_cls.return_value.getClient.return_value.completions.return_value = "项目总体结论\n总分: 84分"

        reviewer = ProjectDeepReviewReviewer(review_profile="security_review", repo_full_name="owner/repo")
        reviewer.review_project("最近权限风险如何？", "这里是项目级证据")

        messages = factory_cls.return_value.getClient.return_value.completions.call_args.kwargs["messages"]
        system_prompt = messages[0]["content"]
        user_prompt = messages[1]["content"]

        self.assertEqual(reviewer.review_mode_name, "project_deep_review")
        self.assertEqual(reviewer.profile.prompt_template_id, "project_deep_review_prompt")
        self.assertIn("项目总体结论", system_prompt)
        self.assertIn("阶段性高风险主题", system_prompt)
        self.assertIn("安全与数据风险控制", system_prompt)
        self.assertIn("输出契约", user_prompt)
        self.assertIn("最近权限风险如何？", user_prompt)

    @patch("biz.utils.code_reviewer.truncate_text_by_tokens", return_value="trimmed evidence")
    @patch("biz.utils.code_reviewer.count_tokens")
    @patch("biz.utils.code_reviewer.Factory")
    def test_project_reviewer_truncates_long_evidence(self, factory_cls, count_tokens, truncate_text_by_tokens):
        """项目级 reviewer 也要有 token 预算保护。"""
        factory_cls.return_value.getClient.return_value.completions.return_value = "项目总体结论\n总分: 84分"
        count_tokens.side_effect = [10, 10, 999999, 10, 10]

        reviewer = ProjectDeepReviewReviewer(review_profile="security_review", repo_full_name="owner/repo")
        reviewer.review_project("最近权限风险如何？", "这里是一个很长很长的项目级证据")

        messages = factory_cls.return_value.getClient.return_value.completions.call_args.kwargs["messages"]
        self.assertIn("trimmed evidence", messages[1]["content"])
        truncate_text_by_tokens.assert_called_once()


if __name__ == "__main__":
    main()
