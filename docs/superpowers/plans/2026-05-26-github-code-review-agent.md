# GitHub Code Review Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a GitHub-first investigation-style code review Agent for PR review, with API-based context collection, structured evidence prompts, trace persistence, and safe fallback to the existing review path.

**Architecture:** Add a focused `biz/agent/` package that owns task objects, diff analysis, investigation planning, GitHub file reading, context collection, evidence building, and Agent orchestration. Keep webhook parsing, PR comments, notifications, and SQLite persistence in the existing worker/event/service layers. Gate the new path behind `AGENT_REVIEW_ENABLED` so current behavior remains the default.

**Tech Stack:** Python 3.10+, Flask worker flow, `unittest`, `requests`, existing LLM factory and `CodeReviewer`, SQLite via existing `ReviewService`.

---

## Scope Check

This plan implements the first independently testable rollout target from the approved spec: GitHub PR investigation review. The shared `PlatformFileReader` interface is shaped so GitLab and Gitea readers can be added next without changing Agent internals, but GitLab MR and Gitea PR wiring will be separate follow-up plans after the GitHub path is working.

## File Structure

- Create `biz/agent/__init__.py`: Agent package marker and public exports.
- Create `biz/agent/task.py`: Dataclasses shared across Agent modules.
- Create `biz/agent/diff_analyzer.py`: Lightweight changed-file analysis.
- Create `biz/agent/planner.py`: Rule-driven bounded investigation planning.
- Create `biz/agent/context_collector.py`: Executes investigation actions through a file reader and enforces budgets.
- Create `biz/agent/evidence_builder.py`: Builds structured evidence text for the LLM.
- Create `biz/agent/review_agent.py`: Orchestrates the Agent review flow and fallback.
- Create `biz/agent/tools/__init__.py`: Tool package marker.
- Create `biz/agent/tools/file_reader.py`: Platform-neutral reader plus GitHub implementation.
- Modify `biz/utils/code_reviewer.py`: Add `AgentCodeReviewer` using a new prompt key.
- Modify `conf/prompt_templates.yml`: Add `agent_code_review_prompt`.
- Modify `biz/entity/review_entity.py`: Add optional `agent_trace`.
- Modify `biz/service/review_service.py`: Add `agent_trace` column to `mr_review_log`.
- Modify `biz/queue/worker.py`: Route GitHub PR review through Agent when enabled.
- Create focused `unittest` files under `biz/agent/`.

## Task 1: Agent Data Objects

**Files:**
- Create: `biz/agent/__init__.py`
- Create: `biz/agent/task.py`
- Test: `biz/agent/test_task.py`

- [ ] **Step 1: Write the failing dataclass test**

Create `biz/agent/test_task.py`:

```python
from unittest import TestCase, main

from biz.agent.task import (
    AgentReviewResult,
    ChangedFile,
    CollectedContext,
    ContextBudget,
    DiffAnalysis,
    FileReadResult,
    InvestigationAction,
    InvestigationPlan,
    ReviewTask,
)


class TestAgentTaskTypes(TestCase):
    def test_review_task_defaults_change_ref_to_source_branch(self):
        task = ReviewTask(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            source_branch="feature/login",
            target_branch="main",
            change_ref="",
            author="octocat",
            url="https://github.com/owner/repo/pull/1",
            commits=[],
            changes=[],
            access_token="token",
            platform_url="https://github.com",
        )

        self.assertEqual(task.effective_ref, "feature/login")

    def test_review_task_prefers_explicit_change_ref(self):
        task = ReviewTask(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            source_branch="feature/login",
            target_branch="main",
            change_ref="abc123",
            author="octocat",
            url="https://github.com/owner/repo/pull/1",
            commits=[],
            changes=[],
            access_token="token",
            platform_url="https://github.com",
        )

        self.assertEqual(task.effective_ref, "abc123")

    def test_agent_trace_is_serializable_shape(self):
        result = AgentReviewResult(
            review_text="总分: 90分",
            score=90,
            risk_level="medium",
            investigated_files=["src/app.py"],
            investigation_summary="Checked changed file context.",
            warnings=[],
            agent_trace={"mode": "context_investigation"},
        )

        self.assertEqual(result.agent_trace["mode"], "context_investigation")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python -m unittest biz.agent.test_task -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'biz.agent'`.

- [ ] **Step 3: Add the Agent package and dataclasses**

Create `biz/agent/__init__.py`:

```python
from biz.agent.task import (
    AgentReviewResult,
    ChangedFile,
    CollectedContext,
    ContextBudget,
    DiffAnalysis,
    FileReadResult,
    InvestigationAction,
    InvestigationPlan,
    ReviewTask,
)

__all__ = [
    "AgentReviewResult",
    "ChangedFile",
    "CollectedContext",
    "ContextBudget",
    "DiffAnalysis",
    "FileReadResult",
    "InvestigationAction",
    "InvestigationPlan",
    "ReviewTask",
]
```

Create `biz/agent/task.py`:

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReviewTask:
    platform: str
    project_id: str
    project_name: str
    source_branch: str
    target_branch: str
    change_ref: str
    author: str
    url: str
    commits: list[dict[str, Any]]
    changes: list[dict[str, Any]]
    access_token: str
    platform_url: str

    @property
    def effective_ref(self) -> str:
        return self.change_ref or self.source_branch


@dataclass
class ChangedFile:
    path: str
    language: str
    additions: int
    deletions: int
    is_test: bool
    is_config: bool
    risk_tags: list[str] = field(default_factory=list)
    changed_symbols: list[str] = field(default_factory=list)


@dataclass
class DiffAnalysis:
    files: list[ChangedFile]
    total_additions: int
    total_deletions: int
    risk_hints: list[str] = field(default_factory=list)


@dataclass
class ContextBudget:
    max_context_files: int = 5
    max_context_tokens: int = 12000
    max_file_chars: int = 30000
    max_import_files: int = 2
    max_test_files: int = 2


@dataclass
class InvestigationAction:
    action_type: str
    path: str
    ref: str
    reason: str
    priority: int


@dataclass
class InvestigationPlan:
    actions: list[InvestigationAction]
    budget: ContextBudget


@dataclass
class FileReadResult:
    path: str
    ref: str
    content: str = ""
    ok: bool = False
    truncated: bool = False
    error: str | None = None


@dataclass
class CollectedContext:
    path: str
    ref: str
    reason: str
    content: str
    truncated: bool = False
    error: str | None = None


