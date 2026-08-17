# LangGraph 原生运行时规范

- **用途：**定义 CRM AI Agent 如何把 LangGraph 作为长期运行、有状态、可恢复的核心运行时。
- **适用范围：**Agent 主入口、业务子图、HITL、跨轮恢复、工具执行、观测和回放。
- **权威性：**本文件拥有 LangGraph runtime 采用规则；与旧 pending task 方案冲突时，以本文件为准。
- **相关规范：**[Memory 规范](memory.md) · [交互编排策略](interaction-policy.md) · [HITL 与 Guardrails](hitl-guardrails.md) · [架构边界](../foundations/architecture-boundary.md)

## 官方能力映射

CRMWolf 采用 LangGraph 的目标不是把流程节点图形化，而是使用它提供的长期运行 Agent 运行时能力：

- `StateGraph`：承载业务状态机和节点间状态合并。
- `thread_id`：绑定同一用户、同一会话、同一 IM thread 的连续交互。
- checkpointer：持久化每一步图状态，让刷新页面、服务重启、跨渠道确认和异常重试后仍能恢复。
- `interrupt()` / `Command(resume=...)`：表达补字段、选择、确认、拒绝、编辑等等待用户输入的暂停点。
- subgraph：把客户识别、跟进记录、商机、合同、回款、客户资料维护等领域流程拆成可组合业务子图。
- conditional edge：把语义澄清、对象选择、字段补全、确认、执行、失败恢复和结束分支显式化。
- streaming：把模型解析、候选对象、guardrail、tool 执行和最终回复统一输出为可观测事件。
- time travel / state history：用于复盘“模型判断 -> 代码裁决 -> 用户确认 -> tool 执行”的完整路径。

## 不可妥协原则

1. Root Graph 是 Agent 运行时入口。

   Web、IM、定时任务和后续渠道进入 Agent 后，必须进入统一 root graph。`AgentApplicationService` 只负责通道归一、会话/thread 映射、权限上下文注入、事件落库和图调用，不再拥有业务 pending 状态机。

2. 等待用户必须用 interrupt 表达。

   补字段、选择客户/商机/合同、写入确认、拒绝、编辑 payload、暂停草稿和恢复草稿都必须是图中的 interrupt 点。不得靠 session context 或自研 pending dispatcher 表达运行时暂停。

3. 跨轮状态必须可 checkpoint。

   当前客户、候选对象、草稿 payload、缺失字段、建议动作、guardrail 结果、允许 tool、幂等 key、最近 tool 结果和当前 interrupt payload 必须进入 LangGraph checkpoint。业务表可保存投影和审计，但不能成为唯一恢复来源。

4. 业务域必须拆成 subgraph。

   Root graph 只做输入归一、语义路由、上下文加载、子图选择、全局 guardrail 和最终响应聚合。客户、跟进、商机、合同、回款、客户资料维护等领域流程必须沉淀为 subgraph，避免所有分支堆在一个单流程编排里。

5. 分支必须显式、可测试、可观测。

   每个 conditional edge 必须有命名原因、结构化输入、置信度、候选集合和 fallback。不能把分支藏在自然语言文案、正则关键词、图外 service if/else 或前端协议解析里。

6. LLM 只产候选，图状态机负责裁决。

   LLM 可以产出意图、实体、候选 action、候选对象和置信度；图节点必须用 schema、权限、候选集合、业务规则、阈值和 API 事实做最终裁决。状态迁移不得只因为模型说“可以签合同了”而发生。

7. 写入执行留在受控 tool runtime。

   LangGraph 负责暂停、恢复、路由和编排；真实写入仍必须通过 CRM API、权限校验、HITL、幂等和审计。框架升级不扩大模型权限。

8. Agent 任务表是审计和展示投影，不是运行时真相。

   `crm_agent_tasks`、消息表和 session context 可以继续用于前端展示、审计和人工排查；运行时恢复以 LangGraph checkpoint + thread state 为准。正常入口和 checkpoint 故障隔离入口都不得扫描 `WAITING_USER` task 来恢复用户等待态。只有当当前 checkpoint interrupt 已经投影出明确 task id/key 时，图节点才能按该 id 精确加载业务审计记录，用于展示、校验或完成审计闭环。

## Root Graph 职责

Root graph 的最小职责：

- 读取 `AgentInput`，生成稳定 `thread_id`。
- 加载 LangGraph checkpoint state 和必要 CRM 上下文。
- 调用 structured output 节点完成语义解析。
- 根据当前 interrupt、用户输入、候选对象和业务上下文做关系判断。
- 路由到对应领域 subgraph。
- 汇总 subgraph 输出，生成唯一 `interaction_action`。
- 在需要用户响应时 `interrupt()`。
- 在用户 resume 后继续原图节点，不重新猜测已确认 payload。
- 通过统一事件流输出 trace、debug、interaction 和最终消息。
- 通过只读 runtime API 暴露当前 checkpoint state 和 checkpoint history，支持按 checkpoint id 复盘分支、interrupt 和 resume payload。

