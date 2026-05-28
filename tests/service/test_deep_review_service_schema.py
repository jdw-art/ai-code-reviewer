import importlib
import os
import sqlite3
import sys
import tempfile
from unittest.mock import patch
from unittest import TestCase, main


class TestDeepReviewServiceSchema(TestCase):
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

    def _execute_sql(self, statements):
        with sqlite3.connect(self.tmp.name) as conn:
            cursor = conn.cursor()
            for statement in statements:
                cursor.execute(statement)
            conn.commit()

    def _fetch_rows(self, query):
        with sqlite3.connect(self.tmp.name) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(query).fetchall()

    def test_create_session_afterwards_can_list_it_by_project_id(self):
        session_id = self.DeepReviewService.create_session(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            profile_name="default_review",
            time_range_start=100,
            time_range_end=200,
            included_review_log_ids=[1, 2],
            baseline_snapshot={"review_count": 2, "themes": ["security"]},
            created_by="tester",
        )

        sessions = self.DeepReviewService.list_sessions(project_id="owner/repo")

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["id"], session_id)
        self.assertEqual(sessions[0]["project_id"], "owner/repo")
        self.assertEqual(sessions[0]["included_review_log_ids"], [1, 2])
        self.assertEqual(sessions[0]["baseline_snapshot"], {"review_count": 2, "themes": ["security"]})
        self.assertEqual(sessions[0]["working_memory"], {})
        self.assertEqual(sessions[0]["session_summary"], {})

    def test_list_sessions_without_project_id_returns_all_sessions(self):
        """不传 project_id 时应返回全部历史会话，供 Dashboard 聚合项目入口。"""
        session_id_a = self.DeepReviewService.create_session(
            platform="github",
            project_id="owner/repo-a",
            project_name="repo-a",
            profile_name="default_review",
            time_range_start=100,
            time_range_end=200,
            included_review_log_ids=[1],
            baseline_snapshot={"review_count": 1},
            created_by="tester",
        )
        session_id_b = self.DeepReviewService.create_session(
            platform="github",
            project_id="owner/repo-b",
            project_name="repo-b",
            profile_name="security_review",
            time_range_start=100,
            time_range_end=200,
            included_review_log_ids=[2],
            baseline_snapshot={"review_count": 1},
            created_by="tester",
        )

        sessions = self.DeepReviewService.list_sessions()

        self.assertEqual({item["id"] for item in sessions}, {session_id_a, session_id_b})

    def test_append_message_and_run_afterwards_can_read_back_structured_run(self):
        session_id = self.DeepReviewService.create_session(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            profile_name="default_review",
            time_range_start=100,
            time_range_end=200,
            included_review_log_ids=[1],
            baseline_snapshot={"review_count": 1},
            created_by="tester",
        )

        user_message_id = self.DeepReviewService.append_message(
            session_id=session_id,
            role="user",
            content="最近有哪些高风险主题？",
        )
        run_id = self.DeepReviewService.append_run(
            session_id=session_id,
            user_message_id=user_message_id,
            profile_name="default_review",
            round_count=2,
            stop_reason="round_limit",
            result_markdown="项目总体结论\n总分: 78分",
            trace_json={"rounds": [{"topic": "security"}], "summary": {"score": 78}},
        )

        run = self.DeepReviewService.get_run(run_id)

        self.assertEqual(run["session_id"], session_id)
        self.assertEqual(run["user_message_id"], user_message_id)
        self.assertEqual(run["round_count"], 2)
        self.assertEqual(run["trace_json"], {"rounds": [{"topic": "security"}], "summary": {"score": 78}})

    def test_get_latest_run_returns_newest_run_for_session(self):
        """应按创建时间与自增 id 返回会话最近一次 run。"""
        session_id = self.DeepReviewService.create_session(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            profile_name="default_review",
            time_range_start=100,
            time_range_end=200,
            included_review_log_ids=[1],
            baseline_snapshot={"review_count": 1},
            created_by="tester",
        )

        first_message_id = self.DeepReviewService.append_message(
            session_id=session_id,
            role="user",
            content="第一次问题",
        )
        self.DeepReviewService.append_run(
            session_id=session_id,
            user_message_id=first_message_id,
            profile_name="default_review",
            round_count=1,
            stop_reason="enough_evidence",
            result_markdown="项目总体结论\n总分: 70分",
            trace_json={"rounds": [{"topic": "stability"}]},
        )
        second_message_id = self.DeepReviewService.append_message(
            session_id=session_id,
            role="user",
            content="第二次问题",
        )
        second_run_id = self.DeepReviewService.append_run(
            session_id=session_id,
            user_message_id=second_message_id,
            profile_name="default_review",
            round_count=2,
            stop_reason="round_limit",
            result_markdown="项目总体结论\n总分: 82分",
            trace_json={"rounds": [{"topic": "security"}]},
        )

        latest_run = self.DeepReviewService.get_latest_run(session_id)

        self.assertEqual(latest_run["id"], second_run_id)
        self.assertEqual(latest_run["round_count"], 2)
        self.assertEqual(latest_run["result_markdown"], "项目总体结论\n总分: 82分")

    def test_get_latest_run_returns_none_when_session_has_no_runs(self):
        session_id = self.DeepReviewService.create_session(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            profile_name="default_review",
            time_range_start=100,
            time_range_end=200,
            included_review_log_ids=[1],
            baseline_snapshot={"review_count": 1},
            created_by="tester",
        )

        self.assertIsNone(self.DeepReviewService.get_latest_run(session_id))

    def test_append_message_rejects_missing_session_id(self):
        with self.assertRaisesRegex(ValueError, "session_id=999 不存在"):
            self.DeepReviewService.append_message(
                session_id=999,
                role="user",
                content="最近有哪些高风险主题？",
            )

    def test_append_run_rejects_missing_session_id(self):
        session_id = self.DeepReviewService.create_session(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            profile_name="default_review",
            time_range_start=100,
            time_range_end=200,
            included_review_log_ids=[1],
            baseline_snapshot={"review_count": 1},
            created_by="tester",
        )
        user_message_id = self.DeepReviewService.append_message(
            session_id=session_id,
            role="user",
            content="最近有哪些高风险主题？",
        )

        with self.assertRaisesRegex(ValueError, "session_id=999 不存在"):
            self.DeepReviewService.append_run(
                session_id=999,
                user_message_id=user_message_id,
                profile_name="default_review",
                round_count=1,
                stop_reason="invalid",
                result_markdown="结果",
                trace_json={"rounds": []},
            )

    def test_append_run_rejects_missing_user_message_id(self):
        session_id = self.DeepReviewService.create_session(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            profile_name="default_review",
            time_range_start=100,
            time_range_end=200,
            included_review_log_ids=[1],
            baseline_snapshot={"review_count": 1},
            created_by="tester",
        )

        with self.assertRaisesRegex(ValueError, "user_message_id=999 不存在"):
            self.DeepReviewService.append_run(
                session_id=session_id,
                user_message_id=999,
                profile_name="default_review",
                round_count=1,
                stop_reason="invalid",
                result_markdown="结果",
                trace_json={"rounds": []},
            )

    def test_append_run_rejects_user_message_from_other_session(self):
        session_id_a = self.DeepReviewService.create_session(
            platform="github",
            project_id="owner/repo-a",
            project_name="repo-a",
            profile_name="default_review",
            time_range_start=100,
            time_range_end=200,
            included_review_log_ids=[1],
            baseline_snapshot={"review_count": 1},
            created_by="tester",
        )
        session_id_b = self.DeepReviewService.create_session(
            platform="github",
            project_id="owner/repo-b",
            project_name="repo-b",
            profile_name="default_review",
            time_range_start=100,
            time_range_end=200,
            included_review_log_ids=[2],
            baseline_snapshot={"review_count": 1},
            created_by="tester",
        )
        user_message_id = self.DeepReviewService.append_message(
            session_id=session_id_b,
            role="user",
            content="B 会话的问题",
        )

        with self.assertRaisesRegex(
            ValueError,
            f"user_message_id={user_message_id} 不属于 session_id={session_id_a}",
        ):
            self.DeepReviewService.append_run(
                session_id=session_id_a,
                user_message_id=user_message_id,
                profile_name="default_review",
                round_count=1,
                stop_reason="invalid",
                result_markdown="结果",
                trace_json={"rounds": []},
            )

    def test_init_db_raises_runtime_error_when_connect_fails(self):
        with patch.object(
            self.service_module.sqlite3,
            "connect",
            side_effect=sqlite3.DatabaseError("boom"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Deep review database initialization failed"):
                self.DeepReviewService.init_db()

    def test_init_db_keeps_clean_legacy_message_and_run_rows(self):
        self._execute_sql([
            "DROP TABLE IF EXISTS project_deep_review_run",
            "DROP TABLE IF EXISTS project_deep_review_message",
            """
            CREATE TABLE project_deep_review_message (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE project_deep_review_run (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                user_message_id INTEGER NOT NULL,
                profile_name TEXT NOT NULL,
                round_count INTEGER NOT NULL,
                stop_reason TEXT NOT NULL,
                result_markdown TEXT NOT NULL,
                trace_json TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """,
        ])
        session_id = self.DeepReviewService.create_session(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            profile_name="default_review",
            time_range_start=100,
            time_range_end=200,
            included_review_log_ids=[1],
            baseline_snapshot={"review_count": 1},
            created_by="tester",
        )
        self._execute_sql([
            f"""
            INSERT INTO project_deep_review_message (id, session_id, role, content, created_at)
            VALUES (11, {session_id}, 'user', '合法消息', 1)
            """,
            f"""
            INSERT INTO project_deep_review_run (
                id, session_id, user_message_id, profile_name, round_count,
                stop_reason, result_markdown, trace_json, created_at
            ) VALUES (
                21, {session_id}, 11, 'default_review', 1,
                'done', '结果', '{{"rounds": []}}', 1
            )
            """,
        ])

        self.DeepReviewService.init_db()

        message_rows = self._fetch_rows("SELECT id, session_id, content FROM project_deep_review_message ORDER BY id")
        run_rows = self._fetch_rows("SELECT id, session_id, user_message_id FROM project_deep_review_run ORDER BY id")
        self.assertEqual([(row["id"], row["session_id"], row["content"]) for row in message_rows], [(11, session_id, "合法消息")])
        self.assertEqual([(row["id"], row["session_id"], row["user_message_id"]) for row in run_rows], [(21, session_id, 11)])

    def test_init_db_drops_dirty_legacy_message_and_run_rows(self):
        self._execute_sql([
            "DROP TABLE IF EXISTS project_deep_review_run",
            "DROP TABLE IF EXISTS project_deep_review_message",
            """
            CREATE TABLE project_deep_review_message (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE project_deep_review_run (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                user_message_id INTEGER NOT NULL,
                profile_name TEXT NOT NULL,
                round_count INTEGER NOT NULL,
                stop_reason TEXT NOT NULL,
                result_markdown TEXT NOT NULL,
                trace_json TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """,
        ])
        session_id_a = self.DeepReviewService.create_session(
            platform="github",
            project_id="owner/repo-a",
            project_name="repo-a",
            profile_name="default_review",
            time_range_start=100,
            time_range_end=200,
            included_review_log_ids=[1],
            baseline_snapshot={"review_count": 1},
            created_by="tester",
        )
        session_id_b = self.DeepReviewService.create_session(
            platform="github",
            project_id="owner/repo-b",
            project_name="repo-b",
            profile_name="default_review",
            time_range_start=100,
            time_range_end=200,
            included_review_log_ids=[2],
            baseline_snapshot={"review_count": 1},
            created_by="tester",
        )
        self._execute_sql([
            f"""
            INSERT INTO project_deep_review_message (id, session_id, role, content, created_at)
            VALUES (11, {session_id_a}, 'user', '合法消息 A', 1)
            """,
            f"""
            INSERT INTO project_deep_review_message (id, session_id, role, content, created_at)
            VALUES (12, {session_id_b}, 'user', '合法消息 B', 1)
            """,
            """
            INSERT INTO project_deep_review_message (id, session_id, role, content, created_at)
            VALUES (13, 999, 'user', '孤儿消息', 1)
            """,
            f"""
            INSERT INTO project_deep_review_run (
                id, session_id, user_message_id, profile_name, round_count,
                stop_reason, result_markdown, trace_json, created_at
            ) VALUES (
                21, {session_id_a}, 11, 'default_review', 1,
                'done', '合法结果', '{{"rounds": []}}', 1
            )
            """,
            """
            INSERT INTO project_deep_review_run (
                id, session_id, user_message_id, profile_name, round_count,
                stop_reason, result_markdown, trace_json, created_at
            ) VALUES (
                22, 999, 11, 'default_review', 1,
                'invalid', '坏结果', '{"rounds": []}', 1
            )
            """,
            """
            INSERT INTO project_deep_review_run (
                id, session_id, user_message_id, profile_name, round_count,
                stop_reason, result_markdown, trace_json, created_at
            ) VALUES (
                23, 1, 999, 'default_review', 1,
                'invalid', '坏结果', '{"rounds": []}', 1
            )
            """,
            f"""
            INSERT INTO project_deep_review_run (
                id, session_id, user_message_id, profile_name, round_count,
                stop_reason, result_markdown, trace_json, created_at
            ) VALUES (
                24, {session_id_a}, 12, 'default_review', 1,
                'invalid', '错配结果', '{{"rounds": []}}', 1
            )
            """,
        ])

        self.DeepReviewService.init_db()

        message_rows = self._fetch_rows("SELECT id, session_id, content FROM project_deep_review_message ORDER BY id")
        run_rows = self._fetch_rows("SELECT id, session_id, user_message_id FROM project_deep_review_run ORDER BY id")
        self.assertEqual(
            [(row["id"], row["session_id"], row["content"]) for row in message_rows],
            [(11, session_id_a, "合法消息 A"), (12, session_id_b, "合法消息 B")],
        )
        self.assertEqual(
            [(row["id"], row["session_id"], row["user_message_id"]) for row in run_rows],
            [(21, session_id_a, 11)],
        )


if __name__ == "__main__":
    main()
