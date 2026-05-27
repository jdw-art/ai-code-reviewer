# Project Deep Review 后端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现项目级 `Project Deep Review` 会话后端，使系统能够围绕一个项目在一段时间内的多条 baseline review 日志，执行最多两轮的闭环调查并生成项目级中文报告。

**Architecture:** 在现有 baseline 审查链路之外，新增独立的 `biz/agent/deep_review/` 会话型 Agent 内核与 `DeepReviewService` 数据服务。Deep Review 不直接依赖 PR webhook 实时触发，而是基于已经落库的 baseline 日志构建固定快照、工作记忆和会话摘要，再通过只读 GitHub 工具执行二轮以内的调查闭环。

**Tech Stack:** Python 3.10+, `unittest`, SQLite, 现有 `GitHubFileReader`、GitHub REST API、现有 LLM Factory、`ReviewService` 中的 baseline 日志。

---

## Scope Check

本计划只覆盖第二阶段 `2B Project Deep Review 后端`。它依赖 `2A Baseline 升级` 已经完成以下前置条件：

1. `mr_review_log` 已持久化 `platform / project_id / review_mode / review_profile / risk_level`。
2. baseline 评论已经稳定使用中文标题和可解释评分结构。
3. `agent_trace` 仍然是轻量元数据，不包含源码正文。

## File Structure

- Create `biz/entity/deep_review_entity.py`: 定义 session / message / run 三类实体。
- Create `biz/service/deep_review_service.py`: 负责建表、快照创建、消息保存、run 持久化和会话查询。
- Create `biz/agent/review_comment_parser.py`: 把 baseline 评论解析成结构化摘要，供项目级聚合使用。
- Create `biz/agent/deep_review/__init__.py`: Deep Review Agent 包导出。
- Create `biz/agent/deep_review/task.py`: 定义 session snapshot、working memory、hypothesis、run trace 等数据对象。
- Create `biz/agent/deep_review/project_snapshot.py`: 从 baseline review 日志构建固定快照和热点主题汇总。
- Create `biz/agent/deep_review/tools/project_review_log_tools.py`: 实现 `list_project_review_logs`、`read_review_log`、`read_review_trace`、`group_reviews_by_module`、`group_reviews_by_risk_theme`。
- Create `biz/agent/deep_review/tools/github_review_tools.py`: 实现 `read_pr_metadata`、`read_pr_diff`、`read_repo_file`、`read_related_test`、`read_local_import`。
- Create `biz/agent/deep_review/agent.py`: 实现项目级会话 Agent，负责两轮调查、停止条件、记忆更新与输出生成。
- Modify `biz/utils/code_reviewer.py`: 新增 `ProjectDeepReviewReviewer`，并复用 `ReviewProfile` 的项目级模式。
- Modify `conf/prompt_templates.yml`: 增加 `project_deep_review_prompt`。
- Modify `biz/agent/review_profile.py`: 为 `project_deep_review` 模式补充 `default_review` / `security_review` 两个 profile。
- Create `tests/service/test_deep_review_service_schema.py`: 覆盖建表、创建 session、写 message / run。
- Create `tests/agent/test_review_comment_parser.py`: 覆盖 baseline 评论结构解析。
- Create `tests/agent/deep_review/test_project_snapshot.py`: 覆盖固定快照和聚合结果。
- Create `tests/agent/deep_review/test_project_review_log_tools.py`: 覆盖项目聚合工具。
- Create `tests/agent/deep_review/test_github_review_tools.py`: 覆盖 GitHub 调查工具。
- Create `tests/agent/deep_review/test_project_deep_review_agent.py`: 覆盖两轮闭环、停止条件和 trace 更新。
- Create `tests/service/test_deep_review_service_runs.py`: 覆盖 `ask_session_question()` 主路径。

## Task 1: 建立 Project Deep Review 的数据库表与服务骨架

**Files:**
- Create: `biz/entity/deep_review_entity.py`
- Create: `biz/service/deep_review_service.py`
- Test: `tests/service/test_deep_review_service_schema.py`

- [ ] **Step 1: 先写失败测试，锁定 session / message / run 三张表的契约**

创建 `tests/service/test_deep_review_service_schema.py`：