@dataclass
class AgentReviewResult:
    review_text: str
    score: int
    risk_level: str
    investigated_files: list[str]
    investigation_summary: str
    warnings: list[str]
    agent_trace: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: Run the dataclass test**

Run:

```bash
python -m unittest biz.agent.test_task -v
```

Expected: PASS all 3 tests.

- [ ] **Step 5: Commit**

```bash
git add biz/agent/__init__.py biz/agent/task.py biz/agent/test_task.py
git commit -m "feat(agent): add review task data types"
```

## Task 2: Diff Analyzer

**Files:**
- Create: `biz/agent/diff_analyzer.py`
- Test: `biz/agent/test_diff_analyzer.py`

- [ ] **Step 1: Write the failing analyzer tests**

Create `biz/agent/test_diff_analyzer.py`:

```python
from unittest import TestCase, main

from biz.agent.diff_analyzer import DiffAnalyzer


class TestDiffAnalyzer(TestCase):
    def test_analyzes_python_service_change(self):
        changes = [
            {
                "new_path": "biz/service/review_service.py",
                "diff": "@@ -1,3 +1,7 @@\n+class ReviewService:\n+    def insert_log(self):\n+        pass\n",
                "additions": 3,
                "deletions": 0,
            }
        ]

        analysis = DiffAnalyzer().analyze(changes)

        self.assertEqual(analysis.total_additions, 3)
        self.assertEqual(analysis.total_deletions, 0)
        self.assertEqual(analysis.files[0].language, "python")
        self.assertFalse(analysis.files[0].is_test)
        self.assertIn("ReviewService", analysis.files[0].changed_symbols)
        self.assertIn("insert_log", analysis.files[0].changed_symbols)

    def test_marks_test_config_and_risk_tags(self):
        changes = [
            {
                "new_path": "tests/test_auth_config.py",
                "diff": "+def test_token_validation():\n+    pass\n",
                "additions": 2,
                "deletions": 0,
            },
            {
                "new_path": "deploy/docker-compose.yml",
                "diff": "+services:\n",
                "additions": 1,
                "deletions": 0,
            },
        ]

        analysis = DiffAnalyzer().analyze(changes)

        self.assertTrue(analysis.files[0].is_test)
        self.assertIn("security", analysis.files[0].risk_tags)
        self.assertTrue(analysis.files[1].is_config)
        self.assertIn("config", analysis.files[1].risk_tags)
        self.assertIn("security", analysis.risk_hints)
        self.assertIn("config", analysis.risk_hints)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the analyzer tests to verify failure**

Run:

```bash
python -m unittest biz.agent.test_diff_analyzer -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'biz.agent.diff_analyzer'`.

- [ ] **Step 3: Implement the analyzer**

Create `biz/agent/diff_analyzer.py`:

```python
import os
import re

from biz.agent.task import ChangedFile, DiffAnalysis


