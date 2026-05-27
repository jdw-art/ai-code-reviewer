# Baseline Review 与 Project Deep Review 第二阶段设计

日期：2026-05-28

## 1. 文档定位

本文档是第二阶段的正式设计说明，覆盖：

1. `Baseline Review` 的输出与配置升级。
2. `Project Deep Review` 的项目级会话式调查 Agent。
3. 第二阶段的阶段拆分、工程约束、数据模型和验收标准。

本文档替代“把单条 GitHub PR Agent 直接升级成多轮闭环 Agent”这一中间方案，作为后续 implementation plan 的唯一设计依据。

## 2. 背景

第一阶段已经完成 GitHub-first 的调查型基础审查能力：

1. GitHub PR 在 `AGENT_REVIEW_ENABLED=1` 时可以走 `ReviewAgent` 路径。
2. Agent 可以分析 diff、规划上下文、读取 GitHub 文件、构造 evidence，并生成结构化审查结果。
3. `agent_trace` 可以写入数据库，并按需查询。
4. 失败时可以回退到 classic reviewer。
5. 所有测试已经统一迁移到顶层 `tests/` 目录。
6. 核心 Agent 链路已经补充中文注释和 docstring。

第一阶段的能力更适合作为自动基础审查能力，而不是通用多轮会话 Agent。

## 3. 第二阶段的业务重心

第二阶段不再把重点放在“把每条 PR 的自动审查升级成多轮闭环 Agent”。

第二阶段的业务重心调整为两条并行能力：

1. `Baseline Review`
   继续面向单条 PR/MR 自动产出审查结果，强调稳定、快速、可配置、可解释。

2. `Project Deep Review`
   通过 Dashboard 在项目维度人工发起，对一个项目在一段时间内的多条 PR/MR review 日志做综合调查，输出项目级深度报告。

这两条能力共享部分底层能力，但产品定位不同：

- Baseline Review 的主语是一条 PR/MR。
- Project Deep Review 的主语是一个项目在一个时间范围内的一组 review 日志。

## 4. 第二阶段范围

### 4.1 包含范围

第二阶段包含以下内容：

1. GitHub-only 的第二阶段能力。
2. Baseline Review 的中文化、模版化和评分升级。
3. 仓库级 `ReviewProfile` 选择机制。
4. 两套评论模版：
   - `default_review`
   - `security_review`
5. 项目级 `Project Deep Review` 会话模型。
6. 项目级 Deep Review 的最多两轮闭环调查。
7. 项目级 Deep Review 的上下文管理、工作记忆和会话摘要。
8. 项目级 Deep Review 的只读工具调用框架。
9. Dashboard 中的项目级入口、session 列表和 session 详情工作台。

### 4.2 不包含范围

第二阶段明确不包含以下内容：

1. 不接入 GitLab MR 和 Gitea PR 的第二阶段能力。
2. 不支持 Push Agent review。
3. 不做本地仓库 clone、测试执行、lint 执行、命令执行。
4. 不做无限轮 autonomous loop。
5. 不引入向量库或长期记忆存储。
6. 不做多用户协作、审批流、外部聊天入口。
7. 不做项目级 Deep Review 的自动触发。

## 5. 第一阶段规范继承

第二阶段必须继承并明确执行第一阶段已经建立的工程规范。

### 5.1 测试目录规范

所有测试统一放在顶层 `tests/` 目录下，按模块镜像组织：

```text
tests/
  agent/
  platforms/
  service/
  workers/
```

后续 TDD 继续遵守这一规范，不再把测试文件混在 `biz/` 业务包中。

### 5.2 中文注释规范

核心类、方法、关键复杂逻辑的注释和 docstring 统一使用中文。注释重点解释：

1. 为什么要这样做。
2. 边界和约束是什么。
3. 哪些地方是为审查场景做的特殊处理。

### 5.3 trace 轻量化原则

`agent_trace`、`trace_json`、`working_memory` 只存结构化元数据和摘要，不直接落大段源码内容，避免：

1. 数据库膨胀。
2. 敏感上下文泄露。
3. session 状态不可控增长。

### 5.4 安全边界

第二阶段继续继承第一阶段的 prompt 安全边界：

1. PR 元数据、路径、commit message、diff、上下文都视为不可信输入。
2. 模版中的输出要求优先级必须高于证据文本内容。
3. Deep Review 的会话历史摘要也不能被直接当作可信指令来源。

### 5.5 预算控制

第二阶段虽然引入多轮闭环和项目级 session，但仍然必须受以下预算约束：

1. 文件数预算。
2. token 预算。
3. 每次回答内部的轮次数预算。
4. 工具调用数量预算。

## 6. 总体拆分

第二阶段建议拆成三个顺序执行的子阶段：

