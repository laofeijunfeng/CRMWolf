# 销售承诺管理系统开发任务拆分清单

来源方案：`CRM-Docs/requirements/2026-08-06-sales-commitment-management.md`

## 1. Phase 1 目标

Phase 1 先交付“结构化任务投影”闭环，让系统能从客户跟进记录中稳定生成、更新、取消和查询客户跟进任务。

第一版必须做到：

1. 客户活动有独立 `owner_id`，任务和承诺归属来自活动 owner，而不是客户 owner。
2. 新增销售承诺、跟进任务、任务事件和任务投影运行表。
3. 页面录入、Agent 录入、客户活动 AI 整理完成、活动更新/删除、历史回填都进入同一套 `FollowUpTaskProjectionService`。
4. Agent 可以回答“今天、本周、下周、逾期、未完成、客户范围内任务”等确定性任务查询。
5. 历史客户活动按最近 90 天、每客户每 owner 最新 1 条开放安排做低打扰回填。
6. 所有对外 API、Agent tool、LLM 上下文和向量 metadata 使用 `public_id`，内部数据库关联使用主键 `id`。
7. 幂等、权限、事件审计和投影运行观测在第一版就形成稳定边界。

## 2. Phase 1 不做范围

- 不新增完整任务管理页面。
- 不做手工通用任务 CRUD。
- 不做自动关闭旧任务。
- 不做低置信追问和确认流。
- 不做跨 owner 自动关闭、转派或代处理。
- 不纳入线索 follow-up。
- 不做管理者聚合任务视图。
- 不做主动日报、定时提醒或 IM 主动推送。
- 不把 Qdrant 作为任务状态事实源。
- 不复用 `crm_agent_tasks` 作为销售业务任务表。

## 3. 实施顺序总览

建议按以下顺序推进，前置 ticket 完成后再进入依赖它的 ticket：

1. `SCM-00` 现状确认和接入点复核。
2. `SCM-01` 客户活动 owner 迁移。
3. `SCM-02` 销售承诺和跟进任务数据模型。
4. `SCM-03` public_id、schema、CRUD 和权限基础。
5. `SCM-04` 时间规范化和查询时间窗口。
6. `SCM-05` 投影服务核心逻辑。
7. `SCM-06` 投影运行记录、重试和观测。
8. `SCM-07` 接入客户活动创建、更新、删除。
9. `SCM-08` 接入客户活动 AI 整理完成入口。
10. `SCM-09` Agent 任务查询 tool 和服务。
11. `SCM-10` 历史回填命令。
12. `SCM-11` Phase 1 集成测试和验收样本。
13. `SCM-12` 最小展示和运维排查能力。

当前实施进展：

- `SCM-00` 已完成：现状接入点清单已写入本文档。
- `SCM-01` 已完成基础实现：`crm_customer_activities.owner_id` 模型、迁移、创建默认值、响应字段和相关测试夹具已补齐。
- `SCM-02` 已完成基础实现：销售承诺、跟进任务、任务事件、投影运行模型和建表迁移已补齐。
- `SCM-03` 已完成：补齐销售承诺/跟进任务 schema、CRUD、public_id helper、任务查看/操作权限 helper 和对应单元测试；同时收紧对外 response 映射，避免内部数据库主键进入 Agent/API 上下文。
- `SCM-04` 已完成：补时间规范化和 today / this_week / next_week / overdue 查询窗口。
- `SCM-05` 已完成核心实现：补确定性 `FollowUpTaskProjectionService`，支持从客户活动生成、更新、取消任务和承诺。
- `SCM-06` 已完成：补投影运行记录编排、失败记录、失败查询和失败重试入口。
- `SCM-07` 已完成：客户活动创建、更新、单独修改下次跟进时间、删除入口已接入统一投影流程。
- `SCM-08` 已完成：客户活动 AI 结构化字段持久化后已接入统一投影流程。
- `SCM-09` 已完成：补 Agent 任务查询服务和只读 tools，支持我的任务、客户范围任务、任务详情和已完成工作查询。
- `SCM-10` 已完成：补历史客户活动回填服务和 dry-run/confirm 脚本。
- `SCM-11` 已完成：补 Phase 1 关键入口集成验收样本，覆盖页面录入、Agent 录入、AI 整理后投影、更新清空、删除取消和历史回填重复执行。
- `SCM-12` 已完成：补最小展示和运维排查 API、投影运行排查、失败重试和日志观测。
- `SCM-P2-00` 已完成：补 Phase 2 reconciliation 评估契约、核心 golden case fixture、纯确定性评估服务和本地评估脚本。
- `SCM-P2-01` 已完成：reconciliation golden set 已扩充到 35 个半真实业务样本，并补分类覆盖测试，覆盖自动完成、延期、取消、无关新动作、跨 owner 确认、低置信确认、手工清空/删除边界和保留开放任务。
- `SCM-P2-02` 已完成第一层实现：补只读 `TaskReconciliationService` 结构化候选任务检索，默认同客户同 owner，跨 owner 只能显式作为需确认候选返回。
- `SCM-P2-03` 已完成建议器实现：补 LLM semantic match structured output、schema 校验、本地 guardrail 降级和单元测试；仍不接入投影流程，不直接开启自动关闭、延期或取消。
- `SCM-P2-04` 已完成底层计划、执行器、灰度策略服务和 executor 级回滚能力：自动执行默认关闭，只有同 owner、高置信、有证据、策略允许的 action 才能进入 executor；自动完成/取消可重开，自动延期可恢复 previous due_at。
- `SCM-P2-05` 已完成确认 Case、确认回复应用层、过期清理、Agent tools、主动提示编排、IM 回复绑定、跨渠道触达去重和 Web/IM smoke 验证：Web Agent / IM Bot 共享同一 Channel Service，确认回复统一通过应用服务和 executor 落库。
- `SCM-P2-06` 已完成跨 owner 候选处理策略复核和测试补强：候选检索可显式纳入跨 owner，但只作为确认候选；语义匹配、计划生成、确认应用和 executor 均阻止跨 owner 自动完成、延期或取消。
- `SCM-P2-07` 已完成回滚、观测事实源和评测指标持久汇总：任务事件补 `fte_` public_id，自动状态迁移事件写 rollback 快照，executor 支持按事件 public_id 幂等撤销；新增任务状态迁移观测汇总服务、只读运维 API、自动迁移策略决策日志、reconciliation run trace、LLM matcher run/schema error 日志和 reconciliation evaluation run 质量门禁记录。
- `SCM-P2-08` 已完成失效 pending confirmation case 清理：任务被完成/取消、来源下一步被清空、来源活动删除或同源任务被投影替换时，关联 pending Case 会幂等取消并记录取消审计，避免 Agent 继续提示已失效问题。
- `SCM-P3-01` 已完成：新增 `sales_commitment` / `follow_up_task` 向量 source type、`CustomerVectorDocument.metadata_json`、builder/service upsert 契约、Qdrant payload 透传和 public-id metadata 测试；旧客户活动 `follow_up` 向量 source 保持兼容。
- `SCM-P3-02` 已完成：任务/承诺创建、更新、取消和任务状态迁移后，会在同一事务内刷新 `CustomerVectorDocument` metadata；Qdrant 仍通过既有异步 sync worker 消费 pending 文档。
- `SCM-P3-03` 已完成：Agent 任务查询 tool 支持 `query_text` 语义条件，先用 Qdrant 召回任务/承诺证据，再按 MySQL 当前状态、owner、客户可见范围和时间窗口回表过滤。
- `SCM-P3-04` 已完成：新增任务/承诺向量证据一致性检查服务，可刷新 stale metadata、标记孤儿证据 `DELETE_PENDING`，并保持重复执行幂等。
- `SCM-P3-05` 已完成：新增任务语义查询 golden suite，覆盖预算、试用、合同、采购、跨 owner、stale status、排序和无命中，并通过实际 `FollowUpTaskQueryService` 执行验证。
- `SCM-P4-01` 已完成：定义 `WorkSummaryService` 结构化工作事实源范围，明确 MySQL 是工作完成事实源，Agent/LLM 只做归纳总结。
- `SCM-P4-02` 已完成：`list_completed_work` 已汇总已完成任务、客户活动、商机阶段、合同、回款、发票和 License 事件，并保留旧 `completed_tasks` / `activities` 兼容输出。
- `SCM-P4-03` 已完成：`list_completed_work` 已支持上周、本月、自定义日期范围、cursor 翻页、截断标记和 source total counts，作为 Agent 周报/月报 structured facts。
- `SCM-P4-04` 已完成：新增带 fact_id 引用的 `WorkSummaryNarrativeService` 和 `summarize_completed_work` 只读 Agent tool，LLM 只能基于 structured facts 归纳。
- `SCM-P4-05` 已完成：新增工作总结 golden suite、确定性质量评测、人工校正样本契约、本地评测脚本和评测运行持久化兼容。
- `SCM-P4-06` 已完成：主 Agent graph 已补全局和客户范围任务查询/工作总结的确定性只读 tool 路由，支持“今天/本周/下周任务”“还有哪些客户要跟进”“某客户下周有哪些任务”“本周完成了什么/周报/月报”等自然语言问题。
- `SCM-P4-07` 已完成：只读查询语义模型已从历史 `CUSTOMER_QUERY` 收敛为 `CRM_READ_QUERY + read_query.type`；新增 planner/presenter 分层，trace 展示业务标签，旧意图只保留在 schema/输入适配边界归一化。

## 4. Phase 1 任务拆分

### SCM-00：现状确认和接入点复核

目标：

- 在动表结构前确认现有客户活动、Agent tool、AI 整理 workflow 的真实接入点。

范围：

- 确认页面客户活动创建接口位置和入参/出参。
- 确认 Agent 创建跟进记录是否复用客户活动 API。
- 确认 `customer_activity_ai_workflow.persist_structured_content` 持久化字段。
- 确认 `CustomerActivity` 当前字段、权限过滤、更新时间、删除/作废语义。
- 确认现有 `next_action`、`next_follow_time` 的生成和覆盖规则。

验收：

- 输出代码层接入点清单，至少包含文件路径、函数名、触发时机。
- 明确哪些入口是同步执行，哪些入口适合异步触发投影。
- 明确活动删除是物理删除、软删除还是状态作废。
- 明确当前系统 datetime 存储口径和团队/用户时区来源。

依赖：无。

现状接入点清单：

| 路径 | 函数/位置 | 当前触发时机 | 对任务投影的含义 |
| --- | --- | --- | --- |
| `CRM-Server/app/api/customer_activities.py` | `create_activity` | 页面或内部 API 创建客户活动后，同步提交活动，再 `trigger_processing` 异步整理 | 保存后如果已有显式 `next_action` 或 `next_follow_time`，可异步触发 `ACTIVITY_CREATED_DETERMINISTIC`；没有显式字段时等待 AI 整理完成 |
| `CRM-Server/app/api/customer_activities.py` | `update_activity` | 更新活动后同步提交，再 `trigger_processing` 异步整理 | 原文、下一步动作、下次跟进时间变化后触发 `ACTIVITY_UPDATED`；后续 AI 整理完成再触发 `ACTIVITY_STRUCTURED_COMPLETED` 更新同源任务 |
| `CRM-Server/app/api/customer_activities.py` | `update_next_time` | 单独更新下次跟进时间后，只触发有效性评分 | 该入口也属于用户明确修改下一步安排，应触发 `ACTIVITY_UPDATED`，不能只评估不投影 |
| `CRM-Server/app/api/customer_activities.py` | `delete_activity` | 当前只允许创建人删除，CRUD 内执行物理删除 | `ACTIVITY_DELETED` 必须在 `db.delete` 提交前用活动快照触发，否则删除后无法可靠定位同源开放任务 |
| `CRM-Server/app/crud/customer_activity.py` | `create` | 写入活动、成交旅程事件、操作日志、客户证据向量 metadata | CRUD 已包含多种副作用；任务投影不应塞入 CRUD 主流程，建议由 API/服务层调用统一投影服务 |
| `CRM-Server/app/crud/customer_activity.py` | `migrate_from_lead` | 线索转客户时迁移历史 follow-up 为客户活动 | Phase 1 虽不纳入线索任务，但 `owner_id` 迁移必须覆盖这里，默认 `owner_id = lead_follow_up.creator_id` |
| `CRM-Server/app/crud/customer_activity.py` | `update_processed_content` | AI 结构化结果落库，可能更新 `next_action`、`next_follow_time` | 这是 AI 整理完成后的最终字段入口；投影应在它之后触发，避免重新解析原文 |
| `CRM-Server/app/services/customer_activity_ai/workflow.py` | `_persist_structured_content` | LangGraph `structure_activity` 后持久化结构化内容 | 适合触发 `ACTIVITY_STRUCTURED_COMPLETED`；此时可拿到最终活动字段和 LangGraph 运行事件 |
| `CRM-Server/app/services/customer_activity_processing_service.py` | `trigger_processing` / `process` | `asyncio.create_task` 异步运行客户活动 AI workflow | 投影触发应采用同样的非阻塞策略，失败只写投影运行和日志，不回滚活动保存 |
| `CRM-Server/app/services/customer_activity_processing_service.py` | `recover_unfinished` | 应用启动时重派 `PENDING/PROCESSING` 或 `GENERATING` 活动 | 任务投影失败/中断也需要类似恢复或重试能力，但独立于 AI workflow 恢复 |
| `CRM-Server/app/services/agent/tools/service.py` | `create_customer_activity` | Agent tool 调内部 API `POST /v1/customer-activities/{customer_public_id}` | Agent 不直接写活动表，所以页面和 Agent 可以复用同一投影入口；tool 继续使用客户 public_id |
| `CRM-Server/app/services/agent/tool_registry.py` | `CreateCustomerActivityInput` / `_build_tools` | 声明 Agent 创建客户活动 tool | 后续新增任务查询 tool 时只暴露任务 public_id，不接受数据库主键 |
| `CRM-Server/app/main.py` | `startup_event` | 启动时恢复客户活动 AI workflow 并启动向量同步任务 | 后续可挂投影失败重试调度或恢复，但不应阻塞应用启动 |

现状语义结论：

- 客户活动当前没有 `owner_id`，只有 `creator_id`；任务归属无法直接从现有字段可靠表达，因此 `SCM-01` 必须先补独立 owner。
- 页面和 Agent 创建活动最终都走客户活动 API，具备统一流程的基础。
- 页面保存时如果用户没有拆填 `next_action` / `next_follow_time`，当前 AI workflow 有机会从正文里的 `next_follow_time_text` 抽取时间并落库；任务投影应等 AI 整理持久化后再处理这类场景。
- AI 结构化时间覆盖规则已经存在：不会覆盖 `USER`、`AGENT`、`MIGRATED` 来源时间；可以覆盖 `UI_DEFAULT`、空值或 AI 来源时间。
- `next_follow_time` 当前用 naive `DateTime` 存储，业务时间 helper 为 `Asia/Shanghai`。Phase 1 先与现有口径兼容，并在任务表显式保存 `due_at_timezone` 和粒度字段，避免后续扩展用户/团队时区时迁移语义不清。
- 活动删除当前是物理删除，不是软删除或状态作废。任务投影需要在删除前记录事件并取消同源开放任务。
- 客户活动证据向量当前在 CRUD 中写 metadata/标记删除；任务状态事实源不能依赖 Qdrant，后续任务/承诺向量同步只能作为语义证据层。
- 活动编辑/删除权限目前是 `creator_id` 限制；任务 owner 后续应来自 `activity.owner_id`，不能把“能编辑活动”和“能操作任务状态”混成同一权限。

### SCM-01：客户活动 owner_id 迁移

目标：

- 给客户活动引入独立跟进归属人，避免任务错误归属到客户负责人或记录创建人。

范围：

- `crm_customer_activities` 增加 `owner_id`。
- 历史活动使用 `creator_id` 初始化 `owner_id`。
- 页面新增活动默认 `owner_id = current_user.id`。
- Agent 新增活动默认 `owner_id = current_user.id`。
- 更新客户活动 schema、CRUD、API 响应和权限逻辑。
- 增加索引，至少覆盖 `team_id + owner_id + occurred_at` 或现有等价时间字段。

验收：

- 既有活动迁移后 `owner_id` 不为空。
- 页面和 Agent 创建的新活动 `creator_id`、`owner_id` 语义正确。
- 客户 owner 不参与任务归属派生。
- 客户成员协作场景下，不同用户给同一客户添加活动时，活动 owner 分别正确。

依赖：`SCM-00`。

### SCM-02：销售承诺和跟进任务数据模型

目标：

- 建立销售承诺和跟进任务的结构化事实源。

范围：

- 新增模型和迁移：
  - `crm_sales_commitments`
  - `crm_follow_up_tasks`
  - `crm_follow_up_task_events`
  - `crm_follow_up_task_projection_runs`
- 承诺和任务表必须包含 `public_id`、`team_id`、`customer_id`、`owner_id`、`creator_id`、来源字段、时间字段、状态字段、置信度和 `evidence_json`。
- 任务表包含 `task_hash`，承诺表包含 `commitment_hash`。
- 承诺和任务表包含非空 `source_key`，用于承载活动来源或历史回填来源的稳定幂等键；`source_activity_id` 仅作为可空关联字段。
- 投影运行表包含 trigger、status、skip_reason、input snapshot hash、projection hash、created/updated task id 列表、错误信息和耗时字段。
- 补充必要 enum 或常量定义。

验收：

- Alembic 可升级、可回滚。
- `crm_sales_commitments.public_id` 全局唯一。
- `crm_follow_up_tasks.public_id` 全局唯一。
- `team_id + source_type + source_key + task_hash` 可阻止同一来源重复生成相同任务，避免 MySQL 唯一约束遇到 `NULL` 失效。
- 常用查询索引覆盖“我的任务”“客户任务”“失败投影运行排查”。

依赖：`SCM-01`。

### SCM-03：public_id、schema、CRUD 和权限基础

目标：

- 让任务/承诺实体在 API、Agent tool 和 LLM 上下文中只暴露 public_id。

范围：

- 实现承诺、任务、事件、投影运行的 schema。
- 实现 CRUD 或 repository 层：
  - 按 public_id 解析任务/承诺。
  - 创建/更新任务。
  - 创建承诺。
  - 写任务事件。
  - 写投影运行。
- 实现 public_id 生成策略，建议前缀：
  - 承诺：`scm_`
  - 跟进任务：`fut_`
  - 投影运行：`tpr_`，如果需要对外排查。
