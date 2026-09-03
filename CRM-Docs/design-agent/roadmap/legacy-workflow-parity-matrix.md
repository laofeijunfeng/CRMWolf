# 旧 Agent 流程到新 Workflow 的 Parity Matrix

> **状态说明（2026-09-02）：**本文保留为旧流程与当前代码的差异证据。产品规则和目标实现已完成确认，权威实施合同见 [客户活动 Agent Workflow Parity 实施规格](./customer-activity-workflow-parity-spec.md)，完整发布验收见 [客户活动 Agent Workflow 验收矩阵](./customer-activity-workflow-acceptance-matrix.md)。本文中的“待核实/待确认”不应覆盖已冻结的实施规格。

- **盘点日期：**2026-09-01
- **目的：**对照统一 Root Orchestrator / Workflow Runtime 迁移前后的能力，识别“已等价迁移、部分迁移、确认遗漏、待核实”和“有意设计变更”。
- **范围：**以 `5641fff`（`feat: ship unified agent runtime and follow-up workflows`）之前的旧 Agent 图为基线，以当前 `app.services.agent.orchestrator.runtime.get_root_orchestrator()` 生产组装为新基线。
- **性质：**分析和验收基线，不是实现方案；本文不授权恢复旧图，也不替代产品/API 合同。

## 1. 结论摘要

当前迁移不是只遗漏了“跟进质量评估”一个节点。旧版跟进链路中至少有四类能力没有完整接回统一 Workflow：

1. **创建前业务质量门禁：**跟进质量评分、下一步行动闭环检查、低质量补充、补充后重新解析/质检。
2. **客户业务理解：**客户上下文加载，以及基于上下文生成商机/阶段/回款等后续建议。
3. **后续动作投影：**将当前跟进后的二级业务建议转成 next task，并在下一轮单独确认。
4. **部分领域写入能力：**`PAYMENT_RECORD` 仍在语义合同中，但当前 `CRMWorkflowPlanner.plan()` 没有对应分支；其余部分业务写入已由统一 Planner 承接。

当前保留的是通用执行骨架：Root 路由、Workflow checkpoint、interrupt/resume、客户候选选择、字段补充、确认、授权范围、幂等写入和 CRM API 边界。问题主要发生在**旧领域编排没有全部映射到新 Planner/Workflow domain step**。

## 2. 状态定义

| 标记 | 含义 |
|---|---|
| ✅ 等价保留 | 新流程已经覆盖，行为和边界基本等价。 |
| 🟡 部分迁移 | 主能力存在，但旧流程中的关键语义、数据或交互仍缺失。 |
| ❌ 确认遗漏 | 旧流程有明确能力，当前生产调用链没有对应实现或分支。 |
| 🔍 待核实 | 当前代码看不到等价实现，但可能由 API、独立 Runtime 或有意设计变更承接。 |
| ➖ 设计变更 | 旧能力被明确限制或移除；不应直接按回归处理，需要产品/架构确认。 |

## 3. 端到端编排矩阵