1. `2A Baseline 升级`
2. `2B Project Deep Review 后端`
3. `2C Dashboard Deep Review 工作台`

推荐顺序为：

```text
2A -> 2B -> 2C
```

原因：

1. `2A` 先把 baseline 输出质量和模版能力稳定下来。
2. `2B` 在 baseline 摘要质量提高后，再构建项目级 Deep Review 内核。
3. `2C` 最后做 Dashboard 工作台，避免在核心状态机未稳定前反复调整 UI。

## 7. 2A：Baseline Review 升级

### 7.1 目标

Baseline Review 继续使用现有 `ReviewAgent` 承接，不强制升级成多轮闭环 Agent。

第二阶段只升级它的输出表达和配置能力。

### 7.2 包含内容

1. 评论标题统一改为中文。
2. 支持仓库级 `ReviewProfile` 选择。
3. 支持两个 prompt 模版。
4. 评分方式升级为“维度评分 + 总分”。
5. 在 prompt 中明确每个维度的评分依据要求。
6. Dashboard 中 baseline review 的展示增强。

### 7.3 不包含内容

1. 不把 Baseline Review 改成多轮闭环。
2. 不引入 baseline 的会话能力。
3. 不让 baseline 自动演化成项目级分析。

## 8. Baseline Review 模版系统

### 8.1 设计目标

Baseline Review 不再使用单一固定 prompt，而是通过 `ReviewProfile` 选择评论模版。

选择粒度为仓库级。

### 8.2 第一批模版

#### `default_review`

评分维度：

1. 功能正确性
2. 风险控制
3. 测试充分性
4. 可维护性

#### `security_review`

评分维度：

1. 功能正确性
2. 安全与数据风险
3. 测试充分性
4. 架构与可维护性

### 8.3 `ReviewProfile` 结构

第二阶段把“prompt 模版”收敛为结构化 `ReviewProfile`。

每个 `ReviewProfile` 至少定义以下字段：

1. `profile_name`
2. `mode`
3. `dimension_definitions`
4. `section_titles`
5. `prompt_template_id`
6. `total_score_formula`

其中：

1. `mode` 在第二阶段主要支持 `baseline_review`，项目级 Deep Review 后续可复用同一套 profile 思路。
2. `dimension_definitions` 至少包含维度名称、权重、判分关注点。
3. `section_titles` 用于统一中文标题输出。
4. `prompt_template_id` 用于绑定对应提示词模版。
5. `total_score_formula` 用于明确总分的计算方式，避免出现不可解释的综合拍分。

第二阶段先内置两套 profile，不开放 UI 自定义编辑。

### 8.4 配置方式

建议配置：

```text
AGENT_REVIEW_PROFILE=default_review
AGENT_REVIEW_PROFILE_REPOS=jdw-art/ai-code-reviewer:default_review,org/security-service:security_review
```

如果仓库未命中映射，则回退到 `AGENT_REVIEW_PROFILE`。

### 8.5 输出结构

Baseline Review 建议使用以下中文结构：

1. `已确认问题`
2. `待关注风险`
3. `调查摘要`
4. `证据与判断依据`
5. `评分明细`
6. `建议`
7. `风险等级`
8. `总分`

### 8.6 评分要求

不允许只给一个孤立总分。必须同时输出：

1. 各维度得分。
2. 各维度的简短扣分依据。
3. 按模版定义汇总后的总分。

推荐默认规则：

1. 总分满分为 `100`。
2. 第二阶段首批两套 baseline 模版都使用 `4` 个维度，每个维度默认满分 `25`。
3. `总分 = 各维度得分直接求和`，不允许由模型自由心证给出额外综合分。
4. 每个维度至少输出：
   - 维度得分
   - 一句话结论
   - 扣分点列表
   - 对应证据引用
5. 同一个问题默认只在一个主维度扣分，避免重复扣分导致总分失真。
6. 如果证据不足，不直接重扣分，而是在 `待关注风险` 中说明不确定性。

后续如果新增 profile 需要不同权重，必须在 `dimension_definitions` 和 `total_score_formula` 中显式声明。

## 9. 2B：Project Deep Review 后端

### 9.1 目标

Project Deep Review 是项目级、人工发起、会话式的综合调查 Agent。

它的输入不是单条 PR/MR，而是：

1. 一个项目。
2. 一个时间范围。
3. 该时间范围内的一组 baseline review 日志。

### 9.2 关键业务语义

Project Deep Review 会继承 baseline 的结论摘要作为线索，但不会直接复用 baseline 的调查计划。

它会重新生成项目级假设，并围绕项目级风险主题执行最多两轮调查。

### 9.3 解决的问题

Project Deep Review 主要用于回答这类问题：

