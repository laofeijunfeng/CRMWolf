# 架构边界

- **用途：**定义 Agent 各层职责和不可跨越的边界。
- **适用范围：**后端服务、LangGraph 编排、LangChain 调用、Tool 实现。
- **权威性：**本文件拥有 Agent 架构边界规则。
- **相关规范：**[LangChain 采用原则](langchain-principles.md) · [Tool 规范](../runtime/tools.md)

## 分层职责

- LangChain：负责模型调用、结构化输出、tool-calling 子 Agent、middleware 能力。
- LangGraph：负责 root graph、domain subgraph、checkpoint、thread、interrupt/resume、conditional edge、streaming 和后续可恢复执行。
- Agent Runtime：负责 graph 调用入口、tool 执行入口、guardrails、幂等、执行结果标准化和事件投影。
- CRM API：负责真实业务读写、权限校验、审批和通知。
- Agent 自有存储：负责会话、消息、LangGraph checkpoint、待确认任务投影、tool 调用记录和幂等键。

## 不可跨越边界

- Agent tool 不得直接访问客户、商机、合同、回款、发票等业务 CRUD/model/table。
- Agent 不得绕过 CRM API 的权限、审批和通知逻辑。
- AI 不得直接决定执行写入动作；写入动作必须经过 HITL。
- Prompt 不得要求模型编造客户、合同、回款计划或对象 ID。
- 不得在 LangGraph 之外再实现一套拥有最终运行时真相的 pending task 状态机。
- `crm_agent_tasks` 不得替代 LangGraph checkpoint；只能作为用户界面和审计的业务投影。

## 推荐编排方式

受控 CRM 流程必须由 LangGraph root graph + domain subgraphs 编排，LangChain 用于语义理解、业务建议和受控 tool-calling 子图。

当业务链路涉及多步写入时，每一步写入都必须有明确上下文、确认任务和可审计 tool 调用记录。

当业务链路需要等待用户输入时，暂停点必须使用 LangGraph interrupt，并通过 resume payload 回到原图节点继续执行。

## 语义候选与确定性裁决（2026-09-03）

Agent 的自然语言理解与业务对象绑定分为两步：

1. Root/Domain LLM 判断本轮任务含义，并在需要时对已授权候选做语义排序；
2. 服务端 resolver 负责权限、归属、状态、候选集和最终 ID 校验。

候选排序器只能接收当前用户有权看到的候选，模型只返回候选序号（ordinal）和置信度，不能返回或创造 CRM 业务 ID。自动选择必须同时满足高置信度和明显领先的 margin；否则回退到既有签名选择交互或澄清，不把模型猜测变成写入。

模型选中候选后必须重新调用 authoritative resolver，以应对候选在模型调用期间被删除、状态变化、权限变化或跨用户提交。服务端复核失败时不得执行 mutation，也不得把失败润色成成功。

自然语言路由、查询/写入判断、待办/跟进/商机/阶段的语义判断不得由正则、关键词表或 substring score 实现。结构化 public ID、UI 序号、字段格式和安全边界校验可以保留确定性解析。

## Root 语义恢复与能力投影（2026-09-03）

Root 是普通文本的顶层路由所有者，但不应该用正则、关键词或 substring 自行理解用户意图。Root Decision Model 必须输出结构化 `semantic_plan`，包括用户是在陈述事件（`ASSERT_EVENT`）、查询事实（`ASK_FACT`）、请求动作（`REQUEST_ACTION`）还是补充/确认当前任务，以及业务对象和操作类型。

对于 Root 初步选择 `QUERY` 或 `CLARIFY` 的普通文本，Root 可以调用一次 canonical CRM semantic parser 进行结构化语义恢复。该恢复专门防止明确写入被错误降级为读取，例如“刚刚和河南双汇技术经理沟通了 POC 部署的问题”必须进入客户活动新增 Workflow，而不是查询历史活动。恢复仍然是 LLM structured output，不读取 Query 结果，也不通过词面规则判断。

恢复后的计划由 Root 做闭世界能力投影，并由共享语义契约统一 Root 与 Workflow 的映射：

- `CUSTOMER_ACTIVITY + CREATE` → `CUSTOMER_ACTIVITY` Workflow intent → `WORKFLOW + WRITE`；
- `CUSTOMER + CREATE` → `CREATE_CUSTOMER` Workflow intent → `WORKFLOW + WRITE`；
- `OPPORTUNITY + CREATE` → `CREATE_OPPORTUNITY` Workflow intent → `WORKFLOW + WRITE`；
- `OPPORTUNITY + TRANSITION` → `MOVE_OPPORTUNITY_STAGE` Workflow intent → `WORKFLOW + WRITE`；
- `FOLLOW_UP_TASK + TRANSITION` → `FOLLOW_UP_TASK_TRANSITION` Workflow intent → `WORKFLOW + WRITE`；
- `ASK_FACT + READ` → `QUERY + READ_ONLY`；
- 不支持的写入 → `CLARIFY`，不得泛化投影到其他业务；
- 低置信度或读写矛盾 → `CLARIFY`，不得静默降级为 Query。

Workflow 的后续详细解析只负责补齐执行字段和业务校验，不能把 Root 已确认的上述写入能力改写成另一个顶层 intent。

Query Executor 必须在语义恢复、能力投影和上下文校验之后才可执行。Query 子 Agent 只能补充查询条件，不能反向改变 Root 的顶层能力。Root 将确认后的语义计划传给 Workflow；Workflow 可以补齐字段并做业务校验，但不得把高置信度的客户活动新增改写成查询或其他顶层意图。

CLARIFY 的处理需要区分阶段：初始模型 CLARIFY 如果被 canonical parser 可靠识别为受支持写入，可以恢复为 Workflow；后续因客户绑定、确认交互或 checkpoint 安全校验产生的服务端 CLARIFY 必须保持终态，避免保护逻辑被重新投影冲掉。完整决策见 `docs/adr/0002-root-semantic-route-recovery.md`。

## 待办语义检索的兼容边界（2026-09-03）

待办查询同时保留两种执行形态，但不由词面或模型自行切换：

- 普通结构化 `CRMQuerySpec` 继续把 `tracking_content` 作为原有 `filters` 传给 CRM API，保证旧调用和页面列表行为兼容；
- 只有 Root 已确认本轮是 `QUERY + READ_ONLY`，且 Query Semantic Plan 明确是 `search`、`get_detail` 或 `get_status` 并提供 `task_text` 时，服务端才向本轮只读工具上下文注入 `semantic_filter` 执行提示；
- 该提示不属于模型可写入的 QuerySpec 字段，模型不能自行扩大语义检索范围；权限、客户范围、状态范围和任务引用仍由 Authority 层强制约束；
- 活动新增、任务状态推进、商机创建/推进等写入请求不经过该提示，也不会因为待办查询能力增强而进入 Query 分支。

因此，语义检索是 Query 能力内部的受控实现选择，不是新的顶层路由器，也不改变普通 CRM 查询的兼容协议。
