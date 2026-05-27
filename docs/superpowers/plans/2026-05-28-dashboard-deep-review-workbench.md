# Dashboard Deep Review 工作台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 Streamlit Dashboard 中增加项目级 `Deep Review` 工作台，使用户可以按项目和时间范围创建 session、查看 session 列表、进入详情页并围绕项目发起持续对话式深度审查。

**Architecture:** 保持 `ui.py` 作为 Streamlit 入口，但把 Deep Review 的页面拼装、状态转换和文案格式化抽到新的 `biz/ui/` 辅助模块里。Dashboard 不额外引入 HTTP 中转层，而是直接调用 `ReviewService` 和 `DeepReviewService`，这样能延续当前代码结构并减少第二阶段的接入成本。

**Tech Stack:** Streamlit, Python 3.10+, SQLite, 现有 `ui.py`, `ReviewService`, `DeepReviewService`。

---

## Scope Check

本计划只覆盖第二阶段 `2C Dashboard Deep Review 工作台`。它依赖：

1. `2A` 已经为 baseline review 增加项目元数据和基础展示字段。
2. `2B` 已经提供 `DeepReviewService.create_session_from_review_rows()`、`list_sessions()`、`get_session()`、`list_messages()`、`ask_session_question()`、`get_latest_run()`。

## File Structure

- Create `biz/ui/__init__.py`: Dashboard 辅助模块导出。
- Create `biz/ui/deep_review_dashboard.py`: 项目选择、session 摘要、详情面板、消息列表的纯函数与渲染辅助。
- Modify `ui.py`: 增加项目级 Deep Review 入口、列表和详情工作台。
- Create `tests/ui/test_deep_review_dashboard.py`: 覆盖项目选项、session 标签、回答摘要格式化。
- Modify `README.md`: 补充 Deep Review 工作台的使用方式和环境变量说明。

## Task 1: 提取 Deep Review Dashboard 的纯函数与视图模型

**Files:**
- Create: `biz/ui/__init__.py`
- Create: `biz/ui/deep_review_dashboard.py`
- Create: `tests/ui/test_deep_review_dashboard.py`

- [ ] **Step 1: 先写失败测试，固定项目选项和 session 展示文案**

创建 `tests/ui/test_deep_review_dashboard.py`：

```python
from unittest import TestCase, main

from biz.ui.deep_review_dashboard import build_project_options, format_session_label, summarize_run_result


class TestDeepReviewDashboardHelpers(TestCase):
    def test_build_project_options_deduplicates_and_sorts(self):
        rows = [
            {"project_id": "owner/repo-b", "project_name": "repo-b"},
            {"project_id": "owner/repo-a", "project_name": "repo-a"},
            {"project_id": "owner/repo-a", "project_name": "repo-a"},
        ]

        options = build_project_options(rows)

        self.assertEqual(options, [
            ("owner/repo-a", "repo-a（owner/repo-a）"),
            ("owner/repo-b", "repo-b（owner/repo-b）"),
        ])

    def test_format_session_label_contains_range_and_profile(self):
        session = {
            "id": 7,
            "project_name": "repo",
            "profile_name": "security_review",
            "time_range_start": 1716806400,
            "time_range_end": 1717411199,
        }

        label = format_session_label(session)

        self.assertIn("repo", label)
        self.assertIn("security_review", label)
        self.assertIn("#7", label)

    def test_summarize_run_result_reads_total_score_line(self):
        text = "项目总体结论\\n- 鉴权与测试回归反复出现\\n\\n总分: 68分"
        summary = summarize_run_result(text)

        self.assertIn("68分", summary)
```

- [ ] **Step 2: 跑测试，确认 UI helper 模块还不存在**

Run:

```bash
python -m unittest tests.ui.test_deep_review_dashboard -v
```

Expected: FAIL，提示 `ModuleNotFoundError: No module named 'biz.ui'`。

- [ ] **Step 3: 实现 UI helper 纯函数**

