# Baseline Review 升级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 GitHub Baseline Review 增加仓库级 `ReviewProfile` 选择、中文评论结构、可解释评分规则，以及 Dashboard 里的基础展示升级。

**Architecture:** 延续现有 `ReviewAgent + CodeReviewer + ReviewService + ui.py` 主干，只新增一层轻量 `ReviewProfile` 配置解析与结果元数据持久化。Baseline 仍然是一轮自动审查，不引入会话能力；所有新增信息都围绕“更稳定的输出契约”和“后续 Project Deep Review 可复用的结构化元数据”展开。

**Tech Stack:** Python 3.10+, `unittest`, SQLite, Streamlit, 现有 `ReviewAgent` / `CodeReviewer` / `ReviewService` / GitHub webhook worker。

---

## Scope Check

本计划只覆盖第二阶段 `2A Baseline 升级`。它是 `2B Project Deep Review 后端` 的前置条件，因为项目级 Deep Review 需要依赖 baseline 日志中的 `platform / project_id / review_profile / risk_level` 等结构化元数据。

## File Structure

- Create `biz/agent/review_profile.py`: 定义 `ReviewProfile`、评分维度、仓库级 profile 解析逻辑。
- Modify `biz/agent/task.py`: 为 `ReviewTask` 和 `AgentReviewResult` 增加 baseline 所需的 profile / mode / risk 元数据字段。
- Modify `biz/agent/review_agent.py`: 让 Agent reviewer 与 fallback reviewer 都能感知 `ReviewProfile`，并把 profile 写入 trace。
- Modify `biz/utils/code_reviewer.py`: 让 `CodeReviewer` / `AgentCodeReviewer` 基于 profile 渲染 prompt，并统一中文输出契约。
- Modify `conf/prompt_templates.yml`: 增加 profile 驱动的基线提示词占位符。
- Modify `biz/entity/review_entity.py`: 为合并请求日志实体补充 `platform`、`project_id`、`review_mode`、`review_profile`、`risk_level`。
- Modify `biz/service/review_service.py`: 扩展 `mr_review_log` 表结构与查询方法，持久化 baseline 元数据。
- Modify `biz/queue/worker.py`: 在 GitHub PR 审查链路里解析 repo 级 profile，并把元数据写入日志。
- Modify `ui.py`: 在 MR Dashboard 中展示 baseline 的模式、profile、风险等级，并提供评论详情查看。
- Create `tests/agent/test_review_profile.py`: 覆盖 profile 默认值、仓库映射和非法配置回退。
- Modify `tests/agent/test_task.py`: 覆盖新增 task/result 默认字段。
- Create `tests/agent/test_code_reviewer_profiles.py`: 覆盖不同 profile 下的 prompt 渲染与中文输出要求。
- Modify `tests/agent/test_review_agent.py`: 覆盖 Agent 输出 trace 中的 profile / mode。
- Create `tests/service/test_review_service_baseline_metadata.py`: 覆盖新列建表、插入、查询。
- Modify `tests/workers/test_github_agent_worker.py`: 覆盖 GitHub worker 选择 profile 并写入日志实体。

## Task 1: 增加 ReviewProfile 与仓库级解析

**Files:**
- Create: `biz/agent/review_profile.py`
- Modify: `biz/agent/task.py`
- Test: `tests/agent/test_review_profile.py`
- Test: `tests/agent/test_task.py`

- [ ] **Step 1: 先写失败测试，固定 profile 解析契约**

创建 `tests/agent/test_review_profile.py`：

```python
import os
from unittest import TestCase, main

from biz.agent.review_profile import resolve_review_profile


class TestReviewProfile(TestCase):
    def setUp(self):
        self.old_default = os.environ.get("AGENT_REVIEW_PROFILE")
        self.old_repo_map = os.environ.get("AGENT_REVIEW_PROFILE_REPOS")

    def tearDown(self):
        if self.old_default is None:
            os.environ.pop("AGENT_REVIEW_PROFILE", None)
        else:
            os.environ["AGENT_REVIEW_PROFILE"] = self.old_default

        if self.old_repo_map is None:
            os.environ.pop("AGENT_REVIEW_PROFILE_REPOS", None)
        else:
            os.environ["AGENT_REVIEW_PROFILE_REPOS"] = self.old_repo_map

    def test_repo_mapping_overrides_global_default(self):
        os.environ["AGENT_REVIEW_PROFILE"] = "default_review"
        os.environ["AGENT_REVIEW_PROFILE_REPOS"] = "org/security-service:security_review"

        profile = resolve_review_profile("baseline_review", "org/security-service")

        self.assertEqual(profile.profile_name, "security_review")
        self.assertEqual([item.title for item in profile.dimension_definitions], [
            "功能正确性",
            "安全与数据风险",
            "测试充分性",
            "架构与可维护性",
        ])

    def test_unknown_profile_falls_back_to_default_review(self):
        os.environ["AGENT_REVIEW_PROFILE"] = "unknown_profile"

        profile = resolve_review_profile("baseline_review", "owner/repo")

        self.assertEqual(profile.profile_name, "default_review")
        self.assertEqual(profile.total_score_formula, "sum(dimensions)")


if __name__ == "__main__":
    main()
```