| 能力/阶段 | 旧流程行为 | 新 Workflow 当前行为 | 状态 | 证据与判断 |
|---|---|---|---|---|
| Root 统一入口 | 旧版由 `CRMAgentGraphService` 承担 Agent 主图；后来迁移到 Root。 | 当前生产入口为 `get_root_orchestrator()`，统一装配 Query Agent 和 Workflow subgraph。 | ✅ | `CRM-Server/app/services/agent/orchestrator/runtime.py:25-50`。 |
| Root 路由 Query / Workflow | 旧主图内部判断业务意图和分支。 | Root 先分类，再分发到 Query 或 Workflow。 | ✅ | `orchestrator/graph.py`；这是架构重组，不是功能缺失。 |
| Workflow checkpoint | 旧领域图各自有 checkpoint namespace。 | 新 Workflow 使用 Root-owned checkpoint 和 native LangGraph subgraph。 | ✅ | `workflow/graph.py`、`orchestrator/graph.py`。需继续做跨重启回放验收，但主能力已存在。 |
| interrupt / resume | 旧流程通过 pending/confirmed/task 等多层机制承载等待。 | 新流程统一使用 Workflow interrupt/resume 和 `Command(resume=...)`。 | ✅ | `workflow/contracts.py`、`orchestrator/graph.py`。 |
| 语义解析 | 解析 intent、客户、跟进、商机、时间、业务信号和请求动作。 | `CRMWorkflowPlanner.plan()` 仍调用 `parse_with_metadata()`。 | ✅ | `workflow/planning.py:147-187`。 |
| 记忆加载 | 旧流程先 `load_memory`，语义解析可以使用 session memory/current customer。 | Planner 明确以 `memory=None` 调用解析器。 | ➖ / 🟡 | `workflow/planning.py:158-163`。新架构文档限制旧 memory 继承，但用户体验能力不再等价；需产品确认是否恢复 session entity projection。 |
| 读取当前任务/历史业务信息 | 旧流程可按请求执行 `run_agent_read_tool`，客户范围请求还可能读取最近跟进任务。 | Query Agent 独立负责查询；当前写入 Workflow 不会自动执行旧的 read-tool 阶段。 | 🟡 | 旧 `graph.py:_run_agent_read_tool` 已删除；需确认是否支持同一轮“先读后写”，还是要求拆成两轮。 |
| 客户识别 | 旧流程先搜索客户，支持单一、多个、找不到、记忆客户等路径。 | 当前使用 `CRMWorkflowCustomerResolver`，支持候选选择和授权绑定。 | ✅ | `workflow/customer_binding.py`、`workflow/resources.py`、现有 Workflow 测试。memory 客户例外见上一行。 |
| 创建客户/线索前重复检查 | 旧流程有 `CreationDuplicateGraphService`，创建前检查名称、手机号和客户/线索冲突，并向用户提供决策。 | 当前 Planner 没有 duplicate resolver 或前置 duplicate step；底层 API 是否承接全部保护尚未证明。 | 🔍 | 旧 `creation_duplicates_graph.py` 已删除；当前仍有 `search_creation_duplicates` tool，但未见其进入新 Planner 生产路径。 |
| 必填字段补充 | 旧流程按业务对象收集缺失字段。 | 新 Planner 为线索、客户、联系人、商机等生成 form/text interaction。 | ✅ | `workflow/planning.py` 各 `_plan_*` 方法；现有 `test_agent_workflow_subgraph.py` 覆盖。 |
| 当前唯一交互动作 | 旧 `ActionPlanningGraphService` 根据质量、上下文、建议和字段状态选择唯一交互。 | 新 Workflow 支持补字段、选择资源、确认，但 Planner 输入没有业务上下文和建议结果。 | 🟡 | 交互框架保留，决策输入不完整；违反“质量/建议优先级”风险见后文。 |
| 写入确认 | 旧流程对需要确认的写入产生 HITL。 | 新 Planner 生成结构化 confirmation interaction。 | ✅ | `WorkflowActionPlan` 要求 confirmation plan 必须带 confirmation interaction。 |
| 低风险自动执行 | 旧流程会结合 action review / 风险和置信度决定。 | 新 Planner 在 `intent_confidence >= 0.85` 时可自动执行客户活动。 | 🟡 | 自动执行框架保留，但跟进质量和 next_action 门禁缺失，导致执行条件比旧流程宽。 |
| CRM API 写入 | 旧流程通过现有 Agent tools 调内部 CRM API。 | 新 Effect Executor 仍通过 tool registry 和 CRM API 执行。 | ✅ | `workflow/execution.py:90-180`；没有直接写业务表。 |
| 幂等与授权 | 旧工具层有 action key、HITL guardrail、客户范围等。 | 新执行器生成 command idempotency suffix，校验授权客户和资源。 | ✅ | `workflow/execution.py`；当前不应把这些能力误判为迁移遗漏。 |
| 写入后异步工作 | 旧流程由 post-write effects / task factory / customer intelligence 等机制处理。 | 新 effect result 返回 `durable_work` receipt，底层活动 API仍有 post-commit/异步能力。 | 🟡 | 新旧承载机制不同；需以 durable work acceptance fixture 逐项证明，不宜直接恢复旧 side-effect handler。 |
| 结果整理 | 旧 response builder 汇总业务结果、质量、建议、任务和 trace。 | 新 Workflow 统一返回 completed/failed/cancelled/replay result。 | 🟡 | 结果合同保留，但质量、建议、next task 没有进入结果。 |
| 可见执行过程 | 旧事件中可显示客户搜索、质量、上下文、建议等节点。 | 新 progress 只有理解、补充、计划、确认、执行、结果。 | 🟡 | `workflow/progress.py:114-129`；前端 `AgentUIProcessBlock.vue` 只是渲染后端 steps。 |
| Trace/审计 | 旧主图保留 semantic、quality、suggestion、tool 等 trace metadata。 | 新 Workflow 有结构化 result/checkpoint，但当前 Planner 没有质量/建议事件；模型来源/fallback 展示也不完整。 | 🟡 | 与 `CRM-Docs/design-agent/runtime/observability.md` 和 `current-state.md` 的“未充分具备”一致。 |

