import datetime as dt
import re


def build_project_options(rows: list[dict]) -> list[tuple[str, str]]:
    """构建去重且排序后的项目下拉选项。"""
    seen: dict[str, str] = {}
    for row in rows:
        project_id = str(row.get("project_id") or "").strip()
        if not project_id or project_id in seen:
            continue
        project_name = str(row.get("project_name") or project_id).strip()
        seen[project_id] = f"{project_name}（{project_id}）"
    return sorted(seen.items(), key=lambda item: item[0])


def format_session_label(session: dict) -> str:
    """格式化 Deep Review 会话展示文案。"""
    display_range = (session.get("session_summary") or {}).get("display_time_range") or {}
    start_text = display_range.get("start_date") or dt.datetime.fromtimestamp(
        session["time_range_start"],
        dt.timezone.utc,
    ).strftime("%Y-%m-%d")
    end_text = display_range.get("end_date") or dt.datetime.fromtimestamp(
        session["time_range_end"],
        dt.timezone.utc,
    ).strftime("%Y-%m-%d")
    return (
        f"#{session['id']} | {session['project_name']} | "
        f"{session['profile_name']} | {start_text} ~ {end_text}"
    )


def summarize_run_result(markdown_text: str) -> str:
    """提取首行结论与总分，生成摘要文本。"""
    score_match = re.search(r"总分[:：]\s*(\d+)分?", markdown_text)
    score_text = f"总分 {score_match.group(1)}分" if score_match else "总分未解析"
    first_line = markdown_text.splitlines()[0] if markdown_text else "暂无结论"
    return f"{first_line} | {score_text}"


def filter_rows_by_project(rows: list[dict], project_id: str) -> list[dict]:
    """按项目 id 筛选可用于建会的 baseline review 行。"""
    normalized_project_id = str(project_id or "").strip()
    return [
        row
        for row in rows
        if str(row.get("project_id") or "").strip() == normalized_project_id
    ]


def build_project_source_options(
    review_rows: list[dict],
    sessions: list[dict],
) -> list[tuple[str, str]]:
    """合并 baseline rows 与历史 session，确保历史项目可继续访问。"""
    return build_project_options(
        list(review_rows) + [
            {
                "project_id": session.get("project_id"),
                "project_name": session.get("project_name"),
            }
            for session in sessions
        ]
    )


def build_session_options(sessions: list[dict]) -> list[tuple[int, str]]:
    """把会话列表转换为下拉框可用的选项。"""
    return [
        (int(session["id"]), format_session_label(session))
        for session in sessions
    ]


def build_message_timeline(messages: list[dict]) -> list[dict]:
    """提取消息时间线需要的最小字段。"""
    return [
        {
            "role": message["role"],
            "content": message["content"],
        }
        for message in messages
    ]