在 `tests/agent/test_task.py` 增加：

```python
    def test_review_task_defaults_to_baseline_review_mode(self):
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

        self.assertEqual(task.review_mode, "baseline_review")
        self.assertEqual(task.review_profile, "default_review")
```

- [ ] **Step 2: 跑测试，确认现在确实失败**

Run:

```bash
python -m unittest tests.agent.test_review_profile tests.agent.test_task -v
```

Expected: FAIL，报 `ModuleNotFoundError: No module named 'biz.agent.review_profile'`，并且 `ReviewTask` 缺少 `review_mode` / `review_profile` 字段。

- [ ] **Step 3: 实现 ReviewProfile 和 task 默认字段**

创建 `biz/agent/review_profile.py`：

```python
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewDimension:
    key: str
    title: str
    weight: int
    guidance: str


@dataclass(frozen=True)
class ReviewProfile:
    profile_name: str
    mode: str
    dimension_definitions: tuple[ReviewDimension, ...]
    section_titles: tuple[str, ...]
    prompt_template_id: str
    total_score_formula: str


BASELINE_PROFILES = {
    "default_review": ReviewProfile(
        profile_name="default_review",
        mode="baseline_review",
        dimension_definitions=(
            ReviewDimension("correctness", "功能正确性", 25, "重点检查功能语义、边界条件和兼容性。"),
            ReviewDimension("risk_control", "风险控制", 25, "重点检查回滚风险、数据风险和变更面。"),
            ReviewDimension("testing", "测试充分性", 25, "重点检查关键路径是否有对应测试。"),
            ReviewDimension("maintainability", "可维护性", 25, "重点检查结构清晰度、命名和后续扩展成本。"),
        ),
        section_titles=("已确认问题", "待关注风险", "调查摘要", "证据与判断依据", "评分明细", "建议", "风险等级", "总分"),
        prompt_template_id="baseline_review_prompt",
        total_score_formula="sum(dimensions)",
    ),
    "security_review": ReviewProfile(
        profile_name="security_review",
        mode="baseline_review",
        dimension_definitions=(
            ReviewDimension("correctness", "功能正确性", 25, "重点检查功能语义、边界条件和兼容性。"),
            ReviewDimension("security", "安全与数据风险", 25, "重点检查鉴权、越权、注入、敏感数据与数据一致性。"),
            ReviewDimension("testing", "测试充分性", 25, "重点检查安全与异常路径是否被验证。"),
            ReviewDimension("architecture", "架构与可维护性", 25, "重点检查职责边界、配置治理和长期演进成本。"),
        ),
        section_titles=("已确认问题", "待关注风险", "调查摘要", "证据与判断依据", "评分明细", "建议", "风险等级", "总分"),
        prompt_template_id="baseline_review_prompt",
        total_score_formula="sum(dimensions)",
    ),
}


def resolve_review_profile(mode: str, repo_full_name: str | None) -> ReviewProfile:
    default_name = os.getenv("AGENT_REVIEW_PROFILE", "default_review")
    repo_mapping = os.getenv("AGENT_REVIEW_PROFILE_REPOS", "")
    selected_name = _resolve_repo_mapping(repo_mapping, repo_full_name) or default_name
    if mode == "baseline_review":
        return BASELINE_PROFILES.get(selected_name, BASELINE_PROFILES["default_review"])
    raise ValueError(f"Unsupported review mode: {mode}")


def get_review_profile(mode: str, profile_name: str) -> ReviewProfile:
    if mode == "baseline_review":
        return BASELINE_PROFILES.get(profile_name, BASELINE_PROFILES["default_review"])
    raise ValueError(f"Unsupported review mode: {mode}")


def _resolve_repo_mapping(raw_mapping: str, repo_full_name: str | None) -> str | None:
    if not raw_mapping or not repo_full_name:
        return None
    for pair in raw_mapping.split(","):
        repo_name, _, profile_name = pair.partition(":")
        if repo_name.strip() == repo_full_name.strip():
            return profile_name.strip()
    return None
```