## 4. 跟进记录专用矩阵

### 4.1 主流程和数据字段

| 能力 | 旧流程 | 新 Workflow | 状态 | 当前风险 |
|---|---|---|---|---|
| 跟进内容存在性检查 | 没有内容时要求补充。 | 保留，空 `follow_up.content` 触发 `follow_up_content` interaction。 | ✅ | 仅解决“有无内容”，不解决“内容是否有价值”。 |
| 跟进质量评估 | `FollowUpQualityGraphService` 调 `AgentFollowUpQualityEvaluator`，输出 score、passed、reason、missing_aspects、supplement_question、suggested_revision、principle_scores。 | 当前 Planner 没有质量评估器、质量子图或质量结果字段。 | ❌ | 创建前可能直接进入确认/执行。 |
| 质量评分阈值 | `score >= 60` 通过；代码重新按阈值归一化模型 `passed`。 | 没有 score/passed 计算。 | ❌ | 无法阻塞流水账或低信息跟进。 |
| 六大质量原则 | 事实、动作闭环、阶段推进、决策穿透、异议具象、信息可接力。 | 没有执行。 | ❌ | 业务质量标准没有进入新 Workflow。 |
| 下一步行动识别 | 旧语义解析识别 `next_action`，质量规则还会检查行动闭环。 | 仍可解析并在有值时放入 payload。 | 🟡 | 提取能力保留，但没有“缺失即补充”的门禁。 |
| 缺失下一步行动 | 低质量时要求用户补充“由谁在什么时间做什么”等关键信息。 | `next_action` 为 None 时直接跳过；高置信度仍可 auto-execute。 | ❌ | 这是当前最直接的行为回归。 |
| 下一步时间识别 | 旧流程解析 `next_follow_time_text`，由 temporal resolver 转 ISO。 | 当前调用 `resolve_follow_up_time()`，并写入 `next_follow_time`。 | ✅ | `workflow/planning.py:288-300`。需确认缺少时间时是否应作为质量问题，而不是一律可选。 |
| 下一步“人/时间/动作”闭环 | 旧质量问题可要求补充责任人、时间、动作。 | 当前只有字符串 `next_action`，无结构化责任人字段和闭环校验。 | ❌ / 🔍 | 是否必须结构化责任人需产品合同确认，但旧业务规则确实比当前严格。 |
| 原始跟进内容 | 旧 payload 区分 `original_content`/`source_content` 与整理后的 `content`。 | 当前将解析后的 `content` 同时作为 `source_content` 和 `title`。 | 🟡 | 可能丢失用户原文，需由 API/审计合同确认。 |
| 整理后的跟进内容 | 旧质量评估可以生成 `suggested_revision`，通过后可进入确认/写入。 | 当前没有 `suggested_revision` 字段或确认展示。 | ❌ / 🔍 | 如果产品要求写入前展示优化稿，这是确认遗漏；如果新产品只保存原文，则需更新文档。 |
| 跟进方式 `method` | 旧活动 payload 保留 method，如电话、微信、拜访、邮件。 | 当前通过 `infer_activity_kind(method, content)` 映射为 `activity_kind`，不再原样传 method。 | 🟡 | 可能是规范化设计，也可能丢失报表/审计语义。 |
| 客户上下文 | 质检通过后加载 `get_customer_context`。 | 当前 `_plan_customer_activity()` 只绑定客户，不加载历史业务上下文。 | ❌ | 无法基于商机、合同、回款、历史跟进理解本次记录。 |
| 跟进后的业务建议 | 旧 `AgentSuggestionGenerator` 根据 semantic + business context 生成建议。 | 当前生产 Workflow 未注入或调用 `AgentSuggestionGenerator`。 | ❌ | `suggestion.py` 仍存在，但生产调用链断开。 |

