# CRM Agent 当前架构

- **日期：**2026-09-24
- **用途：**描述现在代码里实际运行的 Agent 体系，供排障、改动和评审对照。
- **权威性：**本文件是当前实现基线。原则仍以 [架构边界](architecture-boundary.md) 和 [LangGraph 原生运行时](../runtime/langgraph-native-runtime.md) 为准；两者与代码冲突时，以本文件记录的代码为准，并应回头修正旧文档。
- **不覆盖：**历史迁移步骤见 [架构切换门禁](../../deployment/agent-architecture-migration.md)。`CRM-Docs/design-agent/README.md` 里的 `root_runtime.py`、`pending_graph.py`、`confirmed_task_graph.py` 是旧入口，当前代码不再使用。

## 一句话

所有用户渠道进入同一个应用服务，由一个 Root LangGraph 决定本轮是只读查询、写入工作流还是澄清；真正的 CRM 读写只通过现有 API 发生。

```text
Web / 飞书
  → AgentApplicationService          会话、消息、租约、幂等
  → RootOrchestrator                 任务关系、能力路由、上下文策略
       ├─ Query Agent                只读，无 checkpoint
       └─ Workflow Subgraph          补字段、确认、写入，可恢复
  → Agent UI Envelope                前后端唯一展示协议
  → CRM API                          权限、事务、审批、真实读写
```

生产组装入口只有一个：`get_root_orchestrator()`，定义在 `CRM-Server/app/services/agent/orchestrator/runtime.py`。

## 职责分层

| 层 | 代码 | 负责 | 不负责 |
| --- | --- | --- | --- |
| 渠道适配 | `app/api/agent.py`、`im_feishu.py`、`im_agent_gateway.py` | 鉴权、SSE、飞书事件、@ 过滤、引用和表情映射 | CRM 语义判断 |
| 应用服务 | `services/agent/application.py` | 会话归属、消息落库、执行租约、UI 投影、结果集签名 | 图内业务分支 |
| Root | `services/agent/orchestrator/` | 上下文装载、任务关系、能力投影、Query/Workflow 分发 | 字段补全和 CRM 写入 |
| 语义 | `semantic.py`、`semantic_plan.py`、`orchestrator/decision.py` | 把自然语言变成闭世界结构化计划 | 授权写入、选择对象 ID |
| Query | `services/agent/query/` | 只读工具、目录、权限约束、分页、结果集 | 改变任何业务状态 |
| Workflow | `services/agent/workflow/` | 规划、interrupt、确认、幂等命令执行 | 重新裁决顶层读/写 |
| Tool | `tool_registry.py`、`tools/api_client.py` | allowlist、入参校验、HITL、调用 CRM API | 直接访问业务表 |
| UI | `services/agent/ui/`、`CRM-Client/src/schemas/agent-contracts/` | 把分发结果投影成 `crm.agent.ui.v1` | 从自然语言文案反推动作 |
| CRM API | 现有业务路由 | 权限、事务、审批、通知 | 理解自然语言 |

LLM 只产出候选语义。服务端负责闭世界投影、权限、对象绑定、枚举、日期、幂等和成功失败判定。

## 一轮请求怎么走

```text
POST /v1/agent/chat/stream
  → 校验 client_request_id，创建或复用 crm_agent_turn_executions
  → 写入用户消息
  → worker 领取租约，签发短时 worker token
  → RootOrchestrator.dispatch()
  → AgentUIComposer 投影
  → 同一事务写入助手消息、UI Action、结果集
  → SSE：session / progress / agent_ui final / done
```

`AgentApplicationService` 在 `main.py` 启动时由 `agent_turn_execution_recovery` 扫描过期租约。恢复前重新检查用户、团队成员和权限；失败码包括 `REAUTHORIZATION_FAILED` 和 `ATTEMPT_LIMIT_REACHED`。

同一 `team_id + user_id + client_request_id` 只能有一条执行。刷新页面后，前端用 `GET /v1/agent/sessions/{session_id}/requests/{client_request_id}` 续上未完成请求。

执行状态：

| 状态 | 含义 |
| --- | --- |
| `ACCEPTED` / `RUNNING` | 对外都是 `IN_PROGRESS` |
| `COMPLETED` | 本轮正常结束 |
| `PARTIALLY_COMMITTED` | Workflow 失败前已经提交了部分命令或 durable work |
| `FAILED` | 不可重试失败 |
| `NEEDS_RECONCILIATION` | 可重试失败或尝试次数耗尽，需要人工或后续对账 |

Root 的 checkpoint 线程不是会话：

```text
crm_agent_turn:{team_id}:{user_id}:{session_id}:{turn_token}
```