更新 `biz/agent/task.py`：

```python
    review_mode: str = "baseline_review"
    review_profile: str = "default_review"
```

并在 `AgentReviewResult` 中补充：

```python
    review_mode: str = "baseline_review"
    review_profile: str = "default_review"
```

- [ ] **Step 4: 再跑测试，确认 profile 基础层通过**

Run:

```bash
python -m unittest tests.agent.test_review_profile tests.agent.test_task -v
```

Expected: PASS。

- [ ] **Step 5: 提交这一小步**

```bash
git add biz/agent/review_profile.py biz/agent/task.py tests/agent/test_review_profile.py tests/agent/test_task.py
git commit -m "feat(agent): add baseline review profiles"
```

## Task 2: 让 reviewer 与 Agent 输出变成 profile 驱动的中文评论

**Files:**
- Modify: `biz/utils/code_reviewer.py`
- Modify: `conf/prompt_templates.yml`
- Modify: `biz/agent/review_agent.py`
- Create: `tests/agent/test_code_reviewer_profiles.py`
- Modify: `tests/agent/test_review_agent.py`

- [ ] **Step 1: 写失败测试，锁定中文标题和评分维度**

创建 `tests/agent/test_code_reviewer_profiles.py`：

```python
from unittest import TestCase
from unittest.mock import patch

from biz.utils.code_reviewer import AgentCodeReviewer, CodeReviewer


class TestCodeReviewerProfiles(TestCase):
    @patch("biz.utils.code_reviewer.Factory")
    def test_agent_prompt_contains_default_profile_sections(self, factory_cls):
        factory_cls.return_value.getClient.return_value.completions.return_value = "已确认问题\n总分: 88分"

        reviewer = AgentCodeReviewer(review_profile="default_review")
        reviewer.review_evidence("fake evidence")

        messages = factory_cls.return_value.getClient.return_value.completions.call_args.kwargs["messages"]
        payload = str(messages)
        self.assertIn("已确认问题", payload)
        self.assertIn("评分明细", payload)
        self.assertIn("功能正确性", payload)
        self.assertIn("可维护性", payload)

    @patch("biz.utils.code_reviewer.Factory")
    def test_classic_prompt_contains_security_dimensions(self, factory_cls):
        factory_cls.return_value.getClient.return_value.completions.return_value = "已确认问题\n总分: 80分"

        reviewer = CodeReviewer(review_profile="security_review")
        reviewer.review_and_strip_code("diff text", "commit text")

        messages = factory_cls.return_value.getClient.return_value.completions.call_args.kwargs["messages"]
        payload = str(messages)
        self.assertIn("安全与数据风险", payload)
        self.assertIn("架构与可维护性", payload)
```

在 `tests/agent/test_review_agent.py` 增加：

```python
        self.assertEqual(result.review_profile, "default_review")
        self.assertEqual(result.agent_trace["review_profile"], "default_review")
```

- [ ] **Step 2: 跑测试，确认 prompt 还是旧格式**

Run:

```bash
python -m unittest tests.agent.test_code_reviewer_profiles tests.agent.test_review_agent -v
```

Expected: FAIL，提示 `CodeReviewer.__init__()` 不接受 `review_profile`，且 `agent_trace` 中没有 `review_profile`。

- [ ] **Step 3: 实现 profile 驱动 prompt 与中文输出契约**

更新 `biz/utils/code_reviewer.py` 的构造与 prompt 渲染：

```python
from biz.agent.review_profile import resolve_review_profile


class BaseReviewer(abc.ABC):
    def __init__(self, prompt_key: str, review_profile: str = "default_review", repo_full_name: str | None = None):
        self.client = Factory().getClient()
        resolved_profile = resolve_review_profile("baseline_review", repo_full_name)
        selected_profile_name = review_profile or resolved_profile.profile_name
        self.profile = get_review_profile("baseline_review", selected_profile_name)
        self.prompts = self._load_prompts(prompt_key, os.getenv("REVIEW_STYLE", "professional"))

    def _profile_prompt_context(self) -> dict[str, str]:
        dimension_lines = "\n".join(
            f"- {item.title}（{item.weight}分）：{item.guidance}" for item in self.profile.dimension_definitions
        )
        section_lines = "\n".join(f"{index + 1}. {title}" for index, title in enumerate(self.profile.section_titles))
        return {
            "profile_name": self.profile.profile_name,
            "dimension_lines": dimension_lines,
            "section_lines": section_lines,
            "total_score_formula": "总分 = 各维度得分直接求和，满分 100 分。",
        }
```