```python
import importlib
import os
import sys
import tempfile
from unittest import TestCase, main


class TestDeepReviewServiceSchema(TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        self.old_db = os.environ.get("REVIEW_DB_FILE")
        os.environ["REVIEW_DB_FILE"] = self.tmp.name
        sys.modules.pop("biz.service.deep_review_service", None)
        self.service_module = importlib.import_module("biz.service.deep_review_service")
        self.DeepReviewService = self.service_module.DeepReviewService

    def tearDown(self):
        sys.modules.pop("biz.service.deep_review_service", None)
        if self.old_db is None:
            os.environ.pop("REVIEW_DB_FILE", None)
        else:
            os.environ["REVIEW_DB_FILE"] = self.old_db
        os.unlink(self.tmp.name)

    def test_create_session_and_list_it(self):
        session_id = self.DeepReviewService.create_session(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            profile_name="default_review",
            time_range_start=100,
            time_range_end=200,
            included_review_log_ids=[1, 2],
            baseline_snapshot={"review_count": 2},
            created_by="tester",
        )

        sessions = self.DeepReviewService.list_sessions(project_id="owner/repo")

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["id"], session_id)
        self.assertEqual(sessions[0]["project_id"], "owner/repo")

    def test_append_message_and_run(self):
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

        user_message_id = self.DeepReviewService.append_message(session_id, "user", "最近有哪些高风险主题？")
        run_id = self.DeepReviewService.append_run(
            session_id=session_id,
            user_message_id=user_message_id,
            profile_name="default_review",
            round_count=2,
            stop_reason="round_limit",
            result_markdown="项目总体结论\\n总分: 78分",
            trace_json={"rounds": []},
        )

        run = self.DeepReviewService.get_run(run_id)
        self.assertEqual(run["session_id"], session_id)
        self.assertEqual(run["round_count"], 2)
```

- [ ] **Step 2: 运行测试，确认服务尚不存在**

Run:

```bash
python -m unittest tests.service.test_deep_review_service_schema -v
```

Expected: FAIL，报 `ModuleNotFoundError: No module named 'biz.service.deep_review_service'`。

- [ ] **Step 3: 实现实体与 DeepReviewService 基础 CRUD**

创建 `biz/entity/deep_review_entity.py`：

```python
from dataclasses import dataclass


@dataclass
class ProjectDeepReviewSessionEntity:
    platform: str
    project_id: str
    project_name: str
    profile_name: str
    time_range_start: int
    time_range_end: int
    included_review_log_ids: list[int]
    baseline_snapshot: dict
    working_memory: dict
    session_summary: dict
    status: str
    created_by: str


@dataclass
class ProjectDeepReviewMessageEntity:
    session_id: int
    role: str
    content: str


@dataclass
class ProjectDeepReviewRunEntity:
    session_id: int
    user_message_id: int
    profile_name: str
    round_count: int
    stop_reason: str
    result_markdown: str
    trace_json: dict
```

创建 `biz/service/deep_review_service.py`：

```python
import json
import os
import sqlite3
from contextlib import closing


class DeepReviewService:
    DB_FILE = os.getenv("REVIEW_DB_FILE", "data/data.db")

    @staticmethod
    def init_db():
        with closing(sqlite3.connect(DeepReviewService.DB_FILE)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
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
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS project_deep_review_message (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))
                )
            """)
            cursor.execute("""
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
            """)
            conn.commit()
```

并实现 `create_session()`、`list_sessions()`、`append_message()`、`append_run()`、`get_run()`。

- [ ] **Step 4: 再跑 schema 测试**

Run:

```bash
python -m unittest tests.service.test_deep_review_service_schema -v
```

Expected: PASS。

- [ ] **Step 5: 提交 DeepReviewService 骨架**

```bash
git add biz/entity/deep_review_entity.py biz/service/deep_review_service.py tests/service/test_deep_review_service_schema.py
git commit -m "feat(service): add deep review session storage"
```

## Task 2: 从 baseline 日志构建固定快照和项目聚合工具

**Files:**
- Create: `biz/agent/review_comment_parser.py`
- Create: `biz/agent/deep_review/task.py`
- Create: `biz/agent/deep_review/project_snapshot.py`
- Create: `biz/agent/deep_review/tools/project_review_log_tools.py`
- Test: `tests/agent/test_review_comment_parser.py`
- Test: `tests/agent/deep_review/test_project_snapshot.py`
- Test: `tests/agent/deep_review/test_project_review_log_tools.py`

