# Code Review Agent Design

Date: 2026-05-26

## Goal

Convert the current AI code review pipeline into a first-version investigation-style code review Agent.

The first version focuses on MR/PR review. Instead of sending only diff and commit messages to the LLM, the service will analyze the diff, decide which source context is useful, read that context through platform APIs, build a structured evidence prompt, and produce a review that explains what was investigated.

This is not a general-purpose Agent platform. It is a vertical Agent for code review.

## Current State

The project already has a useful review pipeline:

1. Flask receives GitLab, GitHub, or Gitea webhook events.
2. Platform handlers fetch MR/PR or Push changes and commits.
3. `CodeReviewer` sends diff and commit messages to the configured LLM.
4. The result is written back as a platform comment.
5. Notifications are sent to DingTalk, WeCom, Feishu, or custom webhooks.
6. Review logs are stored in SQLite and shown in the Streamlit dashboard.

The current pipeline is deterministic and single-step. The LLM does not choose tools, inspect related files, or produce a trace of what it checked.

## Scope

Included in the first version:

- MR/PR review only.
- GitLab, GitHub, and Gitea compatibility through a shared file reader interface.
- API-based file reading; no local clone.
- Diff analysis using lightweight rules.
- Rule-driven investigation planning.
- Context collection with strict file and token budgets.
- Structured evidence prompt.
- Investigation summary in the final review.
- Agent trace stored with MR/PR review logs.
- Feature flag to preserve the existing review behavior.
- Graceful fallback to the existing `CodeReviewer` path.

Excluded from the first version:

- Push Agent review.
- Local repository clone, test execution, lint execution, or sandboxed command execution.
- Long-term memory, vector search, or project knowledge base.
- Multi-round autonomous planning loops.
- Dashboard UI for Agent trace details.
- A general tool registry for arbitrary Agents.

## Architecture

Add a new `biz/agent/` package:

```text
biz/agent/
  __init__.py
  task.py
  review_agent.py
  diff_analyzer.py
  planner.py
  context_collector.py
  evidence_builder.py
  tools/
    __init__.py
    file_reader.py
```

Responsibilities:

- `review_agent.py`: Orchestrates one MR/PR investigation review.
- `task.py`: Defines shared task, analysis, plan, context, and result data objects.
- `diff_analyzer.py`: Converts filtered diff changes into structured changed-file metadata.
- `planner.py`: Chooses bounded investigation actions based on diff analysis.
- `context_collector.py`: Executes investigation actions with a platform file reader.
- `evidence_builder.py`: Builds the final LLM input from commits, diff, analysis, context, and investigation notes.
- `tools/file_reader.py`: Defines a platform-neutral API for reading repository files.

Existing responsibilities stay in place:

- `biz/queue/worker.py` remains responsible for event workflow, comments, notifications, and persistence.
- `biz/platforms/*/webhook_handler.py` remains responsible for platform-specific event parsing and MR/PR APIs.
- `biz/utils/code_reviewer.py` remains responsible for LLM calls and score parsing, with an Agent-specific review method or subclass added.

## Core Data Objects

`ReviewTask` represents one MR/PR review:

```python
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
    commits: list[dict]
    changes: list[dict]
    access_token: str
    platform_url: str
```

`change_ref` is the ref used for reading source files. Prefer the MR/PR head commit SHA. If it is unavailable, use the source branch.

`ChangedFile` describes one changed file:

```python
@dataclass
class ChangedFile:
    path: str
    language: str
    additions: int
    deletions: int
    is_test: bool
    is_config: bool
    risk_tags: list[str]
    changed_symbols: list[str]
```

`DiffAnalysis` summarizes all changed files:

```python
@dataclass
class DiffAnalysis:
    files: list[ChangedFile]
    total_additions: int
    total_deletions: int
    risk_hints: list[str]
```

`InvestigationAction` describes one context lookup:

```python
@dataclass
class InvestigationAction:
    action_type: str
    path: str
    ref: str
    reason: str
    priority: int
```

First-version action types:

- `read_changed_file`
- `find_related_test`
- `read_local_import`

`CollectedContext` records the result of one lookup:

```python
@dataclass
class CollectedContext:
    path: str
    ref: str
    reason: str
    content: str
    truncated: bool
    error: str | None
```

`FileReadResult` is returned by platform file readers:

```python
@dataclass
class FileReadResult:
    path: str
    ref: str
    content: str
    ok: bool
    truncated: bool
    error: str | None
```

`AgentReviewResult` is returned to the worker:

```python
@dataclass
class AgentReviewResult:
    review_text: str
    score: int
    risk_level: str
    investigated_files: list[str]
    investigation_summary: str
    warnings: list[str]
    agent_trace: dict
```

## Agent Flow

The first version uses a single bounded investigation pass:

```text
ReviewAgent.review(task)
  -> DiffAnalyzer.analyze(task.changes)
  -> Planner.create_plan(task, diff_analysis)
  -> ContextCollector.collect(plan, file_reader)
  -> EvidenceBuilder.build(task, diff_analysis, contexts)
  -> AgentCodeReviewer.review_evidence(evidence)
  -> parse score and risk level
  -> return AgentReviewResult
```

This gives the system Agent-like behavior without allowing unbounded loops or arbitrary tool use.

## Investigation Strategy

The first planner is rule-driven.

For each changed file:

1. Add a `read_changed_file` action.
2. If the file is not a test, generate likely related test file paths.
3. For supported languages, inspect the changed file content or diff for local imports and add up to two `read_local_import` actions.
4. Prioritize files with risk tags.
5. Enforce file and token budgets.

Lightweight diff analysis rules:

- Language from extension: `.py`, `.js`, `.ts`, `.java`, `.go`, `.php`, `.vue`, `.sql`, `.yml`, `.yaml`.
- Test file if path contains `test`, `tests`, `spec`, or `_test`.
- Config file if path contains `config`, `.env`, `.yml`, `.yaml`, `Dockerfile`, or `docker-compose`.
- Risk tags from path and filename keywords such as `auth`, `token`, `password`, `permission`, `security`, `payment`, `order`, `refund`, `migration`, `sql`, `db`, `api`, `router`, or `controller`.
- Changed symbols from simple patterns such as Python `def` and `class`, JavaScript `function`, TypeScript exported functions/classes, Java methods, and Go `func`.

## Context Budgets

Default values:

```text
AGENT_MAX_CONTEXT_FILES=5
AGENT_MAX_CONTEXT_TOKENS=12000
AGENT_MAX_FILE_CHARS=30000
AGENT_MAX_IMPORT_FILES=2
AGENT_MAX_TEST_FILES=2
```

Priority order:

```text
changed files > related tests > local imports
```

If content exceeds the budget, keep higher-priority context and record skipped or truncated items in the Agent trace.

## Platform File Reader

Define a shared interface:

```python
class PlatformFileReader:
    def read_file(self, path: str, ref: str) -> FileReadResult:
        ...

    def file_exists(self, path: str, ref: str) -> bool:
        ...
```

Implementations:

- `GitLabFileReader`
- `GitHubFileReader`
- `GiteaFileReader`

First-version requirement:

- `read_file` must be implemented.
- `file_exists` may call `read_file` and return true when it succeeds.
- API errors return structured errors instead of crashing the Agent.
- Large files are truncated.
- Binary or generated files are skipped where detectable.

## Evidence Prompt

Add a new prompt key in `conf/prompt_templates.yml`, for example `agent_code_review_prompt`.

The prompt should include:

1. Task instruction: review as an investigation-style code review Agent.
2. Commit messages.
3. Diff summary.
4. Raw diff.
5. Investigation context with file paths, reasons, truncation status, and content.
6. Investigation notes and warnings.
7. Output requirements.

Required output sections:

- Key issues.
- Potential risks.
- Context investigation summary.
- Recommendations.
- Risk level: `low`, `medium`, or `high`.
- Score in the existing parseable format: `总分: XX分`.

The prompt must ask the model to distinguish confirmed issues from potential risks and to mention when context is insufficient.

## Worker Integration

Add feature flags:

```text
AGENT_REVIEW_ENABLED=0
AGENT_MAX_CONTEXT_FILES=5
AGENT_MAX_CONTEXT_TOKENS=12000
AGENT_MAX_FILE_CHARS=30000
```

When `AGENT_REVIEW_ENABLED=1`, MR/PR worker handlers construct a `ReviewTask` and call `ReviewAgent.review(task)`.

When the flag is off, the existing behavior remains unchanged.

If Agent review fails after diff and commits were fetched, fall back to:

```text
CodeReviewer().review_and_strip_code(str(changes), commits_text)
```

This keeps rollout reversible.

## Persistence

Add `agent_trace` to `mr_review_log`.

Store a JSON string like:

```json
{
  "mode": "context_investigation",
  "risk_level": "medium",
  "investigated_files": [
    {
      "path": "biz/service/review_service.py",
      "reason": "changed file context",
      "truncated": false
    }
  ],
  "warnings": [
    "related test file not found"
  ],
  "budget": {
    "max_context_files": 5,
    "used_context_files": 3
  }
}
```

Keep `review_result`, `score`, `additions`, and `deletions` unchanged so the dashboard and daily report continue to work.

Dashboard display of `agent_trace` is deferred.

## Error Handling

Rules:

- Missing diff or commits: keep existing behavior and stop the review.
- File read failure: record a warning and continue.
- Related test not found: record a warning and continue.
- Context budget exceeded: truncate or skip lower-priority context and continue.
- Evidence building failure: fall back to the existing `CodeReviewer`.
- LLM failure: keep the existing error notification path.

The Agent should never make MR/PR review less reliable than the current pipeline.

## Testing

Add focused tests for:

- `DiffAnalyzer`: language detection, test detection, config detection, risk tags, changed symbols.
- `Planner`: expected investigation actions and budget enforcement.
- `ContextCollector`: successful reads, missing files, reader errors, truncation, and warning capture.
- `EvidenceBuilder`: prompt contains commits, diff, context, investigation notes, and output requirements.
- `ReviewAgent`: normal flow and fallback behavior.
- Platform file readers: request construction and response decoding using mocked HTTP responses.

## Rollout Plan

1. Add data objects and `ReviewAgent` skeleton.
2. Add `DiffAnalyzer`.
3. Add `Planner`.
4. Add fake-reader based `ContextCollector`.
5. Add `EvidenceBuilder` and Agent prompt.
6. Add GitLab file reader.
7. Wire GitLab MR handler through `AGENT_REVIEW_ENABLED`.
8. Add GitHub and Gitea file readers and PR integration.
9. Add `agent_trace` persistence.
10. Add tests for Agent modules and file readers.

GitLab should be integrated first because the project is GitLab-first historically and its existing handler is the most complete.

## Success Criteria

- With `AGENT_REVIEW_ENABLED=0`, behavior is unchanged.
- With `AGENT_REVIEW_ENABLED=1`, MR/PR review completes successfully.
- Review output includes a context investigation summary.
- At least changed-file context can be read through the platform API.
- Context read failures do not fail the whole review.
- Context budget limits are enforced.
- `review_result` and `score` remain compatible with the existing dashboard and daily report.
- Agent trace is stored for MR/PR reviews.
- Unit tests cover analyzer, planner, collector, evidence builder, and fallback behavior.
