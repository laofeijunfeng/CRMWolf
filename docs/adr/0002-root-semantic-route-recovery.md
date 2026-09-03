# ADR 0002：Root 语义路由、能力投影与受控恢复

- **日期：**2026-09-03
- **状态：**Accepted
- **范围：**Agent Root Orchestrator 的普通文本路由，以及客户活动、客户、商机和跟进任务能力的入口保护
- **关联文档：**`CRM-Docs/design-agent/foundations/architecture-boundary.md`

## 背景

Agent 的普通文本需要同时满足两件事：一是像 Agent 一样理解自然语言、识别用户真正要做的事；二是不能因为上下文、某个词或某个子解析器的偏差，误读 CRM 数据或执行错误写入。

此前出现过这样的回归：

> “刚刚和河南双汇技术经理沟通了 POC 部署的问题”

被粗粒度路由判成查询，随后进入客户活动查询，返回历史记录，而不是把用户刚刚陈述的事实交给客户活动 Workflow。

这不是回复文案问题，而是**自然语言语义没有成为顶层能力路由的约束**。用正则、关键词表、substring 或固定话术分支修补，会把 Agent 退化成脆弱的规则工作流，也无法覆盖中文自然表达。

## 决策

### 1. Root 是普通文本唯一的顶层路由所有者

普通文本的唯一入口顺序是：

```text
普通文本
  → Root Decision Model
  → 结构化 semantic_plan
  → 服务端闭世界能力投影
  → QUERY / WORKFLOW / CLARIFY
```

Root Decision Model 必须从本轮完整输入和受控上下文中理解：

- 用户是在陈述刚刚发生的事件；
- 用户是在查询已有事实；
- 用户是在要求改变业务状态；
- 用户是在补充、确认或取消当前任务；
- 本轮是新任务、承接当前任务，还是切换到独立任务。

模型输出结构化 `semantic_plan`，至少包含：

- `speech_act`；
- `business_object`；
- `operation`；
- `confidence`；
- 可选的客户引用、活动内容和查询计划。

Root 只对结构化计划执行闭世界能力投影、上下文策略校验、权限边界和失败关闭。Root 不得使用以下方式进行自然语言顶层路由：

- 正则表达式匹配用户语义；
- 关键词表或 substring 命中；
- 通过 Query 结果反推用户意图；
- 让 Query Semantic Resolver 重新裁决 Root 已经选择的顶层能力。

允许使用确定性代码做服务器安全绑定，例如 public ID 格式校验、UI 序号绑定、日期格式解析、数据库字段过滤，以及对模型已经输出的结构化条件做校验。这些不是自然语言意图路由。

### 2. Root 语义计划是共享语义，不是写入授权

`semantic_plan` 是 Root 与下游能力之间共享的业务语义。它用于防止“陈述事件”和“查询历史”被混淆，但不直接授权 CRM mutation。

- Root 负责判断本轮能力和任务边界；
- Query 模块负责受限只读查询；
- Workflow 负责详细字段、客户绑定、评分、确认、幂等和写入；
- CRM API、权限和事务边界负责最终真实读写。

因此，即使 Root 输出了可靠的写入语义，也必须进入对应 Workflow，不能直接调用 CRM 写入接口。

### 3. 结构化语义按闭世界能力投影

当前支持的写入入口为：

| Root 结构化语义 | 能力路由 | Workflow 执行意图 |
| --- | --- | --- |
| `CUSTOMER_ACTIVITY + CREATE` | `WORKFLOW + WRITE` | `CUSTOMER_ACTIVITY` |
| `CUSTOMER + CREATE` | `WORKFLOW + WRITE` | `CREATE_CUSTOMER` |
| `OPPORTUNITY + CREATE` | `WORKFLOW + WRITE` | `CREATE_OPPORTUNITY` |
| `OPPORTUNITY + TRANSITION` | `WORKFLOW + WRITE` | `MOVE_OPPORTUNITY_STAGE` |
| `FOLLOW_UP_TASK + TRANSITION` | `WORKFLOW + WRITE` | `FOLLOW_UP_TASK_TRANSITION` |