- 权限校验拆分：
  - 用户是否有客户访问权。
  - 用户是否是任务 owner。
  - 用户是否允许查看客户范围内其他 owner 的任务。
  - 用户是否允许操作任务状态。

验收：

- API/schema 不向 Agent 或前端暴露任务、承诺数据库主键。
- tool 入参不接受数据库主键。
- “能访问客户”不等于“能关闭别人任务”。
- 查询我的任务时以 `task.owner_id == current_user.id` 为准。
- CRUD 写操作支持在投影服务事务中只 `flush` 不 `commit`，投影服务可一次性提交承诺、任务、事件和投影运行状态。

依赖：`SCM-02`。

实现记录：

- `CRM-Server/app/utils/public_id.py` 已补 `scm_`、`fut_`、`tpr_` 三类 public_id 校验。
- `CRM-Server/app/schemas/sales_commitment.py` 已补承诺、跟进任务、任务事件、投影运行 schema。写入 DTO 明确命名为 `SalesCommitmentInternalCreate`、`FollowUpTaskInternalCreate`、`FollowUpTaskEventInternalCreate`、`FollowUpTaskProjectionRunInternalCreate` 等内部类型，避免后续误用于外部 API 入参。
- 对外 response DTO 不启用直接 ORM `from_attributes` 序列化，必须通过显式 `from_model` 映射；`id` 映射为实体 `public_id`，内部 `customer_id`、`commitment_id`、`task_id`、`source_key`、`source_activity_id` 和投影运行内部 ID 列表不直接外露。
- 投影运行 response 的 `created_task_ids`、`updated_task_ids`、`cancelled_task_ids`、`created_commitment_ids`、`updated_commitment_ids` 只允许填 public_id 列表；CRUD 层提供按内部 ID 批量映射 public_id 的 helper，避免 Agent/API 上下文拿到数据库主键。
- `CRM-Server/app/crud/sales_commitment.py` 已补承诺、跟进任务、任务事件、投影运行 CRUD；支持按 public_id、source key/hash、owner/customer/date/status 查询，支持 `commit=False` 事务写入，支持投影运行 success/skipped/failed 状态更新。
- `source_activity_id` 是可空字段，幂等统一依赖非空 `source_key`；任务、承诺和投影运行表都保存 `source_key`，唯一约束使用 `team_id + source_type + source_key + hash`，避免 MySQL 唯一约束遇到 `NULL` 失效。
- `CRM-Server/app/core/deps.py` 已补 `check_follow_up_task_direct_view_permission`、`check_follow_up_task_view_permission` 和 `check_follow_up_task_owner_permission`；直接任务视图和客户上下文任务视图分开，状态操作以任务 owner 为准，并预留任务级管理权限码。
- `CRM-Server/tests/unit/test_sales_commitment_crud.py` 覆盖 public_id 校验、CRUD 查询、source key 幂等、重复 source/hash 唯一约束、直接 ORM response 序列化失败、投影运行 public-id 列表映射、`commit=False`、owner 过滤、空状态过滤、状态时间一致性、事件写入、投影运行状态更新和权限边界。
- 当前 `CustomerActivity` 还没有 `public_id`，所以活动来源的任务/承诺先保存内部 `source_activity_id` 和非空 `source_key`；`source_public_id` 只在来源对象已有真实 public_id 时填充，不填 synthetic key。后续如果活动本身需要进入 Agent/API 对外链路，应单独补 `CustomerActivity.public_id` 迁移和接口替换。

### SCM-04：时间规范化和查询时间窗口

目标：

- 统一 `due_at`、`due_at_text`、`due_at_granularity`、`due_at_timezone` 的解析、存储和查询口径。

范围：

- 明确使用用户时区还是团队时区，缺省时采用团队时区。
- 实现时间标准化 helper：
  - 日期级任务。
  - 日期时间级任务。
  - 周级任务。
  - 月级任务。
  - 未知粒度。
- 实现 today / this_week / next_week / overdue 的查询窗口计算。
- 避免把 `OVERDUE` 持久化为状态，通过 `due_at` 和查询时区动态计算。

验收：

- 用户问“今天”“本周”“下周”时，查询窗口稳定且可测试。
- 只有日期没有具体时刻的任务，展示不误导为 00:00。
- 历史回填解析相对时间时，以活动发生时间为基准，不以回填执行当天为基准。
- 所有任务都保存 `due_at_granularity` 和 `due_at_timezone`。

依赖：`SCM-03`。

实现记录：

- `CRM-Server/app/utils/time.py` 已补业务时区标准化、aware datetime 转业务本地 naive datetime、`normalize_due_at` 和 `calculate_follow_up_task_due_window`。
- 到期时间标准化覆盖 `DATE`、`DATETIME`、`WEEK`、`MONTH`、`UNKNOWN`；日期级任务存当天 00:00，但依赖 `due_at_granularity` 展示，不能在 UI/Agent 中误读成精确 00:00。
- today / this_week / next_week 以 `Asia/Shanghai` 业务时间计算窗口；周窗口按 ISO 周一开始。
- overdue 不持久化为任务状态；查询时动态计算。日期级任务当天不算逾期，精确时间级任务如果当天已过点可以进入逾期结果。
- `CRM-Server/app/crud/sales_commitment.py` 的 owner/customer 任务查询支持 `due_window=today|this_week|next_week|overdue`，并禁止和手工 `due_at_start/due_at_end` 混用，避免窗口语义冲突。
- `CRM-Server/tests/unit/test_business_time.py` 和 `CRM-Server/tests/unit/test_sales_commitment_crud.py` 覆盖时区转换、粒度标准化、周边界和命名窗口查询。

### SCM-05：FollowUpTaskProjectionService 核心逻辑

目标：

- 建立所有入口共享的任务投影服务，负责从客户活动最终字段生成、更新、取消或跳过任务。

范围：

- 新增 `FollowUpTaskProjectionService`。
- 输入包含：
  - activity id
  - trigger_type
  - actor/current user
  - 是否允许创建低置信任务
  - backfill batch 信息，可选
- 支持触发类型：
  - `ACTIVITY_CREATED_DETERMINISTIC`
  - `ACTIVITY_STRUCTURED_COMPLETED`
  - `ACTIVITY_UPDATED`
  - `ACTIVITY_DELETED`
  - `HISTORICAL_BACKFILL`
- 投影规则：
  - 有明确 `next_follow_time` 且有或可生成动作文案时，生成或更新开放任务。
  - 只有 `next_action`、没有时间时，可生成 commitment/evidence，不进入强待办。
  - `next_action` 和 `next_follow_time` 都没有时，不生成任务，记录 skip。
  - 同源开放任务存在时优先更新，不重复创建。
  - 清空下一步字段时取消同源开放任务，原因 `SOURCE_NEXT_STEP_REMOVED`。
  - 删除/作废活动时取消同源开放任务，原因 `SOURCE_ACTIVITY_DELETED`。
- owner 派生：
  - 任务/承诺 `owner_id = activity.owner_id`。
  - 任务/承诺 `creator_id = activity.creator_id` 或明确系统 actor，并写入 evidence。

验收：

- 同一活动被多次投影不会重复创建任务。
- 页面保存后投影和 AI 整理后投影能更新同一任务。
- 用户编辑下一步动作或时间时，同源任务被更新并写事件。
- 用户清空下一步字段或删除活动时，同源开放任务被取消并写事件。
- 同一客户不同 owner 的任务互不影响。

依赖：`SCM-04`。

实现记录：

- `CRM-Server/app/services/follow_up_task_projection_service.py` 已新增确定性投影服务，输入为 `activity_id`、`trigger_type`、`actor_id`，删除场景支持传入删除前 `activity_snapshot`。
- 投影 owner 明确来自 `CustomerActivity.owner_id`，creator 来自 `CustomerActivity.creator_id`；同一客户不同 owner 的活动分别生成各自任务，互不影响。
- 有 `next_follow_time` 时生成或更新开放跟进任务；有 `next_action` 但无时间时只生成/更新 commitment，不进入强待办；无下一步动作和时间时不生成任务。
- 同源开放任务优先按 `source_key` 更新，不因活动创建、AI 整理完成、用户编辑重复生成；同源重复开放任务会被取消，保留一个开放任务。
- 清空下一步字段时取消同源开放任务和开放 commitment，原因 `SOURCE_NEXT_STEP_REMOVED`；删除活动时通过删除前快照取消同源开放任务和开放 commitment，原因 `SOURCE_ACTIVITY_DELETED`。
- 任务创建、更新、取消都会写 `crm_follow_up_task_events`；事件 payload 记录原因和变更前后业务字段。
- 投影服务返回 `FollowUpTaskProjectionResult`，包含 input/projection hash、skip_reason、created/updated/cancelled 内部 ID 列表；SCM-06 会把这个结果落到 `crm_follow_up_task_projection_runs` 并做 public_id 映射。
- `evidence_json` 不写活动内部数据库 ID，避免未来 response/Agent 上下文泄漏内部主键；幂等仍由库内 `source_key` 和 hash 保证。
- `CRM-Server/tests/unit/test_sales_commitment_crud.py` 覆盖创建幂等、活动更新修正同源任务、清空下一步字段取消、仅 commitment 不生成任务、删除活动快照取消、同客户不同 owner 隔离。

### SCM-06：投影运行记录、重试和观测

目标：

- 让每次投影可排查、可重试、可审计。

范围：

- 投影开始时写入 `crm_follow_up_task_projection_runs`。
- 投影完成时更新状态、skip_reason、task_count、commitment_count、created/updated task ids。
- 失败时记录 `FAILED`、错误摘要、attempt_count。
- 支持按 source activity 查询投影运行历史。
- 支持失败投影运行的重试入口，重试仍调用同一个投影服务。
- 对过期输入写 `SUPERSEDED_INPUT` 或等价 skip_reason。

验收：

- 每个触发入口都能查到投影运行记录。
- 失败不会导致客户活动保存失败。
- 重试不会重复生成任务。
- 排查“为什么没生成任务”时能看到 `NO_NEXT_STEP`、`NO_DUE_AT`、`DUPLICATE`、`SUPERSEDED_INPUT` 等原因。

依赖：`SCM-05`。

实现记录：

- `CRM-Server/app/services/follow_up_task_projection_service.py` 已新增 `run_activity_projection`，作为带观测的投影入口；原 `project_activity` 保持为确定性核心逻辑，便于后续在更大的事务中复用。
- `run_activity_projection` 会先创建 `RUNNING` 投影运行，再在嵌套事务中执行确定性投影；成功后写入 `SUCCESS`，有跳过原因时写入 `SKIPPED`，失败时写入 `FAILED` 和截断后的错误摘要。
- 投影运行记录保存 `input_snapshot_hash`、`projection_hash`、created/updated/cancelled task 内部 ID 列表、created/updated commitment 内部 ID 列表、`task_count`、`commitment_count`、`duration_ms` 和 `finished_at`。
- `SKIPPED` 不等于没有副作用：例如 `NO_DUE_AT` 可能只创建 commitment，不生成强待办；删除或清空下一步可能取消同源开放任务。投影运行记录仍会保存对应 ID 列表和计数，方便排查。
- 活动不存在时支持传入 `team_id` 记录 `ACTIVITY_NOT_FOUND` 的 skipped 运行；没有 `team_id` 时拒绝写运行记录，避免产生无团队归属的观测数据。
- `CRM-Server/app/crud/sales_commitment.py` 已补 `list_failed`，后续调度器、管理接口或运维脚本可按 team/source 拉取失败投影运行。
- `FollowUpTaskProjectionService.retry_projection_run` 支持对 `FAILED` 的客户活动来源运行进行重试；重试创建新的投影运行记录，`attempt_count = 原失败运行 attempt_count + 1`，并继续复用同一套幂等投影逻辑，因此不会重复生成开放任务。
- `FollowUpTaskProjectionSkipReason` 已预留 `SUPERSEDED_INPUT`；当前 Phase 1 的同步入口默认读取活动最新字段，后续如果引入延迟队列快照投影，应在入队快照 hash 和当前活动 hash 不一致时落该原因。
- `CRM-Server/tests/unit/test_sales_commitment_crud.py` 覆盖运行记录成功、重复投影跳过、无下一步跳过、仅 commitment 不生成任务、失败截断、失败查询和重试幂等。

### SCM-07：接入客户活动创建、更新、删除

目标：

- 页面和 Agent 创建/更新/删除客户活动后，进入统一投影流程。

范围：

- 活动创建后：
  - 如果保存时已有显式 `next_action` 或 `next_follow_time`，触发 `ACTIVITY_CREATED_DETERMINISTIC`。
  - 如果没有显式字段，不立即创建任务，等待 AI 整理完成。
- 活动更新后：
  - 原文、`next_action`、`next_follow_time` 变化时触发 `ACTIVITY_UPDATED`。
- 活动删除或作废后：
  - 触发 `ACTIVITY_DELETED`。
- Agent 创建活动不写单独任务逻辑，只复用同一服务。

验收：

- 页面手工录入和 Agent 录入生成的任务字段、owner、creator、事件规则一致。
- 页面只在原文中写了下一步动作和时间但没有拆字段时，不在创建时误生成任务，等待 AI 整理后处理。
- 活动更新/删除后的任务状态与来源活动一致。
- 投影失败不会回滚活动本身。

依赖：`SCM-06`。

实现记录：

- `CRM-Server/app/services/customer_activity_processing_service.py` 已新增 `trigger_follow_up_task_projection` 和 `project_follow_up_task`，页面/Agent 保存后的确定性投影采用后台任务触发，避免阻塞用户保存活动。
- `CRM-Server/app/api/customer_activities.py` 的创建入口在活动保存后，如果已经有 `next_action` 或 `next_follow_time`，触发 `ACTIVITY_CREATED_DETERMINISTIC`；如果页面没有拆填下一步字段，则不触发确定性投影，等待 AI 结构化完成后再判断。
- 客户活动更新入口只有在请求显式包含 `next_action` 或 `next_follow_time` 时触发 `ACTIVITY_UPDATED`；这覆盖新增、修改和清空下一步字段，避免单纯编辑正文时用旧结构化字段过早投影。
- 单独更新下次跟进时间入口会触发 `ACTIVITY_UPDATED`，因为这是用户明确调整跟进安排。
- 删除入口在物理删除客户活动前同步调用 `run_activity_projection(..., ACTIVITY_DELETED, activity_snapshot=activity)`，确保同源开放任务和承诺先被取消；删除后外键可置空，但 `source_key` 继续保留排查和幂等能力。
- 所有页面和 Agent 创建活动都复用 `POST /v1/customer-activities/{customer_public_id}`，因此 Agent 写跟进记录无需单独业务分支。

### SCM-08：接入客户活动 AI 整理完成入口

目标：

- 让 AI 整理后的最终 `next_action` / `next_follow_time` 成为任务投影的最终输入。

范围：

- 在 `customer_activity_ai_workflow.persist_structured_content` 或等价持久化节点之后触发 `ACTIVITY_STRUCTURED_COMPLETED`。
- 如果 AI 从原文补齐了 `next_action` 或 `next_follow_time`，投影服务生成或更新任务。
- 如果 AI 修正了保存后确定性投影的标题、动作或时间，投影服务更新已有任务。
- 如果 AI 判断没有下一步事项，投影服务跳过或取消同源低置信任务。
- 记录 AI 整理模型、置信度、证据摘要到 task/commitment evidence。

验收：

- 活动保存时没有显式字段，但 AI 整理后有下一步动作和时间，可以生成任务。
- AI 整理失败时，保存时已有显式下一步字段的任务仍然存在。
- AI 整理后重复触发不会重复创建任务。
- 投影运行表能区分保存后投影和 AI 整理后投影。

依赖：`SCM-07`。

实现记录：

- `CRM-Server/app/services/customer_activity_ai/workflow.py` 已在 `_persist_structured_content` 中，在 `customer_activity_crud.update_processed_content` 和有效性评分状态更新之后触发 `ACTIVITY_STRUCTURED_COMPLETED` 投影。
- 该入口使用活动最终结构化字段，不重新解析原始正文；`next_action`、`next_follow_time` 的来源和覆盖规则仍由现有 AI workflow 负责。
- 投影失败被捕获并写日志；`run_activity_projection` 内部会尽量落 `FAILED` 投影运行，避免任务投影问题反向打断活动 AI 整理流程。
- 页面未拆填下一步字段、但正文中包含下一步动作/时间的场景，由 AI 结构化持久化后统一生成任务。

### SCM-09：Agent 任务查询 tool 和服务

目标：

- 让 Agent 能通过结构化事实源回答任务相关问题。

范围：

- 新增或扩展 `FollowUpTaskQueryService`。
- 新增 Agent tools：
  - `list_follow_up_tasks`
  - `get_follow_up_task_detail`
  - `resolve_follow_up_task`，Phase 1 可只支持只读或受限操作，状态操作进入后续阶段。
  - `list_completed_work`，Phase 1 可先返回任务和活动基础事实，完整工作总结放 Phase 4。
- 支持过滤：
  - today
  - this_week
  - next_week
  - overdue
  - open
  - completed
  - customer scope
- 回答中展示客户、任务标题、到期时间、逾期天数、来源活动摘要和 public_id。

验收：

- “今天我的任务有哪些？”只返回当前用户 owner 的任务。
- “本周我的任务有哪些？”按用户/团队时区计算范围。
- “我还有哪些客户要跟进？”按客户聚合开放任务。
- “这个客户还有哪些任务？”在客户可访问前提下可按 owner 分组展示。
- tool 输入输出只使用 public_id。
- Agent 不从向量库直接推断任务完成状态。

依赖：`SCM-08`。

实现记录：