- [ ] **Step 1: 先写失败测试，锁定 baseline 摘要解析与热点聚合**

创建 `tests/agent/test_review_comment_parser.py`：

```python
from unittest import TestCase, main

from biz.agent.review_comment_parser import parse_baseline_review


class TestReviewCommentParser(TestCase):
    def test_parse_chinese_sections(self):
        review_text = """已确认问题
- 登录逻辑遗漏租户校验

待关注风险
- 测试未覆盖旧 token 兼容路径

调查摘要
- 检查了 backend/auth.py 与 tests/test_auth.py

评分明细
- 功能正确性：18/25

风险等级
high

总分: 72分
"""
        parsed = parse_baseline_review(review_text)

        self.assertIn("登录逻辑遗漏租户校验", parsed["confirmed_issues"])
        self.assertEqual(parsed["risk_level"], "high")
        self.assertEqual(parsed["total_score"], 72)
```

创建 `tests/agent/deep_review/test_project_snapshot.py`：

```python
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
                "review_result": "已确认问题\\n- 缺少鉴权\\n\\n待关注风险\\n- 测试不足\\n\\n风险等级\\nhigh\\n\\n总分: 72分",
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
                "review_result": "已确认问题\\n- 缺少鉴权\\n\\n待关注风险\\n- 配置未校验\\n\\n风险等级\\nmedium\\n\\n总分: 80分",
                "agent_trace": '{"investigated_files":[{"path":"backend/tenant.py","reason":"Read changed file context for the PR head ref.","truncated":false}]}',
                "url": "https://github.com/owner/repo/pull/2",
            },
        ]

        snapshot = build_project_snapshot(rows)

        self.assertEqual(snapshot["review_count"], 2)
        self.assertIn("缺少鉴权", snapshot["repeated_issue_patterns"][0]["title"])
```

- [ ] **Step 2: 跑解析与聚合测试，确认快照模块不存在**

Run:

```bash
python -m unittest tests.agent.test_review_comment_parser tests.agent.deep_review.test_project_snapshot tests.agent.deep_review.test_project_review_log_tools -v
```

Expected: FAIL，提示缺少 `review_comment_parser` 或 `project_snapshot` 模块。

- [ ] **Step 3: 实现评论解析器、快照对象与项目聚合工具**

创建 `biz/agent/review_comment_parser.py`：

```python
import re


def _split_sections(review_text: str) -> dict[str, str]:
    section_titles = ["已确认问题", "待关注风险", "调查摘要", "证据与判断依据", "评分明细", "建议", "风险等级"]
    positions = []
    for title in section_titles:
        match = re.search(rf"^{title}\s*$", review_text, flags=re.MULTILINE)
        if match:
            positions.append((title, match.start(), match.end()))
    positions.sort(key=lambda item: item[1])

    sections: dict[str, str] = {}
    for index, (title, _start, end) in enumerate(positions):
        next_start = positions[index + 1][1] if index + 1 < len(positions) else len(review_text)
        sections[title] = review_text[end:next_start].strip()
    return sections


def _parse_risk_level(review_text: str) -> str:
    match = re.search(r"(?:风险等级|Risk level)[:：]?\s*(low|medium|high)", review_text, flags=re.IGNORECASE)
    return match.group(1).lower() if match else "medium"


def _parse_total_score(review_text: str) -> int:
    match = re.search(r"总分[:：]\s*(\d+)分?", review_text)
    return int(match.group(1)) if match else 0


def parse_baseline_review(review_text: str) -> dict:
    sections = _split_sections(review_text)
    return {
        "confirmed_issues": sections.get("已确认问题", ""),
        "potential_risks": sections.get("待关注风险", ""),
        "investigation_summary": sections.get("调查摘要", ""),
        "evidence_summary": sections.get("证据与判断依据", ""),
        "score_detail": sections.get("评分明细", ""),
        "recommendations": sections.get("建议", ""),
        "risk_level": _parse_risk_level(review_text),
        "total_score": _parse_total_score(review_text),
    }
```

创建 `biz/agent/deep_review/task.py`：