class DiffAnalyzer:
    LANGUAGE_BY_EXTENSION = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".java": "java",
        ".go": "go",
        ".php": "php",
        ".vue": "vue",
        ".sql": "sql",
        ".yml": "yaml",
        ".yaml": "yaml",
    }

    SECURITY_KEYWORDS = ("auth", "token", "password", "permission", "security")
    BUSINESS_KEYWORDS = ("payment", "order", "refund")
    DATABASE_KEYWORDS = ("migration", "sql", "db", "database")
    INTERFACE_KEYWORDS = ("api", "router", "controller")

    def analyze(self, changes: list[dict]) -> DiffAnalysis:
        files = [self._analyze_change(change) for change in changes]
        risk_hints = sorted({tag for file in files for tag in file.risk_tags})
        return DiffAnalysis(
            files=files,
            total_additions=sum(file.additions for file in files),
            total_deletions=sum(file.deletions for file in files),
            risk_hints=risk_hints,
        )

    def _analyze_change(self, change: dict) -> ChangedFile:
        path = change.get("new_path") or change.get("old_path") or ""
        diff = change.get("diff", "")
        return ChangedFile(
            path=path,
            language=self._detect_language(path),
            additions=int(change.get("additions", 0) or 0),
            deletions=int(change.get("deletions", 0) or 0),
            is_test=self._is_test_path(path),
            is_config=self._is_config_path(path),
            risk_tags=self._risk_tags(path),
            changed_symbols=self._changed_symbols(diff),
        )

    def _detect_language(self, path: str) -> str:
        _, ext = os.path.splitext(path.lower())
        return self.LANGUAGE_BY_EXTENSION.get(ext, "unknown")

    def _is_test_path(self, path: str) -> bool:
        normalized = path.lower().replace("\\", "/")
        basename = os.path.basename(normalized)
        return (
            "/test/" in normalized
            or "/tests/" in normalized
            or "spec" in basename
            or basename.startswith("test_")
            or "_test" in basename
        )

    def _is_config_path(self, path: str) -> bool:
        normalized = path.lower()
        basename = os.path.basename(normalized)
        return (
            "config" in normalized
            or basename.startswith(".env")
            or basename in {"dockerfile", "docker-compose.yml", "docker-compose.yaml"}
            or normalized.endswith((".yml", ".yaml"))
        )

    def _risk_tags(self, path: str) -> list[str]:
        normalized = path.lower()
        tags = set()
        if any(keyword in normalized for keyword in self.SECURITY_KEYWORDS):
            tags.add("security")
        if any(keyword in normalized for keyword in self.BUSINESS_KEYWORDS):
            tags.add("business_critical")
        if any(keyword in normalized for keyword in self.DATABASE_KEYWORDS):
            tags.add("database")
        if any(keyword in normalized for keyword in self.INTERFACE_KEYWORDS):
            tags.add("interface")
        if self._is_config_path(path):
            tags.add("config")
        return sorted(tags)

    def _changed_symbols(self, diff: str) -> list[str]:
        patterns = [
            r"^\+\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            r"^\+\s*class\s+([A-Za-z_][A-Za-z0-9_]*)",
            r"^\+\s*function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(",
            r"^\+\s*export\s+(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(",
            r"^\+\s*export\s+class\s+([A-Za-z_$][A-Za-z0-9_$]*)",
            r"^\+\s*func\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        ]
        symbols = []
        for pattern in patterns:
            symbols.extend(re.findall(pattern, diff, flags=re.MULTILINE))
        return sorted(set(symbols))
```

- [ ] **Step 4: Run the analyzer tests**

Run:

```bash
python -m unittest biz.agent.test_diff_analyzer -v
```

Expected: PASS all tests.

- [ ] **Step 5: Commit**

```bash
git add biz/agent/diff_analyzer.py biz/agent/test_diff_analyzer.py
git commit -m "feat(agent): analyze changed files"
```

## Task 3: Investigation Planner

**Files:**
- Create: `biz/agent/planner.py`
- Test: `biz/agent/test_planner.py`

- [ ] **Step 1: Write the failing planner tests**

Create `biz/agent/test_planner.py`:

```python
from unittest import TestCase, main

from biz.agent.planner import InvestigationPlanner
from biz.agent.task import ChangedFile, ContextBudget, DiffAnalysis, ReviewTask


class TestInvestigationPlanner(TestCase):
    def _task(self):
        return ReviewTask(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            source_branch="feature/login",
            target_branch="main",
            change_ref="abc123",
            author="octocat",
            url="https://github.com/owner/repo/pull/1",
            commits=[],
            changes=[],
            access_token="token",
            platform_url="https://github.com",
        )

    def test_plans_changed_file_and_test_candidates(self):
        analysis = DiffAnalysis(
            files=[
                ChangedFile(
                    path="biz/service/review_service.py",
                    language="python",
                    additions=10,
                    deletions=1,
                    is_test=False,
                    is_config=False,
                )
            ],
            total_additions=10,
            total_deletions=1,
        )

        plan = InvestigationPlanner(ContextBudget(max_context_files=5)).create_plan(self._task(), analysis)
        action_pairs = [(action.action_type, action.path) for action in plan.actions]

        self.assertIn(("read_changed_file", "biz/service/review_service.py"), action_pairs)
        self.assertIn(("find_related_test", "tests/test_review_service.py"), action_pairs)
        self.assertIn(("find_related_test", "biz/service/test_review_service.py"), action_pairs)

    def test_respects_max_context_files(self):
        analysis = DiffAnalysis(
            files=[
                ChangedFile("a.py", "python", 1, 0, False, False),
                ChangedFile("b.py", "python", 1, 0, False, False),
                ChangedFile("c.py", "python", 1, 0, False, False),
            ],
            total_additions=3,
            total_deletions=0,
        )

        plan = InvestigationPlanner(ContextBudget(max_context_files=2)).create_plan(self._task(), analysis)

        self.assertEqual(len(plan.actions), 2)
        self.assertEqual([action.action_type for action in plan.actions], ["read_changed_file", "read_changed_file"])


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the planner tests to verify failure**

Run:

```bash
python -m unittest biz.agent.test_planner -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'biz.agent.planner'`.

- [ ] **Step 3: Implement the planner**

Create `biz/agent/planner.py`:

```python
import os

from biz.agent.task import ContextBudget, DiffAnalysis, InvestigationAction, InvestigationPlan, ReviewTask


class InvestigationPlanner:
    def __init__(self, budget: ContextBudget | None = None):
        self.budget = budget or ContextBudget(
            max_context_files=int(os.getenv("AGENT_MAX_CONTEXT_FILES", 5)),
            max_context_tokens=int(os.getenv("AGENT_MAX_CONTEXT_TOKENS", 12000)),
            max_file_chars=int(os.getenv("AGENT_MAX_FILE_CHARS", 30000)),
            max_import_files=int(os.getenv("AGENT_MAX_IMPORT_FILES", 2)),
            max_test_files=int(os.getenv("AGENT_MAX_TEST_FILES", 2)),
        )

    def create_plan(self, task: ReviewTask, analysis: DiffAnalysis) -> InvestigationPlan:
        actions: list[InvestigationAction] = []
        for changed_file in analysis.files:
            priority = 10 if changed_file.risk_tags else 20
            actions.append(
                InvestigationAction(
                    action_type="read_changed_file",
                    path=changed_file.path,
                    ref=task.effective_ref,
                    reason="Read changed file context for the PR head ref.",
                    priority=priority,
                )
            )
            if not changed_file.is_test:
                for candidate in self._test_candidates(changed_file.path)[: self.budget.max_test_files]:
                    actions.append(
                        InvestigationAction(
                            action_type="find_related_test",
                            path=candidate,
                            ref=task.effective_ref,
                            reason=f"Check whether related tests cover {changed_file.path}.",
                            priority=40,
                        )
                    )

        actions.sort(key=lambda item: (item.priority, item.path))
        return InvestigationPlan(actions=actions[: self.budget.max_context_files], budget=self.budget)

    def _test_candidates(self, path: str) -> list[str]:
        directory, filename = os.path.split(path)
        stem, ext = os.path.splitext(filename)
        candidates = [
            f"tests/test_{stem}{ext}",
            f"{directory}/test_{stem}{ext}" if directory else f"test_{stem}{ext}",
            f"{directory}/{stem}_test{ext}" if directory else f"{stem}_test{ext}",
        ]
        return [candidate.replace("//", "/") for candidate in candidates]
```

- [ ] **Step 4: Run the planner tests**

Run:

```bash
python -m unittest biz.agent.test_planner -v
```

Expected: PASS all tests.

- [ ] **Step 5: Commit**

```bash
git add biz/agent/planner.py biz/agent/test_planner.py
git commit -m "feat(agent): plan context investigation"
```

## Task 4: GitHub File Reader

**Files:**
- Create: `biz/agent/tools/__init__.py`
- Create: `biz/agent/tools/file_reader.py`
- Test: `biz/agent/tools/test_file_reader.py`

- [ ] **Step 1: Write the failing GitHub reader tests**

Create `biz/agent/tools/test_file_reader.py`:

```python
import base64
from unittest import TestCase, main
from unittest.mock import Mock, patch

from biz.agent.tools.file_reader import GitHubFileReader


class TestGitHubFileReader(TestCase):
    @patch("biz.agent.tools.file_reader.requests.get")
    def test_reads_and_decodes_file(self, mock_get):
        encoded = base64.b64encode(b"print('hello')\n").decode("utf-8")
        mock_get.return_value = Mock(status_code=200, json=lambda: {"content": encoded, "encoding": "base64"})

        reader = GitHubFileReader(repo_full_name="owner/repo", token="token")
        result = reader.read_file("src/app.py", "abc123")

        self.assertTrue(result.ok)
        self.assertEqual(result.content, "print('hello')\n")
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], "https://api.github.com/repos/owner/repo/contents/src/app.py")
        self.assertEqual(kwargs["params"], {"ref": "abc123"})

    @patch("biz.agent.tools.file_reader.requests.get")
    def test_returns_error_for_missing_file(self, mock_get):
        mock_get.return_value = Mock(status_code=404, text="not found")

        reader = GitHubFileReader(repo_full_name="owner/repo", token="token")
        result = reader.read_file("missing.py", "abc123")

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "GitHub file read failed: 404 not found")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the reader tests to verify failure**

Run:

```bash
python -m unittest biz.agent.tools.test_file_reader -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'biz.agent.tools'`.

- [ ] **Step 3: Implement the file reader**

Create `biz/agent/tools/__init__.py`:

```python
from biz.agent.tools.file_reader import GitHubFileReader, PlatformFileReader

__all__ = ["GitHubFileReader", "PlatformFileReader"]
```

Create `biz/agent/tools/file_reader.py`:

```python
import base64
from abc import ABC, abstractmethod
from urllib.parse import quote

import requests

from biz.agent.task import FileReadResult


class PlatformFileReader(ABC):
    @abstractmethod
    def read_file(self, path: str, ref: str) -> FileReadResult:
        raise NotImplementedError

    def file_exists(self, path: str, ref: str) -> bool:
        return self.read_file(path, ref).ok


class GitHubFileReader(PlatformFileReader):
    def __init__(self, repo_full_name: str, token: str, api_base_url: str = "https://api.github.com",
                 max_file_chars: int = 30000):
        self.repo_full_name = repo_full_name
        self.token = token
        self.api_base_url = api_base_url.rstrip("/")
        self.max_file_chars = max_file_chars

    def read_file(self, path: str, ref: str) -> FileReadResult:
        encoded_path = quote(path, safe="/")
        url = f"{self.api_base_url}/repos/{self.repo_full_name}/contents/{encoded_path}"
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }
        try:
            response = requests.get(url, headers=headers, params={"ref": ref})
            if response.status_code != 200:
                return FileReadResult(
                    path=path,
                    ref=ref,
                    ok=False,
                    error=f"GitHub file read failed: {response.status_code} {response.text}",
                )
            payload = response.json()
            if isinstance(payload, list):
                return FileReadResult(path=path, ref=ref, ok=False, error="GitHub path is a directory")
            content = payload.get("content", "")
            encoding = payload.get("encoding", "")
            if encoding == "base64":
                decoded = base64.b64decode(content).decode("utf-8", errors="replace")
            else:
                decoded = str(content)
            truncated = len(decoded) > self.max_file_chars
            if truncated:
                decoded = decoded[: self.max_file_chars]
            return FileReadResult(path=path, ref=ref, content=decoded, ok=True, truncated=truncated)
        except Exception as exc:
            return FileReadResult(path=path, ref=ref, ok=False, error=f"GitHub file read exception: {exc}")
