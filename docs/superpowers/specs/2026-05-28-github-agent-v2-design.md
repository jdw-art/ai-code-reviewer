# GitHub 调查型 Review Agent 第二阶段设计

日期：2026-05-28

## 1. 目标

第二阶段的目标不是继续堆更多上下文读取规则，而是把当前 GitHub-first 的调查型代码审查流程，从“单轮增强版 review”推进成“有限闭环的通用 Agent 框架”。

这一阶段仍然只面向 GitHub Pull Request，不扩展到 GitLab、Gitea，也不引入本地命令执行。核心变化有三点：

1. 审查流程从单轮收口升级为最多两轮的调查闭环。
2. 中间状态从“读取一些文件后直接总结”升级为“先生成假设，再围绕假设取证和收口”。
3. 最终评论从单一英文结构升级为中文模版化输出，并支持仓库级选择不同评分维度组合。

第二阶段交付后，系统会更接近真正的 Agent，但仍然保持可控、可测、可回退。

## 2. 第一阶段现状

第一阶段已经完成以下能力：

1. GitHub PR 事件可以在 `AGENT_REVIEW_ENABLED=1` 时走 `ReviewAgent` 路径。
2. Agent 可以分析 diff、规划上下文、读取 GitHub 文件内容、构造结构化 evidence，并调用 LLM 生成审查结果。
3. `agent_trace` 可以落到数据库，并在查询时按需返回。
4. 失败时可以回退到现有 `CodeReviewer`，保证 webhook 主链路不被 Agent 失败拖垮。
5. 测试目录已经统一迁移到顶层 `tests/`，并补充了核心 Agent 链路的中文注释。

第一阶段的本质仍然是“单轮调查增强”：它会在一次固定流水线中收集更多上下文，但仍然只有一次主要的 LLM 收口过程，没有显式的“观察结果后重新决策下一步”的闭环。

## 3. 第二阶段范围

### 3.1 包含范围

第二阶段包含以下内容：

1. 仅支持 GitHub Pull Request 的 Agent v2。
2. 引入最多两轮的调查闭环。
3. 引入“风险假设”作为中间状态。
4. 引入可扩展的只读工具协议。
5. 引入仓库级评论模版系统。
6. 最终评论统一使用中文标题和中文评分维度。
7. 评分方式改为“维度评分 + 总分”。
8. `agent_trace` 升级为过程级 trace。
9. 保留 classic fallback 和现有 feature flag。

### 3.2 不包含范围

第二阶段明确不做以下内容：

1. 不接入 GitLab MR 和 Gitea PR。
2. 不支持 Push Agent review。
3. 不引入本地仓库 clone、测试执行、lint 执行、命令执行。
4. 不做无限轮 autonomous loop。
5. 不做 dashboard UI 改造。
6. 不做人工审批流或交互式中断。
7. 不做大规模场景特化规则库。

## 4. 设计原则

### 4.1 有限闭环而不是无界自主

第二阶段要跨过“单轮增强版 review”和“真正 Agent”之间的门槛，但仍然必须保持边界明确。闭环固定为：

```text
初始化 -> 生成假设 -> 第 1 轮调查 -> 观察与判断 -> 第 2 轮调查 -> 停止 -> 收口输出
```

系统最多执行两轮调查，不允许无限循环。

### 4.2 假设驱动而不是上下文堆叠

Agent 不再只是“把更多文件喂给模型”，而是先提出 2 到 4 条候选假设，再围绕假设找支持证据和反证，最后按假设状态输出结论。

### 4.3 框架与评论模版解耦

调查闭环属于 Agent 框架，评分维度、中文标题、评论结构属于 `ReviewProfile`。以后新增第三种评论模版，不应该修改 Agent 核心状态机。

### 4.4 继承第一阶段工程规范

第二阶段必须继承并明确执行以下已有规范：

1. 所有测试统一放在顶层 `tests/` 目录下。
2. 核心类、方法、关键复杂逻辑的注释和 docstring 使用中文。
3. `agent_trace` 只落结构化元数据，不直接存大段源码内容。
4. PR 元数据、路径、commit message、diff、上下文都视为不可信输入。
5. 调查过程始终受文件数、token 数和轮次数预算约束。
6. 尽量沿用现有 `biz/agent/` 模块边界演进，不推翻第一阶段已经验证过的底层能力。

## 5. 总体架构

第二阶段继续沿用 `biz/agent/` 作为核心目录，但在其上新增“闭环层”和“模版层”。

建议结构如下：

```text
biz/agent/
  __init__.py
  task.py
  diff_analyzer.py
  context_collector.py
  evidence_builder.py
  planner.py
  review_agent.py
  profile.py
  hypothesis.py
  rounds.py
  planner_v2.py
  review_agent_v2.py
  tools/
    __init__.py
    file_reader.py
    registry.py
```

### 5.1 继续复用的第一阶段模块