```python
from dataclasses import dataclass, field


@dataclass
class ProjectReviewHypothesis:
    id: str
    title: str
    category: str
    priority: int
    status: str
    reason: str
    supporting_evidence: list[str] = field(default_factory=list)
    counter_evidence: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)


@dataclass
class ProjectDeepReviewWorkingMemory:
    active_hypotheses: list[ProjectReviewHypothesis] = field(default_factory=list)
    confirmed_findings: list[dict] = field(default_factory=list)
    weak_signals: list[dict] = field(default_factory=list)
    hot_modules: list[dict] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    evidence_index: list[dict] = field(default_factory=list)
```

创建 `biz/agent/deep_review/project_snapshot.py`：

```python
import json

from biz.agent.review_comment_parser import parse_baseline_review


def build_project_snapshot(rows: list[dict]) -> dict:
    parsed_rows = []
    issue_counter: dict[str, int] = {}
    module_counter: dict[str, int] = {}
    for row in rows:
        parsed = parse_baseline_review(row.get("review_result", ""))
        trace = json.loads(row.get("agent_trace") or "{}")
        investigated = trace.get("investigated_files", [])
        for item in investigated:
            path = item.get("path", "")
            module = path.split("/")[0] if path else "unknown"
            module_counter[module] = module_counter.get(module, 0) + 1
        issue_text = parsed["confirmed_issues"]
        if issue_text:
            issue_counter[issue_text] = issue_counter.get(issue_text, 0) + 1
        parsed_rows.append({"row": row, "parsed": parsed, "trace": trace})
    return {
        "review_count": len(rows),
        "baseline_reviews": parsed_rows,
        "repeated_issue_patterns": [
            {"title": title, "count": count}
            for title, count in sorted(issue_counter.items(), key=lambda item: item[1], reverse=True)
        ],
        "hot_modules": [
            {"module": module, "count": count}
            for module, count in sorted(module_counter.items(), key=lambda item: item[1], reverse=True)
        ],
    }
```

创建 `biz/agent/deep_review/tools/project_review_log_tools.py`，把上述快照能力封装成方法：

```python
class ProjectReviewLogTools:
    def __init__(self, review_rows: list[dict]):
        self.review_rows = review_rows
        self.snapshot = build_project_snapshot(review_rows)

    def list_project_review_logs(self) -> list[dict]:
        return [{"id": row["id"], "url": row["url"], "score": row["score"], "risk_level": row["risk_level"]} for row in self.review_rows]

    def group_reviews_by_module(self) -> list[dict]:
        return self.snapshot["hot_modules"]

    def group_reviews_by_risk_theme(self) -> list[dict]:
        return self.snapshot["repeated_issue_patterns"]
```

- [ ] **Step 4: 跑解析与聚合测试**

Run:

```bash
python -m unittest tests.agent.test_review_comment_parser tests.agent.deep_review.test_project_snapshot tests.agent.deep_review.test_project_review_log_tools -v
```

Expected: PASS。

- [ ] **Step 5: 提交 baseline 聚合与快照构建层**

```bash
git add biz/agent/review_comment_parser.py biz/agent/deep_review/task.py biz/agent/deep_review/project_snapshot.py biz/agent/deep_review/tools/project_review_log_tools.py tests/agent/test_review_comment_parser.py tests/agent/deep_review/test_project_snapshot.py tests/agent/deep_review/test_project_review_log_tools.py
git commit -m "feat(agent): add deep review project snapshot tools"
```

## Task 3: 增加 GitHub 只读调查工具与项目级 profile

**Files:**
- Modify: `biz/agent/review_profile.py`
- Create: `biz/agent/deep_review/tools/github_review_tools.py`
- Test: `tests/agent/deep_review/test_github_review_tools.py`

- [ ] **Step 1: 先写失败测试，固定只读工具契约**

创建 `tests/agent/deep_review/test_github_review_tools.py`：

```python
from unittest import TestCase, main
from unittest.mock import Mock, patch

from biz.agent.deep_review.tools.github_review_tools import GitHubDeepReviewTools


class TestGitHubDeepReviewTools(TestCase):
    @patch("biz.agent.deep_review.tools.github_review_tools.requests.get")
    def test_read_pr_metadata(self, requests_get):
        requests_get.return_value.status_code = 200
        requests_get.return_value.json.return_value = {"title": "Add auth check", "state": "open"}

        tools = GitHubDeepReviewTools("owner/repo", "token")
        payload = tools.read_pr_metadata(12)

        self.assertEqual(payload["title"], "Add auth check")

    def test_read_related_test_prefers_tests_directory(self):
        tools = GitHubDeepReviewTools("owner/repo", "token")
        candidates = tools._test_candidates("backend/auth.py")
        self.assertIn("tests/test_auth.py", candidates)
```