创建 `biz/ui/deep_review_dashboard.py`：

```python
import datetime as dt
import re


def build_project_options(rows: list[dict]) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    for row in rows:
        project_id = row.get("project_id", "")
        project_name = row.get("project_name", project_id)
        if project_id and project_id not in seen:
            seen[project_id] = f"{project_name}（{project_id}）"
    return sorted(seen.items(), key=lambda item: item[0])


def format_session_label(session: dict) -> str:
    start_text = dt.datetime.fromtimestamp(session["time_range_start"]).strftime("%Y-%m-%d")
    end_text = dt.datetime.fromtimestamp(session["time_range_end"]).strftime("%Y-%m-%d")
    return f"#{session['id']} | {session['project_name']} | {session['profile_name']} | {start_text} ~ {end_text}"


def summarize_run_result(markdown_text: str) -> str:
    score_match = re.search(r"总分[:：]\s*(\d+)分?", markdown_text)
    score_text = f"总分 {score_match.group(1)}分" if score_match else "总分未解析"
    first_line = markdown_text.splitlines()[0] if markdown_text else "暂无结论"
    return f"{first_line} | {score_text}"
```

创建 `biz/ui/__init__.py`：

```python
from biz.ui.deep_review_dashboard import (
    build_project_options,
    format_session_label,
    summarize_run_result,
)

__all__ = ["build_project_options", "format_session_label", "summarize_run_result"]
```

- [ ] **Step 4: 再跑 helper 测试**

Run:

```bash
python -m unittest tests.ui.test_deep_review_dashboard -v
```

Expected: PASS。

- [ ] **Step 5: 提交 UI helper 基础层**

```bash
git add biz/ui/__init__.py biz/ui/deep_review_dashboard.py tests/ui/test_deep_review_dashboard.py
git commit -m "feat(ui): add deep review dashboard helpers"
```

## Task 2: 在 Dashboard 中增加项目级入口和 session 创建流程

**Files:**
- Modify: `ui.py`
- Modify: `biz/ui/deep_review_dashboard.py`
- Test: `tests/ui/test_deep_review_dashboard.py`

- [ ] **Step 1: 先补失败测试，锁定项目筛选数据源格式**

在 `tests/ui/test_deep_review_dashboard.py` 增加：

```python
    def test_project_option_label_keeps_repo_id(self):
        options = build_project_options([{"project_id": "owner/repo", "project_name": "repo"}])
        self.assertEqual(options[0][1], "repo（owner/repo）")
```

- [ ] **Step 2: 跑测试，确认 helper 仍稳定**

Run:

```bash
python -m unittest tests.ui.test_deep_review_dashboard -v
```

Expected: PASS。

- [ ] **Step 3: 修改 ui.py，增加项目级 Deep Review 入口**

更新 `ui.py` 顶层 tab：

```python
    deep_review_enabled = os.environ.get("PROJECT_DEEP_REVIEW_ENABLED", "1") == "1"

    if show_push_tab and deep_review_enabled:
        mr_tab, push_tab, project_tab = st.tabs(["合并请求", "代码推送", "项目 Deep Review"])
    elif deep_review_enabled:
        mr_tab, project_tab = st.tabs(["合并请求", "项目 Deep Review"])
    else:
        mr_tab = st.container()
```

在 `project_tab` 中渲染项目选择和创建入口：