```

- [ ] **Step 4: Run the reader tests**

Run:

```bash
python -m unittest biz.agent.tools.test_file_reader -v
```

Expected: PASS all tests.

- [ ] **Step 5: Commit**

```bash
git add biz/agent/tools/__init__.py biz/agent/tools/file_reader.py biz/agent/tools/test_file_reader.py
git commit -m "feat(agent): add github file reader"
```

## Task 5: Context Collector

**Files:**
- Create: `biz/agent/context_collector.py`
- Test: `biz/agent/test_context_collector.py`

- [ ] **Step 1: Write the failing collector tests**

Create `biz/agent/test_context_collector.py`:

```python
from unittest import TestCase, main

from biz.agent.context_collector import ContextCollector
from biz.agent.task import ContextBudget, FileReadResult, InvestigationAction, InvestigationPlan


class FakeReader:
    def __init__(self, files):
        self.files = files

    def read_file(self, path, ref):
        if path not in self.files:
            return FileReadResult(path=path, ref=ref, ok=False, error="missing")
        return FileReadResult(path=path, ref=ref, ok=True, content=self.files[path])


class TestContextCollector(TestCase):
    def test_collects_success_and_warning(self):
        plan = InvestigationPlan(
            actions=[
                InvestigationAction("read_changed_file", "src/app.py", "abc123", "changed file", 10),
                InvestigationAction("find_related_test", "tests/test_app.py", "abc123", "related test", 40),
            ],
            budget=ContextBudget(max_context_files=5, max_file_chars=100),
        )

        contexts, warnings = ContextCollector().collect(plan, FakeReader({"src/app.py": "print('hello')"}))

        self.assertEqual(len(contexts), 2)
        self.assertIsNone(contexts[0].error)
        self.assertEqual(contexts[1].error, "missing")
        self.assertIn("Failed to read tests/test_app.py: missing", warnings)

    def test_truncates_large_content(self):
        plan = InvestigationPlan(
            actions=[InvestigationAction("read_changed_file", "src/app.py", "abc123", "changed file", 10)],
            budget=ContextBudget(max_context_files=5, max_file_chars=4),
        )

        contexts, warnings = ContextCollector().collect(plan, FakeReader({"src/app.py": "abcdef"}))

        self.assertEqual(contexts[0].content, "abcd")
        self.assertTrue(contexts[0].truncated)
        self.assertIn("Truncated src/app.py to 4 characters", warnings)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the collector tests to verify failure**

Run:

```bash
python -m unittest biz.agent.test_context_collector -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'biz.agent.context_collector'`.

- [ ] **Step 3: Implement the collector**

Create `biz/agent/context_collector.py`:

```python
from biz.agent.task import CollectedContext, InvestigationPlan
from biz.agent.tools.file_reader import PlatformFileReader


class ContextCollector:
    def collect(self, plan: InvestigationPlan, file_reader: PlatformFileReader) -> tuple[list[CollectedContext], list[str]]:
        contexts: list[CollectedContext] = []
        warnings: list[str] = []

        for action in plan.actions:
            result = file_reader.read_file(action.path, action.ref)
            if not result.ok:
                warning = f"Failed to read {action.path}: {result.error}"
                warnings.append(warning)
                contexts.append(
                    CollectedContext(
                        path=action.path,
                        ref=action.ref,
                        reason=action.reason,
                        content="",
                        truncated=False,
                        error=result.error,
                    )
                )
                continue

            content = result.content
            truncated = result.truncated
            if len(content) > plan.budget.max_file_chars:
                content = content[: plan.budget.max_file_chars]
                truncated = True

            if truncated:
                warnings.append(f"Truncated {action.path} to {plan.budget.max_file_chars} characters")

            contexts.append(
                CollectedContext(
                    path=action.path,
                    ref=action.ref,
                    reason=action.reason,
                    content=content,
                    truncated=truncated,
                    error=None,
                )
            )

        return contexts, warnings
```