> **已确认本期范围：**跟进后的前台二级建议先只恢复商机相关动作；回款、合同、回款计划、发票抬头、部署信息、License 等暂不处理，也不阻塞主跟进记录。商机阶段推进也纳入本期商机范围。
| `business_signals` | 旧建议生成读取语义层业务信号。 | 字段仍在 schema，但当前 Planner 不消费。 | ❌ | 例如“客户已立项”“已回款”等信号不会触发后续建议。 |
| `requested_actions` | 旧流程可结合用户明确请求形成建议/动作。 | 当前跟进 Planner 不消费。 | ❌ | 用户在跟进文本中表达的二级动作可能被忽略。 |
| 商机创建建议 | 旧流程可在跟进成功后投影为下一步动作，不和主跟进写入混执行。 | 当前没有 suggestion result 或 child next task。 | ❌ | 跟进完成后不会自动形成“是否创建商机”的下一轮任务。 |
| 商机阶段推进建议 | 旧流程有阶段推进建议和 next task 测试。 | 当前没有跟进后建议投影；只有用户直接请求 `MOVE_OPPORTUNITY_STAGE` 时才有独立 Planner 分支。 | ❌ | “记录跟进并据此推进阶段”的组合能力缺失。 |
| 后续建议的单独确认 | 旧 interaction policy 要求主跟进完成后，二级动作进入下一轮确认。 | 当前没有二级动作，因此也没有对应确认。 | ❌ | 不能把建议与当前主写入做正确的先后隔离。 |
| 跟进成功后的任务投影 | 旧 `next_waiting_task_projection` 可创建稳定 child task。 | 当前 durable work/Workflow task 机制存在，但没有 suggestion-driven child task 输入。 | 🟡 | 基础任务基础设施不等于跟进后的业务建议投影已恢复。 |
| 跟进相关最近任务 | 旧客户范围读取可能带回 recent follow-up tasks。 | 当前写入 Planner 不读取该信息。 | 🔍 | 需要确认是否由 Query Agent 拆分承接。 |
| 客户活动写入 | 旧通过 `create_customer_activity` API/tool。 | 新通过 `CRMWorkflowEffectExecutor` 调 `create_customer_activity`。 | ✅ | 写入边界本身保留。 |
| 写入后客户智能刷新 | 旧 post-write/customer intelligence 体系存在；新活动 API 返回 durable work receipts。 | 当前看到了 durable work 承载，但尚未验证每种跟进写入都触发同等刷新。 | 🟡 | 应用 acceptance fixture 检查 receipt 类型、状态和幂等行为。 |

### 4.2 跟进可见进度矩阵