读取语义按以下规则投影：

```text
ASK_FACT + READ → QUERY + READ_ONLY
```

本期不支持的写入（例如回款、合同、线索、联系人、发票抬头、部署信息、客户成员）保留其业务对象语义，返回：

```text
CLARIFY + SEMANTIC_WRITE_UNSUPPORTED
```

不能把不支持的写入泛化成客户活动，也不能静默降级成查询。

### 4. 只有 Root 选择 QUERY 后，Query Semantic Resolver 才能补充查询参数

Query Semantic Resolver 是 Query 能力内部的参数补充器，不是第二个 Root。它的边界是：

```text
Root 已选择 QUERY
  → 优先使用 Root.semantic_plan.query_plan
  → query_plan 不完整时，调用一次 Query Semantic Resolver
  → Query Executor 只读执行
```

它可以补充：

- 查询范围（例如 `global_work`、`customer_scoped`）；
- 资源（例如 `follow_up_tasks`、`completed_work`、`customer_activities`）；
- 查询目标；
- 时间范围；
- 客户文本引用或任务文本引用。

它不能：

- 把 `WORKFLOW` 改成 `QUERY`；
- 把 `CLARIFY` 改成 `QUERY`；
- 覆盖 Root 已确认的可靠写入语义；
- 通过关键词或查询结果改变顶层路由。

当 Root 已提供完整 `query_plan` 时，不再重复调用 Query Semantic Resolver。同一轮的解析结果放入 runtime cache，避免 Root 恢复、Query 和 Workflow 重复请求模型。

### 5. 只在 Root 结果不可执行时做一次受控语义恢复

canonical semantic parser 只作为**结构化语义恢复 seam**，不是常规顶层路由器。

允许恢复的情况只有两类：

1. Root 语义未知或低置信度，无法可靠投影为读或写；
2. Root 输出 `CONTINUE_TASK + WORKFLOW + RESUME`，但服务端发现当前没有对应 active Workflow，说明 continuation 上下文不可能成立。

恢复顺序为：

```text
Root Decision
  → 检查 semantic_plan 与 continuation 是否可执行
  → 必要时调用一次 canonical semantic parser
  → 将恢复出的结构化语义重新投影到闭世界能力
  → QUERY / WORKFLOW / CLARIFY
```

恢复规则：

- 可靠的 `ASSERT_EVENT + CUSTOMER_ACTIVITY + CREATE` 必须进入客户活动 Workflow；
- 可靠的 `ASK_FACT + READ` 才能进入 Query；
- 可靠但本期不支持的写入必须澄清；
- 恢复失败、低置信度或语义不闭合时，不能猜测；
- 无效 continuation 恢复出的请求必须重置为新任务，不能残留 `RESUME`、旧查询或旧结果集策略。

恢复不得依赖用户文本关键词，也不得让 Query-only resolver 参与恢复顶层读写裁决。

### 6. 上下文是受控记忆，不是意图覆盖器

Agent 可以记住客户、当前任务、最近查询、结果集和可恢复 Workflow，但记忆只能帮助模型理解省略表达，不能覆盖本轮明确语义。

- 明确的新查询或新写入必须是 `SWITCH_TASK`，挂起旧 Workflow，不误恢复；
- 明确继续当前交互且存在唯一合法 continuation，才允许 `CONTINUE_TASK + RESUME`；
- 没有 active Workflow 时不得输出可执行的 `RESUME`；
- “我本周做了什么”是独立的全局工作查询，即使页面选中了客户或会话存在活动 Workflow，也不能被旧客户上下文吞掉；
- 普通客户活动陈述不能因为存在 pending case 而自动恢复历史待办，除非用户明确引用且服务端唯一绑定。

### 7. Query 与 Workflow 保持原子隔离

两条能力链路必须保持清晰的原子边界：

```text
QUERY
  → 只读
  → 不创建客户活动
  → 不改变跟进任务状态
  → 不创建或推进商机

WORKFLOW
  → 负责一项明确业务操作
  → 自己完成补充、评分、确认、幂等和写入
  → 不借用 Query 结果替代用户意图
```