以下模块继续作为底层能力保留：

1. `diff_analyzer.py`
   负责把 diff 转成结构化文件画像。
2. `context_collector.py`
   负责执行文件读取、控制预算、记录 warning。
3. `tools/file_reader.py`
   负责通过 GitHub API 读取仓库文件内容。

### 5.2 第二阶段新增模块

1. `profile.py`
   负责定义评论模版、评分维度和仓库到模版的映射关系。
2. `hypothesis.py`
   负责定义风险假设对象及其状态。
3. `rounds.py`
   负责定义调查轮次对象、轮次观察结果和停止判断结构。
4. `tools/registry.py`
   负责定义统一的只读工具协议和工具注册表。
5. `planner_v2.py`
   负责根据当前假设状态和预算，规划某一轮调查动作。
6. `review_agent_v2.py`
   负责 orchestrator：加载 profile、生成假设、执行两轮调查、生成最终评论和完整 trace。

## 6. 核心对象设计

### 6.1 ReviewProfile

`ReviewProfile` 表示当前仓库使用的评论模版配置。它不应只是一个 prompt key，而应该是完整的评论策略对象。

建议字段：

```python
@dataclass
class ReviewProfile:
    profile_name: str
    hypothesis_prompt_key: str
    final_prompt_key: str
    titles: dict[str, str]
    score_dimensions: list["ScoreDimension"]
    total_score_rule: str
```

### 6.2 ScoreDimension

`ScoreDimension` 定义一个评分维度。

建议字段：

```python
@dataclass
class ScoreDimension:
    key: str
    title: str
    description: str
    weight: int
```

### 6.3 ReviewHypothesis

`ReviewHypothesis` 表示一条待验证的风险假设。

建议字段：

```python
@dataclass
class ReviewHypothesis:
    id: str
    title: str
    category: str
    priority: int
    status: str
    reason: str
    supporting_evidence: list[str]
    counter_evidence: list[str]
    open_questions: list[str]
```

状态值固定为：

- `pending`
- `investigating`
- `confirmed`
- `unlikely`
- `insufficient_evidence`

### 6.4 AgentRound

`AgentRound` 表示一轮调查的完整记录。

建议字段：

```python
@dataclass
class AgentRound:
    round_index: int
    goal: str
    selected_hypothesis_ids: list[str]
    planned_actions: list["InvestigationAction"]
    executed_actions: list["ToolCallRecord"]
    observations: list[str]
    budget_usage: dict[str, int]
```

### 6.5 ToolCallRecord

`ToolCallRecord` 是 trace 的最小执行单元。

建议字段：

```python
@dataclass
class ToolCallRecord:
    tool_name: str
    target: str
    reason: str
    success: bool
    truncated: bool
    error: str | None = None
```

### 6.6 StopDecision

`StopDecision` 用于表达为什么结束调查。

建议值：

- `enough_evidence`
- `no_high_value_followup`
- `round_limit_reached`
- `budget_exhausted`

## 7. 多轮闭环流程

### 7.1 初始化

`review_agent_v2.py` 接收现有 `ReviewTask`，并根据 `project_id` 或 GitHub `full_name` 解析出 `ReviewProfile`。

### 7.2 生成初始假设

Agent 先基于以下输入生成候选假设：

1. PR diff
2. commit messages
3. diff 分析结果
4. PR 元数据

这一步的输出是结构化假设列表，而不是最终评论。

### 7.3 第 1 轮调查

第一轮根据假设优先级选取有限动作。首轮目标是：

1. 验证高优先级假设是否成立。
2. 明确哪些假设值得进入第二轮。
3. 找出明显的证据缺口。

### 7.4 观察与重规划

第一轮结束后，Agent 必须做显式观察判断：

1. 哪些假设已经有足够支持证据。
2. 哪些假设被反证削弱。
3. 哪些假设证据不足但仍然值得补查。
4. 是否还有高价值第二轮动作。

### 7.5 第 2 轮调查

第二轮只追查第一轮遗留的高优先级假设，不再做平铺式大范围读取。第二轮更像定向补证。

### 7.6 收口输出

调查结束后，Agent 根据 `ReviewProfile` 使用对应最终 prompt 生成中文评论，并同步产出完整的 `agent_trace`。

## 8. 工具协议

第二阶段先把工具协议做通用化，但首批只落地少量只读工具。

### 8.1 第二阶段首批工具

建议实现以下四类工具：

1. `read_changed_file`
2. `read_related_test`
3. `read_local_import`
4. `read_pr_metadata`

### 8.2 工具接口约束

工具必须满足以下要求：

1. 只读，不允许写仓库或执行命令。
2. 返回统一结果结构，便于 trace 和测试。
3. 工具失败不会直接中断整个 Agent，而是进入 warning 和 trace。
4. 工具执行受预算约束。

## 9. 评论模版系统