- [ ] **Step 4: Run the collector tests**

Run:

```bash
python -m unittest biz.agent.test_context_collector -v
```

Expected: PASS all tests.

- [ ] **Step 5: Commit**

```bash
git add biz/agent/context_collector.py biz/agent/test_context_collector.py
git commit -m "feat(agent): collect investigation context"
```

## Task 6: Evidence Builder and Agent Prompt

**Files:**
- Create: `biz/agent/evidence_builder.py`
- Test: `biz/agent/test_evidence_builder.py`
- Modify: `conf/prompt_templates.yml`
- Modify: `biz/utils/code_reviewer.py`

- [ ] **Step 1: Write the failing evidence builder test**

Create `biz/agent/test_evidence_builder.py`:

```python
from unittest import TestCase, main

from biz.agent.evidence_builder import EvidenceBuilder
from biz.agent.task import ChangedFile, CollectedContext, DiffAnalysis, ReviewTask


class TestEvidenceBuilder(TestCase):
    def test_builds_evidence_with_diff_context_and_requirements(self):
        task = ReviewTask(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            source_branch="feature/login",
            target_branch="main",
            change_ref="abc123",
            author="octocat",
            url="https://github.com/owner/repo/pull/1",
            commits=[{"message": "Add login validation"}],
            changes=[{"new_path": "src/auth.py", "diff": "+def validate_token():\n+    return True"}],
            access_token="token",
            platform_url="https://github.com",
        )
        analysis = DiffAnalysis(
            files=[ChangedFile("src/auth.py", "python", 2, 0, False, False, ["security"], ["validate_token"])],
            total_additions=2,
            total_deletions=0,
            risk_hints=["security"],
        )
        contexts = [
            CollectedContext(
                path="src/auth.py",
                ref="abc123",
                reason="Read changed file context.",
                content="def validate_token():\n    return True",
            )
        ]

        evidence = EvidenceBuilder().build(task, analysis, contexts, ["related test file not found"])

        self.assertIn("# Commit Messages", evidence)
        self.assertIn("Add login validation", evidence)
        self.assertIn("Risk tags: security", evidence)
        self.assertIn("src/auth.py", evidence)
        self.assertIn("related test file not found", evidence)
        self.assertIn("总分: XX分", evidence)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the evidence test to verify failure**

Run:

```bash
python -m unittest biz.agent.test_evidence_builder -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'biz.agent.evidence_builder'`.

- [ ] **Step 3: Implement the evidence builder**

Create `biz/agent/evidence_builder.py`:

```python
from biz.agent.task import CollectedContext, DiffAnalysis, ReviewTask


class EvidenceBuilder:
    def build(
        self,
        task: ReviewTask,
        analysis: DiffAnalysis,
        contexts: list[CollectedContext],
        warnings: list[str],
    ) -> str:
        sections = [
            "# Task",
            "Review this GitHub pull request as an investigation-style code review Agent.",
            "",
            "# Pull Request",
            f"- Platform: {task.platform}",
            f"- Project: {task.project_name}",
            f"- Source branch: {task.source_branch}",
            f"- Target branch: {task.target_branch}",
            f"- Ref: {task.effective_ref}",
            f"- Author: {task.author}",
            f"- URL: {task.url}",
            "",
            "# Commit Messages",
            self._commit_messages(task.commits),
            "",
            "# Diff Summary",
            self._diff_summary(analysis),
            "",
            "# Code Diff",
            self._code_diff(task.changes),
            "",
            "# Investigation Context",
            self._contexts(contexts),
            "",
            "# Investigation Notes",
            self._warnings(warnings),
            "",
            "# Output Requirements",
            "Return Markdown with these sections:",
            "1. Key issues",
            "2. Potential risks",
            "3. Context investigation summary",
            "4. Recommendations",
            "5. Risk level: low, medium, or high",
            "6. Score in this exact parseable format: 总分: XX分",
            "Distinguish confirmed issues from potential risks. Mention when context is insufficient.",
        ]
        return "\n".join(sections)

    def _commit_messages(self, commits: list[dict]) -> str:
        messages = [commit.get("message", "").strip() for commit in commits if commit.get("message")]
        return "\n".join(f"- {message}" for message in messages) if messages else "- No commit messages provided."

    def _diff_summary(self, analysis: DiffAnalysis) -> str:
        lines = [
            f"- Total additions: {analysis.total_additions}",
            f"- Total deletions: {analysis.total_deletions}",
            f"- Risk hints: {', '.join(analysis.risk_hints) if analysis.risk_hints else 'none'}",
        ]
        for file in analysis.files:
            risk_tags = ", ".join(file.risk_tags) if file.risk_tags else "none"
            symbols = ", ".join(file.changed_symbols) if file.changed_symbols else "none"
            lines.append(
                f"- File: {file.path}; Language: {file.language}; +{file.additions}/-{file.deletions}; "
                f"Risk tags: {risk_tags}; Changed symbols: {symbols}"
            )
        return "\n".join(lines)

    def _code_diff(self, changes: list[dict]) -> str:
        lines = []
        for change in changes:
            lines.append(f"## {change.get('new_path') or change.get('old_path')}")
            lines.append("```diff")
            lines.append(change.get("diff", ""))
            lines.append("```")
        return "\n".join(lines)

    def _contexts(self, contexts: list[CollectedContext]) -> str:
        if not contexts:
            return "- No context files were collected."
        lines = []
        for index, context in enumerate(contexts, start=1):
            lines.extend([
                f"## Context {index}",
                f"- Path: {context.path}",
                f"- Ref: {context.ref}",
                f"- Reason: {context.reason}",
                f"- Truncated: {context.truncated}",
                f"- Error: {context.error or 'none'}",
                "```",
                context.content,
                "```",
            ])
        return "\n".join(lines)

    def _warnings(self, warnings: list[str]) -> str:
        return "\n".join(f"- {warning}" for warning in warnings) if warnings else "- No investigation warnings."
```

- [ ] **Step 4: Add the Agent prompt and reviewer**

Append this prompt key to `conf/prompt_templates.yml`:

```yaml