1. 最近一段时间内项目最集中的风险点是什么。
2. 哪些问题模式在多条 PR/MR 中重复出现。
3. 哪些模块持续不稳定或缺少验证。
4. baseline review 中哪些结论相互印证，哪些只是单点噪声。
5. 是否存在跨多条 PR/MR 才显现的系统性问题。

## 10. Project Deep Review Agent 架构

### 10.1 模式划分

第二阶段的 Agent 能力建议分成两种模式：

1. `baseline_review_mode`
2. `project_deep_review_mode`

Baseline 继续使用现有 `ReviewAgent`，Project Deep Review 使用新的项目级 Agent 内核。

### 10.2 推荐实现路线

Project Deep Review 推荐采用“结构化会话 Agent”方案，而不是纯问答拼接。

关键特征：

1. 有固定会话上下文。
2. 有结构化工作记忆。
3. 每次用户提问内部最多两轮调查。
4. 每轮工具调用和观察结果都会进入 trace。

### 10.3 每次提问的内部流程

用户在 session 中提问后，后台执行：

```text
读取 session 状态
-> 理解问题
-> 选择或生成项目级假设
-> 第 1 轮工具调用
-> 观察结果
-> 判断是否需要第 2 轮
-> 第 2 轮补证
-> 生成中文回答
-> 更新工作记忆和摘要
```

每次回答内部最多两轮。

## 11. Deep Review 的上下文与记忆管理

### 11.1 三层上下文

Project Deep Review 的上下文拆成三层：

1. 固定快照
   - 项目名
   - 时间范围
   - 纳入的 baseline review 日志 ID
   - baseline 摘要快照
   - baseline trace 摘要

2. 工作记忆
   - 当前项目级假设
   - 已确认结论
   - 弱信号
   - 热点模块
   - 未决问题
   - 证据索引

3. 会话摘要
   - 用户已经问过的主题
   - Agent 已经回答的核心结论
   - 已达成共识的方向
   - 已明确放弃的方向

### 11.2 记忆更新规则

每次调查后：

1. 更新工作记忆。
2. 更新会话摘要。
3. 不把完整长上下文整体写回 session。
4. 只写结构化结论和摘要。

## 12. Deep Review 的假设模型

Project Deep Review 不再关注“单条 PR 可能有问题”，而关注“项目在一段时间内是否出现持续性风险模式”。

### 12.1 假设类型

项目级假设建议优先覆盖：

1. 重复出现的风险类型。
2. 热点模块持续不稳定。
3. 跨 PR 才显现的系统性问题。
4. review 证据长期不足。

### 12.2 假设对象

建议结构：