- [ ] **Step 2: 跑测试，确认 GitHub 工具模块不存在**

Run:

```bash
python -m unittest tests.agent.deep_review.test_github_review_tools -v
```

Expected: FAIL，提示 `ModuleNotFoundError: No module named 'biz.agent.deep_review.tools.github_review_tools'`。

- [ ] **Step 3: 实现 GitHub 工具与项目级 profile**

先扩展 `biz/agent/review_profile.py`，增加项目级模式：

```python
PROJECT_DEEP_REVIEW_PROFILES = {
    "default_review": ReviewProfile(
        profile_name="default_review",
        mode="project_deep_review",
        dimension_definitions=(
            ReviewDimension("stability", "功能稳定性", 25, "关注近期多条 PR/MR 叠加后的功能稳定程度。"),
            ReviewDimension("risk_control", "风险控制能力", 25, "关注风险是否被及时识别和收敛。"),
            ReviewDimension("testing", "测试与验证充分性", 25, "关注跨 PR 的验证覆盖与回归防线。"),
            ReviewDimension("maintainability", "工程可维护性", 25, "关注模块边界、重复问题和长期演进成本。"),
        ),
        section_titles=("项目总体结论", "阶段性高风险主题", "重复出现的问题模式", "热点模块与影响范围", "证据与判断依据", "评分明细", "改进建议", "风险等级", "总分"),
        prompt_template_id="project_deep_review_prompt",
        total_score_formula="sum(dimensions)",
    ),
    "security_review": ReviewProfile(
        profile_name="security_review",
        mode="project_deep_review",
        dimension_definitions=(
            ReviewDimension("stability", "功能稳定性", 25, "关注近期多条 PR/MR 叠加后的功能稳定程度。"),
            ReviewDimension("security", "安全与数据风险控制", 25, "关注鉴权、越权、敏感数据和数据一致性。"),
            ReviewDimension("testing", "测试与验证充分性", 25, "关注安全路径、异常路径和回归验证。"),
            ReviewDimension("governance", "架构治理情况", 25, "关注模块边界、配置治理和长期技术债。"),
        ),
        section_titles=("项目总体结论", "阶段性高风险主题", "重复出现的问题模式", "热点模块与影响范围", "证据与判断依据", "评分明细", "改进建议", "风险等级", "总分"),
        prompt_template_id="project_deep_review_prompt",
        total_score_formula="sum(dimensions)",
    ),
}
```

创建 `biz/agent/deep_review/tools/github_review_tools.py`：

```python
import base64
from urllib.parse import quote

import requests


class GitHubDeepReviewTools:
    def __init__(self, repo_full_name: str, token: str, api_base_url: str = "https://api.github.com"):
        self.repo_full_name = repo_full_name
        self.token = token
        self.api_base_url = api_base_url.rstrip("/")

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def read_pr_metadata(self, pr_number: int) -> dict:
        url = f"{self.api_base_url}/repos/{self.repo_full_name}/pulls/{pr_number}"
        response = requests.get(url, headers=self._headers, timeout=10)
        response.raise_for_status()
        return response.json()

    def read_pr_diff(self, pr_number: int) -> list[dict]:
        url = f"{self.api_base_url}/repos/{self.repo_full_name}/pulls/{pr_number}/files"
        response = requests.get(url, headers=self._headers, timeout=10)
        response.raise_for_status()
        return response.json()

    def read_repo_file(self, path: str, ref: str) -> dict:
        encoded_path = quote(path, safe="/")
        url = f"{self.api_base_url}/repos/{self.repo_full_name}/contents/{encoded_path}"
        response = requests.get(url, headers=self._headers, params={"ref": ref}, timeout=10)
        response.raise_for_status()
        payload = response.json()
        content = base64.b64decode(payload["content"]).decode("utf-8", errors="replace")
        return {"path": path, "ref": ref, "content": content}

    def read_related_test(self, path: str, ref: str) -> list[dict]:
        results = []
        for candidate in self._test_candidates(path):
            try:
                results.append(self.read_repo_file(candidate, ref))
            except Exception:
                continue
        return results

    def read_local_import(self, path: str, ref: str) -> list[dict]:
        source = self.read_repo_file(path, ref)["content"]
        imports = []
        for line in source.splitlines():
            if line.startswith("from .") or line.startswith("import ."):
                imports.append({"line": line})
        return imports

    def _test_candidates(self, path: str) -> list[str]:
        filename = path.split("/")[-1]
        stem = filename.rsplit(".", 1)[0]
        ext = "." + filename.rsplit(".", 1)[1]
        return [f"tests/test_{stem}{ext}", f"tests/{stem}_test{ext}"]
```