- `CRM-Server/app/services/follow_up_task_query_service.py` 已新增 `FollowUpTaskQueryService`，统一承载 Agent/API/IM 后续复用的任务查询逻辑。
- `list_tasks` 支持 `status=open|completed|cancelled|all`、`due_window=today|this_week|next_week|overdue`、`customer_public_id` 和 `owner_scope=mine|customer`。默认 `mine` 只返回当前用户作为任务 owner 的任务；`customer` 需要指定客户 public_id，并在客户可访问时返回该客户范围内任务。
- `get_task_detail` 只接受任务 public_id；任务 owner 可直接查看，非 owner 必须具备客户可见性；输出包含来源活动摘要，但不暴露 `source_activity_id` 或活动内部主键。
- `list_completed_work` 按 `today|this_week` 返回当前用户已完成任务和已记录客户活动，作为 Agent 回答“本周我完成了什么”的结构化事实基础。
- 查询响应显式声明 `usage_policy`：任务状态以 MySQL 结构化任务表为准，Qdrant 只作为语义证据补充，不作为任务完成状态来源。
- `CRM-Server/app/services/agent/tools/service.py` 已接入 `list_follow_up_tasks`、`get_follow_up_task_detail`、`list_completed_work`，统一走 `_run_read_tool` 写 Agent tool 审计。
- `CRM-Server/app/services/agent/tool_registry.py` 已注册三个只读工具；只读 LangChain tool 暴露时可包含任务查询工具，不需要 HITL。
- `CRM-Server/tests/unit/test_agent_tools.py` 已覆盖“今天我的任务”仅返回当前 owner、客户范围任务依赖客户可见性、任务详情只用 public_id 且隐藏内部 activity id、已完成工作查询返回完成任务和客户活动、只读 registry 暴露新工具。

### SCM-10：历史客户活动回填命令

目标：

- 将已有客户活动中的明确下一步安排低打扰地纳入任务体系。

范围：

- 新增历史回填命令或后台 job。
- 只处理客户活动，不处理线索 follow-up。
- 默认窗口最近 90 天，可配置。
- 按 `team_id + customer_id + owner_id` 分组。
- 每个客户、每个 owner 最多保留最新 1 条开放历史任务。
- 没有明确 `next_follow_time` 的历史活动不生成开放任务。
- 历史活动没有 `owner_id` 时，先按 `creator_id` 初始化。
- 回填写入投影运行和任务事件。

验收：

- 回填可 dry-run，能输出预计创建、跳过、关闭/覆盖数量。
- 回填可重复执行，不重复生成任务。
- 每客户每 owner 最多 1 条开放历史任务。
- 90 天以外记录不制造开放待办压力。
- 回填解析相对时间时以活动发生时间和归属人时区为基准。

依赖：`SCM-08`。

实现记录：

- `CRM-Server/app/services/follow_up_task_backfill_service.py` 已新增 `FollowUpTaskBackfillService`，核心回填逻辑和命令入口解耦，后续可复用到后台 job 或管理入口。
- 默认扫描最近 90 天客户活动，可传 `team_id`、`days`、`limit`、`actor_id`、`dry_run`；默认 dry-run，不写入任务、承诺、投影运行或活动 owner。
- 回填选择规则是按 `team_id + customer_id + owner_id` 对最近活动倒序去重，只处理每组最新 1 条活动；如果该最新活动没有明确 `next_follow_time`，整组跳过，不向更早记录回退，避免制造旧待办。
- 历史活动 `owner_id` 缺失时，运行期使用 `creator_id` 作为 owner 兜底；正式执行时会先补齐活动 owner 再进入投影。正常迁移路径仍应优先保证 `owner_id` 非空。
- 正式执行不直接写任务表，而是调用 `run_activity_projection(..., HISTORICAL_BACKFILL)`；因此任务/承诺生成、事件、投影运行记录、失败记录和幂等都复用统一投影服务。
- 当前回填只保证本次历史回填不会为同一客户/owner 创建多条新任务；它不会主动清理已存在的其他来源开放任务，避免误取消部署后正常实时流程产生的任务。
- `CRM-Server/scripts/backfill_follow_up_tasks.py` 已新增 CLI：默认预览，使用 `--confirm` 才写入；输出 JSON 统计，包括扫描数、选中组数、跳过数、预计投影数、创建/更新/取消数量、投影运行 ID 和失败摘要。
- 本地开发库已在 2026-08-07 执行 `--days 90 --limit 1000 --confirm`，扫描 68 条客户活动，生成 11 条销售承诺和 11 条开放跟进任务，投影运行 11 条且无失败。
- 生产发布已接入 `CRM-Docs/deployment/deploy.sh`：Alembic 结构迁移成功后自动执行同一条历史回填命令，避免上线时遗漏数据迁移步骤。
- `CRM-Server/tests/unit/test_sales_commitment_crud.py` 已覆盖 dry-run 不写入、最新无 due 整组跳过、每客户/owner 只投影最新 due 活动、重复执行不重复创建任务。

### SCM-11：Phase 1 集成测试和验收样本

目标：

- 用测试固定 Phase 1 的关键业务边界，防止后续接 Phase 2 时破坏基础可信度。

范围：

- 单元测试：
  - public_id 生成和解析。
  - 时间窗口计算。
  - 投影 hash 和幂等。
  - owner/creator 分离。
- 服务测试：
  - 创建活动后生成任务。
  - AI 整理后补生成任务。
  - AI 整理后更新保存时生成的任务。
  - 更新活动后更新同源任务。
  - 清空下一步字段后取消任务。
  - 删除/作废活动后取消任务。
  - 同客户不同 owner 任务隔离。
  - 历史回填重复执行。
- Agent tool 测试：
  - 我的任务权限。
  - 客户范围任务展示。
  - public_id 输入输出。

验收：

- Phase 1 验收样本覆盖页面录入、Agent 录入、AI 整理、更新/删除和历史回填。
- 自动测试可在本地或 CI 稳定执行。
- 所有关键状态变更都有事件和投影运行记录断言。

依赖：`SCM-09`、`SCM-10`。

实现记录：

- `CRM-Server/tests/unit/test_customer_activity_task_projection_api.py` 已新增轻量 API 入口验收测试，用只挂载 `customer_activities.router` 的测试 app 覆盖真实路由逻辑，避免主应用 startup 连接外部 MySQL 或启动后台任务。
- 页面手工录入显式 `next_action` / `next_follow_time` 时，测试断言创建客户活动后立即通过 `ACTIVITY_CREATED_DETERMINISTIC` 生成开放任务、任务创建事件和成功投影运行记录。
- 页面只填写原始跟进内容但没有结构化下一步字段时，测试断言创建活动阶段不生成任务、不写投影运行；AI 结构化持久化补齐 `next_action` / `next_follow_time` 后，再通过 `ACTIVITY_STRUCTURED_COMPLETED` 生成任务和投影运行。
- Agent 录入样本复用同一个 `POST /v1/customer-activities/{customer_public_id}` 入口，只通过 `next_follow_time_source=AGENT` 表明来源方式，不引入独立业务分支；测试断言同样生成任务。
- 更新活动清空下一步字段时，测试断言原同源开放任务被取消，写入 `CANCELLED` 事件，并记录 `ACTIVITY_UPDATED` / `SOURCE_NEXT_STEP_REMOVED` 投影运行。
- 删除客户活动时，测试断言删除前通过 activity snapshot 取消同源开放任务，写入 `ACTIVITY_DELETED` / `SOURCE_ACTIVITY_DELETED` 投影运行，然后再物理删除活动。
- 历史回填重复执行已在 `CRM-Server/tests/unit/test_sales_commitment_crud.py` 覆盖：每客户/owner 只投影最新 due 活动，重复执行不重复创建任务。

### SCM-12：最小展示和运维排查能力

目标：

- 不做完整任务管理页面，但给用户和开发者提供足够的可见性。

范围：

- Agent 回答任务列表时，提供稳定结构：
  - 客户名
  - 任务标题
  - 到期时间
  - 是否逾期
  - 来源摘要
  - task public_id
- 客户详情可选展示“当前跟进安排”只读块，不提供完整任务管理。
- 后端提供投影运行查询接口或管理排查入口。
- 日志记录投影 trigger、activity id、task public_id、projection run id 和失败摘要。

验收：

- 用户能通过 Agent 清楚看到任务安排，不需要进入新任务页面。
- 开发者能按活动定位投影运行、skip_reason 和失败原因。
- 展示层不使用数据库主键。

依赖：`SCM-09`。

实现记录：

- `CRM-Server/app/api/follow_up_tasks.py` 已新增最小任务查询接口：
  - `GET /v1/follow-up-tasks` 查询当前用户 owner 范围任务，支持 `status`、`due_window`、`customer_id`、`owner_scope` 和 `limit`。
  - `GET /v1/follow-up-tasks/customer-arrangements/{customer_id}` 查询客户详情只读“当前跟进安排”，使用客户 public_id 入参，返回只读展示策略，不提供任务管理操作。
- `CRM-Server/app/api/follow_up_tasks.py` 已新增投影排查接口：
  - `GET /v1/follow-up-task-projection-runs/by-activity/{activity_id}` 按当前客户活动内部 ID 查询投影运行；这是因为客户活动当前尚未引入 `public_id`，该接口定位为开发/运维排查入口，不作为普通展示字段。
  - `GET /v1/follow-up-task-projection-runs/failed` 查询失败投影运行。
  - `POST /v1/follow-up-task-projection-runs/{run_id}/retry` 通过投影运行 public_id 重试失败运行；只允许 `FAILED` 状态重试。
- `CRM-Server/app/main.py` 已注册 `follow_up_tasks.router` 和 `follow_up_tasks.projection_router`。
- `CRM-Server/app/services/follow_up_task_query_service.py` 的客户 payload 已补充 `name` 字段，同时保留 `account_name`，便于 Agent 生成自然回答并兼容既有展示字段。
- `CRM-Server/app/services/follow_up_task_projection_service.py` 已补充投影运行日志，记录 trigger、activity id、projection run public_id/internal id、task public_id、skip_reason 和失败摘要。
- `CRM-Server/tests/unit/test_follow_up_tasks_api.py` 已覆盖：
  - 任务列表返回 task/customer public_id、客户名、客户汇总和 MySQL 状态源说明，不暴露 `source_activity_id`。
  - 客户当前跟进安排按客户范围返回只读结构，并隐藏内部任务/活动 ID。
  - 投影运行按活动查询需要排查权限，并将内部 task/commitment ID 映射为 public_id。
  - 失败投影运行可查询，并可通过 projection run public_id 重试；重试成功后返回新的投影运行 public_id 和创建任务 public_id。
- 已验证：
  - `venv/bin/python -m pytest --no-cov tests/unit/test_follow_up_tasks_api.py`
  - `venv/bin/python -m pytest --no-cov tests/unit/test_follow_up_tasks_api.py tests/unit/test_customer_activity_task_projection_api.py tests/unit/test_sales_commitment_crud.py tests/unit/test_agent_tools.py tests/unit/test_customer_activity_ai_workflow.py tests/unit/test_agent_customer_activity_graph.py`
  - 结果：`86 passed`，仅有项目既有 Pydantic/SQLAlchemy deprecation warnings。

## 5. Phase 2 任务拆分：自动关闭和低置信追问

Phase 2 需要在 Phase 1 真实数据跑稳定后逐步打开，不能直接开启自动流转。第一批实现必须先建立评测、观测和只读候选能力，后续才允许接入 LLM semantic match 和状态迁移。

### SCM-P2-00：reconciliation 评估契约和核心样本基线

目标：

- 在实现自动关闭、延期、取消前，先固定 Phase 2 的安全合同和最小 golden case。

范围：

- 定义 reconciliation 输出结构：
  - `decision`
  - `task_public_id`
  - `candidate_public_ids`
  - `confidence`
  - `needs_confirmation`
  - `proposed_due_at`
  - `forbid_auto_reasons`
  - `evidence_terms`
  - `state_mutation_requested`
- 建立纯确定性 evaluation service，不调用 LLM，不访问数据库，不修改任务状态。
- 建立 golden fixture，覆盖同 owner 完成、同 owner 延期、同客户无关新动作、跨 owner 需确认、低置信需确认。
- 建立本地脚本，后续 CI 或手工验收可直接运行。

验收：

- 同 owner 高置信完成/延期样本通过。
- 跨 owner 样本不能自动完成，必须进入确认。
- 低置信样本不能自动延期、完成或取消。
- 评估输出只能使用任务 public_id，不能依赖数据库主键。
- 评估运行不产生任何业务状态变更。

实现记录：

- `CRM-Server/app/services/follow_up_task_reconciliation_evaluation_service.py` 已新增确定性评估服务，校验 decision、candidate、confidence、确认标记、禁止自动变更原因、证据词、public_id 和无副作用约束。
- `CRM-Server/app/services/follow_up_task_reconciliation_golden_suite.py` 已新增 golden suite loader，复用现有 customer context answer eval 的 fixture + service 模式。
- `CRM-Server/tests/fixtures/follow_up_task_reconciliation_golden_cases.json` 已新增 5 个核心样本。
- `CRM-Server/scripts/run_follow_up_task_reconciliation_eval.py` 已新增本地评估脚本。
- `CRM-Server/tests/unit/test_follow_up_task_reconciliation_evaluation_service.py` 和 `CRM-Server/tests/unit/test_follow_up_task_reconciliation_golden_suite.py` 已覆盖通过样本、跨 owner 自动关闭拒绝、低置信自动延期拒绝、内部 ID 拒绝和脚本成功运行。
- 已验证：
  - `venv/bin/python -m pytest --no-cov tests/unit/test_follow_up_task_reconciliation_evaluation_service.py tests/unit/test_follow_up_task_reconciliation_golden_suite.py`
  - 结果：`7 passed`。

依赖：`SCM-12`。

### SCM-P2-01：收集 Phase 1 样本并扩充自动关闭/延期评测集

目标：

- 将 Phase 1 运行中的真实跟进记录、开放任务和人工判断结果纳入 reconciliation golden set。

范围：

- 从投影运行、任务事件和客户活动中抽样。
- 优先收集：
  - 高置信完成旧任务。
  - 明确延期旧任务。
  - 新动作与旧任务无关。
  - 同客户不同 owner 的活动。
  - 语义含糊、容易误关的活动。
  - 用户手工清空下一步字段或删除活动后的边界样本。
- 每个样本人工标注 expected decision、expected task、是否需要确认、禁止自动处理原因和证据词。
- 样本进入 `follow_up_task_reconciliation_golden_cases.json` 或按来源拆分 fixture。

验收：

- 样本覆盖至少 30 个真实或半真实业务 case。
- 跨 owner、低置信、无关新动作和延期样本占比不能过低，避免评测集只覆盖“容易完成”的场景。
- 评测脚本能在不连接外部服务的情况下稳定运行。

实现记录：

- `CRM-Server/tests/fixtures/follow_up_task_reconciliation_golden_cases.json` 已从 5 个核心样本扩充到 35 个半真实业务样本。
- 样本新增 `category` 元数据，仅用于评测覆盖审查，不进入 `FollowUpTaskReconciliationEvaluationCase` 业务契约。
- 当前覆盖分布：
  - `same_owner_complete`：6 个。
  - `same_owner_delay`：5 个。
  - `unrelated_new_action`：5 个。
  - `cross_owner_confirmation`：5 个。
  - `low_confidence_confirmation`：6 个。
  - `same_owner_cancel`：2 个。
  - `manual_clear_boundary`：2 个。
  - `delete_boundary`：2 个。
  - `keep_open`：2 个。
- `CRM-Server/tests/unit/test_follow_up_task_reconciliation_golden_suite.py` 已改为至少 30 个样本的下限验收，并校验核心 5 个历史样本仍在、重点分类占比达标、脚本无外部服务可稳定运行。
- 已验证：
  - `venv/bin/ruff check app/services/follow_up_task_reconciliation_golden_suite.py tests/unit/test_follow_up_task_reconciliation_golden_suite.py --select F,E9,I`
  - `venv/bin/python -m pytest --no-cov tests/unit/test_follow_up_task_reconciliation_golden_suite.py tests/unit/test_follow_up_task_reconciliation_evaluation_service.py -q`
  - 结果：`9 passed`。

依赖：`SCM-P2-00`。

### SCM-P2-02：实现 TaskReconciliationService 只读候选任务检索

目标：

- 在新活动保存和 AI 整理完成后，只读检索可能相关的旧开放任务，为后续 semantic match 做准备。

范围：

- 新增 `TaskReconciliationService`。
- 输入为客户活动 public/source 上下文、team_id、activity owner、customer_id、触发类型。
- 第一层使用 MySQL 结构化条件召回：
  - 同 team_id。
  - 同 customer_id。
  - 默认同 owner_id。
  - status 为 `OPEN`。
  - due_at 位于过去 90 天到未来 30 天。
- 输出候选任务 public_id、owner_id、title、due_at、source/evidence 摘要和候选原因。
- 不调用 LLM，不写任务状态，不写任务事件。
- 可以写只读 reconciliation trace/log，便于后续分析召回质量；不得改变 `crm_follow_up_tasks.status`。

验收：

- 同客户同 owner 的开放任务可被召回。
- 已完成、已取消、其它客户任务不会被召回。
- 跨 owner 默认不进入自动候选，只能在显式开启 cross-owner candidate mode 时作为需确认候选返回。
- 候选输出只含 public_id，不暴露内部数据库主键。
- 单元测试证明该服务不会修改任务状态。

实现记录：

- `CRM-Server/app/services/task_reconciliation_service.py` 已新增只读 `TaskReconciliationService`。
- 支持 `list_candidates_for_activity`：按 `team_id + activity_id` 读取客户活动，并使用活动 `owner_id` 作为 reconciliation owner，不使用客户 owner。
- 支持 `list_candidates`：按同 team、同 customer、OPEN 状态、默认同 owner、过去 90 天到未来 30 天的 due_at 窗口召回任务。
- `include_cross_owner=False` 时只返回同 owner 候选；`include_cross_owner=True` 时会返回跨 owner 候选，但标记 `auto_transition_eligible=false` 和 `confirmation_required_reason=CROSS_OWNER`。
- 输出只包含任务 `public_id`、owner、标题、描述、due_at 展示字段、source/evidence 摘要、候选原因和安全策略，不暴露 `source_activity_id` 或内部 task id。
- 当前服务不接入投影流程、不调用 LLM、不写任务事件、不改任务状态，只作为 Phase 2 semantic match 的候选来源。
- `CRM-Server/tests/unit/test_task_reconciliation_service.py` 已覆盖默认同 owner 过滤、状态/客户/窗口过滤、跨 owner 需确认候选、无状态变更和活动不存在错误。
- 已验证：
  - `venv/bin/python -m pytest --no-cov tests/unit/test_task_reconciliation_service.py`
  - 结果：`4 passed`，仅有项目既有 Pydantic/SQLAlchemy deprecation warnings。

依赖：`SCM-P2-01` 可并行启动，但进入 LLM match 前必须合并真实样本。