```python
@dataclass
class ProjectReviewHypothesis:
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

状态值：

- `pending`
- `investigating`
- `confirmed`
- `unlikely`
- `insufficient_evidence`

## 13. Project Deep Review 的工具调用

第二阶段工具继续保持只读。

### 13.1 项目聚合工具

建议首批提供：

1. `list_project_review_logs`
2. `read_review_log`
3. `read_review_trace`
4. `group_reviews_by_module`
5. `group_reviews_by_risk_theme`

### 13.2 仓库调查工具

建议首批提供：

1. `read_pr_metadata`
2. `read_pr_diff`
3. `read_repo_file`
4. `read_related_test`
5. `read_local_import`

### 13.3 调用策略

建议：

1. 第一轮优先使用项目聚合工具。
2. 第二轮仅对高价值主题使用仓库调查工具补证。

## 14. 多轮闭环与停止条件

Project Deep Review 每次回答内部最多两轮。

停止条件固定为：

1. 已达到两轮上限。
2. 没有新的高价值动作可执行。
3. 当前高优先级假设全部进入终态。
4. 上下文或工具预算耗尽。

## 15. Deep Review 的数据模型

第二阶段推荐采用“关系表 + JSON 工作记忆”的混合存储。

### 15.1 `project_deep_review_session`

建议字段：

1. `id`
2. `platform`
3. `project_name`
4. `project_id`
5. `profile_name`
6. `time_range_start`
7. `time_range_end`
8. `included_review_log_ids`
9. `baseline_snapshot`
10. `working_memory`
11. `session_summary`
12. `status`
13. `created_by`
14. `created_at`
15. `updated_at`

### 15.2 `project_deep_review_message`

建议字段：

1. `id`
2. `session_id`
3. `role`
4. `content`
5. `created_at`

### 15.3 `project_deep_review_run`

建议字段：

1. `id`
2. `session_id`
3. `user_message_id`
4. `profile_name`
5. `round_count`
6. `stop_reason`
7. `result_markdown`
8. `trace_json`
9. `created_at`

第二阶段不单独拆 `hypothesis` 表，项目级假设先保存在 `working_memory` 和 `trace_json` 中。

## 16. Deep Review 输出结构

Project Deep Review 不适合沿用“单条 PR 发现了哪些问题”的结构，而更像一份阶段性项目调查报告。

建议结构：

1. `项目总体结论`
2. `阶段性高风险主题`
3. `重复出现的问题模式`
4. `热点模块与影响范围`
5. `证据与判断依据`
6. `评分明细`
7. `改进建议`
8. `风险等级`
9. `总分`

### 16.1 项目级评分维度

项目级默认模版建议使用：

1. 功能稳定性
2. 风险控制能力
3. 测试与验证充分性
4. 工程可维护性

项目级安全模版建议使用：

1. 功能稳定性
2. 安全与数据风险控制
3. 测试与验证充分性
4. 架构治理情况

### 16.2 项目级评分计算原则

Project Deep Review 的评分也必须可解释，不使用“仅凭整体印象”的黑盒总分。

建议规则：

1. 默认仍使用 `100` 分制。
2. 首批项目级模版同样采用 `4` 个维度，每个维度默认满分 `25`。
3. `总分 = 各维度得分求和`。
4. 每个维度要输出：
   - 当前项目阶段的判断结论
   - 主要扣分项
   - 支撑该扣分的项目级证据
   - 是否存在反例或证据不足
5. 如果某个结论主要来自 baseline 线索而非二轮补证，必须在说明中标记“证据强度有限”。

## 17. 2C：Dashboard Deep Review 工作台

### 17.1 产品入口

入口位于 Dashboard 的项目维度，不在单条 PR/MR 日志详情下触发。

### 17.2 页面结构

建议最小页面结构：

1. 项目页
   - 选择项目
   - 选择时间范围
   - baseline review 概览
   - 按钮：发起 Deep Review

2. session 列表
   - 展示已有 Project Deep Review session
   - 显示时间范围、模版、状态、更新时间

3. session 详情页
   - baseline 概览
   - 热点模块
   - 风险主题
   - 当前假设状态
   - 对话区
   - 输入框
   - 当前 deep review 回答内容

### 17.3 不做的 UI 内容

第二阶段不做：

1. session 间比较视图
2. 跨项目分析视图
3. 实时协作会话
4. 自动建议发起 deep review

## 18. 实施顺序

第二阶段建议按以下顺序实施：

1. `2A Baseline 升级`
2. `2B Project Deep Review 后端`
3. `2C Dashboard Deep Review 工作台`

## 19. 测试策略

### 19.1 2A 测试重点

1. 仓库级 `ReviewProfile` 选择是否正确。
2. 两套模版是否输出不同中文标题和评分维度。
3. Baseline 评论是否包含维度评分和总分。

### 19.2 2B 测试重点

1. session 创建是否正确冻结 baseline snapshot。
2. 项目级假设是否能稳定生成结构化结果。
3. 每次提问内部是否按预期执行至多两轮调查。
4. 工作记忆和会话摘要是否正确更新。
5. trace 是否包含轮次、工具调用和停止原因。

### 19.3 2C 测试重点

1. 项目入口和时间范围筛选是否正常。
2. session 列表和详情页是否正确展示。
3. Deep Review 提问后结果是否能正确落库并回显。

所有新增测试继续放在顶层 `tests/` 目录中。

## 20. 风险与权衡

### 20.1 风险

1. Project Deep Review 可能引入更高 token 消耗和更长响应时间。
2. 如果项目级假设过多，会让每次提问内部的两轮调查不够聚焦。
3. 如果工作记忆设计过于自由文本化，会让会话越聊越失控。

### 20.2 权衡

第二阶段采用“baseline 继续轻量自动运行，deep review 作为项目级人工发起 Agent”的方案，是为了在产品价值、实现复杂度和可控性之间取得平衡。

它避免了把所有 PR 都强行升级成重型 Agent，同时又给 Dashboard 提供了真正有展示力的 Agent 业务入口。

## 21. 验收标准

第二阶段完成后应满足以下标准。

### 21.1 2A 验收标准

1. Baseline Review 使用中文标题。
2. Baseline Review 支持仓库级模版选择。
3. Baseline Review 评论包含维度评分和总分。
4. 现有 `ReviewAgent` 继续可用并保留 fallback。

### 21.2 2B 验收标准

1. 可以为项目创建 Project Deep Review session。
2. session 能冻结时间范围和 baseline 快照。
3. 用户每次提问内部最多执行两轮调查。
4. Deep Review 能输出项目级中文报告。
5. Deep Review 能记录结构化 trace。

### 21.3 2C 验收标准

1. Dashboard 有项目级入口。
2. Dashboard 支持发起和查看 Project Deep Review session。
3. Dashboard 能展示 baseline 概览、风险主题、会话对话和当前结论。