```python
    if deep_review_enabled:
        with project_tab:
            review_rows = ReviewService.get_mr_review_logs(
                updated_at_gte=int(start_datetime.timestamp()),
                updated_at_lte=int(end_datetime.timestamp()),
                include_review_metadata=True,
            ).to_dict("records")
            project_options = build_project_options(review_rows)
            if not project_options:
                st.info("当前时间范围内没有可用于 Deep Review 的 baseline 日志。")
                st.stop()
            project_map = {label: project_id for project_id, label in project_options}
            project_label = st.selectbox("选择项目", list(project_map.keys()), key="deep_review_project")
            profile_name = st.selectbox("Deep Review 模版", ["default_review", "security_review"], key="deep_review_profile")

            if st.button("发起 Deep Review", key="create_deep_review_session", use_container_width=True):
                selected_project_id = project_map[project_label]
                selected_rows = filter_rows_by_project(review_rows, selected_project_id)
                session_id = DeepReviewService.create_session_from_review_rows(
                    platform="github",
                    project_id=selected_project_id,
                    project_name=selected_rows[0]["project_name"],
                    profile_name=profile_name,
                    time_range_start=int(start_datetime.timestamp()),
                    time_range_end=int(end_datetime.timestamp()),
                    review_rows=selected_rows,
                    created_by=st.session_state["username"],
                )
                st.session_state["deep_review_session_id"] = session_id
                st.success("Deep Review 会话已创建")
```

为了让 `create_session_from_review_rows()` 成立，同时在 `biz/ui/deep_review_dashboard.py` 增加：

```python
def filter_rows_by_project(rows: list[dict], project_id: str) -> list[dict]:
    return [row for row in rows if row.get("project_id") == project_id]
```

- [ ] **Step 4: 跑 helper 测试并做一次手工检查**

Run:

```bash
python -m unittest tests.ui.test_deep_review_dashboard -v
```

Expected: PASS。

手工检查：

```bash
streamlit run ui.py
```

Manual check:

1. 顶部能看到 `项目 Deep Review` tab。
2. tab 内可以按项目选择仓库。
3. 点击“发起 Deep Review”后不会报错，并能生成 session。

- [ ] **Step 5: 提交项目级入口和 session 创建**

```bash
git add ui.py biz/ui/deep_review_dashboard.py tests/ui/test_deep_review_dashboard.py
git commit -m "feat(ui): add deep review project entry"
```

## Task 3: 增加 session 列表、详情面板和对话工作区

**Files:**
- Modify: `biz/ui/deep_review_dashboard.py`
- Modify: `ui.py`
- Test: `tests/ui/test_deep_review_dashboard.py`

- [ ] **Step 1: 先写失败测试，锁定 session 列表与回答摘要格式**

在 `tests/ui/test_deep_review_dashboard.py` 增加：

```python
    def test_summarize_run_result_returns_first_line_and_score(self):
        result = summarize_run_result("项目总体结论\\n- 持续存在鉴权缺口\\n\\n总分: 61分")
        self.assertIn("项目总体结论", result)
        self.assertIn("61分", result)
```

- [ ] **Step 2: 跑测试，确认 helper 仍然稳定**

Run:

```bash
python -m unittest tests.ui.test_deep_review_dashboard -v
```

Expected: PASS。

- [ ] **Step 3: 在 UI 中增加 session 列表和详情页**

更新 `biz/ui/deep_review_dashboard.py`，增加：

```python
def build_session_options(sessions: list[dict]) -> list[tuple[int, str]]:
    return [(session["id"], format_session_label(session)) for session in sessions]


def build_message_timeline(messages: list[dict]) -> list[dict]:
    return [
        {
            "role": message["role"],
            "content": message["content"],
        }
        for message in messages
    ]
```

在 `ui.py` 的 `project_tab` 中增加：

```python
            sessions = DeepReviewService.list_sessions(project_id=selected_project_id)
            session_options = build_session_options(sessions)
            if session_options:
                session_label_map = {label: session_id for session_id, label in session_options}
                selected_session_label = st.selectbox("历史会话", list(session_label_map.keys()), key="deep_review_session_select")
                selected_session_id = session_label_map[selected_session_label]
                st.session_state["deep_review_session_id"] = selected_session_id
```

并在下方渲染详情区：

