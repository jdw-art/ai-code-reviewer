import importlib
import os
import sys
import tempfile
from unittest import TestCase, main


class StubProjectDeepReviewAgent:
    """用于隔离服务层持久化行为的假 Agent。"""

    last_session = None

    def __init__(self, session):
        self.session = session

    @classmethod
    def from_session(cls, session):
        cls.last_session = session
        return cls(session)

    def answer(self, question: str) -> dict:
        return {
            "result_markdown": "项目总体结论\n总分: 75分",
            "round_count": 2,
            "stop_reason": "round_limit",
            "trace": {"rounds": [], "round_count": 2},
            "updated_working_memory": {"latest_risk_themes": [{"title": "鉴权缺失", "count": 2}]},
            "updated_session_summary": {
                "question_count": 1,
                "last_question": question,
                "answered_topics": [question],
            },
        }


class StubReviewService:
    """用于返回原始 baseline review rows 的假查询层。"""

    @staticmethod
    def get_mr_review_rows_by_ids(review_log_ids: list[int]) -> list[dict]:
        return [
            {
                "id": review_log_ids[0],
                "project_id": "owner/repo",
                "project_name": "repo",
                "score": 72,
                "risk_level": "high",
                "review_profile": "security_review",
                "review_result": "已确认问题\n- 鉴权缺失\n\n风险等级\nhigh\n\n总分: 72分",
                "agent_trace": '{"mode":"context_investigation","investigated_files":[]}',
                "url": "https://github.com/owner/repo/pull/17",
            }
        ]


class FailingProjectDeepReviewAgent:
    """用于验证提问失败时不会留下半成品消息。"""

    @classmethod
    def from_session(cls, session):
        return cls()

    def answer(self, question: str) -> dict:
        raise RuntimeError("llm failed")


class TestDeepReviewServiceRuns(TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        self.original_review_db_file = os.environ.get("REVIEW_DB_FILE")
        self.module_name = "biz.service.deep_review_service"
        self.original_service_module = sys.modules.pop(self.module_name, None)
        self.service_package = importlib.import_module("biz.service")
        self.had_service_attr = hasattr(self.service_package, "deep_review_service")
        self.original_service_attr = getattr(self.service_package, "deep_review_service", None)
        if self.had_service_attr:
            delattr(self.service_package, "deep_review_service")

        os.environ["REVIEW_DB_FILE"] = self.tmp.name
        self.service_module = importlib.import_module(self.module_name)
        self.DeepReviewService = self.service_module.DeepReviewService

    def tearDown(self):
        sys.modules.pop(self.module_name, None)
        if self.original_service_module is not None:
            sys.modules[self.module_name] = self.original_service_module
        if self.had_service_attr:
            setattr(self.service_package, "deep_review_service", self.original_service_attr)
        elif hasattr(self.service_package, "deep_review_service"):
            delattr(self.service_package, "deep_review_service")

        if self.original_review_db_file is None:
            os.environ.pop("REVIEW_DB_FILE", None)
        else:
            os.environ["REVIEW_DB_FILE"] = self.original_review_db_file
        os.unlink(self.tmp.name)

    def test_create_session_from_review_rows_builds_snapshot_and_review_ids(self):
        review_rows = [
            {
                "id": 17,
                "project_id": "owner/repo",
                "project_name": "repo",
                "score": 72,
                "risk_level": "high",
                "review_profile": "security_review",
                "review_result": "已确认问题\n- 鉴权缺失\n\n风险等级\nhigh\n\n总分: 72分",
                "agent_trace": '{"investigated_files":[{"path":"backend/auth.py","reason":"Read changed file context.","truncated":false}]}',
                "url": "https://github.com/owner/repo/pull/17",
            }
        ]

        session_id = self.DeepReviewService.create_session_from_review_rows(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            profile_name="security_review",
            time_range_start=100,
            time_range_end=200,
            review_rows=review_rows,
            created_by="tester",
        )

        session = self.DeepReviewService.get_session(session_id)

        self.assertEqual(session["included_review_log_ids"], [17])
        self.assertEqual(session["baseline_snapshot"]["review_count"], 1)
        self.assertEqual(session["baseline_snapshot"]["baseline_reviews"][0]["id"], 17)
        self.assertEqual(
            session["session_summary"]["display_time_range"],
            {"start_date": "1970-01-01", "end_date": "1970-01-01"},
        )

    def test_ask_session_question_persists_messages_run_and_session_state(self):
        session_id = self.DeepReviewService.create_session_from_review_rows(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            profile_name="security_review",
            time_range_start=100,
            time_range_end=200,
            review_rows=StubReviewService.get_mr_review_rows_by_ids([17]),
            created_by="tester",
        )
        self.service_module.ProjectDeepReviewAgent = StubProjectDeepReviewAgent
        self.service_module.ReviewService = StubReviewService

        result = self.DeepReviewService.ask_session_question(session_id, "最近有哪些高风险主题？")

        self.assertEqual(result["round_count"], 2)
        self.assertEqual(result["stop_reason"], "round_limit")
        messages = self.DeepReviewService.list_messages(session_id)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "最近有哪些高风险主题？")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["content"], "项目总体结论\n总分: 75分")
        session = self.DeepReviewService.get_session(session_id)
        self.assertEqual(session["session_summary"]["last_question"], "最近有哪些高风险主题？")
        self.assertIn("display_time_range", session["session_summary"])
        self.assertEqual(session["working_memory"]["latest_risk_themes"][0]["title"], "鉴权缺失")
        run = self.DeepReviewService.get_run(1)
        self.assertEqual(run["result_markdown"], "项目总体结论\n总分: 75分")
        self.assertEqual(run["round_count"], 2)
        self.assertEqual(StubProjectDeepReviewAgent.last_session["review_rows"][0]["id"], 17)

    def test_ask_session_question_rolls_back_user_message_when_agent_fails(self):
        session_id = self.DeepReviewService.create_session(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            profile_name="security_review",
            time_range_start=100,
            time_range_end=200,
            included_review_log_ids=[17],
            baseline_snapshot={"review_count": 1, "baseline_reviews": []},
            created_by="tester",
        )
        self.service_module.ProjectDeepReviewAgent = FailingProjectDeepReviewAgent
        self.service_module.ReviewService = StubReviewService

        with self.assertRaisesRegex(RuntimeError, "llm failed"):
            self.DeepReviewService.ask_session_question(session_id, "这次会失败吗？")

        self.assertEqual(self.DeepReviewService.list_messages(session_id), [])
        self.assertIsNone(self.DeepReviewService.get_latest_run(session_id))


if __name__ == "__main__":
    main()