Root graph 不应该：

- 直接拼接所有业务字段补全细节。
- 直接调用业务写入 API。
- 用自然语言文案判断用户是否确认。
- 在图外创建另一个 pending 状态机。

## 领域 Subgraph

每个业务 subgraph 必须满足同一接口：

- 输入：`AgentRuntimeState` 中的 channel、tenant、user、session、semantic result、current customer、候选对象和当前领域草稿。
- 输出：领域事件、草稿更新、候选 action、缺失字段、guardrail 结果、待执行 tool request 或 final response patch。
- 暂停：只能通过 interrupt 返回选择、补字段、确认、编辑或拒绝。
- 恢复：只能通过 `Command(resume=...)` 接收用户决策，并继续原 subgraph。

等待点应尽量位于拥有该业务分支的领域 subgraph 内。Root graph 可以作为 Web/IM/API 的统一 interrupt 门面，把子图产出的 `current_interrupt` 写入 root checkpoint 并对外暴露，但不能长期把所有等待逻辑集中在 root 的通用等待节点里。已经迁入子图的等待类型，必须由子图 thread 自己 checkpoint，并在 resume 后继续原子图节点和后续 conditional edge。

建议优先拆分：

- `customer_resolution_subgraph`：客户识别、搜索、选择、当前客户记忆更新。
- `follow_up_subgraph`：跟进记录解析、质量评估、补充、确认、创建。
- `opportunity_subgraph`：商机创建、商机候选匹配、阶段建议、阶段推进确认。
- `customer_maintenance_subgraph`：联系人、发票抬头、部署信息、客户成员维护。
- `payment_subgraph`：回款计划和回款登记。
- `confirmed_task_subgraph` / `tool_execution_subgraph`：用户确认后的 tool request 校验、幂等、执行、结果分类、任务完成/失败和下一步等待投影。

## Interrupt 协议

Graph interrupt payload 必须能直接映射到前端和 IM 的统一 `interaction` 协议：

- `type`：`choice`、`form`、`confirm`、`text`。
- `reason`：为什么暂停，例如 `customer_disambiguation`、`missing_required_fields`、`write_confirmation`、`low_confidence_route`。
- `business_action`：候选业务动作。
- `target_refs`：允许用户选择或确认的对象引用。
- `draft_payload`：待确认或待编辑 payload。
- `allowed_resume_actions`：`select`、`submit_fields`、`approve`、`edit`、`reject`、`cancel`。
- `task_projection_id`：可选，仅用于前端展示和审计，不用于恢复状态真相。

用户回复进入下一轮时，Adapter 必须把结构化按钮、表单、reaction 或文本确认转换成 resume payload。执行层必须校验 resume payload 属于当前 interrupt 允许范围。

## 状态 Schema

`AgentRuntimeState` 至少包含：

- `input`：本轮归一化输入。
- `identity`：tenant、user、channel、session、thread。
- `messages`：必要消息摘要和模型上下文。
- `semantic`：结构化语义结果、来源、模型、置信度和 fallback。
- `current_customer`：已确认客户上下文。
- `business_context`：通过 CRM API 获取的客户、商机、合同、回款计划等事实。
- `drafts`：各领域未完成草稿。
- `candidates`：客户、商机、合同、回款计划等候选集合。
- `interrupt`：当前等待用户响应的结构化暂停点。
- `tool_requests`：待执行 tool 请求。
- `tool_results`：tool 执行结果和错误分类。
- `guardrails`：权限、业务前置条件、幂等和风险判定。
- `events`：对前端、IM 和审计可见的结构化事件。

状态中不得保存不可序列化对象、数据库 session、HTTP client、模型 client 或临时 coroutine。

业务子图必须区分三类类型边界：

- Graph input：应用层注入的本轮依赖，可以包含 DB session、ORM task、授权 token、通道输入等运行时对象。
- Checkpoint state：LangGraph 持久化状态，只能包含 JSON-ish 事实、分支结果、候选集合、草稿、interrupt payload 和可审计事件。
- Graph result：返回给应用层的结果，可以通过 side effects 合并本轮运行时对象，但不能反向污染 checkpoint state schema。

授权 token、数据库连接、ORM 对象、HTTP client 和模型 client 一律只能存在于 `context_schema` 或 side effects 中，不得进入 checkpoint state。需要审计时只保存权限校验结果、tool request/result、幂等 key 和错误分类，不保存敏感运行凭据。

## 迁移策略

迁移按 LangGraph-native 优先推进：