| 旧可见/内部步骤 | 新 progress 是否有对应项 | 状态 | 说明 |
|---|---|---|---|
| 理解业务操作 | `understand_request` | ✅ | 保留。 |
| 语义解析 | 合并在 `understand_request` | 🟡 | 没有单独展示模型解析和结构化结果。 |
| 客户搜索/候选解析 | 没有独立 progress step | 🟡 | 用户可看到选择 interaction，但执行过程不体现客户解析阶段。 |
| 跟进质量评估 | 无 | ❌ | 当前用户感知缺失的主要步骤。 |
| 下一步行动检查 | 无 | ❌ | 没有独立门禁或展示。 |
| 客户业务上下文加载 | 无 | ❌ | 后端实际也没有执行。 |
| 业务建议生成 | 无 | ❌ | 后端实际也没有执行。 |
| 生成执行计划 | `prepare_plan` | ✅ | 通用计划步骤保留。 |
| 等待用户确认 | `await_confirmation` | ✅ | 通用确认步骤保留。 |
| 创建跟进记录 | `execute_action` | ✅ | 通用执行步骤保留。 |
| 整理执行结果 | `prepare_result` | ✅ | 通用结果步骤保留。 |
| 下一步建议/next task 投影 | 无 | ❌ | 没有建议驱动的后续步骤。 |

## 5. 领域写入能力矩阵

| 旧领域能力/语义 intent | 旧实现 | 新 Planner 当前分支 | 状态 | 说明 |
|---|---|---|---|---|
| `CUSTOMER_ACTIVITY` | `customer_activity_graph` + 主图质量/上下文/建议编排。 | `_plan_customer_activity()`。 | 🟡 | 基础创建已迁移，领域编排未完整迁移。 |
| `PAYMENT_RECORD` | `payment_record_graph`，并可由语义和业务上下文触发。 | `AgentIntent` 仍声明 `PAYMENT_RECORD`，但 `CRMWorkflowPlanner.plan()` 没有对应 `if intent == "PAYMENT_RECORD"` 分支。 | ❌ | 当前会落到 `WORKFLOW_ACTION_UNSUPPORTED`；这是跟进以外已确认的写入能力缺口。 |
| `CREATE_LEAD` | `lead_graph`，含字段收集、可附带跟进。 | `_plan_lead()`。 | 🟡 | 基础字段/创建已迁移；重复检查、附带跟进质量和 next_action 门禁需核实/补齐。 |
| `CREATE_CUSTOMER` | `customer_creation_graph`，含字段收集、重复检查、可附带跟进。 | `_plan_customer()`。 | 🟡 | 基础创建已迁移；重复检查和附带跟进质量仍有缺口。 |
| `CREATE_CONTACT` | `contact_graph`。 | `_plan_contact()`。 | ✅ | 资源解析和创建计划已存在。 |
| `CREATE_INVOICE_TITLE` | `invoice_title_graph`。 | `_plan_invoice_title()`。 | ✅ | 当前 Planner 有对应分支。 |
| `CREATE_DEPLOYMENT_INFO` | `deployment_info_graph`。 | `_plan_deployment_info()`。 | ✅ | 当前 Planner 有对应分支。 |
| `CREATE_CUSTOMER_MEMBER` | `customer_member_graph`。 | `_plan_customer_member()`。 | ✅ | 当前 Planner 有对应分支。 |
| `CREATE_OPPORTUNITY` | `opportunity_graph`，含字段补充、采购方式选择和客户关联。 | `_plan_opportunity()`。 | ✅ / 🟡 | 基础领域流程存在；跟进后的自动建议触发不在该分支。 |
| `MOVE_OPPORTUNITY_STAGE` | 旧阶段动作/建议与资源解析。 | `_plan_opportunity_stage_transition()`。 | ✅ | 直接用户请求的阶段推进已单独迁移；不代表跟进后 suggestion chain 已迁移。 |
| `FOLLOW_UP_TASK_TRANSITION` | 旧 follow-up task transition/policy/confirmation。 | `_plan_follow_up_task_transition()` 和资源重校验。 | ✅ / 🟡 | 直接任务状态变更存在；旧 policy 名称和部分 projection 机制发生重构，需做合同回归。 |
| `CREATE_PAYMENT_PLAN` | 主要作为业务建议动作。 | 没有 standalone `AgentIntent` 或 Planner 分支。 | 🔍 | 需确认它是否只允许作为 suggestion/next task，还是应成为独立 Workflow。 |
| `CREATE_PAYMENT_RECORD` | 主要作为业务建议动作，同时有 `PAYMENT_RECORD` 领域图。 | suggestion schema/prompt 仍支持，但当前 Workflow Planner 无对应写入分支。 | ❌ / 🔍 | 直接回款登记能力至少未在当前 Planner 中闭环。 |
| `CREATE_LICENSE_APPLICATION` | 主要作为业务建议动作/后置领域能力。 | 当前 Planner 无对应 intent 分支。 | 🔍 | 需根据本期范围确认是否本来就不属于 unified Workflow parity。 |
| 客户智能刷新 | 旧有 customer intelligence graph/trigger。 | 独立 Customer Intelligence Runtime 仍存在；活动写入通过 durable work 连接的完整性未证明。 | 🟡 | 不是简单恢复旧 graph，应验证异步 receipt 到 intelligence run 的链路。 |

