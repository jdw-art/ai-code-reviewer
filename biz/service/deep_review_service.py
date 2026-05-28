import json
import os
import sqlite3
import datetime
from contextlib import closing
from typing import Any

from biz.entity.deep_review_entity import (
    ProjectDeepReviewMessageEntity,
    ProjectDeepReviewRunEntity,
    ProjectDeepReviewSessionEntity,
)


class DeepReviewService:
    DB_FILE = os.getenv("REVIEW_DB_FILE", "data/data.db")

    @staticmethod
    def init_db():
        """初始化 Deep Review 所需的数据库表。"""
        try:
            db_dir = os.path.dirname(DeepReviewService.DB_FILE)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

            with closing(DeepReviewService._connect()) as conn:
                DeepReviewService._ensure_session_table(conn)
                DeepReviewService._ensure_message_table(conn)
                DeepReviewService._ensure_run_table(conn)
                DeepReviewService._ensure_indexes(conn)
                conn.commit()
        except (OSError, sqlite3.DatabaseError) as e:
            raise RuntimeError("Deep review database initialization failed") from e

    @staticmethod
    def create_session(
        platform: str,
        project_id: str,
        project_name: str,
        profile_name: str,
        time_range_start: int,
        time_range_end: int,
        included_review_log_ids: list[int],
        baseline_snapshot: dict[str, Any],
        created_by: str,
        working_memory: dict[str, Any] | None = None,
        session_summary: dict[str, Any] | None = None,
        status: str = "active",
    ) -> int:
        entity = ProjectDeepReviewSessionEntity(
            platform=platform,
            project_id=project_id,
            project_name=project_name,
            profile_name=profile_name,
            time_range_start=time_range_start,
            time_range_end=time_range_end,
            included_review_log_ids=included_review_log_ids,
            baseline_snapshot=baseline_snapshot,
            created_by=created_by,
            working_memory=working_memory or {},
            session_summary=session_summary or {},
            status=status,
        )
        with closing(DeepReviewService._connect()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO project_deep_review_session (
                    platform, project_id, project_name, profile_name,
                    time_range_start, time_range_end, included_review_log_ids,
                    baseline_snapshot, working_memory, session_summary, status,
                    created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity.platform,
                    entity.project_id,
                    entity.project_name,
                    entity.profile_name,
                    entity.time_range_start,
                    entity.time_range_end,
                    DeepReviewService._dump_json(entity.included_review_log_ids),
                    DeepReviewService._dump_json(entity.baseline_snapshot),
                    DeepReviewService._dump_json(entity.working_memory),
                    DeepReviewService._dump_json(entity.session_summary),
                    entity.status,
                    entity.created_by,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def list_sessions(project_id: str | None = None) -> list[dict[str, Any]]:
        with closing(DeepReviewService._connect()) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if project_id is None:
                cursor.execute(
                    """
                    SELECT *
                    FROM project_deep_review_session
                    ORDER BY created_at DESC, id DESC
                    """
                )
            else:
                cursor.execute(
                    """
                    SELECT *
                    FROM project_deep_review_session
                    WHERE project_id = ?
                    ORDER BY created_at DESC, id DESC
                    """,
                    (project_id,),
                )
            rows = cursor.fetchall()
            return [DeepReviewService._session_row_to_dict(row) for row in rows]

    @staticmethod
    def get_session(session_id: int) -> dict[str, Any] | None:
        """按会话 id 读取结构化会话对象。"""
        with closing(DeepReviewService._connect()) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT *
                FROM project_deep_review_session
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return DeepReviewService._session_row_to_dict(row)

    @staticmethod
    def create_session_from_review_rows(
        platform: str,
        project_id: str,
        project_name: str,
        profile_name: str,
        time_range_start: int,
        time_range_end: int,
        review_rows: list[dict[str, Any]],
        created_by: str,
    ) -> int:
        """根据 baseline review rows 构建快照并创建会话。"""
        from biz.agent.deep_review.project_snapshot import build_project_snapshot

        normalized_rows = review_rows or []
        snapshot = build_project_snapshot(normalized_rows)
        return DeepReviewService.create_session(
            platform=platform,
            project_id=project_id,
            project_name=project_name,
            profile_name=profile_name,
            time_range_start=time_range_start,
            time_range_end=time_range_end,
            included_review_log_ids=[
                int(row.get("id", 0))
                for row in normalized_rows
                if row.get("id") is not None
            ],
            baseline_snapshot=snapshot,
            created_by=created_by,
            session_summary={
                "display_time_range": {
                    "start_date": DeepReviewService._format_display_date(time_range_start),
                    "end_date": DeepReviewService._format_display_date(time_range_end),
                }
            },
        )

    @staticmethod
    def append_message(session_id: int, role: str, content: str) -> int:
        entity = ProjectDeepReviewMessageEntity(session_id=session_id, role=role, content=content)
        with closing(DeepReviewService._connect()) as conn:
            cursor = conn.cursor()
            DeepReviewService._require_session_exists(conn=conn, session_id=session_id)
            cursor.execute(
                """
                INSERT INTO project_deep_review_message (session_id, role, content)
                VALUES (?, ?, ?)
                """,
                (entity.session_id, entity.role, entity.content),
            )
            message_id = cursor.lastrowid
            DeepReviewService._touch_session(conn=conn, session_id=session_id)
            conn.commit()
            return message_id

    @staticmethod
    def list_messages(session_id: int) -> list[dict[str, Any]]:
        """按时间顺序读取会话消息。"""
        with closing(DeepReviewService._connect()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT *
                FROM project_deep_review_message
                WHERE session_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (session_id,),
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "role": row["role"],
                    "content": row["content"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    @staticmethod
    def append_run(
        session_id: int,
        user_message_id: int,
        profile_name: str,
        round_count: int,
        stop_reason: str,
        result_markdown: str,
        trace_json: dict[str, Any],
    ) -> int:
        entity = ProjectDeepReviewRunEntity(
            session_id=session_id,
            user_message_id=user_message_id,
            profile_name=profile_name,
            round_count=round_count,
            stop_reason=stop_reason,
            result_markdown=result_markdown,
            trace_json=trace_json,
        )
        with closing(DeepReviewService._connect()) as conn:
            cursor = conn.cursor()
            DeepReviewService._require_session_exists(conn=conn, session_id=session_id)
            DeepReviewService._require_user_message_belongs_to_session(
                conn=conn,
                session_id=session_id,
                user_message_id=user_message_id,
            )
            cursor.execute(
                """
                INSERT INTO project_deep_review_run (
                    session_id, user_message_id, profile_name, round_count,
                    stop_reason, result_markdown, trace_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity.session_id,
                    entity.user_message_id,
                    entity.profile_name,
                    entity.round_count,
                    entity.stop_reason,
                    entity.result_markdown,
                    DeepReviewService._dump_json(entity.trace_json),
                ),
            )
            run_id = cursor.lastrowid
            DeepReviewService._touch_session(conn=conn, session_id=session_id)
            conn.commit()
            return run_id

    @staticmethod
    def get_run(run_id: int) -> dict[str, Any] | None:
        with closing(DeepReviewService._connect()) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT *
                FROM project_deep_review_run
                WHERE id = ?
                """,
                (run_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return DeepReviewService._run_row_to_dict(row)

    @staticmethod
    def get_latest_run(session_id: int) -> dict[str, Any] | None:
        """读取会话最近一次执行记录，供 Dashboard 展示摘要。"""
        with closing(DeepReviewService._connect()) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT *
                FROM project_deep_review_run
                WHERE session_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return DeepReviewService._run_row_to_dict(row)

    @staticmethod
    def update_session_state(
        session_id: int,
        working_memory: dict[str, Any] | None = None,
        session_summary: dict[str, Any] | None = None,
    ):
        """更新会话工作记忆与摘要，并刷新更新时间。"""
        current_session = DeepReviewService.get_session(session_id)
        if current_session is None:
            raise ValueError(f"session_id={session_id} 不存在")

        next_working_memory = current_session["working_memory"] if working_memory is None else working_memory
        next_session_summary = current_session["session_summary"] if session_summary is None else session_summary

        with closing(DeepReviewService._connect()) as conn:
            conn.execute(
                """
                UPDATE project_deep_review_session
                SET working_memory = ?, session_summary = ?, updated_at = strftime('%s', 'now')
                WHERE id = ?
                """,
                (
                    DeepReviewService._dump_json(next_working_memory),
                    DeepReviewService._dump_json(next_session_summary),
                    session_id,
                ),
            )
            conn.commit()

    @staticmethod
    def ask_session_question(session_id: int, question: str) -> dict[str, Any]:
        """围绕已持久化会话执行一次提问、回放和状态更新。"""
        agent_cls = globals().get("ProjectDeepReviewAgent")
        if agent_cls is None:
            from biz.agent.deep_review.agent import ProjectDeepReviewAgent as agent_cls

        review_service_cls = globals().get("ReviewService")
        if review_service_cls is None:
            from biz.service.review_service import ReviewService as review_service_cls
        from biz.agent.deep_review.tools.project_review_log_tools import ProjectReviewLogTools

        session = DeepReviewService.get_session(session_id)
        if session is None:
            raise ValueError(f"session_id={session_id} 不存在")
        review_rows = review_service_cls.get_mr_review_rows_by_ids(session.get("included_review_log_ids", []))
        session_payload = {**session, "review_rows": review_rows}
        project_tools = ProjectReviewLogTools(review_rows) if review_rows else None

        # 兼容测试替身与真实 Agent：真实 Agent 优先吃原始 rows，替身只保留最小签名。
        if project_tools is None:
            agent = agent_cls.from_session(session_payload)
        else:
            try:
                agent = agent_cls.from_session(session_payload, project_tools=project_tools)
            except TypeError:
                agent = agent_cls.from_session(session_payload)

        result = agent.answer(question)
        result_markdown = result.get("result_markdown", "")
        round_count = int(result.get("round_count", 0))
        stop_reason = result.get("stop_reason", "")
        trace_json = result.get("trace") or {}
        updated_working_memory = result.get("updated_working_memory")
        updated_session_summary = result.get("updated_session_summary")

        user_message_id = DeepReviewService.append_message(session_id, "user", question)
        DeepReviewService.append_message(session_id, "assistant", result_markdown)
        run_id = DeepReviewService.append_run(
            session_id=session_id,
            user_message_id=user_message_id,
            profile_name=session["profile_name"],
            round_count=round_count,
            stop_reason=stop_reason,
            result_markdown=result_markdown,
            trace_json=trace_json,
        )
        DeepReviewService.update_session_state(
            session_id=session_id,
            working_memory=updated_working_memory,
            session_summary=DeepReviewService._merge_session_summary(
                session.get("session_summary") or {},
                updated_session_summary or {},
            ),
        )
        return {**result, "run_id": run_id}

    @staticmethod
    def _dump_json(value: dict[str, Any] | list[Any]) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _load_json(value: str) -> dict[str, Any] | list[Any]:
        return json.loads(value)

    @staticmethod
    def _session_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "platform": row["platform"],
            "project_id": row["project_id"],
            "project_name": row["project_name"],
            "profile_name": row["profile_name"],
            "time_range_start": row["time_range_start"],
            "time_range_end": row["time_range_end"],
            "included_review_log_ids": DeepReviewService._load_json(row["included_review_log_ids"]),
            "baseline_snapshot": DeepReviewService._load_json(row["baseline_snapshot"]),
            "working_memory": DeepReviewService._load_json(row["working_memory"]),
            "session_summary": DeepReviewService._load_json(row["session_summary"]),
            "status": row["status"],
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _run_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "user_message_id": row["user_message_id"],
            "profile_name": row["profile_name"],
            "round_count": row["round_count"],
            "stop_reason": row["stop_reason"],
            "result_markdown": row["result_markdown"],
            "trace_json": DeepReviewService._load_json(row["trace_json"]),
            "created_at": row["created_at"],
        }

    @staticmethod
    def _merge_session_summary(current_summary: dict[str, Any], next_summary: dict[str, Any]) -> dict[str, Any]:
        merged = dict(current_summary or {})
        merged.update(next_summary or {})
        return merged

    @staticmethod
    def _format_display_date(timestamp: int) -> str:
        """把时间戳回显为与创建时一致的自然日期。"""
        return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")

    @staticmethod
    def _touch_session(conn: sqlite3.Connection, session_id: int):
        conn.execute(
            """
            UPDATE project_deep_review_session
            SET updated_at = strftime('%s', 'now')
            WHERE id = ?
            """,
            (session_id,),
        )

    @staticmethod
    def _connect() -> sqlite3.Connection:
        conn = sqlite3.connect(DeepReviewService.DB_FILE)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def _ensure_session_table(conn: sqlite3.Connection):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_deep_review_session (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                project_id TEXT NOT NULL,
                project_name TEXT NOT NULL,
                profile_name TEXT NOT NULL,
                time_range_start INTEGER NOT NULL,
                time_range_end INTEGER NOT NULL,
                included_review_log_ids TEXT NOT NULL,
                baseline_snapshot TEXT NOT NULL,
                working_memory TEXT NOT NULL,
                session_summary TEXT NOT NULL,
                status TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))
            )
            """
        )

    @staticmethod
    def _ensure_message_table(conn: sqlite3.Connection):
        if not DeepReviewService._table_exists(conn, "project_deep_review_message"):
            conn.execute(DeepReviewService._message_table_sql())
            return
        if DeepReviewService._has_message_foreign_key(conn):
            return
        DeepReviewService._migrate_legacy_message_table(conn)

    @staticmethod
    def _ensure_run_table(conn: sqlite3.Connection):
        if not DeepReviewService._table_exists(conn, "project_deep_review_run"):
            conn.execute(DeepReviewService._run_table_sql())
            return
        if DeepReviewService._has_run_foreign_keys(conn):
            return
        DeepReviewService._migrate_legacy_run_table(conn)

    @staticmethod
    def _ensure_indexes(conn: sqlite3.Connection):
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_project_deep_review_session_project_id
            ON project_deep_review_session (project_id, created_at DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_project_deep_review_message_session_id
            ON project_deep_review_message (session_id, created_at DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_project_deep_review_run_session_id
            ON project_deep_review_run (session_id, created_at DESC)
            """
        )

    @staticmethod
    def _message_table_sql() -> str:
        return """
            CREATE TABLE project_deep_review_message (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                FOREIGN KEY (session_id) REFERENCES project_deep_review_session(id)
            )
        """

    @staticmethod
    def _run_table_sql() -> str:
        return """
            CREATE TABLE project_deep_review_run (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                user_message_id INTEGER NOT NULL,
                profile_name TEXT NOT NULL,
                round_count INTEGER NOT NULL,
                stop_reason TEXT NOT NULL,
                result_markdown TEXT NOT NULL,
                trace_json TEXT NOT NULL,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                FOREIGN KEY (session_id) REFERENCES project_deep_review_session(id),
                FOREIGN KEY (user_message_id) REFERENCES project_deep_review_message(id)
            )
        """

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        row = conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _has_message_foreign_key(conn: sqlite3.Connection) -> bool:
        rows = conn.execute("PRAGMA foreign_key_list(project_deep_review_message)").fetchall()
        return any(row[2] == "project_deep_review_session" and row[3] == "session_id" and row[4] == "id" for row in rows)

    @staticmethod
    def _has_run_foreign_keys(conn: sqlite3.Connection) -> bool:
        rows = conn.execute("PRAGMA foreign_key_list(project_deep_review_run)").fetchall()
        has_session_fk = any(
            row[2] == "project_deep_review_session" and row[3] == "session_id" and row[4] == "id"
            for row in rows
        )
        has_message_fk = any(
            row[2] == "project_deep_review_message" and row[3] == "user_message_id" and row[4] == "id"
            for row in rows
        )
        return has_session_fk and has_message_fk

    @staticmethod
    def _migrate_legacy_message_table(conn: sqlite3.Connection):
        old_table_name = "project_deep_review_message_old"
        conn.execute("ALTER TABLE project_deep_review_message RENAME TO project_deep_review_message_old")
        conn.execute(DeepReviewService._message_table_sql())
        conn.execute(
            f"""
            INSERT INTO project_deep_review_message (id, session_id, role, content, created_at)
            SELECT legacy.id, legacy.session_id, legacy.role, legacy.content, legacy.created_at
            FROM {old_table_name} AS legacy
            INNER JOIN project_deep_review_session AS session
                ON session.id = legacy.session_id
            """
        )
        conn.execute(f"DROP TABLE {old_table_name}")

    @staticmethod
    def _migrate_legacy_run_table(conn: sqlite3.Connection):
        old_table_name = "project_deep_review_run_old"
        conn.execute("ALTER TABLE project_deep_review_run RENAME TO project_deep_review_run_old")
        conn.execute(DeepReviewService._run_table_sql())
        conn.execute(
            f"""
            INSERT INTO project_deep_review_run (
                id, session_id, user_message_id, profile_name, round_count,
                stop_reason, result_markdown, trace_json, created_at
            )
            SELECT legacy.id,
                   legacy.session_id,
                   legacy.user_message_id,
                   legacy.profile_name,
                   legacy.round_count,
                   legacy.stop_reason,
                   legacy.result_markdown,
                   legacy.trace_json,
                   legacy.created_at
            FROM {old_table_name} AS legacy
            INNER JOIN project_deep_review_session AS session
                ON session.id = legacy.session_id
            INNER JOIN project_deep_review_message AS message
                ON message.id = legacy.user_message_id
               AND message.session_id = legacy.session_id
            """
        )
        conn.execute(f"DROP TABLE {old_table_name}")

    @staticmethod
    def _require_session_exists(conn: sqlite3.Connection, session_id: int):
        row = conn.execute(
            """
            SELECT 1
            FROM project_deep_review_session
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"session_id={session_id} 不存在")

    @staticmethod
    def _require_user_message_belongs_to_session(
        conn: sqlite3.Connection,
        session_id: int,
        user_message_id: int,
    ):
        row = conn.execute(
            """
            SELECT session_id
            FROM project_deep_review_message
            WHERE id = ?
            """,
            (user_message_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"user_message_id={user_message_id} 不存在")
        if row[0] != session_id:
            raise ValueError(f"user_message_id={user_message_id} 不属于 session_id={session_id}")


DeepReviewService.init_db()