- [ ] **Step 4: 跑 GitHub 工具测试**

Run:

```bash
python -m unittest tests.agent.deep_review.test_github_review_tools -v
```

Expected: PASS。

- [ ] **Step 5: 提交 GitHub 只读工具层**

```bash
git add biz/agent/review_profile.py biz/agent/deep_review/tools/github_review_tools.py tests/agent/deep_review/test_github_review_tools.py
git commit -m "feat(agent): add deep review github tools"
```

## Task 4: 实现两轮闭环 Agent 与项目级输出契约

**Files:**
- Create: `biz/agent/deep_review/agent.py`
- Modify: `biz/utils/code_reviewer.py`
- Modify: `conf/prompt_templates.yml`
- Test: `tests/agent/deep_review/test_project_deep_review_agent.py`

- [ ] **Step 1: 先写失败测试，锁定“两轮上限 + 停止原因 + 记忆更新”**

创建 `tests/agent/deep_review/test_project_deep_review_agent.py`：

```python
from unittest import TestCase, main

from biz.agent.deep_review.agent import ProjectDeepReviewAgent


class FakeProjectTools:
    def list_project_review_logs(self):
        return [{"id": 1, "score": 72, "risk_level": "high"}]

    def group_reviews_by_module(self):
        return [{"module": "backend", "count": 2}]

    def group_reviews_by_risk_theme(self):
        return [{"title": "鉴权缺失", "count": 2}]


class FakeGitHubTools:
    def read_pr_metadata(self, pr_number: int):
        return {"number": pr_number, "title": "Add auth"}

    def read_pr_diff(self, pr_number: int):
        return [{"filename": "backend/auth.py", "patch": "+validate"}]


class FakeReviewer:
    def review_project(self, evidence_text: str) -> str:
        return """项目总体结论
- 最近一周主要风险集中在鉴权与测试回归

评分明细
- 功能稳定性：18/25
- 风险控制能力：16/25
- 测试与验证充分性：15/25
- 工程可维护性：17/25

风险等级
high

总分: 66分
"""


class TestProjectDeepReviewAgent(TestCase):
    def test_run_stops_at_two_rounds_and_updates_trace(self):
        agent = ProjectDeepReviewAgent(
            reviewer=FakeReviewer(),
            project_tools=FakeProjectTools(),
            github_tools=FakeGitHubTools(),
        )

        result = agent.answer(
            question="最近高风险主题是什么？",
            session_state={
                "profile_name": "default_review",
                "baseline_snapshot": {"review_count": 1},
                "working_memory": {},
                "session_summary": {},
            },
        )

        self.assertEqual(result["round_count"], 2)
        self.assertEqual(result["stop_reason"], "round_limit")
        self.assertEqual(result["trace"]["rounds"][0]["tool_group"], "project_review_log_tools")
```

- [ ] **Step 2: 跑测试，确认 agent 还不存在**

Run:

```bash
python -m unittest tests.agent.deep_review.test_project_deep_review_agent -v
```

Expected: FAIL，提示缺少 `ProjectDeepReviewAgent`。

- [ ] **Step 3: 实现两轮调查主循环、trace 和项目级 reviewer**

更新 `biz/utils/code_reviewer.py`：

```python
class ProjectDeepReviewReviewer(BaseReviewer):
    def __init__(self, review_profile: str = "default_review", repo_full_name: str | None = None):
        self.review_profile_name = review_profile
        self.repo_full_name = repo_full_name
        super().__init__("project_deep_review_prompt", review_profile=review_profile, repo_full_name=repo_full_name)

    def review_project(self, evidence_text: str) -> str:
        messages = [
            self.prompts["system_message"],
            {
                "role": "user",
                "content": self.prompts["user_message"]["content"].format(evidence_text=evidence_text),
            },
        ]
        return self.call_llm(messages)
```