1. 已建立 root graph、`AgentRuntimeState`、checkpointer 和 thread 映射，保持现有 API response contract 不变。
2. 已将等待态迁为 LangGraph interrupt payload，同时继续写 `crm_agent_tasks` 供前端展示和审计；session context 与 `crm_agent_tasks` 不再保存、恢复或反向投影 HITL 运行时等待态，也不得进入 LLM memory。
3. 已要求本轮产生的等待事件在 graph node 内完成业务投影后，立即写入 root checkpoint 的 `current_interrupt`。例如 `confirmation_required` 创建 `crm_agent_tasks` 后，task id/key 只能作为 interrupt payload 的投影字段，恢复语义仍由 checkpoint 承载。
4. 已将主要 pending interaction 路径迁到 interrupt/resume：挂起草稿归属澄清、字段补充、客户选择、业务对象选择、文本补充和二段确认均通过 root `Command(resume=...)` 返回同一 pending 子图 thread。
5. 已将 pending interaction planner 拆为 `pending_interaction_graph.py` 的显式节点、handler registry 和 conditional edge；字段类等待任务的 route/node/predicate/collector/event 由图注册表声明，等待恢复执行原语已并入子图节点边界，不再保留独立 pending interaction runtime。
6. 已将 `CRMAgentGraphService` 新流程纳入 root graph，并拆出客户识别、重复检查、业务上下文、行动规划、跟进质量、商机、客户资料维护、回款登记等领域 subgraph。
7. 已将确认后 tool 执行纳入 dedicated confirmed-task/tool-execution subgraph，保留现有 tool registry、guardrails、幂等和 CRM API 边界；底层 runtime 只能作为子图节点调用的执行原语，不能再由 application 正常路径直接编排。
8. 已在 root runtime 接入 LangGraph state history/time-travel 读取接口，并通过 `/v1/agent/sessions/{session_id}/runtime/state`、`/v1/agent/sessions/{session_id}/runtime/history` 和 `/v1/agent/sessions/{session_id}/runtime/checkpoints/{checkpoint_id}` 按 session ownership 暴露 JSON-safe 状态投影、分支事件、interrupt 和 resume payload；后续继续把该投影接入前端 trace 展示。
9. 已将 application 正常路径收敛为 `agent_root_runtime.run_turn()` 单入口；checkpoint interrupt 读取、初始 root state 构造、`Command(resume=...)` 恢复和 checkpoint task projection 对齐均由 root runtime 负责，application 不再手工编排 root graph 分支。
10. 继续删除或降级旧 pending dispatcher/session task 状态职责；`crm_agent_tasks` 只保留展示、审计和本轮新等待事件的 task projection 职责。checkpoint 不可用时不得通过 `crm_agent_tasks` 恢复旧 pending；该场景必须显式降级并输出 checkpoint outage trace。PendingTask 恢复只接受 continuation 中的精确 `thread_id + checkpoint_ns`，saver 返回的 locator 必须完全一致，不允许 namespace/history 扫描或用返回值重写 locator。
11. PendingTask 的用户可见等待由 Root Graph 持有。用户 `Command(resume=...)` 后，Root 先验证 authoritative child checkpoint；任何无法读取的结果都 fail closed，不得进入 child。`checkpoint_locator_not_found`、`checkpoint_interrupt_not_found`、`checkpoint_corrupt`、`invalid_continuation` 进入不可重试失败节点并释放等待；`checkpoint_store_unavailable`、`checkpoint_recovery_exception` 进入可重试失败节点并保留 Root-owned interrupt，待基础设施恢复后重新建立原生 interrupt 再恢复 child。首次 child 已产生 interrupt、但 authoritative read 瞬态失败时，也必须保留本轮生成的 exact continuation 与已观察到的 interrupt，不能产生孤立 child checkpoint。
12. PendingTask outcome 的 CRM/application projection 失败与 checkpoint recovery 失败是两个独立状态机分支。所有 terminal projection failure 必须经 `pending_projection_failure -> finish_turn -> END`，所有 recovery failure 必须经 `pending_resume_recovery_failure -> finish_turn -> END`；失败节点是业务失败事件和用户提示的唯一 owner，不得通过 `projection_aborted`、图外终态伪造或重复发布事件。隐藏 application step 的 terminal projector failure、continuation 校验失败和 task/continuation 身份不一致同样属于 projection failure；Root 不得用 `FAILED` acknowledgement 恢复 child，而应保持 child interrupt checkpoint 不变后进入统一失败分支。
13. `pending_interrupt_projection` 只保存 CRM/application projection 状态，不得承载 checkpoint recovery 状态。用户已提交并通过 Root interrupt 校验后若发生可重试 recovery failure，Root checkpoint 必须保存与 exact continuation + interrupt identity 绑定的 deferred resume capability（包含原始、已验证的 resume payload）；下一次请求只负责触发恢复，Application adapter 必须先重新建立原生 Root interrupt，再自动重放该 payload 并继续 `Command(resume=...)`，不得再次调用意图路由或要求用户重复确认，也不能先消费一轮输入做提示重放。首次 child authoritative read 瞬态失败、尚无用户 resume payload 时，只保留 exact continuation 和 Root-owned interrupt，不得伪造 deferred resume。deferred resume capability 必须区分 absent 与 present-but-invalid；后者（continuation 篡改、interrupt identity 不匹配、resume payload 非法或 capability 构建 invariant 失败）必须 fail closed，经 `pending_resume_recovery_failure -> finish_turn -> END` 显式终止，不得退回意图路由、要求用户重复确认或触碰 child checkpoint。恢复 authoritative child outcome 时只读取 exact child checkpoint，不得把 Root/application 的累计 delivery events 当作 child trace 合并回 outcome，否则会造成失败事件重复投影。child 终态后必须清除 continuation 与 deferred resume capability，避免后续 turn 持有陈旧恢复权限。