## 6. 交互合同矩阵

| 交互场景 | 旧规则 | 新 Workflow | 状态 |
|---|---|---|---|
| 缺客户 | 追问客户名或进入客户选择。 | 有客户解析和选择 interaction。 | ✅ |
| 多客户候选 | 先让用户选择客户，再继续写入。 | `select_workflow_customer` interaction 已存在。 | ✅ |
| 缺跟进内容 | 要求补充内容。 | `follow_up_content` interaction 已存在。 | ✅ |
| 低质量跟进 | 只问一个最关键质量补充问题，不确认、不创建、不生成建议。 | 没有质量 interaction。 | ❌ |
| 缺下一步行动 | 要求补充行动闭环。 | 当前可直接确认或自动执行。 | ❌ |
| 缺普通必填字段 | 先补字段，再确认。 | 新 Planner 有 form/text interaction。 | ✅ |
| 写入确认 | 当前主动作确认。 | 新 Workflow 有 confirmation interrupt。 | ✅ |
| 主动作与二级建议 | 先创建跟进，后续建议进入 next task/下一轮。 | 二级建议未生成。 | ❌ |
| 同轮多个问题 | 旧 interaction planner 保持一轮一个用户响应目标。 | 通用 Workflow 结构支持单一 interaction，但未接入质量/建议输入后无法保证跟进场景优先级。 | 🟡 |
| 用户补充后重新规划 | 旧图重新解析/重新评估/重新生成下一步。 | 普通 supplements 会重新调用 semantic parser，但跟进质量评估不存在，不能实现完整重规划。 | 🟡 |
| 用户取消 | 旧流程取消当前 pending action。 | 新 Workflow 返回 cancelled result。 | ✅ |
| 跨轮恢复 | 旧 pending/confirmed/task 多层恢复。 | 新 Root + Workflow checkpoint/resume。 | ✅ / 🟡 | 机制已迁移，旧任务数据合同需要单独回放验收。 |

## 7. 当前证据边界和待核实项

以下项目不能仅凭 Planner 缺少代码就直接定性为回归，应在补实现前先确认合同：