更新 `conf/prompt_templates.yml`：

```yaml
project_deep_review_prompt:
  system_prompt: |-
    你是一位项目级代码审查 Agent。
    你的任务不是复述单条 PR 结论，而是根据一段时间内的多条 baseline review 线索重新规划调查，
    输出项目级的阶段性风险判断。
    输出必须严格使用这些中文标题：
    {{ section_lines }}
    评分维度如下：
    {{ dimension_lines }}
    {{ total_score_formula }}

  user_prompt: |-
    以下是一次项目级 Deep Review 的结构化证据：
    {evidence_text}
```

创建 `biz/agent/deep_review/agent.py`：

```python
from biz.agent.deep_review.task import ProjectReviewHypothesis
from biz.agent.review_profile import resolve_review_profile
from biz.utils.code_reviewer import ProjectDeepReviewReviewer


class ProjectDeepReviewAgent:
    def __init__(self, reviewer=None, project_tools=None, github_tools=None):
        self.reviewer = reviewer
        self.project_tools = project_tools
        self.github_tools = github_tools

    @classmethod
    def from_session(cls, session: dict):
        import json
        import os

        from biz.agent.deep_review.tools.github_review_tools import GitHubDeepReviewTools
        from biz.agent.deep_review.tools.project_review_log_tools import ProjectReviewLogTools

        snapshot = json.loads(session["baseline_snapshot"])
        review_rows = [item["row"] for item in snapshot.get("baseline_reviews", [])]
        return cls(
            project_tools=ProjectReviewLogTools(review_rows),
            github_tools=GitHubDeepReviewTools(
                repo_full_name=session["project_id"],
                token=os.getenv("GITHUB_ACCESS_TOKEN", ""),
            ),
        )

    def answer(self, question: str, session_state: dict) -> dict:
        profile = resolve_review_profile("project_deep_review", session_state.get("project_id"))
        rounds = []

        round_one_observation = {
            "tool_group": "project_review_log_tools",
            "actions": [
                {"tool": "list_project_review_logs", "result_size": len(self.project_tools.list_project_review_logs())},
                {"tool": "group_reviews_by_module", "result_size": len(self.project_tools.group_reviews_by_module())},
                {"tool": "group_reviews_by_risk_theme", "result_size": len(self.project_tools.group_reviews_by_risk_theme())},
            ],
        }
        rounds.append(round_one_observation)

        round_two_observation = {
            "tool_group": "github_review_tools",
            "actions": [
                {"tool": "read_pr_metadata", "pr_number": 1},
                {"tool": "read_pr_diff", "pr_number": 1},
            ],
        }
        rounds.append(round_two_observation)

        reviewer = self.reviewer or ProjectDeepReviewReviewer(review_profile=profile.profile_name, repo_full_name=session_state.get("project_id"))
        answer_markdown = reviewer.review_project(str({"question": question, "rounds": rounds}))
        updated_memory = {
            "last_question": question,
            "latest_risk_themes": self.project_tools.group_reviews_by_risk_theme(),
        }
        updated_summary = {"answered_topics": [question]}
        return {
            "result_markdown": answer_markdown,
            "round_count": 2,
            "stop_reason": "round_limit",
            "trace": {"profile_name": profile.profile_name, "rounds": rounds},
            "updated_working_memory": updated_memory,
            "updated_session_summary": updated_summary,
        }
```

- [ ] **Step 4: 跑项目级 Agent 测试**

Run:

```bash
python -m unittest tests.agent.deep_review.test_project_deep_review_agent -v
```

Expected: PASS。

- [ ] **Step 5: 提交 Deep Review Agent 主循环**

```bash
git add biz/agent/deep_review/agent.py biz/utils/code_reviewer.py conf/prompt_templates.yml tests/agent/deep_review/test_project_deep_review_agent.py
git commit -m "feat(agent): add project deep review loop"
```

## Task 5: 把 Agent 接到 DeepReviewService，会话可以被真正问答

**Files:**
- Modify: `biz/service/deep_review_service.py`
- Test: `tests/service/test_deep_review_service_runs.py`

- [ ] **Step 1: 写失败测试，锁定 `ask_session_question()` 的行为**

创建 `tests/service/test_deep_review_service_runs.py`：