把 `CodeReviewer` / `AgentCodeReviewer` 构造改成：

```python
class CodeReviewer(BaseReviewer):
    def __init__(self, review_profile: str = "default_review", repo_full_name: str | None = None):
        self.review_profile_name = review_profile
        self.repo_full_name = repo_full_name
        super().__init__("baseline_review_prompt", review_profile=review_profile, repo_full_name=repo_full_name)

    @staticmethod
    def parse_risk_level(review_text: str) -> str:
        match = re.search(r"(?:风险等级|Risk level)[:：]?\s*(low|medium|high)", review_text, flags=re.IGNORECASE)
        return match.group(1).lower() if match else "medium"
```

把 Agent 输出要求改成中文：

```python
OUTPUT_REQUIREMENTS = """请输出 Markdown，并严格使用以下中文标题：
1. 已确认问题
2. 待关注风险
3. 调查摘要
4. 证据与判断依据
5. 评分明细
6. 建议
7. 风险等级
8. 总分

评分要求：
- 必须给出每个维度的得分和扣分依据
- 总分 = 各维度得分直接求和
- 总分格式必须为：总分: XX分
"""
```

更新 `conf/prompt_templates.yml`：

```yaml
baseline_review_prompt:
  system_prompt: |-
    你是一位资深的软件开发工程师，负责进行结构化代码审查。
    整个评论请保持{{ style }}风格，但优先保证技术判断准确。
    本次审查必须严格遵守以下评分维度：
    {{ dimension_lines }}
    输出时必须严格使用这些中文标题：
    {{ section_lines }}
    {{ total_score_formula }}

  user_prompt: |-
    以下是某次代码审查任务的输入。
    代码变更内容：
    {diffs_text}

    提交历史：
    {commits_text}
```

更新 `biz/agent/review_agent.py`：

```python
    def _default_reviewer(self, task: ReviewTask) -> EvidenceReviewer:
        from biz.utils.code_reviewer import AgentCodeReviewer
        return AgentCodeReviewer(review_profile=task.review_profile, repo_full_name=task.project_id)
```

并在成功返回时补充：

```python
                "review_profile": task.review_profile,
                "review_mode": task.review_mode,
```

- [ ] **Step 4: 跑 reviewer 与 Agent 测试**

Run:

```bash
python -m unittest tests.agent.test_code_reviewer_profiles tests.agent.test_review_agent -v
```

Expected: PASS。

- [ ] **Step 5: 提交 prompt 与输出契约升级**

```bash
git add biz/utils/code_reviewer.py biz/agent/review_agent.py conf/prompt_templates.yml tests/agent/test_code_reviewer_profiles.py tests/agent/test_review_agent.py
git commit -m "feat(agent): add baseline chinese review contract"
```

## Task 3: 持久化 baseline 元数据，并接入 GitHub worker

**Files:**
- Modify: `biz/entity/review_entity.py`
- Modify: `biz/service/review_service.py`
- Modify: `biz/queue/worker.py`
- Create: `tests/service/test_review_service_baseline_metadata.py`
- Modify: `tests/service/test_review_service_agent_trace.py`
- Modify: `tests/workers/test_github_agent_worker.py`

- [ ] **Step 1: 先写失败测试，锁定新列和 worker 透传**

创建 `tests/service/test_review_service_baseline_metadata.py`：

```python
from unittest import TestCase

from biz.entity.review_entity import MergeRequestReviewEntity
from biz.service.review_service import ReviewService


class TestReviewServiceBaselineMetadata(TestCase):
    def test_insert_and_query_baseline_metadata(self):
        entity = MergeRequestReviewEntity(
            project_name="repo",
            project_id="owner/repo",
            platform="github",
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
            review_mode="baseline_review",
            review_profile="security_review",
            risk_level="high",
        )

        ReviewService.insert_mr_review_log(entity)
        df = ReviewService.get_mr_review_logs(include_agent_trace=True, include_review_metadata=True)

        self.assertEqual(df.iloc[0]["platform"], "github")
        self.assertEqual(df.iloc[0]["project_id"], "owner/repo")
        self.assertEqual(df.iloc[0]["review_profile"], "security_review")
        self.assertEqual(df.iloc[0]["risk_level"], "high")
```