### SCM-P2-03：实现 LLM 语义匹配 structured output

目标：

- 基于候选任务、新活动内容、结构化字段和语义证据，输出可审计的 reconciliation decision。

范围：

- 使用 LangChain structured output，输出 `SCM-P2-00` 固定的结构。
- 支持 decision：
  - `COMPLETE`
  - `DELAY`
  - `CANCEL`
  - `KEEP_OPEN`
  - `UNRELATED`
  - `ASK_CONFIRMATION`
- 输出必须包含置信度、证据词、引用来源和禁止自动处理原因。
- LLM 只能返回迁移建议，不直接写任务状态。
- 运行结果必须通过 reconciliation evaluation service 校验。

验收：

- golden set 全量通过。
- LLM 输出 schema 校验失败时不做状态变更。
- 缺少证据、低置信、跨 owner、高风险样本进入 `ASK_CONFIRMATION` 或 `KEEP_OPEN`。

实现记录：

- 新增 `CRM-Server/app/services/task_reconciliation_semantic_matcher.py`。
- `TaskReconciliationSemanticOutput` 使用 LangChain structured output schema，强制 `task_public_id` / `candidate_public_ids` 只能使用 `fut_` public_id，`DELAY` 必须包含 `proposed_due_at`，自动流转建议必须引用候选任务。
- `TaskReconciliationSemanticMatcher.match_activity` 负责按 `activity_id` 读取活动和 `TaskReconciliationService` 候选；`match_candidates` 作为底层公共 seam，便于后续接向量召回、LangGraph 节点和评测 fixture。
- 传给 LLM 的 prompt 不暴露活动 `owner_id` 或候选任务 `owner_id`；owner 判断只在内部候选服务和 evaluation service 使用。LLM 只看到 `owner_relation`、`auto_transition_eligible` 和 `confirmation_required_reason` 等语义标记。
- LLM 输出先归一化为 `FollowUpTaskReconciliationDecision`，再通过 `FollowUpTaskReconciliationEvaluationService` 做确定性安全校验。
- 同 owner、高置信、证据充分且没有状态写入请求时，可以返回 `COMPLETE` / `DELAY` / `CANCEL` 建议，但 `state_mutation_requested` 永远被压为 `False`。
- 自动流转类建议要求 `evidence_terms` 能在当前活动内容或候选任务标题、描述、原始时间文本中命中；缺少证据或证据无法落地时降级确认。
- 跨 owner、低置信、缺少证据、证据无法落地、未知候选、LLM 请求状态写入、LLM 不可用、schema 失败或安全合同失败，统一降级为 `ASK_CONFIRMATION` 或 `KEEP_OPEN`，并写入 `forbid_auto_reasons`。
- 当前实现不写 `crm_follow_up_tasks`、不写任务事件、不接入客户活动投影流程；只是 Phase 2 后续状态迁移计划的只读建议输入。
- 新增 `CRM-Server/tests/unit/test_task_reconciliation_semantic_matcher.py`，覆盖同 owner 完成建议、LLM prompt 隐藏内部 owner id、LLM 状态写入请求降级、跨 owner 自动完成降级、缺失或无法落地证据降级、未知候选降级、低置信延期降级、structured output 失败安全回退、内部 ID / 缺少延期时间 schema 拒绝。

依赖：`SCM-P2-02`。

### SCM-P2-04：同 owner 高置信自动完成、延期、取消

目标：

- 只对同客户、同 owner、高置信、证据充分的任务执行自动状态迁移。

范围：

- 将 `SCM-P2-03` 的 decision 转换为状态迁移计划。
- 自动完成、延期、取消必须写事件审计、match confidence、证据和来源活动。
- 保留 rollback/reopen 能力。
- 默认 feature flag 关闭，先允许灰度。

验收：

- 仅同 owner 高置信样本自动变更。
- 状态迁移后 Agent 查询“未完成任务”和“本周完成了什么”结果正确。
- 误关时可通过事件恢复。

依赖：`SCM-P2-03`。

已完成：

- 新增 `CRM-Server/app/services/follow_up_task_transition_plan_service.py`，将 `SCM-P2-03` 的只读语义匹配结果转换为状态迁移计划。
- 当前实现只生成 `FollowUpTaskTransitionPlan` / `FollowUpTaskTransitionAction`，不写 `crm_follow_up_tasks`，不写任务事件，不触发 rollback/reopen，也不接入自动执行。
- 计划层输出只使用任务、活动 `public_id`，不向下游计划 payload 暴露内部 owner id 或数据库主键 id。
- `COMPLETE` / `DELAY` / `CANCEL` 只有在同 owner、高置信、候选任务存在、无需确认、无 `forbid_auto_reasons`、有证据、未请求状态写入、且 evaluation guardrail 通过时才标记 `executable=true`。
- `DELAY` 额外要求 `proposed_due_at` 是可解析 ISO datetime；缺失或无效时转为 `ASK_CONFIRMATION`，不允许自动延期。
- 跨 owner、低置信、未知候选、已有禁止自动原因、需要确认、LLM 请求状态写入或 guardrail 失败时统一输出不可执行的确认计划。
- `KEEP_OPEN` / `UNRELATED` 统一输出 `NOOP`，不产生状态迁移。
- 新增 `CRM-Server/tests/unit/test_follow_up_task_transition_plan_service.py`，覆盖同 owner 高置信完成可执行、无效延期时间阻断、跨 owner 和低置信阻断、未知候选阻断、KEEP_OPEN/UNRELATED no-op、计划输出不暴露内部 owner id、可从 semantic match result 构建计划。
- 新增 `CRM-Server/app/services/follow_up_task_transition_execution_service.py`，作为受控状态迁移 executor。该服务默认 `enabled=false`，不接入投影流程、Agent 自动调用或 IM Bot 自动调用。
- executor 只消费计划层 `executable=true` 且无需确认的 `COMPLETE` / `DELAY` / `CANCEL` action；执行前按 task `public_id` 回表校验 team、OPEN 状态和 owner。
- `COMPLETE` / `CANCEL` 使用现有 `follow_up_task_crud.complete/cancel(commit=False)`，`DELAY` 使用 `follow_up_task_crud.update(commit=False)` 更新 `due_at` 并保持 `OPEN`。
- executor 通过 `follow_up_task_event_crud.record_status_change(commit=False)` 写事件，payload 包含 plan_source、action、task_public_id、confidence、evidence_terms、source_activity_public_id、proposed_due_at 和 decision，不暴露内部 owner id。
- 新增 `CRM-Server/tests/unit/test_follow_up_task_transition_execution_service.py`，覆盖默认关闭不落库、启用后完成任务并写事件、owner mismatch 阻断、延期任务不关闭。
- 新增 `CRM-Server/app/services/follow_up_task_transition_policy_service.py`，作为自动状态迁移的团队灰度策略服务；该服务只负责判断是否允许自动执行，不负责生成计划或写任务状态。
- 灰度配置复用 `crm_system_configs`，新增 `ConfigType.AUTOMATION` 用于自动化策略类配置；当前配置键：
  - `follow_up_task_auto_transition_enabled`：团队总开关，缺失或非 bool 时失败关闭。
  - `follow_up_task_auto_transition_owner_allowlist`：owner allowlist，可选；缺失表示团队开启后不按 owner 限制，存在时必须是字符串数组，空数组表示不允许任何 owner 自动执行。
  - `follow_up_task_auto_transition_action_allowlist`：action allowlist，可选；缺失时默认允许 `COMPLETE` / `DELAY` / `CANCEL`，存在时必须是上述 action 的字符串数组。
- 策略服务失败关闭：配置缺失、JSON 解析失败、类型错误、未知 action、owner 不在 allowlist、action 不在 allowlist，均返回 `allowed=false`，调用方不得把 executor 打开。
- 策略服务不暴露给 LLM，不进入 Agent prompt；后续投影链路、Agent Web 和 IM Bot 集成都必须先拿策略结果，再决定是否以 `enabled=true` 调用 executor。
- 新增 `CRM-Server/tests/unit/test_follow_up_task_transition_policy_service.py`，覆盖配置缺失默认关闭、团队开启、团队关闭、owner allowlist、action allowlist、无效配置失败关闭。

剩余：

- executor 尚未接入任何自动触发链路；后续从投影或 Agent reconciliation graph 调用时，必须先通过 `FollowUpTaskTransitionPolicyService` 判断团队、owner 和 action 是否允许自动执行。
- 自动化策略目前只有底层服务，尚未提供后台配置 API / 管理 UI；灰度阶段可以由内部配置写入 `crm_system_configs`。
- executor 级 rollback/reopen 已有底层能力；产品入口、管理权限和 Agent 工具入口仍未接入。
- Agent 查询“未完成任务”和“本周完成了什么”的状态正确性，需要在 executor 和事件审计落地后做端到端验证。

### SCM-P2-05：低置信确认流，统一 Agent Web 和 IM Bot

目标：

- 当系统不能可靠判断旧任务是否已完成、延期或取消时，通过统一业务服务生成确认问题。

范围：

- 新增确认意图和确认状态模型。
- Agent Web、IM Bot 只负责呈现和收集用户回复，不复制业务判断逻辑。
- 用户回复“先放着”“不用管了”“已确认”“下周五再说”等进入同一解析和状态迁移服务。
- 做频率控制，避免重复追问。

验收：

- Web Agent 和 IM Bot 对同一确认 case 的业务结果一致。
- 用户自然语言回复能正确完成、延期、取消或保留任务。
- 追问不会在多个渠道重复触达同一人同一任务。

依赖：`SCM-P2-04` 可并行设计，状态迁移服务需共用。

已完成：

- 新增 `CRM-Server/app/models/sales_commitment.py` 中的 `FollowUpTaskConfirmationCase`、`FollowUpTaskConfirmationStatus` 和 `FollowUpTaskConfirmationResolutionAction`。
- 新增迁移 `CRM-Server/migrations/versions/069_follow_up_task_confirmation_cases.py`，创建 `crm_follow_up_task_confirmation_cases`，用于保存待用户确认的问题，不把确认状态塞进任务表。
- 确认 Case 使用 `fuc_` public_id；`CRM-Server/app/utils/public_id.py` 已补 `FOLLOW_UP_TASK_CONFIRMATION_CASE_PUBLIC_ID_PATTERN` 和 `is_follow_up_task_confirmation_case_public_id`。
- `CRM-Server/app/schemas/sales_commitment.py` 已补确认 Case internal create/update 和 response；response 继续遵守 public-id-only 边界，不暴露内部 `task_id`、`customer_id`、`source_activity_id`、`source_plan_json` 或 `application_result_json`。
- `CRM-Server/app/crud/sales_commitment.py` 已补 `FollowUpTaskConfirmationCaseCRUD`，支持按 public_id/team 查询、按 `confirmation_hash` 幂等查 pending case、查询 owner 待确认 case、标记已提醒和解析后关闭 case。
- 确认 Case 保存 `application_status`、`application_skip_reason`、`application_result_json`、`applied_by_id` 和 `applied_at`，用于记录确认回复是否已经应用，避免同一确认 Case 被重复请求时重复写任务事件。
- 新增 `CRM-Server/app/services/follow_up_task_confirmation_service.py`，只负责确认 Case 创建、提醒计数和用户回复解释，不直接修改 `crm_follow_up_tasks.status`。
- `create_case_from_plan_action` 只接受 `requires_confirmation=true` 的 transition action；确认哈希基于 team、task public_id、decision、action、source activity public_id 和 proposed due 生成，避免同一低置信判断重复追问。
- 确认问题从 blocked transition plan 生成，保留 source plan 快照供审计；Case 的 owner 来自任务 owner，creator 来自触发 actor。
- 确认 Case 新增 `expires_at` 和 `expired_at`；新建 Case 默认 14 天回复窗口。待确认列表默认过滤已过期 pending Case，避免 Web/IM/Agent 长期展示陈旧追问。
- 确认 Case 新增 `unresolved_reply_count`、`last_unresolved_reply_text`、`last_unresolved_reply_by_id` 和 `last_unresolved_reply_at`，用于保存无法解析的用户回复 trace。`UNKNOWN` 回复仍保持 Case 为 `PENDING`，不写任务事件、不关闭 Case。
- 新增 `CRM-Server/app/services/follow_up_task_confirmation_cleanup_service.py`，用于批量扫描 `expires_at <= before` 且仍为 `PENDING` 的 Case，并标记为 `EXPIRED`；已解决、未到期或非 pending Case 不会被清理服务改写。
- 用户通过旧 `case_public_id` 回复已过期 Case 时，确认服务只把 Case 标记为 `EXPIRED`，不会进入 `RESOLVED`，也不会触发 executor 修改任务状态。
- `interpret_reply` 已覆盖常见销售回复：
  - “已确认/完成/通过了/已处理” -> `COMPLETE`。
  - “不管了/不用管/取消” -> `CANCEL`。
  - “下周五再说/明天/后天/几天后”等带时间回复 -> `DELAY`，并解析 `resolved_due_at`。
  - “先放着/还没有进展/继续跟进” -> `KEEP_OPEN`。
  - 无法判断时 -> `UNKNOWN`，不关闭确认 Case。
