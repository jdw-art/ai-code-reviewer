import json
import os
import sqlite3
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

            with closing(sqlite3.connect(DeepReviewService.DB_FILE)) as conn:
                cursor = conn.cursor()
                cursor.execute(
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
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS project_deep_review_message (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id INTEGER NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS project_deep_review_run (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id INTEGER NOT NULL,
                        user_message_id INTEGER NOT NULL,
                        profile_name TEXT NOT NULL,
                        round_count INTEGER NOT NULL,
                        stop_reason TEXT NOT NULL,
                        result_markdown TEXT NOT NULL,
                        trace_json TEXT NOT NULL,
                        created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_project_deep_review_session_project_id
                    ON project_deep_review_session (project_id, created_at DESC)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_project_deep_review_message_session_id
                    ON project_deep_review_message (session_id, created_at DESC)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_project_deep_review_run_session_id
                    ON project_deep_review_run (session_id, created_at DESC)
                    """
                )
                conn.commit()
        except sqlite3.DatabaseError as e:
            print(f"Deep review database initialization failed: {e}")

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
        with closing(sqlite3.connect(DeepReviewService.DB_FILE)) as conn:
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
    def list_sessions(project_id: str) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(DeepReviewService.DB_FILE)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
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
    def append_message(session_id: int, role: str, content: str) -> int:
        entity = ProjectDeepReviewMessageEntity(session_id=session_id, role=role, content=content)
        with closing(sqlite3.connect(DeepReviewService.DB_FILE)) as conn:
            cursor = conn.cursor()
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
        with closing(sqlite3.connect(DeepReviewService.DB_FILE)) as conn:
            cursor = conn.cursor()
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
        with closing(sqlite3.connect(DeepReviewService.DB_FILE)) as conn:
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
    def _touch_session(conn: sqlite3.Connection, session_id: int):
        conn.execute(
            """
            UPDATE project_deep_review_session
            SET updated_at = strftime('%s', 'now')
            WHERE id = ?
            """,
            (session_id,),
        )


DeepReviewService.init_db()