在 `tests/workers/test_github_agent_worker.py` 增加：

```python
        self.assertEqual(entity.platform, "github")
        self.assertEqual(entity.project_id, "owner/repo")
        self.assertEqual(entity.review_mode, "baseline_review")
        self.assertEqual(entity.review_profile, "default_review")
```

- [ ] **Step 2: 跑服务层与 worker 测试，确认 schema 还没跟上**

Run:

```bash
python -m unittest tests.service.test_review_service_baseline_metadata tests.service.test_review_service_agent_trace tests.workers.test_github_agent_worker -v
```

Expected: FAIL，报 `MergeRequestReviewEntity.__init__()` 参数不匹配，或数据库查询缺少 `platform` / `project_id` / `review_profile` / `risk_level` 列。

- [ ] **Step 3: 实现实体、数据库字段与 worker 透传**

更新 `biz/entity/review_entity.py`：

```python
class MergeRequestReviewEntity:
    def __init__(
        self,
        project_name: str,
        author: str,
        source_branch: str,
        target_branch: str,
        updated_at: int,
        commits: list,
        score: float,
        url: str,
        review_result: str,
        url_slug: str,
        webhook_data: dict,
        additions: int,
        deletions: int,
        last_commit_id: str,
        agent_trace: str = "",
        platform: str = "github",
        project_id: str = "",
        review_mode: str = "baseline_review",
        review_profile: str = "default_review",
        risk_level: str = "medium",
    ):
        self.platform = platform
        self.project_id = project_id
        self.review_mode = review_mode
        self.review_profile = review_profile
        self.risk_level = risk_level
```

更新 `biz/service/review_service.py`：

```python
                cursor.execute('''
                        CREATE TABLE IF NOT EXISTS mr_review_log (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            platform TEXT DEFAULT 'github',
                            project_id TEXT DEFAULT '',
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
                            agent_trace TEXT DEFAULT '',
                            review_mode TEXT DEFAULT 'baseline_review',
                            review_profile TEXT DEFAULT 'default_review',
                            risk_level TEXT DEFAULT 'medium'
                        )
                    ''')
```

并扩展查询参数：

```python
    def get_mr_review_logs(
        authors: list = None,
        project_names: list = None,
        updated_at_gte: int = None,
        updated_at_lte: int = None,
        include_agent_trace: bool = False,
        include_review_metadata: bool = False,
    ) -> pd.DataFrame:
        columns = "project_name, author, source_branch, target_branch, updated_at, commit_messages, score, url, review_result, additions, deletions"
        if include_review_metadata:
            columns = "platform, project_id, review_mode, review_profile, risk_level, " + columns
```

更新 `biz/queue/worker.py`：

```python
from biz.agent.review_profile import resolve_review_profile

        profile = resolve_review_profile("baseline_review", webhook_data["repository"]["full_name"])
        task = ReviewTask(
            platform="github",
            project_id=webhook_data["repository"]["full_name"],
            project_name=webhook_data["repository"]["name"],
            source_branch=webhook_data["pull_request"]["head"]["ref"],
            target_branch=webhook_data["pull_request"]["base"]["ref"],
            change_ref=github_last_commit_id,
            author=webhook_data["pull_request"]["user"]["login"],
            url=webhook_data["pull_request"]["html_url"],
            commits=commits,
            changes=changes,
            access_token=github_token,
            platform_url=github_url,
            review_mode="baseline_review",
            review_profile=profile.profile_name,
        )
        review_result = CodeReviewer(
            review_profile=profile.profile_name,
            repo_full_name=webhook_data["repository"]["full_name"],
        ).review_and_strip_code(str(changes), commits_text)
        risk_level = CodeReviewer.parse_risk_level(review_result)
        MergeRequestReviewEntity(
            project_name=webhook_data["repository"]["name"],
            author=webhook_data["pull_request"]["user"]["login"],
            source_branch=webhook_data["pull_request"]["head"]["ref"],
            target_branch=webhook_data["pull_request"]["base"]["ref"],
            updated_at=int(datetime.now().timestamp()),
            commits=commits,
            score=score,
            url=webhook_data["pull_request"]["html_url"],
            review_result=review_result,
            url_slug=github_url_slug,
            webhook_data=webhook_data,
            additions=additions,
            deletions=deletions,
            last_commit_id=github_last_commit_id,
            agent_trace=agent_trace,
            platform="github",
            project_id=webhook_data["repository"]["full_name"],
            review_mode="baseline_review",
            review_profile=profile.profile_name,
            risk_level=risk_level,
        )
```