- `resolve_case_from_reply` 只把 pending confirmation case 标记为 `RESOLVED` 并保存用户原始回复、解析动作、解析延期时间和处理人；它不调用 executor，不写任务事件，不改变任务状态。
- 新增 `CRM-Server/app/services/follow_up_task_confirmation_application_service.py`，负责把已解析的确认 Case 转换为用户确认后的 transition plan，并统一调用 `FollowUpTaskTransitionExecutionService` 应用任务变更。
- 确认应用服务在关闭 Case 前预校验 `actor_id == case.owner_id`，非 owner 回复不能关闭 Case，也不能修改任务；executor 仍会二次校验 team、task public_id、OPEN 状态和 owner。
- 用户明确确认回复属于“人工确认后的操作”，不依赖自动流转灰度策略开关；自动流转策略仍只用于无需用户确认的自动完成、延期和取消。
- `COMPLETE` / `DELAY` / `CANCEL` 会通过 executor 写正常任务事件；`KEEP_OPEN` 只关闭确认 Case 并记录应用结果，不改变任务状态；`UNKNOWN` 保持 pending，不关闭 Case，不写任务事件，只记录未解析回复 trace。
- 确认应用结果写回 Case 后具备幂等性；同一 `case_public_id` 重放时直接返回已记录应用结果，不会再次调用 executor，尤其避免 `DELAY` 重放产生重复 `UPDATED` 事件。
- 新增 `CRM-Server/app/services/follow_up_task_confirmation_channel_service.py`，作为 Web Agent、IM Agent 和后续页面按钮复用的业务通道服务。通道层只传 `case_public_id` 和用户原始回复，不复制确认解析、owner 校验或任务状态迁移逻辑。
- 共享 Channel Service 在 `UNKNOWN` 回复时返回 `assistant_follow_up_prompt`，供 Web Agent / IM Agent 使用同一条追问建议，不在渠道层复制判断逻辑。
- 新增 `FollowUpTaskConfirmationPromptDelivery` 模型和 `crm_follow_up_task_confirmation_prompt_deliveries` 表，记录确认问题每次被投递到 Web Agent / IM Bot 的事实。delivery log 使用 `fcp_` public_id，保存 `case_id`、`owner_id`、`channel`、`provider`、`agent_session_id`、`interaction_id`、`prompt_key`、`status`、`payload_json` 和 `prompted_at`。
- 触达频控以 delivery log 为事实源，不依赖内存状态：同一 owner 默认 4 小时内不重复触达确认问题，同一 Case 默认 4 小时内不重复触达，且同一 Case 最多主动提示 3 次。该策略同时覆盖 Web Agent 和 IM Bot，避免同一人被多个渠道重复追问。
- `CRM-Server/app/crud/sales_commitment.py` 已补 `FollowUpTaskConfirmationPromptDeliveryCRUD`，支持查询 owner/case 最近投递记录和创建 sent delivery 记录。
- Channel Service 新增 `prompt_next_pending_case`，负责挑选当前 owner 的待确认 Case、执行跨渠道冷却和次数上限、写 delivery log、更新 Case 的 `prompt_count` / `last_prompted_at`，并返回统一的 `agent.interaction.v1` 选择交互。
- Channel Service 新增 `preview_reply_decision` 和 `resolve_bound_reply`：前者用于判断自然语言回复是否足以绑定到最近确认交互，后者统一调用确认应用服务并返回结构化 resolved 事件。
- `CRM-Server/app/services/agent/tools/service.py` 和 `CRM-Server/app/services/agent/tool_registry.py` 已补 `list_follow_up_task_confirmation_cases`、`resolve_follow_up_task_confirmation_case` 两个 Agent tools；查询只返回当前用户 owner 的 pending Case，回复应用只接受确认 Case 对外 ID。
- `resolve_follow_up_task_confirmation_case` 标记为写工具但采用“用户回复即业务确认”的 guardrail 模式，避免用户回答确认问题后再被普通 HITL 机制二次确认；真正变更仍必须通过 `FollowUpTaskConfirmationApplicationService` 和 executor 的二次校验。
- `CRM-Server/app/services/agent/application.py` 已接入确认提示和回复绑定：用户消息持久化后优先解析 turn metadata 中的 `case_public_id`，否则读取最近 assistant trace event 中未完成的确认 interaction；当自然语言回复能被解析为明确确认动作时，直接通过 `resolve_bound_reply` 应用并提前返回确认结果。普通 Agent 运行完成、准备输出最终 assistant 消息前，会调用 `prompt_next_pending_case` 尝试追加一个低打扰确认 interaction。
- `CRM-Server/app/services/im_agent_gateway.py` 已接入同一确认流：IM 引用某条确认 bot 消息时，会回到原 Agent session 并带上确认 Case metadata；没有引用但当前会话最近一次 interaction 是待确认问题时，也能把自然语言回复绑定到该 Case。IM 网关只做会话定位和 metadata 传递，不复制确认业务判断。
- 现有 IM Bot 网关继续只负责把 IM 文本、引用消息、选项回复和表情归一化进入 Agent 会话；当用户回复确认 Case 时，Web Agent 和 IM Agent 走同一个后端服务和同一套业务结果。
- `CRM-Server/app/services/agent/__init__.py` 已改为 lazy `__getattr__` 导出 `crm_agent_graph_service`，避免确认 Channel Service 复用 Agent interaction contract 时引入循环 import。
- `CRM-Server/app/models/__init__.py` 和 `CRM-Server/app/schemas/__init__.py` 已导出确认 Case 相关模型和 schema。
- 新增 `CRM-Server/tests/unit/test_follow_up_task_confirmation_service.py`，覆盖确认 Case 幂等创建、public_id 校验、response 隐藏内部字段、提醒计数、常见回复解析、关闭确认 Case 但不改任务状态。
- `CRM-Server/tests/unit/test_follow_up_task_confirmation_service.py` 已补确认 Case 默认过期窗口、待确认列表过滤过期 Case、过期清理服务和过期 Case 回复不改任务状态。
- 新增 `CRM-Server/tests/unit/test_follow_up_task_confirmation_application_service.py`，覆盖确认回复完成任务、延期任务、保留任务、未知回复 trace、非 owner 回复、任务已关闭 guardrail 和延期重放幂等。
- `CRM-Server/tests/unit/test_agent_tools.py` 已覆盖 Agent 查询当前 owner 确认 Case、自然语言回复完成任务、未知回复保留 pending 并返回追问提示、非 owner 回复不关闭 Case 且不修改任务。
- 新增 `CRM-Server/tests/unit/test_follow_up_task_confirmation_channel_service.py`，覆盖主动提示生成 `agent.interaction.v1`、写 delivery log、更新 prompt 计数、owner 级跨渠道冷却、Case 最大提示次数和绑定回复后完成任务。
- `CRM-Server/tests/unit/test_im_agent_gateway.py` 已补 IM 侧确认绑定：覆盖最近确认 interaction 的自然语言回复 metadata 注入，以及引用确认 bot 消息时回到原 Agent session 并绑定 Case。
- `CRM-Server/tests/unit/test_agent_api.py` 已补真实 Web SSE 和 IM Gateway smoke：Web `/v1/agent/chat/stream` 能追加 `follow_up_task_confirmation_case_prompt`，IM 网关通过同一 `AgentApplicationService` 和 Channel Service 追加确认 interaction，且通道参数分别记录为 `web` / `im`。
- `CRM-Server/tests/unit/test_agent_api.py` 已补 Web SSE 绑定回复 smoke：前端携带 `interaction_metadata.case_public_id` 时，用户自然语言回复直接进入 `resolve_bound_reply`，不进入普通 root runtime，并持久化为 `follow_up_task_confirmation_reply` assistant message。
- `CRM-Server/tests/unit/test_im_agent_gateway.py` 已补飞书 provider 渲染 smoke：跟进确认 choice 渲染为编号选项，保留 `agent_session_id` 隐藏绑定；引用或普通文本回复继续由 IM Gateway 回到最近确认 interaction 中的同一 `case_public_id`。
- 已验证：
  - `venv/bin/ruff check app/models/sales_commitment.py app/schemas/sales_commitment.py app/crud/sales_commitment.py app/services/follow_up_task_confirmation_application_service.py tests/unit/test_follow_up_task_confirmation_application_service.py migrations/versions/069_follow_up_task_confirmation_cases.py`
  - `venv/bin/python -m pytest --no-cov tests/unit/test_follow_up_task_confirmation_service.py tests/unit/test_follow_up_task_confirmation_application_service.py`
  - `venv/bin/ruff check app/services/follow_up_task_confirmation_channel_service.py`
  - `venv/bin/ruff check --select F,E9 app/services/agent/tools/service.py app/services/agent/tool_registry.py app/services/agent/guardrails.py tests/unit/test_agent_tools.py`
  - `venv/bin/python -m pytest --no-cov tests/unit/test_agent_tools.py tests/unit/test_follow_up_task_confirmation_application_service.py -q`
  - `venv/bin/ruff check app/services/follow_up_task_confirmation_service.py app/services/follow_up_task_confirmation_cleanup_service.py app/services/follow_up_task_confirmation_channel_service.py app/crud/sales_commitment.py app/models/sales_commitment.py app/schemas/sales_commitment.py tests/unit/test_follow_up_task_confirmation_service.py --select F,E9`
  - `venv/bin/python -m pytest --no-cov tests/unit/test_follow_up_task_confirmation_service.py tests/unit/test_follow_up_task_confirmation_application_service.py tests/unit/test_agent_tools.py -q`
  - `venv/bin/ruff check app/services/follow_up_task_confirmation_service.py app/services/follow_up_task_confirmation_cleanup_service.py app/services/follow_up_task_confirmation_channel_service.py app/crud/sales_commitment.py app/models/sales_commitment.py app/schemas/sales_commitment.py tests/unit/test_follow_up_task_confirmation_service.py tests/unit/test_follow_up_task_confirmation_application_service.py tests/unit/test_agent_tools.py --select F,E9`
  - `venv/bin/python -m pytest --no-cov tests/unit/test_follow_up_task_confirmation_service.py tests/unit/test_follow_up_task_confirmation_application_service.py tests/unit/test_follow_up_task_confirmation_channel_service.py tests/unit/test_im_agent_gateway.py tests/unit/test_agent_tools.py -q`
  - `venv/bin/python -m py_compile app/models/sales_commitment.py app/crud/sales_commitment.py app/services/follow_up_task_confirmation_channel_service.py app/services/agent/__init__.py app/services/agent/application.py app/services/im_agent_gateway.py`
  - `venv/bin/ruff check app/services/agent/__init__.py app/services/follow_up_task_confirmation_channel_service.py tests/unit/test_follow_up_task_confirmation_channel_service.py migrations/versions/069_follow_up_task_confirmation_cases.py`
  - `venv/bin/ruff check app/services/im_agent_gateway.py --select I`
  - `venv/bin/ruff check tests/unit/test_agent_api.py tests/unit/test_im_agent_gateway.py --select F,E9,I`
  - `venv/bin/python -m pytest --no-cov tests/unit/test_agent_api.py tests/unit/test_im_agent_gateway.py tests/unit/test_agent_tools.py -q -k 'follow_up_confirmation or follow_up_task_confirmation or im_gateway_binds_latest_follow_up_confirmation_interaction or im_gateway_binds_referenced_follow_up_confirmation_session or renders_follow_up_confirmation'`
  - 结果：确认服务、确认应用、Channel Service、IM 绑定和 Agent 工具相关测试 `83 passed`，仅有项目既有 Pydantic/SQLAlchemy warnings。针对本次新增文件和 import 顺序的 ruff 校验已通过；完整扫描 `agent/application.py` 和 `im_agent_gateway.py` 仍会暴露既有类型标注/现代化规则问题，本轮未做无关大规模清理。

剩余：

- 主动提示当前只在用户已有 Agent 会话上下文中低打扰追加，不做每日摘要或离线主动推送；后者留到 Phase 5 的触达治理和用户偏好模型。
- 旧任务完成/取消、来源活动删除或下一步清空后的 pending confirmation case 主动取消已在 `SCM-P2-08` 补齐；当前 executor/application guardrail 仍保留为最后防线，阻止任务非 OPEN 的 Case 继续改任务。

### SCM-P2-06：跨 owner 候选处理策略

目标：

- 支持协作场景下识别跨 owner 相关任务，但不默认自动操作他人任务。

范围：

- 明确跨 owner 候选进入条件。
- 默认跨 owner 只返回需确认候选或提示任务 owner。
- 预留管理者指派/代处理权限，但当前不启用。

验收：

- 售前跟进销售客户时，不会误关闭销售自己的任务。
- 销售跟进售前承诺时，不会误取消售前任务。
- 明确代处理语义也必须进入确认或权限受控流程。

依赖：`SCM-P2-02`。

已完成：

- 候选检索层保持只读：`TaskReconciliationService.list_candidates_for_activity` 默认只返回同客户、同活动 owner 的开放任务；只有调用方显式传 `include_cross_owner=True` 时才纳入跨 owner 候选。
- 跨 owner 候选统一标记为 `auto_transition_eligible=False`、`confirmation_required_reason=CROSS_OWNER`，并在 `candidate_reasons` 中写入 `cross_owner_confirmation_only`；同 owner 候选仍按 due window、时间和 public_id 顺序稳定排序。
- Reconciliation run trace 已记录 `include_cross_owner`、过滤条件、usage policy 和 `candidate_public_ids_json`；候选快照只保存任务 `public_id`，不保存任务数据库主键。
- LLM semantic matcher 的 prompt 不暴露 `owner_id`，只暴露 `owner_relation=same_owner|cross_owner_confirmation_only`、`auto_transition_eligible` 和确认原因；模型即便返回跨 owner 的 `COMPLETE`、`DELAY` 或 `CANCEL`，本地 guardrail 也会降级为 `ASK_CONFIRMATION`。
- Transition plan 再次执行安全校验：跨 owner、低置信、缺证据、未知候选或非法 public_id 都不能生成 executable action；跨 owner mutating decision 统一转为 `ASK_CONFIRMATION`。
- Confirmation application 以确认 Case owner 为业务权限边界；非 owner 即使拿到 case public_id 并回复“已完成”，也只返回 `CONFIRMATION_ACTOR_NOT_OWNER`，不会关闭 Case 或修改任务。
- Executor 使用 `expected_owner_id or actor_id` 做最终 owner mismatch guardrail；即使上游 plan 异常把跨 owner action 标成 executable，执行层仍会跳过并返回 `TASK_OWNER_MISMATCH`。
- Agent tool 查询 pending confirmation case 只返回当前用户 owner 的 Case；Web Agent 和 IM Bot 走同一 Channel Service，不做通道差异化业务判断。
- 已验证：
  - `venv/bin/ruff check tests/unit/test_task_reconciliation_service.py tests/unit/test_task_reconciliation_semantic_matcher.py tests/unit/test_follow_up_task_transition_plan_service.py tests/unit/test_follow_up_task_transition_execution_service.py tests/unit/test_follow_up_task_confirmation_application_service.py tests/unit/test_follow_up_task_reconciliation_evaluation_service.py --select F,E9,I`
  - `venv/bin/python -m pytest --no-cov tests/unit/test_task_reconciliation_service.py tests/unit/test_task_reconciliation_semantic_matcher.py tests/unit/test_follow_up_task_transition_plan_service.py tests/unit/test_follow_up_task_transition_execution_service.py tests/unit/test_follow_up_task_confirmation_application_service.py tests/unit/test_follow_up_task_reconciliation_evaluation_service.py -q`
  - 结果：`47 passed`，仅有项目既有 Pydantic/SQLAlchemy warnings。

剩余：

- 管理者指派、代处理、转派和跨 owner 明确授权暂不启用；后续需要独立权限模型、操作理由和审计事件。

### SCM-P2-07：Phase 2 评测、观测和回滚策略

目标：

- 在打开任何自动状态迁移前，具备可衡量、可追溯、可回滚的安全机制。

范围：

- 评测指标：
  - 误关闭率。
  - 误延期率。
  - 该追问未追问率。
  - 过度追问率。
- 观测：
  - reconciliation run trace。
  - LLM schema error。
  - feature flag 命中情况。
  - 自动迁移和人工确认比例。
- 回滚：
  - 自动完成/取消任务可恢复。
  - 自动延期保留 previous due_at。

验收：

- Phase 2 golden set 全量通过。
- 自动迁移开关默认关闭，可按团队或用户灰度。
- 每一次状态自动变更都能解释来源、证据和恢复路径。

依赖：`SCM-P2-04`、`SCM-P2-05`。

已完成：

- `crm_follow_up_task_events` 补 `public_id`，使用 `fte_` 前缀；外部接口、Agent 或后续回滚入口引用事件时不需要暴露数据库主键。
- `CRM-Server/migrations/versions/068_sales_commitment_task_tables.py` 的新建事件表定义已包含 `public_id`；新增 `CRM-Server/migrations/versions/070_follow_up_task_event_public_id.py` 用于已执行过 068/069 的环境补列、回填历史事件 public_id 并建立索引/唯一约束。
- `FollowUpTaskEventResponse` 已暴露事件 `id/public_id`，同时继续隐藏内部 `task_id` 和 `source_activity_id`。
- 自动状态迁移 executor 写事件时，payload 中新增 `rollback` 快照：
  - `COMPLETE` / `CANCEL` 记录 `type=REOPEN`，保留 previous status 和 previous due_at 字段。
  - `DELAY` 记录 `type=RESTORE_DUE_AT`，保留延期前的 `due_at`、`due_at_text`、`due_at_granularity` 和 `due_at_timezone`。
- `FollowUpTaskTransitionExecutionService.rollback_event` 支持按 `event_public_id` 幂等撤销自动迁移事件；事件 payload 使用 `execution_kind` 区分 `automatic` 和 `manual_confirmation`，用户明确确认后的操作不走自动回滚入口。
  - 自动完成/取消通过 `reopen` 恢复为 `OPEN`，清空 `completed_at` / `cancelled_at`。
  - 自动延期恢复延期前 due_at 相关字段。
  - 撤销动作会写新的审计事件，payload 记录 `rolled_back_event_public_id`，重复撤销返回 `EVENT_ALREADY_ROLLED_BACK`，不重复写事件。
- 回滚入口继续校验 team 和 task owner；非 owner 不能用事件 public_id 撤销他人的任务迁移。
- 新增 `CRM-Server/app/services/follow_up_task_transition_observability_service.py`，作为 Phase 2 状态迁移安全观测的统一只读汇总服务：
  - 只读 `crm_follow_up_task_events`、`crm_follow_up_task_confirmation_cases`、`crm_follow_up_task_confirmation_prompt_deliveries` 和 `crm_follow_up_task_transition_policy_decision_logs`，不调用 LLM，不修改任务状态。
  - 支持按 team、时间窗口和可选 owner 过滤，窗口采用 `[start_at, end_at)` 半开区间。
  - 从事件 payload 统一解析 `reason`、`execution_kind`、`action`、`decision`、`plan_source`、`confidence`、`rolled_back_action` 和 `rolled_back_event_public_id`。
  - 输出自动迁移数、人工确认迁移数、回滚数、自动/人工比例、按 action/decision/plan_source/event_type 分组、确认 Case 创建/解决/应用状态、提示投递 channel/provider/status 分布。
  - 输出策略决策总量、允许/阻断数量、允许率、按 reason/action/enabled/owner allowlist 分组和配置错误总量。
  - 返回内容只包含聚合数、业务 owner 和 `fte_` 事件 public_id 引用，不暴露 `task_id`、`case_id`、`source_activity_id` 等内部数据库主键。
- 新增 `crm_follow_up_task_transition_policy_decision_logs`：
  - 使用 `tpd_` public_id；数据库内部可关联 `task_id` 和 `source_activity_id`，但 API/Agent 侧只读聚合指标。
  - 记录自动状态迁移策略每次判断的 `allowed`、`reason`、`enabled`、`owner_allowlist_configured`、`allowed_actions_json`、`config_errors_json`、完整 `policy_result_json` 和 `context_json`。
  - `FollowUpTaskTransitionPolicyDecisionLogCRUD.record_result` 提供统一落库入口，后续自动化编排拿到 `FollowUpTaskTransitionPolicyResult` 后调用，避免各入口重复拼审计字段。
- 新增 `crm_follow_up_task_reconciliation_runs`：
  - 使用 `trr_` public_id；记录候选检索的 team、customer、活动 owner、actor、source activity、窗口、跨 owner 配置、候选 public_id 快照、过滤条件、使用策略、耗时和运行状态。
  - `TaskReconciliationService.list_candidates_for_activity` 在返回候选集时写入 run trace，并把 `run_public_id` 附在候选集上，供后续 LLM matcher 日志关联。
  - 无候选不是错误，按 `SKIPPED / NO_OPEN_CANDIDATES` 记录；候选检索仍不修改任务、承诺或客户活动状态。
- 新增 `crm_follow_up_task_llm_matcher_runs`：
  - 使用 `tlm_` public_id；记录 LLM semantic matcher 每次运行的来源、归一化 decision、候选任务 public_id、置信度、是否需要确认、禁止自动迁移原因、证据词、评测失败项、模型名、结构化输出策略和耗时。
  - 结构化输出失败单独记录 `schema_error_type` 和 `schema_error_message`，使 LLM schema error 从观测缺口变成可聚合事实源。
  - 日志只使用候选任务 public_id 作为语义关联，不要求 LLM 输出或引用数据库主键。
- 新增 `crm_follow_up_task_reconciliation_evaluation_runs`：
  - 使用 `ter_` public_id；作为 append-only 质量门禁运行记录，和业务任务状态完全分离，不修改客户、活动、承诺或任务。
  - 支持系统级评测 `team_id=NULL` 和团队级评测 `team_id=<team>`；观测汇总读取当前团队 run 与系统级 run，但只返回聚合指标和最新 run public_id。
  - 记录 suite 名称、fixture path/hash、运行状态、质量门禁是否通过、总样本/通过/失败样本数、误关闭、误延期、该追问未追问、过度追问的 count/rate、完整 metrics、失败样本摘要、全部样本结果、阈值快照、错误摘要和耗时。
  - `FollowUpTaskReconciliationEvaluationRunCRUD.record_summary` 持久化确定性 evaluation summary；`record_failed` 记录 fixture 解析或运行异常，避免 CI/本地评测失败只有控制台日志。