```python
            session_id = st.session_state.get("deep_review_session_id")
            if session_id:
                session = DeepReviewService.get_session(session_id)
                messages = DeepReviewService.list_messages(session_id)
                st.subheader("会话详情")
                st.markdown(f"**项目：** {session['project_name']}  \n**模版：** {session['profile_name']}  \n**状态：** {session['status']}")
                for item in build_message_timeline(messages):
                    role_title = "你" if item["role"] == "user" else "Deep Review Agent"
                    with st.expander(role_title, expanded=item["role"] == "assistant"):
                        st.markdown(item["content"])
```

- [ ] **Step 4: 跑测试并做第二次手工 smoke**

Run:

```bash
python -m unittest tests.ui.test_deep_review_dashboard -v
```

Expected: PASS。

再启动：

```bash
streamlit run ui.py
```

Manual check:

1. 能看到同一项目下的 session 列表。
2. 切换 session 时详情区会同步变化。
3. 历史回答可以按消息时间顺序展示。

- [ ] **Step 5: 提交 session 列表与详情工作区**

```bash
git add ui.py biz/ui/deep_review_dashboard.py tests/ui/test_deep_review_dashboard.py
git commit -m "feat(ui): add deep review session workbench"
```

## Task 4: 打通会话提问、结果刷新和用户文档

**Files:**
- Modify: `ui.py`
- Modify: `README.md`
- Test: `tests/ui/test_deep_review_dashboard.py`

- [ ] **Step 1: 写一个小测试，锁定回答摘要能处理空文本**

在 `tests/ui/test_deep_review_dashboard.py` 增加：

```python
    def test_summarize_run_result_handles_empty_text(self):
        self.assertIn("暂无结论", summarize_run_result(""))
```

- [ ] **Step 2: 跑测试，确认 helper 契约齐全**

Run:

```bash
python -m unittest tests.ui.test_deep_review_dashboard -v
```

Expected: PASS。

- [ ] **Step 3: 增加提问输入框、刷新逻辑和 README 说明**

更新 `ui.py`：

```python
                question = st.text_area("继续追问", placeholder="例如：最近一周反复出现的问题模式是什么？", key="deep_review_question")
                if st.button("发送问题", key="deep_review_ask", use_container_width=True):
                    if not question.strip():
                        st.warning("请输入问题后再发送。")
                    else:
                        result = DeepReviewService.ask_session_question(session_id, question.strip())
                        st.success(f"本次调查完成，共执行 {result['round_count']} 轮。")
                        st.rerun()
```

在 session 详情中补充最近一次 run 摘要：

```python
                latest_run = DeepReviewService.get_latest_run(session_id)
                if latest_run:
                    st.info(summarize_run_result(latest_run["result_markdown"]))
```

更新 `README.md` 的 Dashboard 部分：

```markdown
### 项目级 Deep Review

设置 `PROJECT_DEEP_REVIEW_ENABLED=1` 后，Dashboard 会出现“项目 Deep Review”入口。

使用步骤：

1. 选择项目与时间范围。
2. 选择 `default_review` 或 `security_review` 模版。
3. 点击“发起 Deep Review”创建项目级会话。
4. 在会话详情中持续提问，系统会围绕该项目的一组 baseline review 日志做最多两轮的补充调查。
```

- [ ] **Step 4: 跑全量相关测试并做最终手工验收**

Run:

```bash
python -m unittest tests.ui.test_deep_review_dashboard tests.service.test_deep_review_service_schema tests.service.test_deep_review_service_runs tests.agent.deep_review.test_project_deep_review_agent -v
```

Expected: PASS。

最终手工验收：

```bash
streamlit run ui.py
```

Manual check:

1. 创建 session 后可以连续提问。
2. 提问后消息区会新增“用户问题 + Agent 回答”两条记录。
3. 最近一次 run 摘要会刷新。
4. 没有 session 时页面不会抛异常。

- [ ] **Step 5: 提交 Deep Review 工作台闭环**

```bash
git add ui.py README.md tests/ui/test_deep_review_dashboard.py
git commit -m "feat(ui): wire deep review conversation flow"
```