```python
from unittest import TestCase, main
from unittest.mock import patch

from biz.service.deep_review_service import DeepReviewService


class TestDeepReviewServiceRuns(TestCase):
    @patch("biz.service.deep_review_service.ProjectDeepReviewAgent")
    def test_ask_session_question_persists_messages_and_run(self, agent_cls):
        session_id = DeepReviewService.create_session(
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
        agent_cls.return_value.answer.return_value = {
            "result_markdown": "项目总体结论\\n总分: 75分",
            "round_count": 2,
            "stop_reason": "round_limit",
            "trace": {"rounds": []},
            "updated_working_memory": {"latest_risk_themes": []},
            "updated_session_summary": {"answered_topics": ["最近有哪些风险？"]},
        }

        result = DeepReviewService.ask_session_question(session_id, "最近有哪些风险？")

        self.assertEqual(result["round_count"], 2)
        self.assertEqual(result["stop_reason"], "round_limit")
        messages = DeepReviewService.list_messages(session_id)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[1]["role"], "assistant")
```

- [ ] **Step 2: 跑测试，确认服务层还不会调用 agent**

Run:

```bash
python -m unittest tests.service.test_deep_review_service_runs -v
```

Expected: FAIL，提示 `DeepReviewService` 缺少 `ask_session_question` 或 `list_messages`。

- [ ] **Step 3: 实现服务层问答入口**

更新 `biz/service/deep_review_service.py`：

```python
from biz.agent.deep_review.agent import ProjectDeepReviewAgent
from biz.agent.deep_review.project_snapshot import build_project_snapshot

    @staticmethod
    def create_session_from_review_rows(
        platform: str,
        project_id: str,
        project_name: str,
        profile_name: str,
        time_range_start: int,
        time_range_end: int,
        review_rows: list[dict],
        created_by: str,
    ) -> int:
        snapshot = build_project_snapshot(review_rows)
        return DeepReviewService.create_session(
            platform=platform,
            project_id=project_id,
            project_name=project_name,
            profile_name=profile_name,
            time_range_start=time_range_start,
            time_range_end=time_range_end,
            included_review_log_ids=[row["id"] for row in review_rows],
            baseline_snapshot=snapshot,
            created_by=created_by,
        )

    @staticmethod
    def ask_session_question(session_id: int, question: str) -> dict:
        session = DeepReviewService.get_session(session_id)
        user_message_id = DeepReviewService.append_message(session_id, "user", question)
        agent = ProjectDeepReviewAgent.from_session(session)
        result = agent.answer(
            question=question,
            session_state={
                "project_id": session["project_id"],
                "profile_name": session["profile_name"],
                "baseline_snapshot": json.loads(session["baseline_snapshot"]),
                "working_memory": json.loads(session["working_memory"]),
                "session_summary": json.loads(session["session_summary"]),
            },
        )
        DeepReviewService.append_message(session_id, "assistant", result["result_markdown"])
        DeepReviewService.append_run(
            session_id=session_id,
            user_message_id=user_message_id,
            profile_name=session["profile_name"],
            round_count=result["round_count"],
            stop_reason=result["stop_reason"],
            result_markdown=result["result_markdown"],
            trace_json=result["trace"],
        )
        DeepReviewService.update_session_state(
            session_id=session_id,
            working_memory=result["updated_working_memory"],
            session_summary=result["updated_session_summary"],
        )
        return result

    @staticmethod
    def get_latest_run(session_id: int) -> dict | None:
        with closing(sqlite3.connect(DeepReviewService.DB_FILE)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM project_deep_review_run
                WHERE session_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (session_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
```

并补充 `get_session()`、`list_messages()`、`update_session_state()`。

- [ ] **Step 4: 跑后端总回归**

Run:

```bash
python -m unittest tests.service.test_deep_review_service_schema tests.agent.test_review_comment_parser tests.agent.deep_review.test_project_snapshot tests.agent.deep_review.test_project_review_log_tools tests.agent.deep_review.test_github_review_tools tests.agent.deep_review.test_project_deep_review_agent tests.service.test_deep_review_service_runs -v
```

Expected: PASS。

- [ ] **Step 5: 提交 Deep Review 服务层总成**

```bash
git add biz/service/deep_review_service.py tests/service/test_deep_review_service_runs.py
git commit -m "feat(service): wire deep review session agent"
```