- `CRM-Server/scripts/run_follow_up_task_reconciliation_eval.py` 默认仍为无副作用本地评测脚本；显式传 `--persist` 时才写入 evaluation run，可选 `--team-id` 和 `--suite-name`，输出 payload 会包含 `evaluation_run_id`。
- 新增 `GET /v1/follow-up-task-transition-observability/summary` 只读运维接口，复用任务排查权限；默认查最近 7 天，支持 `start_at`、`end_at` 和 `owner_scope=team|mine`。
- 观测汇总结果新增 `reconciliation_runs`、`llm_matcher_runs` 和 `evaluation_runs` 聚合，覆盖 run 数、状态分布、skip reason、跨 owner 候选、候选总量、LLM source/decision/model/schema error 分布、确认比例、评测失败总量、置信度、耗时、质量门禁失败次数、最新评测 run public_id 和四类安全指标汇总。
- `metric_gaps` 当前为空；feature flag / policy decision、reconciliation run trace、LLM schema error 和 evaluation run 指标均已由独立事实表提供真实来源，避免用不完整数据伪造指标。
- 已验证：
  - `venv/bin/python -m pytest --no-cov tests/unit/test_follow_up_task_transition_execution_service.py tests/unit/test_sales_commitment_crud.py tests/unit/test_follow_up_task_confirmation_application_service.py tests/unit/test_follow_up_task_confirmation_channel_service.py tests/unit/test_follow_up_tasks_api.py -q`
  - `venv/bin/python -m pytest --no-cov tests/unit/test_follow_up_task_transition_observability_service.py tests/unit/test_follow_up_tasks_api.py -q`
  - `venv/bin/ruff check app/utils/public_id.py app/models/sales_commitment.py app/schemas/sales_commitment.py app/crud/sales_commitment.py app/services/follow_up_task_transition_execution_service.py tests/unit/test_follow_up_task_transition_execution_service.py migrations/versions/070_follow_up_task_event_public_id.py --select F,E9,I`
  - `venv/bin/ruff check app/api/follow_up_tasks.py app/main.py app/services/follow_up_task_transition_observability_service.py tests/unit/test_follow_up_task_transition_observability_service.py tests/unit/test_follow_up_tasks_api.py --select F,E9,I`
  - `venv/bin/ruff check app/models/sales_commitment.py app/crud/sales_commitment.py app/schemas/sales_commitment.py app/services/follow_up_task_transition_observability_service.py tests/unit/test_follow_up_task_transition_observability_service.py migrations/versions/071_follow_up_task_transition_policy_decision_logs.py --select F,E9,I`
  - `venv/bin/ruff check app/utils/public_id.py app/models/sales_commitment.py app/crud/sales_commitment.py app/schemas/sales_commitment.py app/services/task_reconciliation_service.py app/services/task_reconciliation_semantic_matcher.py app/services/follow_up_task_transition_observability_service.py app/models/__init__.py app/crud/__init__.py app/schemas/__init__.py tests/unit/test_task_reconciliation_service.py tests/unit/test_task_reconciliation_semantic_matcher.py tests/unit/test_follow_up_task_transition_observability_service.py tests/unit/test_follow_up_tasks_api.py migrations/versions/072_follow_up_task_reconciliation_and_llm_run_logs.py --select F,E9,I`
  - `venv/bin/python -m py_compile app/utils/public_id.py app/models/sales_commitment.py app/schemas/sales_commitment.py app/crud/sales_commitment.py app/services/follow_up_task_transition_execution_service.py`
  - `venv/bin/python -m py_compile app/api/follow_up_tasks.py app/services/follow_up_task_transition_observability_service.py`
	  - `venv/bin/python -m py_compile app/models/sales_commitment.py app/crud/sales_commitment.py app/schemas/sales_commitment.py app/services/follow_up_task_transition_observability_service.py`
	  - `venv/bin/python -m py_compile app/utils/public_id.py app/models/sales_commitment.py app/crud/sales_commitment.py app/schemas/sales_commitment.py app/services/task_reconciliation_service.py app/services/task_reconciliation_semantic_matcher.py app/services/follow_up_task_transition_observability_service.py app/models/__init__.py app/crud/__init__.py app/schemas/__init__.py migrations/versions/072_follow_up_task_reconciliation_and_llm_run_logs.py`
	  - `venv/bin/python -m pytest --no-cov tests/unit/test_task_reconciliation_service.py tests/unit/test_task_reconciliation_semantic_matcher.py tests/unit/test_follow_up_task_transition_observability_service.py tests/unit/test_follow_up_tasks_api.py -q`
	  - `venv/bin/python -m pytest --no-cov tests/unit/test_follow_up_task_transition_execution_service.py tests/unit/test_sales_commitment_crud.py tests/unit/test_follow_up_task_confirmation_application_service.py tests/unit/test_follow_up_task_confirmation_channel_service.py tests/unit/test_follow_up_tasks_api.py tests/unit/test_follow_up_task_transition_observability_service.py tests/unit/test_task_reconciliation_service.py tests/unit/test_task_reconciliation_semantic_matcher.py -q`
	  - `venv/bin/python -m pytest --no-cov tests/unit/test_customer_activity_task_projection_api.py tests/unit/test_follow_up_task_confirmation_service.py tests/unit/test_follow_up_task_confirmation_application_service.py tests/unit/test_follow_up_task_confirmation_channel_service.py tests/unit/test_follow_up_task_reconciliation_evaluation_service.py tests/unit/test_follow_up_task_reconciliation_golden_suite.py tests/unit/test_follow_up_task_transition_execution_service.py tests/unit/test_follow_up_task_transition_observability_service.py tests/unit/test_follow_up_task_transition_plan_service.py tests/unit/test_follow_up_task_transition_policy_service.py tests/unit/test_follow_up_tasks_api.py tests/unit/test_sales_commitment_crud.py tests/unit/test_task_reconciliation_semantic_matcher.py tests/unit/test_task_reconciliation_service.py tests/unit/test_agent_tools.py tests/unit/test_im_agent_gateway.py tests/unit/test_business_time.py tests/unit/test_sales_dashboard_api.py -q`
	  - `venv/bin/ruff check app/utils/public_id.py app/models/sales_commitment.py app/schemas/sales_commitment.py app/crud/sales_commitment.py app/services/follow_up_task_reconciliation_evaluation_service.py app/services/follow_up_task_transition_observability_service.py scripts/run_follow_up_task_reconciliation_eval.py tests/unit/test_follow_up_task_reconciliation_evaluation_service.py tests/unit/test_follow_up_task_reconciliation_golden_suite.py tests/unit/test_sales_commitment_crud.py tests/unit/test_follow_up_task_transition_observability_service.py tests/unit/test_follow_up_tasks_api.py migrations/versions/073_follow_up_task_reconciliation_evaluation_runs.py --select F,E9,I`
	  - `venv/bin/python -m alembic heads`：当前单 head 为 `073_follow_up_task_reconciliation_evaluation_runs`。
	  - `venv/bin/python -m pytest --no-cov tests/unit/test_follow_up_task_reconciliation_evaluation_service.py tests/unit/test_follow_up_task_reconciliation_golden_suite.py tests/unit/test_sales_commitment_crud.py tests/unit/test_follow_up_task_transition_observability_service.py tests/unit/test_follow_up_tasks_api.py -q`
	  - 最终相关回归：`177 passed`，仅有项目既有 Pydantic/SQLAlchemy warnings；新增/修改文件的语法级 lint 和 import 顺序通过。

剩余：

- 回滚目前是 executor 底层能力，尚未暴露管理 API、Agent tool 或前端入口；暴露前还需要补管理者权限和操作理由记录。

### SCM-P2-08：失效 pending confirmation case 清理

目标：

- 当任务或来源活动的业务事实已经失效时，主动关闭关联 pending confirmation case，避免 Agent 继续向用户追问已经不可操作的问题。

范围：

- 在确认 Case 表补充取消审计字段：
  - `cancelled_at`：Case 被业务事实取消的时间。
  - `cancelled_by_id`：触发取消的操作人或系统 actor。
  - `cancelled_reason`：取消原因。
- 扩展确认 Case CRUD：
  - 按任务查询 pending Case。
  - 按来源活动查询 pending Case，供后续页面删除/活动失效入口复用。
  - 幂等标记 `PENDING -> CANCELLED`。
- 扩展 `FollowUpTaskConfirmationCleanupService`：
  - 保留原有过期清理语义：`PENDING -> EXPIRED`。
  - 新增按任务/来源活动取消 pending Case 的业务事实清理能力。
  - 取消原因使用稳定枚举字符串，包括 `TASK_COMPLETED`、`TASK_CANCELLED`、`SOURCE_ACTIVITY_DELETED`、`SOURCE_NEXT_STEP_REMOVED`、`SOURCE_TASK_SUPERSEDED`。
- 接入任务状态变化入口：
  - `FollowUpTaskProjectionService` 取消同源任务时，同步取消该任务关联 pending Case。
  - `FollowUpTaskTransitionExecutionService` 自动完成/取消任务后，同步取消该任务关联 pending Case。
  - `DELAY` 不取消 pending Case，因为任务仍保持 `OPEN`，用户确认问题仍可能有效。

验收：

- 只取消目标任务或目标来源活动上的 `PENDING` Case。
- `RESOLVED`、`EXPIRED`、`CANCELLED` Case 不被重复改写。
- 任务完成/取消后，Agent pending confirmation 查询不会再返回旧 Case。
- 来源下一步被清空、来源活动删除或同源任务被投影替换后，旧 Case 不再继续提示。
- 取消行为有独立审计字段，不复用过期字段，也不伪装成用户确认回复。

依赖：`SCM-P2-05`、`SCM-P2-07`。

已完成：

- `crm_follow_up_task_confirmation_cases` 模型和 schema 已补 `cancelled_at`、`cancelled_by_id`、`cancelled_reason`。
- 新增迁移 `CRM-Server/migrations/versions/074_follow_up_task_confirmation_case_cancellation_fields.py`，当前 Alembic 单 head 为 `074_follow_up_task_confirmation_case_cancellation_fields`。
- `FollowUpTaskConfirmationCaseCRUD` 已支持：
  - `list_pending_by_task`。
  - `list_pending_by_source_activity`。
  - `mark_cancelled`。
- `FollowUpTaskConfirmationCleanupService` 已支持：
  - 过期清理结果继续返回 `expired_count` 和过期 Case public_id。
  - 业务事实取消结果返回 `cancelled_count` 和取消 Case public_id。
  - 按任务和按来源活动取消 pending Case。
- `FollowUpTaskProjectionService._cancel_tasks` 已在任务被投影取消后调用清理服务：
  - 来源活动删除映射为 `SOURCE_ACTIVITY_DELETED`。
  - 下一步清空或没有 due_at 映射为 `SOURCE_NEXT_STEP_REMOVED`。
  - owner 变化、重复同源任务等投影替换映射为 `SOURCE_TASK_SUPERSEDED`。
- `FollowUpTaskTransitionExecutionService` 已在 `COMPLETE` / `CANCEL` 执行成功并写任务事件后调用清理服务：
  - 完成任务映射为 `TASK_COMPLETED`。
  - 取消任务映射为 `TASK_CANCELLED`。
  - 延期任务不触发 Case 取消。
- 已验证：
  - `venv/bin/ruff check app/models/sales_commitment.py app/schemas/sales_commitment.py app/crud/sales_commitment.py app/services/follow_up_task_confirmation_cleanup_service.py app/services/follow_up_task_projection_service.py app/services/follow_up_task_transition_execution_service.py tests/unit/test_follow_up_task_confirmation_service.py tests/unit/test_follow_up_task_transition_execution_service.py tests/unit/test_sales_commitment_crud.py tests/unit/test_customer_activity_task_projection_api.py --select F,E9,I`
  - `venv/bin/python -m pytest --no-cov tests/unit/test_follow_up_task_confirmation_service.py tests/unit/test_follow_up_task_transition_execution_service.py tests/unit/test_sales_commitment_crud.py tests/unit/test_customer_activity_task_projection_api.py tests/unit/test_follow_up_task_confirmation_application_service.py -q`
  - `venv/bin/python -m alembic heads`
  - 结果：`61 passed`，仅有项目既有 Pydantic/SQLAlchemy warnings；Alembic 当前单 head 为 `074_follow_up_task_confirmation_case_cancellation_fields`。

剩余：

- 如果后续新增独立的手工任务完成/取消 API，应复用同一清理服务，不能绕过 `FollowUpTaskConfirmationCleanupService`。
- 管理者指派、代处理、转派场景仍未启用；未来开启后需要明确 `cancelled_by_id` 是操作者、被指派 owner 还是系统 actor，并补操作理由。

## 6. Phase 3 拆分：向量证据和语义查询

### SCM-P3-01：新增 commitment/task 向量 source type 和 metadata contract

目标：

- 将销售承诺和跟进任务纳入现有客户证据向量体系。
- 明确 MySQL 任务/承诺表仍是状态事实源，Qdrant 只保存语义证据和可回表 public_id。
- 确保 Agent、LLM 上下文和向量 metadata 不依赖任务/承诺内部数据库主键。

实现范围：

- `CustomerVectorDocumentSourceType` 新增：
  - `SALES_COMMITMENT = "sales_commitment"`
  - `FOLLOW_UP_TASK = "follow_up_task"`
- `crm_customer_vector_documents` 新增 `metadata_json`，保存业务元数据快照。
- `CustomerEvidenceBuilder` 新增：
  - `from_sales_commitment(commitment, customer=None)`
  - `from_follow_up_task(task, customer=None, commitment=None)`
- `CustomerVectorDocumentService` 新增：
  - `upsert_sales_commitment`
  - `upsert_follow_up_task`
  - `mark_sales_commitment_deleted`
  - `mark_follow_up_task_deleted`
- `CustomerEvidenceDocument` / Qdrant payload 新增 `metadata_json` 透传。

metadata contract：

| 字段 | 承诺 | 任务 | 说明 |
|------|------|------|------|
| source_type | `sales_commitment` | `follow_up_task` | 与旧客户活动 `follow_up` 分离 |
| source_object_id | `commitment.public_id` | `task.public_id` | public_id，不用数据库主键 |
| business_object_type | `sales_commitment` | `follow_up_task` | 回表实体类型 |
| business_object_id | `commitment.public_id` | `task.public_id` | 回表实体 public_id |
| metadata_json.customer_public_id | 是 | 是 | 客户对外 ID |
| metadata_json.owner_id | 是 | 是 | 继承跟进记录 owner |
| metadata_json.creator_id | 是 | 是 | 预留后续指派/代办场景 |
| metadata_json.status | 是 | 是 | 状态快照，仅用于解释，最终状态必须回 MySQL 校验 |
| metadata_json.due_at / due_at_text / due_at_granularity / due_at_timezone | 是 | 是 | 时间语义快照 |
| metadata_json.commitment_public_id | 是 | 关联时写入 | 任务命中后可解释关联承诺 |
| metadata_json.source_public_id | 来源有 public_id 时写 | 来源有 public_id 时写 | 当前客户活动没有 public_id 时不写 synthetic id |
| metadata_json.evidence | 是 | 是 | 过滤内部数据库 id，只保留 quote/reason/terms 等语义字段 |

完成情况：

- 已新增迁移 `075_customer_vector_document_metadata_json.py`。
- 已补承诺/任务向量 evidence 构建和 metadata upsert。
- 已补 Qdrant payload metadata 透传。
- 已补测试覆盖 public-id source object、metadata 契约、幂等更新、旧客户活动向量行为不变。

验收命令：

- `venv/bin/ruff check app/models/customer_vector_document.py app/services/customer_evidence_builder.py app/services/customer_qdrant_index_service.py app/services/customer_vector_document_service.py app/services/customer_vector_sync_service.py tests/unit/test_customer_vector_document_service.py migrations/versions/075_customer_vector_document_metadata_json.py --select F,E9,I`
- `venv/bin/python -m pytest tests/unit/test_customer_vector_document_service.py --no-cov`
- `venv/bin/python -m py_compile app/models/customer_vector_document.py app/services/customer_evidence_builder.py app/services/customer_qdrant_index_service.py app/services/customer_vector_document_service.py app/services/customer_vector_sync_service.py migrations/versions/075_customer_vector_document_metadata_json.py`
- `venv/bin/alembic heads`

### SCM-P3-02：实现任务/承诺变更后的 Qdrant 索引同步

目标：

- 任务/承诺生命周期发生变化后，稳定刷新向量证据 metadata，让语义检索能拿到可解释、可回表的 public_id。
- 保持 MySQL 任务/承诺表是状态事实源，向量库只保存语义证据和状态快照。
- 保持事务一致性：业务状态变更成功才产生待同步向量文档，业务事务回滚时向量 metadata 也随之回滚。

实现范围：

- `FollowUpTaskProjectionService` 在以下路径中调用 `CustomerVectorDocumentService`：
  - 创建或更新 `SalesCommitment` 后 upsert `sales_commitment` metadata。
  - 创建或更新 `FollowUpTask` 后 upsert `follow_up_task` metadata。
  - 来源下一步清空、来源活动删除、无 due_at 导致任务取消时，upsert 已取消任务和已取消承诺的 metadata。
  - 同源重复任务、owner 变化导致旧任务被取消时，upsert 旧任务的已取消 metadata。
- `FollowUpTaskTransitionExecutionService` 在以下真实执行路径中刷新任务 metadata：
  - `COMPLETE`：任务变为 `COMPLETED` 后刷新 `status`、`completed_at`。
  - `CANCEL`：任务变为 `CANCELLED` 后刷新 `status`、`cancelled_at`。
  - `DELAY`：任务保持 `OPEN`，刷新 `due_at`、`due_at_text` 和证据快照。
  - `ROLLBACK`：任务重开或恢复 due_at 后刷新当前任务 metadata。
- 所有调用均使用 `commit=False`，由投影服务或状态执行器的外层事务统一 commit。
- 本阶段不直接调用 Qdrant。服务只把 `crm_customer_vector_documents.sync_status` 置为 `PENDING`，实际写入 Qdrant 继续由 `CustomerVectorSyncService` 执行。

状态同步语义：

- 状态变更不删除向量证据，而是更新 metadata 中的状态快照，方便 Agent 在语义命中后解释“这是已完成/已取消任务的历史证据”。
- Agent 回答任务状态、未完成任务、逾期任务时仍必须通过 public_id 回查 MySQL；`metadata_json.status` 只用于检索解释和候选缩小。
- 只有业务实体被硬删除、来源证据不再存在或未来明确需要物理撤回时，才使用 `mark_sales_commitment_deleted` / `mark_follow_up_task_deleted` 进入 `DELETE_PENDING`。
- 若投影或状态执行发生异常，向量 metadata 写入和业务变更在同一事务中回滚，避免“任务没变但向量先变”的不一致。

完成情况：

- 已接入投影创建/更新/取消路径的承诺和任务 metadata upsert。
- 已接入任务状态执行器和回滚路径的任务 metadata upsert。
- 已补测试覆盖：
  - 投影创建任务和承诺时生成两类向量 metadata。
  - 活动更新导致任务 due_at 变化时刷新任务 metadata。
  - 活动下一步清空导致任务/承诺取消时刷新关闭状态 metadata。
  - 只有承诺、没有明确 due_at 时仍写入承诺 metadata。
  - 任务完成、延期和回滚后刷新任务 metadata。
  - 页面录入、Agent 录入、投影重试、确认回复应用和 Agent tools 共享同一同步链路。

验收命令：