- [ ] **Step 4: 跑数据库与 worker 回归测试**

Run:

```bash
python -m unittest tests.service.test_review_service_baseline_metadata tests.service.test_review_service_agent_trace tests.workers.test_github_agent_worker -v
```

Expected: PASS。

- [ ] **Step 5: 提交 baseline 元数据持久化**

```bash
git add biz/entity/review_entity.py biz/service/review_service.py biz/queue/worker.py tests/service/test_review_service_baseline_metadata.py tests/service/test_review_service_agent_trace.py tests/workers/test_github_agent_worker.py
git commit -m "feat(service): persist baseline review metadata"
```

## Task 4: 升级 Dashboard 的 baseline 展示

**Files:**
- Modify: `ui.py`
- Modify: `biz/service/review_service.py`
- Test: `tests/service/test_review_service_baseline_metadata.py`

- [ ] **Step 1: 先补失败测试，锁定 Dashboard 查询需要的字段**

在 `tests/service/test_review_service_baseline_metadata.py` 增加：

```python
    def test_get_mr_review_logs_includes_dashboard_metadata_when_requested(self):
        df = ReviewService.get_mr_review_logs(include_review_metadata=True)
        self.assertIn("review_mode", df.columns)
        self.assertIn("review_profile", df.columns)
        self.assertIn("risk_level", df.columns)
```

- [ ] **Step 2: 跑服务测试，确认查询契约稳定**

Run:

```bash
python -m unittest tests.service.test_review_service_baseline_metadata -v
```

Expected: PASS；如果 FAIL，先修复 `ReviewService.get_mr_review_logs(authors=None, project_names=None, updated_at_gte=None, updated_at_lte=None, include_agent_trace=False, include_review_metadata=True)`。

- [ ] **Step 3: 修改 Streamlit 页面，展示 baseline 元数据和评论详情**

更新 `ui.py`：

```python
    mr_columns = [
        "project_name",
        "author",
        "source_branch",
        "target_branch",
        "updated_at",
        "review_mode",
        "review_profile",
        "risk_level",
        "commit_messages",
        "delta",
        "score",
        "url",
        "additions",
        "deletions",
    ]
```

调整查询：

```python
            data = service_func(
                authors=authors,
                project_names=project_names,
                updated_at_gte=int(start_datetime.timestamp()),
                updated_at_lte=int(end_datetime.timestamp()),
                include_review_metadata=True,
            )
```

在表格下方补一个详情区：

```python
            if not df.empty and "review_result" in data.columns:
                detail_options = [
                    f"{row['updated_at']} | {row['project_name']} | {row['source_branch']} -> {row['target_branch']}"
                    for _, row in data.iterrows()
                ]
                selected_label = st.selectbox("查看评论详情", detail_options, key=f"{tab}_review_detail")
                selected_index = detail_options.index(selected_label)
                selected_row = data.iloc[selected_index]
                st.markdown(selected_row["review_result"])
```

把列配置补成中文：

```python
        "review_mode": "审查模式",
        "review_profile": "评论模版",
        "risk_level": "风险等级",
```

- [ ] **Step 4: 运行自动化测试并做一次手工 smoke**

Run:

```bash
python -m unittest tests.agent.test_review_profile tests.agent.test_code_reviewer_profiles tests.agent.test_review_agent tests.service.test_review_service_baseline_metadata tests.service.test_review_service_agent_trace tests.workers.test_github_agent_worker -v
```

Expected: PASS。

然后启动 Dashboard：

```bash
streamlit run ui.py
```

Manual check:

1. MR 表格里能看到 `审查模式 / 评论模版 / 风险等级`。
2. 详情区能看到完整 baseline 评论 Markdown。
3. 旧记录即使这些字段为空，也不会让页面报错。

- [ ] **Step 5: 提交 baseline Dashboard 升级**

```bash
git add ui.py biz/service/review_service.py tests/service/test_review_service_baseline_metadata.py
git commit -m "feat(ui): show baseline review metadata"
```