agent_code_review_prompt:
  system_prompt: |-
    你是一位调查型代码审查 Agent。你会基于 PR diff、提交信息和额外读取的上下文进行审查。
    请保持{{ style }}风格，但必须优先保证技术判断准确。
    输出时要明确区分“确定问题”和“潜在风险”，并说明你检查了哪些上下文。
    如果上下文不足，请直接说明不足，不要编造事实。

  user_prompt: |-
    以下是一次代码审查任务的结构化证据。请基于这些证据输出 Markdown 审查报告。

    {evidence_text}
```

Modify `biz/utils/code_reviewer.py` by adding this class after `CodeReviewer`:

```python
class AgentCodeReviewer(BaseReviewer):
    """Investigation-style review based on structured evidence."""

    def __init__(self):
        super().__init__("agent_code_review_prompt")

    def review_evidence(self, evidence_text: str) -> str:
        review_result = self.review_code(evidence_text).strip()
        if review_result.startswith("```markdown") and review_result.endswith("```"):
            return review_result[11:-3].strip()
        return review_result

    def review_code(self, evidence_text: str) -> str:
        messages = [
            self.prompts["system_message"],
            {
                "role": "user",
                "content": self.prompts["user_message"]["content"].format(evidence_text=evidence_text),
            },
        ]
        return self.call_llm(messages)
```

- [ ] **Step 5: Run evidence builder tests**

Run:

```bash
python -m unittest biz.agent.test_evidence_builder -v
```

Expected: PASS all tests.

- [ ] **Step 6: Commit**

```bash
git add biz/agent/evidence_builder.py biz/agent/test_evidence_builder.py conf/prompt_templates.yml biz/utils/code_reviewer.py
git commit -m "feat(agent): build review evidence prompt"
```

## Task 7: Review Agent Orchestrator

**Files:**
- Create: `biz/agent/review_agent.py`
- Test: `biz/agent/test_review_agent.py`

- [ ] **Step 1: Write the failing orchestrator tests**

Create `biz/agent/test_review_agent.py`:

```python
from unittest import TestCase, main

from biz.agent.review_agent import ReviewAgent
from biz.agent.task import FileReadResult, ReviewTask


class FakeReader:
    def read_file(self, path, ref):
        return FileReadResult(path=path, ref=ref, ok=True, content="def validate_token():\n    return True")


class FakeReviewer:
    def __init__(self, text):
        self.text = text

    def review_evidence(self, evidence):
        self.evidence = evidence
        return self.text


class TestReviewAgent(TestCase):
    def _task(self):
        return ReviewTask(
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            source_branch="feature/login",
            target_branch="main",
            change_ref="abc123",
            author="octocat",
            url="https://github.com/owner/repo/pull/1",
            commits=[{"message": "Add login validation"}],
            changes=[{"new_path": "src/auth.py", "diff": "+def validate_token():\n+    return True", "additions": 2, "deletions": 0}],
            access_token="token",
            platform_url="https://github.com",
        )

    def test_returns_agent_result_with_trace(self):
        reviewer = FakeReviewer("## Review\nRisk level: medium\n总分: 88分")
        result = ReviewAgent(file_reader=FakeReader(), reviewer=reviewer).review(self._task())

        self.assertEqual(result.score, 88)
        self.assertEqual(result.risk_level, "medium")
        self.assertEqual(result.investigated_files, ["src/auth.py"])
        self.assertEqual(result.agent_trace["mode"], "context_investigation")
        self.assertIn("src/auth.py", reviewer.evidence)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the orchestrator test to verify failure**

Run:

```bash
python -m unittest biz.agent.test_review_agent -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'biz.agent.review_agent'`.

- [ ] **Step 3: Implement the orchestrator**

Create `biz/agent/review_agent.py`:

```python
import re

from biz.agent.context_collector import ContextCollector
from biz.agent.diff_analyzer import DiffAnalyzer
from biz.agent.evidence_builder import EvidenceBuilder
from biz.agent.planner import InvestigationPlanner
from biz.agent.task import AgentReviewResult, ReviewTask
from biz.agent.tools.file_reader import PlatformFileReader
from biz.utils.code_reviewer import AgentCodeReviewer, CodeReviewer


class ReviewAgent:
    def __init__(
        self,
        file_reader: PlatformFileReader,
        reviewer: AgentCodeReviewer | None = None,
        analyzer: DiffAnalyzer | None = None,
        planner: InvestigationPlanner | None = None,
        collector: ContextCollector | None = None,
        evidence_builder: EvidenceBuilder | None = None,
    ):
        self.file_reader = file_reader
        self.reviewer = reviewer or AgentCodeReviewer()
        self.analyzer = analyzer or DiffAnalyzer()
        self.planner = planner or InvestigationPlanner()
        self.collector = collector or ContextCollector()
        self.evidence_builder = evidence_builder or EvidenceBuilder()

    def review(self, task: ReviewTask) -> AgentReviewResult:
        analysis = self.analyzer.analyze(task.changes)
        plan = self.planner.create_plan(task, analysis)
        contexts, warnings = self.collector.collect(plan, self.file_reader)
        evidence = self.evidence_builder.build(task, analysis, contexts, warnings)
        review_text = self.reviewer.review_evidence(evidence)
        score = CodeReviewer.parse_review_score(review_text)
        risk_level = self._parse_risk_level(review_text)
        investigated_files = [context.path for context in contexts if context.error is None]
        investigation_summary = self._summary(investigated_files, warnings)
        return AgentReviewResult(
            review_text=review_text,
            score=score,
            risk_level=risk_level,
            investigated_files=investigated_files,
            investigation_summary=investigation_summary,
            warnings=warnings,
            agent_trace={
                "mode": "context_investigation",
                "risk_level": risk_level,
                "investigated_files": [
                    {"path": context.path, "reason": context.reason, "truncated": context.truncated}
                    for context in contexts
                    if context.error is None
                ],
                "warnings": warnings,
                "budget": {
                    "max_context_files": plan.budget.max_context_files,
                    "used_context_files": len(investigated_files),
                },
            },
        )

    def _parse_risk_level(self, review_text: str) -> str:
        match = re.search(r"risk level[:：]\s*(low|medium|high)", review_text, flags=re.IGNORECASE)
        return match.group(1).lower() if match else "medium"

    def _summary(self, investigated_files: list[str], warnings: list[str]) -> str:
        checked = ", ".join(investigated_files) if investigated_files else "no context files"
        if warnings:
            return f"Checked {checked}. Warnings: {'; '.join(warnings)}"
        return f"Checked {checked}."
```