1. **重复检查是否已下沉到 CRM API。**需要检查 API acceptance fixture 是否覆盖“创建前主动提示”而不只是“请求后拒绝”。
2. **`source_content` 是否保存原文。**如果新合同允许只保存规范化内容，则当前映射是设计变化；否则是数据审计回归。
3. **`method` 是否由 `activity_kind` 完全替代。**需要确认列表、报表、详情和查询是否仍依赖原 method。
4. **memory/current customer 是否有意下线。**当前 schema 已将 `AgentCustomerEntity.resolution_source` 限制为 `EXPLICIT`/`NONE`，这更像安全架构变更，而不是遗漏的旧逻辑。
5. **Query 与 Workflow 是否允许一轮读写混合。**如果产品规定读写拆成两轮，则缺少旧 read-tool 并非 bug；如果允许组合输入，则需要 Root 级组合编排。
6. **支付、License、payment plan 的范围。**语义 prompt 和 suggestion 仍保留这些动作，但不代表它们都应成为本期独立 Workflow。
7. **异步 post-commit 完整性。**当前 `durable_work` 是新承载方式，需要验证活动写入、任务投影、客户智能刷新、失败重试和幂等是否都能闭环。

## 8. 建议的验收优先级

### P0：阻止错误写入或直接丢失主业务价值

1. 跟进质量评估和 `< 60` 阻塞；
2. `next_action`/行动闭环门禁；
3. 高置信度无行动时禁止自动写入；
4. 跟进内容补充后的重新解析和重新质检；
5. `PAYMENT_RECORD` 当前 Planner 分支缺失问题。

### P1：恢复跟进后的业务闭环

1. 客户业务上下文加载；
2. suggestion generator 接入；
3. `business_signals`/`requested_actions` 消费；
4. 商机创建/阶段推进建议；
5. 建议驱动的 next task projection 和下一轮确认；
6. 质量、上下文、建议进度和 trace。

### P2：数据和边界 parity

1. `source_content`/整理内容的原文与规范化稿合同；
2. `method`/`activity_kind` 兼容策略；
3. 创建客户/线索重复检查的 API 与交互 parity；
4. 最近任务读取与读写组合语义；
5. memory/current customer 产品决策；
6. durable work 到 customer intelligence 的端到端验收。

## 9. 本文不作出的结论

- 不建议直接把删除的旧图整体恢复；新架构要求能力进入 Root + native Workflow + interrupt/resume + checkpoint。
- 不把所有旧模块删除都视为 bug；很多模块已经由统一 Planner 或新资源 Resolver 承接。
- 不把前端 `AgentUIProcessBlock` 作为主要修复点；如果后端没有生成质量、上下文和建议步骤，前端无法凭空恢复业务流程。
- 不在没有 API/产品合同的情况下决定 `source_content`、`method`、memory 和重复检查的最终语义。

## 10. 证据索引

### 旧流程

- 迁移提交：`5641fff`。
- 旧主图：`5641fff^:CRM-Server/app/services/agent/graph.py`。
- 旧质量图：`5641fff^:CRM-Server/app/services/agent/follow_up_quality_graph.py`。
- 旧业务上下文图：`5641fff^:CRM-Server/app/services/agent/business_context_graph.py`。
- 旧创建重复检查：`5641fff^:CRM-Server/app/services/agent/creation_duplicates_graph.py`。
- 旧 post-write/task projection：`5641fff^:CRM-Server/app/services/agent/post_write_effects.py`、`next_waiting_task_projection.py`。

### 当前流程

- 生产组装：`CRM-Server/app/services/agent/orchestrator/runtime.py`。
- Root 路由：`CRM-Server/app/services/agent/orchestrator/graph.py`。
- Workflow Planner：`CRM-Server/app/services/agent/workflow/planning.py`。
- Workflow 执行器：`CRM-Server/app/services/agent/workflow/execution.py`。
- Workflow 进度：`CRM-Server/app/services/agent/workflow/progress.py`。
- Workflow 合同：`CRM-Server/app/services/agent/workflow/contracts.py`。
- 当前生产 Workflow 测试：`CRM-Server/tests/unit/test_agent_workflow_subgraph.py`。

### 规则文档

- `CRM-Docs/design-agent/runtime/follow-up-quality.md`。
- `CRM-Docs/design-agent/runtime/interaction-policy.md`。
- `CRM-Docs/design-agent/runtime/langgraph-native-runtime.md`。
- `CRM-Docs/design-agent/roadmap/current-state.md`。