会话只是消息容器。跨轮可恢复的是 Workflow interrupt，不是整段聊天线程。

## Root

`RootOrchestrator` 在 `orchestrator/graph.py`。节点顺序：

```text
load_context
  → resolve_deterministic_continuation
  → decide                         仅普通文本
  → validate_decision
  → apply_context_policy
       ├─ QUERY     → query_agent
       ├─ WORKFLOW  → workflow_subgraph → finalize_workflow
       └─ CLARIFY   → build_clarification
  → finalize_dispatch
```

结构化输入不经过决策模型：

- `interaction`：先由 `DatabaseInteractionResolver` 校验服务端签发的 action，再恢复对应 Workflow。
- `workflow_trigger`：服务端自己的触发器，例如跟进确认 Case、商机建议，直接进入 Workflow。
- 文本续跑：只有一个合法 continuation，且用户明确继续当前交互时，才 `CONTINUE_TASK + RESUME`。确认类等待必须走结构化按钮，不能靠自由文本恢复。

`RootDecision` 是闭世界合同：

| 字段 | 取值 |
| --- | --- |
| `task_relation` | `NEW_TASK` / `CONTINUE_TASK` / `SWITCH_TASK` |
| `route` | `QUERY` / `WORKFLOW` / `CLARIFY` |
| `risk` | `READ_ONLY` / `WRITE` |
| `context_policy` | 对选中实体、上次查询、结果集、活动 Workflow、会话记忆分别 `USE/IGNORE` 或 `RESUME/SUSPEND/NONE` |
| `semantic_plan` | 本轮业务语义；缺失即失败关闭 |
| `confidence` | 低于 `0.80` 不能执行，转为澄清 |
| `pending_case_relation` | 只在用户明确引用待确认 Case 时匹配 |

上下文来自 `DatabaseRootContextResolver`，不是模型自己回忆：

- 最近查询和结果集：`crm_agent_query_result_sets`
- 可恢复 Workflow：`crm_agent_ui_actions` 里仍有效的 continuation
- 短时记忆：`crm_agent_sessions.context_json._root_conversation_memory`
- 最近 12 条消息摘要

记忆可以补全省略，不能覆盖本轮明确语义。例如“我本周做了什么”是 `global_work` 查询，即使页面选中了客户或存在旧 Workflow，也必须忽略它们。

### 语义投影

Root Decision Model 先输出 `AgentSemanticPlan`，服务端再投影能力。计划至少包含 `speech_act`、`business_object`、`operation`、`confidence`，查询时还可带 `query_plan`。

当前写入投影（`semantic_plan.py`）：

| 结构化语义 | Workflow intent |
| --- | --- |
| `CUSTOMER_ACTIVITY + CREATE` | `CUSTOMER_ACTIVITY` |
| `CUSTOMER + CREATE` | `CREATE_CUSTOMER` |
| `CONTACT / INVOICE_TITLE / DEPLOYMENT_INFO / CUSTOMER_MEMBER + CREATE` | 各自独立的创建 intent |
| `LEAD + CREATE` | `CREATE_LEAD` |
| `OPPORTUNITY + CREATE` | `CREATE_OPPORTUNITY` |
| `OPPORTUNITY + TRANSITION` | `MOVE_OPPORTUNITY_STAGE` |
| `FOLLOW_UP_TASK + TRANSITION` | `FOLLOW_UP_TASK_TRANSITION` |
| `ASK_FACT + READ` | `QUERY`，风险 `READ_ONLY` |

合同、回款、发票、删除等未列入上表的写入返回 `CLARIFY + SEMANTIC_WRITE_UNSUPPORTED`。不能把它们降级成客户活动，也不能改成查询。

受控恢复只发生一次，且只在两种情况：

1. Root 语义未知或低置信度，无法可靠投影。
2. Root 要求 `CONTINUE_TASK + RESUME`，但服务端没有对应活动 Workflow。

恢复使用 canonical semantic parser（`CRMRootSemanticPlanResolver`），不使用关键词，也不让 Query resolver 改写顶层能力。完整规则见 `docs/adr/0002-root-semantic-route-recovery.md`。

## Query

Query 是无状态 LangChain `create_agent`，只挂只读工具。它不是第二个 Root。

```text
Root 已选择 QUERY
  → 优先使用 semantic_plan.query_plan
  → query_plan 不完整时，LLMQuerySemanticIntentResolver 补充一次
  → CRMQueryAuthority 固化实体、过滤器和范围
  → QueryPolicyValidator + CRMQueryCatalog
  → API Adapter
  → 结果集签名并持久化
```