- [ ] **Step 4: Run the orchestrator test**

Run:

```bash
python -m unittest biz.agent.test_review_agent -v
```

Expected: PASS all tests.

- [ ] **Step 5: Commit**

```bash
git add biz/agent/review_agent.py biz/agent/test_review_agent.py
git commit -m "feat(agent): orchestrate investigation review"
```

## Task 8: Persist Agent Trace

**Files:**
- Modify: `biz/entity/review_entity.py`
- Modify: `biz/service/review_service.py`
- Test: `biz/service/test_review_service_agent_trace.py`

- [ ] **Step 1: Write the failing persistence test**

Create `biz/service/test_review_service_agent_trace.py`:

```python
import os
import tempfile
from unittest import TestCase, main

from biz.entity.review_entity import MergeRequestReviewEntity
from biz.service.review_service import ReviewService


class TestReviewServiceAgentTrace(TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        self.original_db = ReviewService.DB_FILE
        ReviewService.DB_FILE = self.tmp.name
        ReviewService.init_db()

    def tearDown(self):
        ReviewService.DB_FILE = self.original_db
        os.unlink(self.tmp.name)

    def test_insert_mr_review_log_stores_agent_trace(self):
        entity = MergeRequestReviewEntity(
            project_name="repo",
            author="octocat",
            source_branch="feature",
            target_branch="main",
            updated_at=1,
            commits=[{"message": "Add feature"}],
            score=90,
            url="https://github.com/owner/repo/pull/1",
            review_result="总分: 90分",
            url_slug="github_com",
            webhook_data={},
            additions=1,
            deletions=0,
            last_commit_id="abc123",
            agent_trace='{"mode": "context_investigation"}',
        )

        ReviewService.insert_mr_review_log(entity)
        df = ReviewService.get_mr_review_logs()

        self.assertEqual(df.iloc[0]["agent_trace"], '{"mode": "context_investigation"}')


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the persistence test to verify failure**

Run:

```bash
python -m unittest biz.service.test_review_service_agent_trace -v
```

Expected: FAIL because `MergeRequestReviewEntity.__init__` does not accept `agent_trace` or query does not return the field.

- [ ] **Step 3: Add `agent_trace` to the entity and service**

Modify `biz/entity/review_entity.py`:

```python
class MergeRequestReviewEntity:
    def __init__(self, project_name: str, author: str, source_branch: str, target_branch: str, updated_at: int,
                 commits: list, score: float, url: str, review_result: str, url_slug: str, webhook_data: dict,
                 additions: int, deletions: int, last_commit_id: str, agent_trace: str = ""):
        self.project_name = project_name
        self.author = author
        self.source_branch = source_branch
        self.target_branch = target_branch
        self.updated_at = updated_at
        self.commits = commits
        self.score = score
        self.url = url
        self.review_result = review_result
        self.url_slug = url_slug
        self.webhook_data = webhook_data
        self.additions = additions
        self.deletions = deletions
        self.last_commit_id = last_commit_id
        self.agent_trace = agent_trace
```

Modify `biz/service/review_service.py`:

```python
cursor.execute('''
        CREATE TABLE IF NOT EXISTS mr_review_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT,
            author TEXT,
            source_branch TEXT,
            target_branch TEXT,
            updated_at INTEGER,
            commit_messages TEXT,
            score INTEGER,
            url TEXT,
            review_result TEXT,
            additions INTEGER DEFAULT 0,
            deletions INTEGER DEFAULT 0,
            last_commit_id TEXT DEFAULT '',
            agent_trace TEXT DEFAULT ''
        )
    ''')