- `venv/bin/python -m pytest tests/unit/test_sales_commitment_crud.py tests/unit/test_follow_up_task_transition_execution_service.py tests/unit/test_customer_activity_task_projection_api.py tests/unit/test_follow_up_tasks_api.py tests/unit/test_follow_up_task_confirmation_application_service.py --no-cov`
- `venv/bin/python -m pytest tests/unit/test_agent_tools.py --no-cov`
- `venv/bin/python -m pytest tests/unit/test_customer_vector_document_service.py --no-cov`
- `venv/bin/ruff check app/services/follow_up_task_projection_service.py app/services/follow_up_task_transition_execution_service.py tests/unit/test_sales_commitment_crud.py tests/unit/test_follow_up_task_transition_execution_service.py tests/unit/test_customer_activity_task_projection_api.py tests/unit/test_follow_up_tasks_api.py tests/unit/test_follow_up_task_confirmation_application_service.py tests/unit/test_agent_tools.py --select F,E9,I`
- `venv/bin/python -m py_compile app/services/follow_up_task_projection_service.py app/services/follow_up_task_transition_execution_service.py tests/unit/test_sales_commitment_crud.py tests/unit/test_follow_up_task_transition_execution_service.py tests/unit/test_customer_activity_task_projection_api.py tests/unit/test_follow_up_tasks_api.py tests/unit/test_follow_up_task_confirmation_application_service.py tests/unit/test_agent_tools.py`
- `venv/bin/alembic heads`

结果：

- 关键投影/状态/API/确认应用测试：`58 passed`。
- Agent tools 测试：`48 passed`。
- 向量文档服务测试：`21 passed`。
- Ruff 和 py_compile 通过。
- Alembic 当前单 head 为 `075_customer_vector_document_metadata_json`。

### SCM-P3-03：实现结构化查询 + 向量证据补充的 Agent 查询 graph

目标：

- 支持用户用自然语义查询任务，例如“预算相关未完成任务”“试用反馈还有哪些要跟”“合同卡点有哪些客户要处理”。
- 保持今天、本周、下周、逾期、未完成等确定性查询仍走 MySQL 结构化事实源。
- 保持向量库只提供语义候选和解释证据，不承担任务状态、owner、权限或时间窗口判断。

实现范围：

- 新增 `FollowUpTaskSemanticEvidenceService`：
  - 当 `query_text` 为空时不调用 embedding 和 Qdrant。
  - 当 Qdrant 未启用、embedding 不可用或召回异常时，返回可解释 retrieval event，并降级为空候选。
  - 召回 `follow_up_task` 和 `sales_commitment` 两类 source type。
  - 命中 `follow_up_task` 时通过任务 public_id 回表。
  - 命中 `sales_commitment` 时先用 commitment public_id 找承诺，再映射到关联 `FollowUpTask`。
- `FollowUpTaskQueryService.list_tasks` 增加 `query_text`：
  - 无 `query_text` 时保持纯 MySQL 结构化查询。
  - 有 `query_text` 时，先取向量候选 public_id，再叠加 status、due window、owner、customer 和可见客户范围过滤。
  - 输出 `semantic_retrieval` 和每条任务的 `semantic_evidence`，供 Agent 解释命中原因。
- `AgentToolService.list_follow_up_tasks` 和 `ListFollowUpTasksInput` 增加 `query_text`：
  - Agent 对外仍只暴露一个任务查询 tool，不新增割裂的“语义任务搜索”工具。
  - tool audit 记录 `query_text`，方便排查 Agent 为什么使用语义召回。

状态和权限语义：

- MySQL 是任务状态事实源；Qdrant 中的 `metadata_json.status` 只是召回解释和快照。
- 向量命中的已完成、已取消、其他 owner 或无权限客户任务，必须在 MySQL 回表阶段被过滤。
- 客户范围过滤先由结构化权限逻辑解析；向量候选不能绕过客户可见性。
- 回答“今天我的任务有哪些”“本周我的任务有哪些”“我还有哪些任务没完成”时，不需要 `query_text`，因此不会产生额外向量依赖。
- 回答“预算相关还有哪些客户要跟”“试用反馈相关任务”时，Agent 可以把语义条件放入 `query_text`，但最终列表仍是当前有效任务。

完成情况：

- 已新增 `CRM-Server/app/services/follow_up_task_semantic_evidence_service.py`。
- 已更新 Agent 任务查询服务和 tool schema，支持 `query_text` 语义条件。
- 已补测试覆盖：
  - 结构化 today 查询不会调用向量证据服务，`semantic_retrieval.status = not_attempted`。
  - 语义召回命中的已完成任务和其他 owner 任务不会出现在开放任务结果中。
  - 承诺向量命中可以映射回关联跟进任务。
  - Agent tool registry 接受、透传并审计 `query_text`。

验收命令：

- `venv/bin/python -m pytest tests/unit/test_agent_tools.py --no-cov`
- `venv/bin/ruff check app/services/follow_up_task_query_service.py app/services/follow_up_task_semantic_evidence_service.py app/services/agent/tools/service.py app/services/agent/tool_registry.py tests/unit/test_agent_tools.py --select F,E9,I`
- `venv/bin/python -m py_compile app/services/follow_up_task_query_service.py app/services/follow_up_task_semantic_evidence_service.py app/services/agent/tools/service.py app/services/agent/tool_registry.py`
- `venv/bin/python -m pytest tests/unit/test_follow_up_tasks_api.py tests/unit/test_follow_up_task_confirmation_application_service.py tests/unit/test_customer_activity_task_projection_api.py --no-cov`

结果：

- Agent tools 测试：`51 passed`。
- 跟进任务 API、确认应用和投影 API 测试：`15 passed`。
- Ruff 和 py_compile 通过。

### SCM-P3-04：建立向量证据过期、删除和状态不一致处理策略

目标：

- 防止 Agent 语义查询长期命中过期、已删除或状态快照明显落后的向量证据。
- 保持不一致处理可观测、可重跑、可降级，不让 Qdrant 成为任务状态事实源。
- 为后续运维巡检、异步修复和主动同步重试建立稳定边界。

实现范围：

- 增加任务/承诺向量证据一致性检查能力：
  - 扫描 `sales_commitment` / `follow_up_task` 向量文档。
  - 通过 `source_object_id` / `business_object_id` 的 public_id 回表。
  - 对比 MySQL 当前状态、owner、customer、due_at、completed_at、cancelled_at 等关键字段与 `metadata_json` 快照。
  - 对缺失源实体、软删除源实体或来源不合法的文档做删除标记或重建标记。
- 明确处理策略：
  - 状态快照落后：重新 upsert 当前 MySQL 快照，置为 `PENDING` 等待 Qdrant sync。
  - MySQL 源实体不存在：标记对应向量文档 `DELETE_PENDING`。
  - Qdrant/embedding 不可用：不阻塞 MySQL 查询，只记录诊断结果。
  - 多次 sync 失败：保留结构化任务查询可用，并暴露运维排查入口。
- 增加测试覆盖常见不一致：
  - 已完成任务 metadata 仍显示 open 时会被刷新。
  - 承诺取消后 metadata 仍显示 open 时会被刷新。
  - source public_id 找不到实体时标记删除。
  - 检查过程幂等，重复执行不会创建重复向量文档。

完成情况：

- 已新增 `CustomerVectorEvidenceReconciliationService`：
  - 扫描 `follow_up_task` / `sales_commitment` 向量文档。
  - 使用 public_id 回 MySQL 查任务/承诺实体。
  - 用现有 `CustomerEvidenceBuilder` 构建当前证据快照并与文档 metadata、text hash 和 source contract 比对。
  - stale 文档通过 `CustomerVectorDocumentService.upsert_follow_up_task` / `upsert_sales_commitment` 重建 metadata，并置为 `PENDING`。
  - 源实体不存在、source public_id 不合法或当前 evidence 无法构建时，标记为 `DELETE_PENDING`。
  - 已经一致的文档保持原 `sync_status`，避免巡检任务重复 requeue。
- 输出 `CustomerVectorEvidenceReconciliationResult.as_event()`，包含 scanned/refreshed/delete_pending/unchanged 和逐项处理 reason，方便后续接入运维日志、后台 job 或管理 API。
- 当前服务只处理 MySQL metadata 表一致性，不直接调用 Qdrant；真正 upsert/delete 仍由 `CustomerVectorSyncService` 消费 `PENDING` / `DELETE_PENDING` 文档。

验收命令：

- `venv/bin/python -m pytest tests/unit/test_customer_vector_document_service.py --no-cov`
- `venv/bin/ruff check app/services/customer_vector_evidence_reconciliation_service.py tests/unit/test_customer_vector_document_service.py --select F,E9,I`
- `venv/bin/python -m py_compile app/services/customer_vector_evidence_reconciliation_service.py`

结果：

- 向量文档服务和一致性巡检测试：`25 passed`。
- Ruff 和 py_compile 通过。

### SCM-P3-05：补充“卡在预算/试用/合同/采购”等语义查询评测集

目标：

- 用稳定 golden case 覆盖 Agent 任务语义查询的业务场景，避免后续改 Agent tool、向量召回或查询服务时破坏关键体验。
- 明确当前语义查询的边界：向量召回负责语义相关性，MySQL 负责状态、owner、权限和时间过滤。
- 把预算、试用、合同、采购这类高频销售语言固化为可 review 的 fixture。

实现范围：

- 新增 `follow_up_task_semantic_query_golden_cases.json`：
  - 预算：向量命中已完成和开放任务时，只返回开放任务。
  - 试用：命中试用反馈类任务。
  - 合同：命中合同法务/付款条款卡点任务。
  - 采购：命中采购挂网/采购预算任务。
  - 跨 owner：语义命中其他 owner 开放任务时，“我的任务”查询不返回。
  - stale status：语义命中已取消任务时，开放任务查询不返回。
  - ranking：多个开放候选通过结构化过滤后保留语义召回顺序。
  - no hit：无语义候选时返回空结果，不退化为全量开放任务。
- 新增 `FollowUpTaskSemanticQueryGoldenSuite`：
  - 加载 JSON fixture。
  - 做静态契约校验，确保 public_id、query_text、status、owner_scope、expected/forbidden 集合合法。
- 新增单元测试：
  - 静态校验 fixture 覆盖类别。
  - 使用 fake semantic evidence service 驱动真实 `FollowUpTaskQueryService`，验证 golden case 结果。

设计边界：

- 当前 P3-05 不假设 Qdrant 一定能排除所有语义误召回；如果 Qdrant 返回“开放、同 owner、但语义不该相关”的候选，查询服务会返回它。
- 后续如果要进一步提升自然性，应新增 reranker/LLM verifier 或向量召回质量评测，而不是把语义判断塞进 MySQL 过滤层。

验收命令：

- `venv/bin/python -m pytest tests/unit/test_follow_up_task_semantic_query_golden_suite.py --no-cov`
- `venv/bin/ruff check app/services/follow_up_task_semantic_query_golden_suite.py tests/unit/test_follow_up_task_semantic_query_golden_suite.py --select F,E9,I`
- `venv/bin/python -m py_compile app/services/follow_up_task_semantic_query_golden_suite.py tests/unit/test_follow_up_task_semantic_query_golden_suite.py`

结果：

- 任务语义查询 golden suite 测试：`10 passed`。
- Ruff 和 py_compile 通过。

## 7. Phase 4 拆分：工作总结

目标：

- 让 Agent 能回答“本周我完成了什么”“今天完成了哪些客户工作”等工作复盘类问题。
- 工作完成事实源必须来自结构化 MySQL 业务表；向量库只可用于语义检索和上下文补充，不能单独作为“已完成”的事实来源。
- Agent/LLM 负责把结构化 facts 归纳为自然语言，并保留事实引用，避免凭记忆或向量片段编造工作成果。

ticket：

- `SCM-P4-01` 定义 `WorkSummaryService` 事实源范围。
- `SCM-P4-02` 汇总任务、客户活动、商机阶段、合同、回款、发票和 License 事件。
- `SCM-P4-03` 实现 Agent 周报/月报 structured facts。
- `SCM-P4-04` 实现 LLM 总结生成，并保留事实引用。
- `SCM-P4-05` 建立工作总结准确性评测和人工校正机制。
- `SCM-P4-06` 硬化 Agent 全局任务查询和工作总结路由。
- `SCM-P4-07` 收敛只读查询语义模型和 trace 展示。

### SCM-P4-01：定义 WorkSummaryService 事实源范围

目标：

- 建立独立于 `FollowUpTaskQueryService` 的工作总结读模型，避免“任务查询”和“工作复盘”职责混在一起。
- 明确每类工作事实的时间字段、归属字段和对外标识策略。

范围：

- 新增 `WorkSummaryService.list_completed_work`。
- 输出统一 `items` facts，同时保留 `completed_tasks`、`activities` 兼容字段。
- 输出 `fact_source_scope` 和 `usage_policy`，让 Agent 编排层知道哪些事实可用于工作总结。

事实源范围：

| fact_type | 表 | 时间字段 | 归属字段 | 对外标识策略 |
| --- | --- | --- | --- | --- |
| `completed_follow_up_task` | `crm_follow_up_tasks` | `completed_at` | `owner_id` | `public_id` |
| `customer_activity` | `crm_customer_activities` | `occurred_at` | `owner_id` | 不暴露活动内部 ID |
| `opportunity_stage_entered` | `crm_opportunity_stage_snapshots` + `crm_opportunities` | `entered_at` | `crm_opportunities.owner_id` | `opportunity.public_id` |
| `contract_signed` / `contract_created` | `crm_contracts` | `signing_date`，缺失时回退 `created_time` | `owner_id` | `contract_number` |
| `payment_recorded` | `crm_payment_records` + `crm_contract_payment_plans` + `crm_contracts` | `payment_date`，缺失时回退 `created_time` | `creator_id` 或 `commission_member_id` | `record_number` |
| `invoice_application` | `crm_invoice_applications` | `issued_time`，缺失时回退 `reviewed_time` / `created_time` | `applicant_id` | `application_number` |
| `license_application` | `crm_license_applications` | `approved_time`，缺失时回退 `created_time` | `applicant_id` | `application_number` |

验收：

- Agent 查询工作总结时，默认不再只看跟进任务，而是拿到任务、活动和业务推进事件的统一事实列表。
- 输出明确禁止把 Qdrant 证据当作完成事实。
- 客户活动不暴露内部主键；任务和商机使用 public_id；当前无 public_id 的业务单据使用既有业务编号。

实现记录：

- `CRM-Server/app/services/work_summary_service.py` 已新增 `WorkSummaryService`。
- `CRM-Server/app/services/follow_up_task_query_service.py` 的旧 `list_completed_work` 已改为兼容 wrapper，默认只返回任务和活动，避免旧调用方意外扩张事实范围。
- `CRM-Server/app/services/agent/tools/service.py` 的 `list_completed_work` 已切换到 `WorkSummaryService`，默认包含业务事件。
- `CRM-Server/app/services/agent/tool_registry.py` 为 `list_completed_work` 补充 `include_tasks`、`include_activities`、`include_business_events` 参数。

### SCM-P4-02：汇总任务、活动和业务推进事件

目标：

- 把“本周完成了什么”从任务完成状态扩展为真实销售工作事实，覆盖跟进、商机推进、合同、回款、开票和 License 申请。

范围：

- 支持 `today` / `this_week` 时间窗口。
- 支持按客户 public_id 过滤；客户过滤前先做客户可见性检查。
- 宽查询仍按当前用户的事实归属字段过滤，不因客户 owner 是当前用户就自动合并别人的工作。
- 支持 include flags，用于后续不同 Agent 提问按需裁剪事实源。

验收：

- “本周我完成了什么”可返回已完成跟进任务、已记录客户活动和业务推进事件。
- 其他 owner 的任务、活动和业务事件不会进入“我的工作总结”。
- 指定客户时，当前用户必须能访问该客户；团队成员可查看客户范围内自己的工作事实。
- 输出不泄露任务/活动/业务对象内部数据库关联 ID。

实现记录：

- 单元测试 `CRM-Server/tests/unit/test_work_summary_service.py` 覆盖：
  - 任务、活动、商机阶段、合同、回款、发票、License 统一 facts。
  - owner 过滤。
  - 客户成员可见性和不可见客户拒绝。
  - include flags。
  - Agent-facing payload 不暴露内部 activity id / source_activity_id。
- `CRM-Server/tests/unit/test_agent_tools.py` 的 SQLite 建表 helper 已补业务事件依赖表，并使用测试内索引重命名规避 SQLite 全局索引名冲突。

验收命令：

- `venv/bin/python -m pytest tests/unit/test_agent_tools.py tests/unit/test_work_summary_service.py --no-cov`
- `venv/bin/ruff check app/services/work_summary_service.py app/services/agent/tools/service.py app/services/agent/tool_registry.py app/services/follow_up_task_query_service.py tests/unit/test_work_summary_service.py tests/unit/test_agent_tools.py --select F,E9,I`
- `venv/bin/python -m py_compile app/services/work_summary_service.py app/services/agent/tools/service.py app/services/agent/tool_registry.py app/services/follow_up_task_query_service.py tests/unit/test_work_summary_service.py tests/unit/test_agent_tools.py`

结果：

- Agent tools + WorkSummaryService 测试：`55 passed`。
- Ruff 和 py_compile 通过。

### SCM-P4-03：Agent 周报/月报 structured facts

目标：

- 在 `list_completed_work` 的基础上扩展面向周报/月报的 structured facts，而不是让 LLM 临时扫库或临时读向量。

范围：

- 增加 `last_week`、`this_month`、自定义日期范围等窗口。
- 按客户、事实类型、业务对象聚合 source counts 和重点事件。
- 明确分页/limit 对周报完整性的影响，例如返回 `truncated=true` 和下一页 cursor。

实现记录：

- `CRM-Server/app/services/work_summary_service.py` 已扩展 `WorkSummaryService.list_completed_work`：
  - `window` 支持 `today`、`this_week`、`last_week`、`this_month`、`custom`。
  - `custom` 支持 `start_at` / `end_at` ISO 日期或日期时间；日期型 `end_at` 按包含当天处理，内部转成独占结束时间。
  - 返回 `available_total`、`truncated`、`next_cursor`、`pagination`、`source_total_counts`。
  - `source_counts` 表示本页返回事实数，`source_total_counts` 表示当前过滤条件下 MySQL 可用事实总数。
  - 当 `truncated=true` 时，`usage_policy.pagination_rule` 明确要求 Agent 继续用 `next_cursor` 获取后续 facts，或在回答中声明当前总结基于部分事实。