本轮路由优化只保护入口，不改写现有客户活动 Workflow、跟进任务状态变更、商机创建/推进、页面表单、确认交互和后台任务的业务步骤。

### 8. 失败必须可解释且失败关闭

模型、解析、上下文或 CRM 依赖异常时，系统返回 typed failure 或有针对性的澄清，不执行猜测性读写。

尤其不能出现：

```text
用户陈述写入事实
  → 解析异常
  → 默认进入客户活动查询
  → 返回一条看似正常的历史记录
```

## 失败策略

| 情况 | 处理 |
| --- | --- |
| Root 模型不可用 | 返回 Root typed failure，不调用 Query 或 Workflow |
| Root 输出完整可靠 Query plan | 直接 Query，不调用 Query Semantic Resolver |
| Root 输出 Query 但 Query plan 不完整 | Query Semantic Resolver 补充一次；失败则返回 Query typed failure/澄清 |
| Root 语义未知、低置信度，或 continuation 不可能成立 | 允许一次 canonical semantic recovery |
| canonical recovery 不可用 | 保留 Root 的安全结果；无法确认时澄清，不猜测 |
| canonical recovery 是可靠支持写入 | 按结构化计划进入对应 Workflow |
| canonical recovery 是可靠本期不支持写入 | `CLARIFY + SEMANTIC_WRITE_UNSUPPORTED` |
| 读写语义矛盾且置信度不足 | `CLARIFY + SEMANTIC_ROUTE_AMBIGUOUS` |
| Query Executor 在路由确认前 | 禁止 CRM 读取 |
| Query 试图改变状态 | 禁止，Query 只读 |
| active Workflow 不存在但模型要求 RESUME | 不恢复旧任务；必要时做一次 canonical recovery，仍不明确则澄清 |

## 回归防护

本次优化不以“改完代码后人工看几条返回”为验收标准，而以 Root 公共 seam 的行为测试锁定边界。至少持续验证：

1. “刚刚和河南双汇技术经理沟通了 POC 部署的问题”进入客户活动 Workflow，Query Executor 调用次数为 0；
2. “查询河南双汇最近的跟进记录”进入 Query，风险为 `READ_ONLY`，Workflow 调用次数为 0；
3. “我本周做了什么”进入 `global_work` 只读查询，忽略旧 selected customer 和旧 Workflow；
4. Root 输出 QUERY 但 semantic plan 是可靠客户活动写入时，纠正为 Workflow；
5. Root 输出 WORKFLOW/RESUME 但没有 active Workflow 时，不使用 Query-only resolver 偷换成查询；
6. Root 输出可靠 Query plan 时不重复调用 Query Semantic Resolver；
7. 低置信度写入不能进入 Query；
8. 回款等不支持写入不能进入 Workflow；
9. 已有确认交互、多个可恢复 Workflow、pending case 绑定和上下文缺失保护保持原有行为；
10. 客户活动、跟进任务和商机能力仍由各自 Workflow 原子执行。

对应测试文件：

```text
CRM-Server/tests/unit/test_agent_root_orchestrator.py
CRM-Server/tests/unit/test_agent_query_executor.py
CRM-Server/tests/unit/test_agent_query_semantic_intent.py
CRM-Server/tests/unit/test_agent_workflow_subgraph.py
CRM-Server/tests/unit/test_customer_activity_ai_workflow.py
```

## 结果

该设计把 Agent 的职责分层清楚：

```text
LLM：理解本轮自然语言
Root：决定顶层任务关系和能力边界
Query：受限只读
Workflow：执行一项明确业务操作
CRM API：负责最终权限、事务和真实读写
```

因此，本次优化不会通过正则或关键词把某个流程“硬拽”到另一条链路，也不会让 Query 子模块重新成为顶层路由器。已有业务流程通过闭世界投影、原子隔离、失败关闭和回归测试保护；新能力只在 Root 明确选择后进入对应能力链路。