目录资源：

| resource | adapter |
| --- | --- |
| `customer` | `customers_api` |
| `contact` | `customer_contacts_api` |
| `customer_activity` | `customer_activities_api` |
| `deployment_info` | `deployment_infos_api` |
| `follow_up_task` | `follow_up_tasks_api` |
| `completed_work` | `completed_work_api` |

待办的语义检索只在 Root 已确认只读、且查询计划明确是 `search`、`get_detail` 或 `get_status` 时，由服务端向只读工具注入 `semantic_filter`。模型不能自己扩大检索范围。

结果里的 `entity_ref` 由服务端签发。前端只拿引用打开详情，不接收内部数据库 ID。

## Workflow

`WorkflowSubgraph` 继承 Root checkpointer，每次执行使用独立 child namespace，前缀 `workflow_subgraph:`。

```text
initialize
  → plan
       ├─ 缺字段 → await_required_input → apply_supplement → plan
       ├─ 需确认 → await_confirmation → execute / cancel
       ├─ 取消   → cancel_required_input / cancel_terminal
       └─ 静默跳过 → skip_terminal
  → execute
```

`plan` 由 `CRMWorkflowPlanner` 完成：二次语义补字段、客户绑定、资源排序、跟进质量评分、时间解析、闭世界枚举。它不能把 Root 已确认的写入 intent 改成另一个顶层能力。

`execute` 由 `CRMWorkflowEffectExecutor` 按顺序执行命令。每条命令经过 tool guardrails、资源复核和幂等键，再由 `InternalCRMAPIClient` 调现有 API。已成功的命令记入 `committed_resources`；不可重试失败时退役确认卡，下一轮禁止重放已成功的 create。

等待协议是 `crm.workflow.interrupt.v2`。恢复必须携带精确的 `root_thread_id + parent_checkpoint_id + subgraph checkpoint`。checkpoint 缺失、损坏或 continuation 不一致时失败关闭，不能改用消息文本或旧任务表恢复。

跟进质量沿用 ADR 0001：Agent 路径在写入前评分，`score >= 60` 且下一步行动齐全才调用 `create_final_from_agent()`。页面表单走另一条 durable AIJob，不进这条聊天 Workflow。

## Tool

全部工具在 `tool_registry.py` 的 allowlist 中注册，入参是 Pydantic 模型。写入工具必须经过确认，除非该工具显式声明用户回复本身即确认。

| 类型 | 工具 |
| --- | --- |
| 只读 | `search_customers`、`search_creation_duplicates`、`get_customer_context`、`list_follow_up_tasks`、`get_follow_up_task_detail`、`list_completed_work`、`summarize_completed_work`、`list_follow_up_task_confirmation_cases`、`list_customer_opportunities`、`get_opportunity_detail`、`get_opportunity_procurement_stages` |
| 写入 | `create_customer_activity`、`create_lead`、`create_customer`、`create_lead_follow_up`、`create_contact`、`create_invoice_title`、`create_deployment_info`、`create_customer_member`、`create_opportunity`、`move_opportunity_stage`、`transition_follow_up_task`、`resolve_follow_up_task_confirmation_case`、`create_payment_plan`、`create_payment_record` |

工具注册不等于 Root 已开放该能力。回款工具存在，但当前语义投影不接收回款写入，调用会停在澄清。创建合同没有工具：现有合同创建要求附件。

Query Agent 只能拿到 `include_write_tools=False` 的子集。Workflow 只能执行计划里列出的命令，不能临时改调别的工具。

## 前端协议

协议版本是 `crm.agent.ui.v1`。Python 合同在 `services/agent/ui/schemas.py`，TypeScript 合同在 `CRM-Client/src/schemas/agent-contracts/`。

用户输入只有三种：

| type | 用途 |
| --- | --- |
| `text` | 普通自然语言 |
| `interaction_submission` | 提交服务端签发的 choice / form / confirm |
| `entity_action` | 从结果集实体启动一个已签名 workflow |

助手消息由 block 组成：`text`、`entity_list`、`entity_card`、`table`、`timeline`、`process`、`metric`、`interaction`。交互块的 `state`、`submit_action_id` 和字段约束都由服务端签名；前端提交值后，`InteractionInputResolver` 再校验一次。

动作类型：`open_entity`、`query_refinement`、`start_workflow`、`submit_interaction`、`retry`。Action 有所有权、TTL 和一次性消费；状态错误返回 `ACTION_ALREADY_CONSUMED`、`ACTION_EXPIRED` 等，不重放业务写入。