```

Add this migration entry to the existing `mr_columns` list:

```python
{
    "name": "agent_trace",
    "type": "TEXT",
    "default": "''"
}
```

Update `insert_mr_review_log` SQL:

```python
cursor.execute('''
                INSERT INTO mr_review_log (project_name,author, source_branch, target_branch, 
                updated_at, commit_messages, score, url,review_result, additions, deletions, 
                last_commit_id, agent_trace)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
               (entity.project_name, entity.author, entity.source_branch,
                entity.target_branch, entity.updated_at, entity.commit_messages, entity.score,
                entity.url, entity.review_result, entity.additions, entity.deletions,
                entity.last_commit_id, entity.agent_trace))
```

Update `get_mr_review_logs` select:

```python
SELECT project_name, author, source_branch, target_branch, updated_at, commit_messages, score, url, review_result, additions, deletions, agent_trace
FROM mr_review_log
```

- [ ] **Step 4: Run the persistence test**

Run:

```bash
python -m unittest biz.service.test_review_service_agent_trace -v
```

Expected: PASS all tests.

- [ ] **Step 5: Commit**

```bash
git add biz/entity/review_entity.py biz/service/review_service.py biz/service/test_review_service_agent_trace.py
git commit -m "feat(agent): persist review trace"
```

## Task 9: GitHub PR Worker Integration

**Files:**
- Modify: `biz/queue/worker.py`
- Test: `biz/queue/test_github_agent_worker.py`

- [ ] **Step 1: Write the failing worker integration test**

Create `biz/queue/test_github_agent_worker.py`:

```python
import os
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from biz.agent.task import AgentReviewResult


class TestGithubAgentWorker(TestCase):
    def setUp(self):
        os.environ["AGENT_REVIEW_ENABLED"] = "1"

    def tearDown(self):
        os.environ.pop("AGENT_REVIEW_ENABLED", None)

    @patch("biz.queue.worker.event_manager")
    @patch("biz.queue.worker.GitHubFileReader")
    @patch("biz.queue.worker.ReviewAgent")
    @patch("biz.queue.worker.GithubPullRequestHandler")
    @patch("biz.queue.worker.ReviewService.check_mr_last_commit_id_exists", return_value=False)
    def test_github_pr_uses_agent_when_enabled(
        self,
        _check_exists,
        handler_cls,
        agent_cls,
        reader_cls,
        event_manager,
    ):
        webhook_data = {
            "action": "opened",
            "repository": {"name": "repo", "full_name": "owner/repo"},
            "pull_request": {
                "number": 1,
                "head": {"sha": "abc123", "ref": "feature"},
                "base": {"ref": "main"},
                "user": {"login": "octocat"},
                "html_url": "https://github.com/owner/repo/pull/1",
            },
        }
        handler = MagicMock()
        handler.action = "opened"
        handler.get_pull_request_changes.return_value = [
            {"new_path": "src/app.py", "diff": "+print('hello')", "additions": 1, "deletions": 0}
        ]
        handler.get_pull_request_commits.return_value = [{"message": "Add app"}]
        handler_cls.return_value = handler
        agent_cls.return_value.review.return_value = AgentReviewResult(
            review_text="Risk level: low\n总分: 95分",
            score=95,
            risk_level="low",
            investigated_files=["src/app.py"],
            investigation_summary="Checked src/app.py.",
            warnings=[],
            agent_trace={"mode": "context_investigation"},
        )

        from biz.queue.worker import handle_github_pull_request_event

        handle_github_pull_request_event(webhook_data, "token", "https://github.com", "github_com")

        reader_cls.assert_called_once()
        agent_cls.return_value.review.assert_called_once()
        handler.add_pull_request_notes.assert_called_once()
        event_manager["merge_request_reviewed"].send.assert_called_once()
        entity = event_manager["merge_request_reviewed"].send.call_args.args[0]
        self.assertEqual(entity.score, 95)
        self.assertIn("context_investigation", entity.agent_trace)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the worker test to verify failure**

Run:

```bash
python -m unittest biz.queue.test_github_agent_worker -v
```

Expected: FAIL because `GitHubFileReader` and `ReviewAgent` are not imported or used by the worker.

- [ ] **Step 3: Integrate the Agent path in the GitHub PR worker**

Modify imports at the top of `biz/queue/worker.py`:

```python
import json
```

Add these imports:

```python
from biz.agent.review_agent import ReviewAgent
from biz.agent.task import ReviewTask
from biz.agent.tools.file_reader import GitHubFileReader
```

In `handle_github_pull_request_event`, replace the current review block:

```python
commits_text = ';'.join(commit.get('message', '').strip() for commit in commits)
review_result = CodeReviewer().review_and_strip_code(str(changes), commits_text)
```

with:

```python
commits_text = ';'.join(commit.get('message', '').strip() for commit in commits)
agent_trace = ""
agent_review_enabled = os.environ.get('AGENT_REVIEW_ENABLED', '0') == '1'
if agent_review_enabled:
    try:
        task = ReviewTask(
            platform="github",
            project_id=webhook_data['repository']['full_name'],
            project_name=webhook_data['repository']['name'],
            source_branch=webhook_data['pull_request']['head']['ref'],
            target_branch=webhook_data['pull_request']['base']['ref'],
            change_ref=github_last_commit_id,
            author=webhook_data['pull_request']['user']['login'],
            url=webhook_data['pull_request']['html_url'],
            commits=commits,
            changes=changes,
            access_token=github_token,
            platform_url=github_url,
        )
        file_reader = GitHubFileReader(
            repo_full_name=webhook_data['repository']['full_name'],
            token=github_token,
            max_file_chars=int(os.environ.get('AGENT_MAX_FILE_CHARS', 30000)),
        )
        agent_result = ReviewAgent(file_reader=file_reader).review(task)
        review_result = agent_result.review_text
        agent_trace = json.dumps(agent_result.agent_trace, ensure_ascii=False)
    except Exception as agent_error:
        logger.error(f"GitHub Agent review failed, falling back to classic review: {agent_error}")
        review_result = CodeReviewer().review_and_strip_code(str(changes), commits_text)
else:
    review_result = CodeReviewer().review_and_strip_code(str(changes), commits_text)
```

In the `MergeRequestReviewEntity(...)` call, change:

```python
last_commit_id=github_last_commit_id,
```

to:

```python
last_commit_id=github_last_commit_id,
agent_trace=agent_trace,
```

- [ ] **Step 4: Run the worker test**

Run:

```bash
python -m unittest biz.queue.test_github_agent_worker -v
```

Expected: PASS all tests.

- [ ] **Step 5: Run all Agent tests**

Run:

```bash
python -m unittest biz.agent.test_task biz.agent.test_diff_analyzer biz.agent.test_planner biz.agent.tools.test_file_reader biz.agent.test_context_collector biz.agent.test_evidence_builder biz.agent.test_review_agent biz.queue.test_github_agent_worker -v
```

Expected: PASS all tests.

- [ ] **Step 6: Commit**

```bash
git add biz/queue/worker.py biz/queue/test_github_agent_worker.py
git commit -m "feat(agent): enable github pr investigation review"
```

## Task 10: Final Verification

**Files:**
- Modify only if verification exposes a defect in files changed by earlier tasks.

- [ ] **Step 1: Run all focused tests**

Run:

```bash
python -m unittest \
  biz.agent.test_task \
  biz.agent.test_diff_analyzer \
  biz.agent.test_planner \
  biz.agent.tools.test_file_reader \
  biz.agent.test_context_collector \
  biz.agent.test_evidence_builder \
  biz.agent.test_review_agent \
  biz.service.test_review_service_agent_trace \
  biz.queue.test_github_agent_worker \
  -v
```

Expected: PASS all tests.

- [ ] **Step 2: Run existing platform tests**

Run:

```bash
python -m unittest \
  biz.platforms.github.test_webhook_handler \
  biz.platforms.gitlab.test_webhook_handler \
  biz.platforms.gitea.test_webhook_handler \
  -v
```

Expected: PASS existing tests. If an existing test calls a live external API and fails because credentials or network are unavailable, record the exact failure and confirm no Agent code path was involved.

- [ ] **Step 3: Check configuration defaults**

Run:

```bash
python - <<'PY'
import os
print(os.environ.get("AGENT_REVIEW_ENABLED", "0"))
PY
```

Expected output:

```text
0
```

- [ ] **Step 4: Confirm the feature flag guards the new path**

Run:

```bash
rg -n "AGENT_REVIEW_ENABLED|ReviewAgent|GitHubFileReader|agent_trace" biz conf
```

Expected: matches in `biz/queue/worker.py`, `biz/agent/`, `biz/entity/review_entity.py`, `biz/service/review_service.py`, and `conf/prompt_templates.yml`.

- [ ] **Step 5: Commit any verification fixes**

If Step 1 or Step 2 required fixes in Agent files, stage the files owned by this plan and commit them:

```bash
git add biz/agent biz/queue/worker.py biz/queue/test_github_agent_worker.py biz/entity/review_entity.py biz/service/review_service.py biz/service/test_review_service_agent_trace.py conf/prompt_templates.yml biz/utils/code_reviewer.py
git commit -m "fix(agent): address verification issues"
```

If no fixes were required, do not create an empty commit.