当前迁移不追求把纯 CRUD、字段清洗、枚举归一和幂等实现包装成图节点。LangGraph 必须充分负责长期运行的 orchestration、branching、checkpoint、interrupt/resume、subgraph 组合和状态历史；确定性业务原语应保持为普通可测试模块，由图节点调用。

## 验收标准

一次架构升级只有满足以下条件，才算充分使用 LangGraph：

- 服务重启或刷新页面后，等待确认、补字段和选择流程能从 checkpoint 恢复。
- 用户确认时通过 `Command(resume=...)` 回到原 interrupt 节点，而不是重新解析一遍 payload。
- 至少客户识别、跟进记录、商机流程、confirmed-task/tool 执行被拆为 subgraph 或明确的可替换子图边界。
- 所有会等待用户的业务分支都有 interrupt payload、allowed resume actions 和审计事件。
- 所有 conditional edge 都能在测试中验证分支原因。
- PendingTask resume 在 exact checkpoint 未验证成功前不会进入 child；瞬态存储故障保留可重试 Root interrupt，确定性损坏显式终止。
- PendingTask 的 projection failure 与 recovery failure 经过不同命名节点，且每次失败只发布一条业务失败事件。
- PendingTask 的 durable resume 遇到 checkpoint storage error 时不得进入 no-checkpointer fallback；fallback 只允许处理未持有 continuation 的首次无状态调用。
- terminal application-step projection failure 经 Root `pending_projection_failure` 终止，且不消费、不改写 child checkpoint。
- 瞬态 recovery failure 恢复后，下一次用户响应在同一 turn 内重新建立 Root interrupt 并成功恢复 child，不要求用户重复确认；Root/application 事件不会反向污染 child outcome。
- `crm_agent_tasks` 不再是运行时唯一 pending 状态来源。
- 当前 checkpoint state 与 checkpoint history 能通过只读 API 查询，排查复杂分支时以 LangGraph checkpoint 为准，而不是从消息文案或旧任务投影反推。
- 真实写入仍全部经过 CRM API、权限、HITL、幂等和审计。

## 剩余收敛边界

- `AgentApplicationService` 可以保留 checkpoint 存储不可用时的显式 fallback，但 fallback 只能作为故障隔离路径，不能承载正常业务状态机，也不能扫描 `crm_agent_tasks` 恢复旧 pending；进入该路径时必须输出 `agent_root_checkpoint_unavailable_fallback_started`，并在 SSE 与 assistant trace 中记录 `runtime`、`checkpoint_unavailable` 和 `fallback_reason`。
- 会跨轮等待或执行写入的 domain subgraph 如果保留 no-checkpointer fallback，也必须输出 `agent_checkpoint_unavailable_fallback_started`；fallback 仅适用于没有 continuation capability 的首次调用，任何 durable resume 必须 fail closed 并保留 exact continuation。pending-task 和 confirmed-task 子图已经将该事件写入 graph result，confirmed-task 还必须同步写入 application-facing `output_events`。
- `session_state.py` 可以保留会话绑定、当前客户记忆、task projection 读取和 suspended task 展示，但不能成为恢复用户等待态的事实来源。
- 应用入口恢复等待态时必须读取 root graph checkpoint 中的 active interrupt；没有 active interrupt 时按无当前等待态的新一轮输入进入 root graph，不得把 `WAITING_USER` task 反向投影为恢复 interrupt。
- 新增业务分支如果会跨轮等待、改变草稿或触发写入，必须先设计 domain subgraph 的 state、interrupt payload、resume action 和 checkpoint thread，再实现具体业务逻辑。
- 领域子图可以调用普通 runtime/helper，但 helper 只能处理确定性原语；一旦 helper 开始拥有分支编排、等待用户或跨轮状态，就必须上移为 graph node。