### 9.1 目标

第二阶段支持多个评论模版，每个模版定义不同中文标题和评分维度组合。运行时按仓库选择模版。

### 9.2 第一批模版

#### 模版 A：default_review

评分维度：

1. 功能正确性
2. 风险控制
3. 测试充分性
4. 可维护性

#### 模版 B：security_review

评分维度：

1. 功能正确性
2. 安全与数据风险
3. 测试充分性
4. 架构与可维护性

### 9.3 仓库级选择

第二阶段选择粒度为仓库级别。建议通过配置完成映射，不在 worker 中硬编码分支逻辑。

示例：

```text
AGENT_REVIEW_PROFILE=default_review
AGENT_REVIEW_PROFILE_REPOS=jdw-art/ai-code-reviewer:default_review,org/security-service:security_review
```

如果仓库未命中映射，则回退到默认模版。

## 10. 中文评论输出格式

最终评论统一使用中文标题。建议基础结构如下：

1. `已确认问题`
2. `待关注风险`
3. `调查摘要`
4. `证据与判断依据`
5. `评分明细`
6. `建议`
7. `风险等级`
8. `总分`

### 10.1 评分明细要求

第二阶段不允许只给一个孤立的综合总分。必须同时输出：

1. 各维度得分
2. 各维度简短扣分依据
3. 汇总后的总分

这样可以让“总分是怎么得来的”更透明，也更容易让审查对象信服。

### 10.2 总分规则

第二阶段建议总分仍然保留，但总分必须来自模版定义的维度组合，而不是模型自由发挥。即使最终分值仍由 LLM 生成，也要在 prompt 中明确要求它按模版维度逐项说明后再汇总。

## 11. agent_trace 升级

第二阶段的 `agent_trace` 从轻量结果摘要升级为过程 trace，但仍然只存元数据。

建议结构：

```json
{
  "mode": "multi_round_investigation",
  "profile": "default_review",
  "round_limit": 2,
  "rounds": [
    {
      "round_index": 1,
      "goal": "验证高优先级假设并收集基础证据",
      "selected_hypothesis_ids": ["H1", "H2"],
      "tool_calls": [
        {
          "tool_name": "read_changed_file",
          "target": "backend/auth.py",
          "reason": "验证 token 变更",
          "success": true,
          "truncated": false
        }
      ],
      "observations": [
        "H1 获得支持证据",
        "H2 仍需补充测试上下文"
      ]
    }
  ],
  "hypotheses": [
    {
      "id": "H1",
      "title": "tenant 默认回退可能掩盖错误调用",
      "status": "confirmed"
    }
  ],
  "stop_reason": "round_limit_reached",
  "budget_usage": {
    "max_context_files": 8,
    "used_context_files": 6
  },
  "final_assessment": {
    "risk_level": "high",
    "score": 72
  }
}
```

## 12. 停止条件

第二阶段停止逻辑写死成稳定规则，不让模型自行无限扩张：

1. 达到两轮上限时停止。
2. 没有新的高价值动作可执行时停止。
3. 所有高优先级假设都进入终态时停止。
4. 上下文预算耗尽时停止。

这四条保证系统是“闭环”而不是“失控自主”。

## 13. 测试策略

第二阶段测试重点从单函数行为扩展到状态机式验证。

建议重点覆盖：

1. 仓库到 `ReviewProfile` 的映射是否正确。
2. 初始假设是否能稳定产出结构化结果。
3. 第一轮结束后是否能正确决定进入第二轮。
4. 停止条件是否按预期触发。
5. `agent_trace` 是否包含完整轮次信息。
6. 不同评论模版是否输出不同中文标题和评分维度。
7. fallback 是否仍然成立。

所有新增测试继续放在顶层 `tests/` 目录中，遵守第一阶段已经建立的测试目录规范。

## 14. 风险与权衡

### 14.1 风险

1. 多轮闭环会增加 token 消耗和响应时延。
2. 假设生成如果约束不够，可能让第二轮调查方向发散。
3. 评论模版系统如果只做 prompt 文本切换，会导致评分解释仍然不稳定。

### 14.2 权衡

第二阶段选择“最多两轮 + 少量只读工具 + 仓库级模版”的设计，是为了在真实 Agent 行为和工程可控性之间取得平衡。它足以让系统跨过“单轮增强 review”这条线，但又不会把范围扩张到难以验证和维护。

## 15. 验收标准

第二阶段完成后，应满足以下标准：

1. GitHub PR 在 Agent v2 路径下能够执行最多两轮调查。
2. Agent 能生成结构化假设，并按假设状态驱动第二轮动作。
3. 最终评论使用中文标题。
4. 最终评论包含维度评分与总分。
5. 不同仓库可以使用不同评论模版。
6. `agent_trace` 能体现轮次、假设、工具调用和停止原因。
7. 失败时仍可回退到 classic reviewer。