Web 页面是 `CRM-Client/src/views/AgentChat.vue`，交互主体是 `components/agent/CRMAgentChat.vue`。它消费 SSE，按 `client_request_id` 在本地保存未完成请求，并在刷新后续询。

运行日志不进聊天界面。管理员走 `GET /v1/agent/run-log/turns`，数据来自助手消息 `diagnostics_json.turn_observability`。权限与 AI 配置相同：团队 owner，或 `ai:read` / `ai:manage` / `system:config`。

## 存储

| 表 | 角色 |
| --- | --- |
| `crm_agent_sessions` | 消息容器；`context_json` 只放非 HITL 短时记忆 |
| `crm_agent_messages` | 用户/助手消息、UI JSON、运行日志诊断 |
| `crm_agent_turn_executions` | 一次请求的租约、幂等和恢复账本 |
| `crm_agent_ui_actions` | 可撤销的交互投影和 Workflow continuation |
| `crm_agent_query_result_sets` | 不可变查询结果快照 |
| `crm_agent_workflow_actions` | Workflow 命令审计账本 |
| `crm_agent_tool_calls` | 工具调用审计 |
| `crm_agent_idempotency_keys` | 写入幂等 |
| `crm_agent_async_operations` | 聊天外的后台操作投影 |
| `crm_agent_memory_entries` | LangGraph Store 长时记忆 |
| LangGraph checkpoint 表 | Root/Workflow 暂停与恢复的运行时真相 |

`crm_agent_tasks` 已退出运行时。等待态只认 checkpoint interrupt 和当前 UI Action。

## 聊天之外的图

这些图不进入 Root 的普通文本路由，也不能从 Query/Workflow 节点调用迁移脚本。

| 图 | 入口 | 职责 |
| --- | --- | --- |
| Customer Intelligence | `customer_intelligence_graph.py` | 按 `crm_agent_customer_intelligence:{team}:{event}` 持久运行档案事件 |
| Profile Projection | `customer_profile_projection_graph.py` | 单客户、单 run 的档案刷新 |
| Initial Enrichment | `customer_initial_enrichment_graph.py` | 客户创建后补行业；只计算，不写客户行 |
| Work Summary | `work_summary_graph.py` | 一次临时的工作事实分页、归因和总结 |
| Customer Activity AI | `services/customer_activity_ai/` | 页面保存后的整理、评分和最终化 |
| Post-commit / 商机建议 | durable job + `follow_up_confirmation_projection.py` | 活动写入成功后的任务对账、商机建议和 Agent UI 卡片 |

活动事实、后台副作用和商机创建必须分开。商机建议先出确认卡，确认后再进入 Agent 内嵌表单；它不放进活动写入事务。

## 渠道

Web 和飞书都进 `AgentApplicationService`。

`IMAgentGateway` 只做：

- 用户绑定
- 文本归一
- 群聊 @ 过滤
- 引用消息定位 session
- reaction 映射为确认或拒绝

它不做客户、商机、跟进的语义判断。群聊 session 按 `team + provider + chat + thread + user` 隔离。未引用的“确认/是”只有在唯一可执行确认任务时才绑定。

## 失败怎么收

| 失败点 | 行为 |
| --- | --- |
| Root 模型不可用 | typed failure，不调用 Query 或 Workflow |
| 低置信度或读写矛盾 | `CLARIFY`，reason `LOW_CONFIDENCE` 或 `SEMANTIC_ROUTE_AMBIGUOUS` |
| 不支持的写入 | `CLARIFY + SEMANTIC_WRITE_UNSUPPORTED` |
| Query 上游 408 | `UPSTREAM_TIMEOUT` |
| Query 上游 429/5xx | `UPSTREAM_UNAVAILABLE` |
| checkpoint 不可用 | 首次无 continuation 的调用可显式降级；已有 continuation 的恢复失败关闭 |
| 已提交命令后失败 | `PARTIALLY_COMMITTED`，保留已成功资源 |

模型输出、API 错误和权限失败不能被改写成成功文案。

## 改动时怎么放

- 新的自然语言能力：先加 `AgentSemanticPlan` 的闭世界投影和 Workflow intent，再写 planner。不要在 Root 里加关键词分支。
- 新的只读对象：加 catalog resource、API adapter 和只读 tool。不要给 Query Agent 写工具。
- 新的写入：tool allowlist + planner 命令 + interrupt/确认 + 幂等。不要从 application 直接调 CRM API。
- 新的等待：放在拥有该业务的 subgraph，使用 interrupt。不要把暂停态写进 session context。
- 新渠道：只写适配器，复用 `stream_chat_events()`。
- 历史数据修复：只能走 `scripts/` 下的一次性工具，不能从在线请求调用。