- `CRM-Server/app/services/agent/tool_registry.py` 和 `CRM-Server/app/services/agent/tools/service.py` 已透传 `start_at`、`end_at`、`cursor`，让 Web Agent / IM Bot 共享同一工具能力。
- `CRM-Server/app/services/follow_up_task_query_service.py` 的兼容 wrapper 已支持新增参数，但默认仍只返回任务和活动，不自动扩张到业务事件。
- 新增单元测试覆盖：
  - `last_week`、`this_month` 和自定义日期范围。
  - 日期型 `end_at` 包含当天。
  - limit 截断、`next_cursor` 翻页、`available_total` 和 `source_total_counts`。

验收命令：

- `venv/bin/python -m pytest tests/unit/test_agent_tools.py tests/unit/test_work_summary_service.py --no-cov`
- `venv/bin/ruff check app/services/work_summary_service.py app/services/agent/tools/service.py app/services/agent/tool_registry.py app/services/follow_up_task_query_service.py tests/unit/test_work_summary_service.py tests/unit/test_agent_tools.py --select F,E9,I`
- `venv/bin/python -m py_compile app/services/work_summary_service.py app/services/agent/tools/service.py app/services/agent/tool_registry.py app/services/follow_up_task_query_service.py tests/unit/test_work_summary_service.py tests/unit/test_agent_tools.py`

结果：

- Agent tools + WorkSummaryService 测试：`57 passed`。
- Ruff 和 py_compile 通过。

### SCM-P4-04：LLM 总结生成，并保留事实引用

目标：

- 用 LLM 把 structured facts 生成自然语言总结，但每条总结都能回指事实来源。

范围：

- 设计事实引用格式，例如 `fact_id` 列表。
- 增加 prompt guardrail：只能总结 `items` 中存在的事实。
- 区分“已完成事实”“过程记录”“待办任务”，避免把未完成任务写成已完成。

实现记录：

- `CRM-Server/app/services/agent/schemas.py` 已新增：
  - `WorkSummaryNarrativeItem`
  - `WorkSummaryNarrativeResult`
- `WorkSummaryNarrativeItem` 必须包含 `fact_ids`，并按 `completed_work`、`process_record`、`business_progress` 分类：
  - `completed_follow_up_task` 才能归为 `completed_work`。
  - `customer_activity` 只能归为 `process_record`，不能写成“任务已完成”。
  - 商机阶段、合同、回款、开票、License 归为 `business_progress`。
- `CRM-Server/app/services/work_summary_narrative_service.py` 已新增 `WorkSummaryNarrativeService`：
  - 复用团队 AI 配置和 `AgentLangChainRuntime.ainvoke_structured`。
  - system prompt 明确禁止使用 `items` 外事实，禁止输出内部数据库主键、表名、`source_key`、`source_activity_id`。
  - LLM 返回后会再次按本页 `items.fact_id` 做 grounding：无效或幻觉 `fact_id` 会被过滤；没有任何有效引用时退回确定性总结。
  - 当 `truncated=true` 时，降低 confidence，并在 `missing_context` 中加入后续分页事实，避免误称完整总结。
  - 无 AI 配置、无 API key、LLM 失败或空事实时，返回确定性 fallback，但仍保留 citations。
- `CRM-Server/app/services/agent/tool_registry.py` 已新增 `summarize_completed_work` 只读 tool。
- `CRM-Server/app/services/agent/tools/service.py` 的 `summarize_completed_work` 先调用 `WorkSummaryService.list_completed_work` 获取 MySQL structured facts，再调用 `WorkSummaryNarrativeService` 生成 narrative，返回：
  - `facts`
  - `narrative`
  - `summary_source`
  - `model`
  - `fallback_reason`
  - `fallback_error`

验收命令：

- `venv/bin/python -m pytest tests/unit/test_work_summary_narrative_service.py tests/unit/test_work_summary_service.py tests/unit/test_agent_tools.py --no-cov`
- `venv/bin/ruff check app/services/work_summary_narrative_service.py app/services/work_summary_service.py app/services/agent/schemas.py app/services/agent/tools/service.py app/services/agent/tool_registry.py app/services/follow_up_task_query_service.py tests/unit/test_work_summary_narrative_service.py tests/unit/test_work_summary_service.py tests/unit/test_agent_tools.py --select F,E9,I`
- `venv/bin/python -m py_compile app/services/work_summary_narrative_service.py app/services/work_summary_service.py app/services/agent/schemas.py app/services/agent/tools/service.py app/services/agent/tool_registry.py app/services/follow_up_task_query_service.py tests/unit/test_work_summary_narrative_service.py tests/unit/test_work_summary_service.py tests/unit/test_agent_tools.py`

结果：

- WorkSummaryNarrative + WorkSummary + Agent tools 测试：`60 passed`。
- Ruff 和 py_compile 通过。

### SCM-P4-05：工作总结准确性评测和人工校正机制

目标：

- 建立工作总结质量闭环，防止 Agent 生成看似自然但事实不准的总结。

实现记录：

- `CRM-Server/app/services/work_summary_service.py` 的 `items` 已补顶层 `attribution`：
  - `user_id`：该事实归属到哪个用户。
  - `field`：归属字段，例如 `owner_id`、`applicant_id`、`creator_id`、`commission_member_id`。
  - `source`：归属字段来源，例如 `crm_follow_up_tasks.owner_id`。
  - 任务、客户活动、商机阶段、合同、回款、开票、License 事实均有可审计归属。
- 新增 `CRM-Server/app/services/work_summary_evaluation_service.py`：
  - 不调用 LLM，不修改业务数据。
  - 评测 structured facts 和 narrative 的契约，而不是评测自然语言风格。
  - 检查必需事实是否被引用、禁止事实是否被引用、引用是否都来自 `work_facts.items`、每个引用是否有 citation。
  - 检查 `completed_follow_up_task` 只能归为 `completed_work`，`customer_activity` 只能归为 `process_record`，业务事件只能归为 `business_progress`。
  - 检查 `attribution.user_id` 是否符合预期 owner。
  - 检查 `occurred_at` 是否落在 `filters.starts_at <= occurred_at < filters.ends_at`。
  - 检查 `truncated=true` 时是否披露“部分事实/后续分页事实”。
  - 检查回答中不能泄露内部字段名或内部数据库关联 ID。
- 新增 `CRM-Server/tests/fixtures/work_summary_golden_cases.json`：
  - 覆盖混合事实源周总结。
  - 覆盖客户活动只能作为过程记录。
  - 覆盖合同、开票、回款、License 等业务事件归类。
  - 覆盖分页截断披露。
  - 覆盖同客户多 owner 场景下只引用当前工作归属人的事实。
  - 覆盖人工校正样本的结构化记录。
- 新增 `CRM-Server/app/services/work_summary_golden_suite.py` 和 `CRM-Server/scripts/run_work_summary_eval.py`：
  - 本地可运行 `work_summary_golden` 质量门禁。
  - 支持 `--persist` 把评测运行写入现有 evaluation run 表，`suite_name` 使用 `work_summary_golden` 区分。
- `CRM-Server/app/crud/sales_commitment.py` 的评测运行持久化已兼容非 reconciliation 指标：
  - reconciliation 专用列继续保留。
  - work summary 指标完整保存到 `metrics_json`。
  - 非 reconciliation 套件的 `false_close` / `false_delay` / `missed_confirmation` / `over_confirmation` 汇总列为 0。
- 人工校正第一版不直接改事实、不直接改 prompt：
  - 校正以 `WorkSummaryHumanCorrection` 结构保存到评测样本或后续反馈表。
  - 支持 `missing_fact`、`remove_fact`、`reclassify_item`、`rewrite_summary`、`time_window_fix`、`owner_scope_fix`、`citation_fix`。
  - 校正必须指向真实 `fact_id`，除非类型是 `missing_fact`。
  - 校正样本后续可并入 golden suite，用于 prompt、事实源规则和读模型优化的回归。

评测指标：

- `fact_recall`：应被总结引用的事实召回率。
- `citation_completeness`：已引用事实是否都有 citation。
- `hallucination_rate`：narrative 引用不存在 fact_id 的比例。
- `owner_attribution_errors`：工作事实归属错误样本比例。
- `time_window_errors`：事实时间窗错误样本比例。
- `classification_errors`：完成工作、过程记录、业务推进分类错误比例。
- `correction_actionability`：人工校正样本是否结构化、可回放。

验收命令：

- `venv/bin/python -m pytest tests/unit/test_work_summary_evaluation_service.py tests/unit/test_work_summary_golden_suite.py tests/unit/test_work_summary_service.py tests/unit/test_sales_commitment_crud.py --no-cov`
- `venv/bin/ruff check app/services/work_summary_evaluation_service.py app/services/work_summary_golden_suite.py app/services/work_summary_service.py app/crud/sales_commitment.py scripts/run_work_summary_eval.py tests/unit/test_work_summary_evaluation_service.py tests/unit/test_work_summary_golden_suite.py tests/unit/test_work_summary_service.py tests/unit/test_sales_commitment_crud.py --select F,E9,I`
- `venv/bin/python -m py_compile app/services/work_summary_evaluation_service.py app/services/work_summary_golden_suite.py app/services/work_summary_service.py app/crud/sales_commitment.py scripts/run_work_summary_eval.py tests/unit/test_work_summary_evaluation_service.py tests/unit/test_work_summary_golden_suite.py tests/unit/test_work_summary_service.py tests/unit/test_sales_commitment_crud.py`

结果：

- Work summary evaluation + golden suite + WorkSummaryService + evaluation run CRUD 测试：`36 passed`。
- Ruff 和 py_compile 通过。

### SCM-P4-06：Agent 全局任务查询和工作总结路由硬化

目标：

- 让用户可以直接用自然语言问 Agent：“今天我的任务有哪些”“本周我的任务有哪些”“下周有什么工作安排”“还有哪些客户要跟进”“某个客户下周有哪些任务”“某个客户本月完成了什么”“本周我完成了什么”“帮我生成周报/月报”。
- 对全局只读查询使用确定性路由，避免 LLM 把任务查询误走客户上下文回答，或把“任务有哪些”误判成“工作总结”。
- 保持 Agent 体验自然，但事实读取仍通过只读 tool、权限校验和 MySQL 当前状态完成。

范围：

- 主 `CRMAgentGraphService` 在 `semantic_parse` 后增加 `run_agent_read_tool` 节点；全局查询可直接进入该节点，明确客户范围查询先走客户解析，解析成功后再进入同一节点。
- read-tool 路由只接受规范化后的 `CRM_READ_QUERY` 意图，并通过 `read_query.type` 区分任务查询、工作总结、客户档案等二级查询类型，避免继续把历史 `CUSTOMER_QUERY` 扩展为泛读意图。
- 全局工作总结问题路由到 `summarize_completed_work`：
  - 命中“完成了什么”“做了什么”“工作总结”“周报”“月报”等表达。
  - “本月/这个月/月报”映射 `this_month`，“上周”映射 `last_week`，“今天/今日”映射 `today`，默认映射 `this_week`。
  - 如果同一句包含“任务/待办/安排/要跟进/未完成/逾期”等任务查询词，优先按任务查询处理，避免“本周我的任务有哪些”被误当成工作总结。
- 全局任务/安排问题路由到 `list_follow_up_tasks`：
  - 命中“任务”“待办”“安排”“要跟进”“需要跟进”“还有哪些客户”“未完成”“逾期/延期/过期”等表达。
  - “今天/今日”“本周/这周”“下周”“逾期/延期/过期”映射对应 `due_window`。
  - 默认 `owner_scope=mine`、`status=open`；明确问“已完成任务/完成了任务”时使用 `status=completed`。
  - 非通用关键词会作为 `query_text` 传入任务查询 tool，用于 Phase 3 的向量证据语义条件，例如预算、试用、合同、采购等。
- 只读 tool 执行放在主 Agent graph，而不是 `ActionPlanningGraphService`：
  - 主 graph 持有 db、authorization、tool registry 和 user/team/session 上下文。
  - `ActionPlanningGraphService` 只负责把已执行的 tool result 转成最终 markdown 回复，不再重复执行工具。
- 输出格式：
  - 工作总结优先返回 `summarize_completed_work.narrative.answer`；无可用 answer 时回退确定性提示。
  - 任务列表最多直接展示前 10 条，包含客户名、任务标题、到期时间和逾期天数；超出部分提示用户继续缩小时间或语义条件。

边界：

- 全局 read query 在 `semantic_parse` 后直接执行。
- 如果 semantic parse 已识别出明确客户名，不在语义解析后直接执行全局工具，而是先进入客户解析，解析成功后带 `customer_id` 执行只读 tool，避免把“某个客户的任务”误答成“我的全局任务”。
- 通用片段型误识别，例如“下周我还有哪些客户要跟进”被 parser 误当作客户名时，会被识别为查询片段，仍允许走全局任务查询。
- 具体客户范围的任务/总结查询已采用二段只读路由：先 resolve customer，再把客户 public id 通过 `customer_id` 参数传给 `list_follow_up_tasks` 或 `summarize_completed_work`。

验收命令：

- `venv/bin/python -m pytest tests/unit/test_agent_graph.py tests/unit/test_agent_action_planning_graph.py tests/unit/test_agent_tools.py --no-cov`
- `venv/bin/ruff check app/services/agent/graph.py app/services/agent/action_planning_graph.py app/services/agent/state.py tests/unit/test_agent_graph.py --select F,E9,I`

结果：

- Agent graph + ActionPlanningGraph + Agent tools 测试：`127 passed`。
- Ruff 通过。

### SCM-P4-07：收敛只读查询语义模型和 trace 展示

目标：

- 避免继续使用 `CUSTOMER_QUERY` 作为泛读一级意图，防止后续任务查询、工作总结、合同查询、回款查询都堆到“客户查询”语义下形成历史债。
- 让 LangGraph 编排、只读 tool 计划、结果展示和前端 trace 各司其职。

范围：

- Schema 一级意图新增并使用 `CRM_READ_QUERY`，二级读取类型放入 `read_query.type`，当前覆盖 `FOLLOW_UP_TASKS`、`WORK_SUMMARY`、`CUSTOMER_PROFILE`、`OPPORTUNITY`、`CONTRACT`、`PAYMENT`、`INVOICE`、`LICENSE`。
- 旧 `CUSTOMER_QUERY` 只允许在 schema 或子图输入适配边界归一化为 `CRM_READ_QUERY`，不得继续作为业务路由判断。
- 新增 `AgentReadQueryPlanner`，负责把 `CRM_READ_QUERY + read_query.type + content + selected_customer` 转换成确定性 tool plan。
- 新增 read-query presenter，ActionPlanningGraph 只消费已执行 tool result 并输出 markdown，不再关心底层读取策略。
- Trace 事件同时保留 `technical_intent` 和 `intent_label`；前端优先展示 `intent_label`，用户看到“任务查询”“工作总结”“客户查询”，而不是技术枚举。
- Customer intelligence trigger 只响应规范化后的 `CRM_READ_QUERY`。

验收命令：

- `venv/bin/python -m pytest tests/unit/test_agent_read_query_planner.py tests/unit/test_agent_graph.py tests/unit/test_agent_action_planning_graph.py tests/unit/test_agent_business_context_graph.py tests/unit/test_agent_customer_resolution_graph.py tests/unit/test_customer_intelligence_trigger.py --no-cov`
- `venv/bin/ruff check app/services/agent/schemas.py app/services/agent/read_query_planner.py app/services/agent/read_query_presenters.py app/services/agent/graph.py app/services/agent/action_planning_graph.py app/services/agent/trace_events.py app/services/agent/semantic_payload.py app/services/agent/business_context_graph.py app/services/agent/customer_resolution_graph.py app/services/agent/follow_up_quality_graph.py app/services/agent/customer_intelligence_trigger.py tests/unit/test_agent_read_query_planner.py tests/unit/test_agent_action_planning_graph.py tests/unit/test_agent_business_context_graph.py tests/unit/test_agent_customer_resolution_graph.py tests/unit/test_customer_intelligence_trigger.py --select F,E9,I`
- `cd CRM-Client && npx eslint --max-warnings=0 src/components/agent/CRMAgentChat.vue src/api/agent.ts`

结果：

- Agent read-query planner、主 Agent graph、ActionPlanningGraph、BusinessContextGraph、CustomerResolutionGraph、CustomerIntelligenceTrigger 测试：`104 passed`。
- 后端 ruff 通过。
- 本次前端 touched 文件 eslint 通过。

## 8. Phase 5 占位拆分：主动摘要和偏好记忆

预留 ticket：

- `SCM-P5-01` 设计主动触达治理和用户偏好模型。
- `SCM-P5-02` 实现每日/每周摘要候选生成。
- `SCM-P5-03` 实现用户偏好记忆和频率控制。
- `SCM-P5-04` 统一 Web Agent 和 IM Bot 的触达编排，不分裂业务逻辑。
- `SCM-P5-05` 建立提醒疲劳、误提醒和关闭率监控。

## 9. 开发前检查清单

进入 Phase 1 编码前，需要确认：

1. `SCM-00` 的现状接入点清单已经完成。
2. 当前数据库迁移策略允许给客户活动补充非空 `owner_id`。
3. 当前项目已有 public_id 生成模式可复用；如果没有，需要先固化统一 helper。
4. 客户活动删除/作废语义已经明确。
5. 用户/团队时区来源已经明确。
6. Agent tool 权限校验已有可复用客户访问判断。
7. 历史回填允许先 dry-run，再正式执行。

## 10. Phase 1 完成定义

Phase 1 完成时，应满足：

1. 用户继续围绕客户跟进记录工作，不需要手动维护任务状态。
2. 页面和 Agent 录入活动都能通过统一流程生成任务。
3. AI 整理后补齐的下一步动作和时间能触发任务投影。
4. 用户能通过 Agent 查询今天、本周、下周、逾期、未完成和客户范围任务。
5. 任务事实来自 MySQL，LLM 和 Qdrant 不承担最终状态判断。
6. owner、creator、customer owner 三个概念没有混用。
7. 历史客户活动被低打扰回填，且不会制造大量重复过期待办。
8. 每次投影都有运行记录，关键状态变化都有事件审计。
9. 任务和承诺对外只暴露 public_id。
10. 自动关闭、低置信追问、跨 owner 处理、主动提醒仍保持关闭，等待 Phase 2+ 设计和验收。
