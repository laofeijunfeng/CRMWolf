# CRM Agent 单版本架构切换门禁

本文档是 CRM Agent Root Orchestrator / Workflow Agent / Query Agent 单版本切换的唯一运维入口，对应：

```text
CRM-Docs/requirements/2026-08-21-crm-agent-query-architecture-prd.md
CRM-Docs/requirements/2026-08-21-crm-agent-query-architecture-trd.md
```

本次切换不提供双写、双读、旧 Runtime fallback、兼容 adapter 或长期 feature flag。生产异常通过完整应用版本与数据库备份恢复，不通过新版本继续读取旧 Agent checkpoint。

## 1. 工具与边界

常规单版本切换只使用三项一次性数据工具：

| 工具 | 作用 | 是否写库 |
|---|---|---|
| `scripts/inventory_agent_migration_data.py` | 生成消息与 checkpoint 的无业务内容盘点报告 | 否 |
| `scripts/migrate_agent_messages.py` | 将历史消息收敛到唯一 Agent UI message schema | 是，分批提交 |
| `scripts/cutover_agent_checkpoints.py` | 在一个事务中校验所有权、删除静默旧 Agent checkpoint 并写 journal | 是，单事务 |

另有**事故恢复专用**工具 `scripts/recover_agent_runtime_after_forced_schema_upgrade.py`。它不是常规门禁的替代方案；只在新 schema 已被误提前升级、旧应用无法再启动、没有可恢复的升级前数据库备份，且变更负责人已明确接受旧 Agent runtime 与历史消息丢失时使用。它必须同时带 `--execute`、`--accept-legacy-agent-runtime-loss`、`--accept-agent-message-history-loss` 与 `--reset-terminal-customer-intelligence-checkpoints` 四个确认参数。

旧 `checkpoint_migration.py`、`migrate_agent_checkpoints.py` 及其多阶段迁移合同已经删除，不得恢复、转发或重新包装。

所有 inventory 和 checkpoint cutover 必须使用同一个固定业务时间：

```text
2026-08-23T23:59:59+08:00
```

`--as-of` 必须是带时区的 ISO 8601 时间。工具会转换成 `Asia/Shanghai` 的数据库业务时间；禁止读取执行机器的当前时间来改变门禁结论。

## 2. Checkpoint 所有权矩阵

| 分类 | 身份 | Cutover 行为 |
|---|---|---|
| `target_root` | 当前运行时生成的 `crm_agent_turn:{team_id}:{user_id}:{session_id}:{turn_token}` + 根 namespace | 保留并严格校验 Root state/metadata |
| `target_workflow` | 当前 Root turn thread + `workflow_subgraph:*` | 保留并校验 interrupt、Workflow continuation、Action Registry |
| `legacy_root` | 旧 5 段 `crm_agent:{team_id}:{user_id}:{session_id}:{session_key}` | 静默后删除 |
| `legacy_query` | 旧 `query_agent:*` child | 删除；查询连续性只由 message/canonical query/result set 提供 |
| `legacy_workflow` | 旧 `workflow_graph:*`、`crm_agent_new_flow:*` 等 | 静默后删除；可恢复业务状态直接阻断 |
| `legacy_pending_confirmed` | 旧 pending/confirmed child 或独立 thread | 静默后删除；等待、挂起、interrupt 或未提交 write 直接阻断 |
| `legacy_helper` | 已删除 planner/helper runtime | 静默后删除 |
| `customer_intelligence` | `crm_agent_customer_intelligence:*` | 保留；校验物理链、active run、review case 和 interrupt barrier |
| `adjacent_workflow` | customer activity 等非本次 Agent 所有权 | 字节级保留并纳入 checksum |
| `unknown` | 无法归属的 thread/runtime/namespace/state/serde | 整体阻断 |

说明：`crm_agent:{team_id}:{user_id}:{session_id}` 是上一版目标实现遗留的三段 Root identity，迁移分类器仍仅为盘点/切换识别保留该形状；当前运行时不会再生成或恢复它，不属于新版本的兼容执行路径。

Legacy/unknown checkpoint 只允许通过 inert inspector 读取结构和 constructor identity，盘点与 cutover 都不得导入或执行历史应用构造器。Target Root/Workflow 与 Customer Intelligence 的 checkpoint、metadata、blob、write 和 review interrupt 必须先证明不存在应用自定义 constructor，再由 strict serializer 恢复允许的 LangGraph framework type。

Customer Intelligence 的 checkpoint/blob/write 还必须满足：根 namespace、完整单链、无 orphan、blob 引用闭合、metadata 的 team/event 一致。`RUNNING`/`RETRY_PENDING` 必须具有可恢复控制通道；`REVIEW_REQUIRED` 必须具有唯一 review case、候选事实、证据引用、运行结果摘要与 LangGraph interrupt barrier。`CANCELLED`、`EXPIRED` 或缺失的 review case 不可作为恢复依据。

## 3. 发布前责任与证据

生产执行前在发布工单登记：

| 字段 | 要求 |
|---|---|
| 变更负责人 | 姓名与可联系渠道 |
| 数据库备份负责人 | 姓名与可联系渠道 |
| 失败终止责任人 | 有权终止切换并批准数据库恢复 |
| 维护窗口 | 带时区的开始与结束时间 |
| 目标制品 | Git commit、镜像 digest、依赖锁校验结果 |
| 证据目录 | 服务器绝对路径，权限 `0700` |
| 数据库备份 | 文件路径、SHA-256、创建时间 |
| 恢复演练 | 临时库、开始/结束时间、关键表计数 |
| 最终 inventory | 文件路径、退出码、`blocking_unknowns` |
| message migration | 报告路径与状态 |
| checkpoint cutover | 报告路径、状态和 evidence SHA |

证据只能保存在服务器受限目录或发布工单附件中，不提交到 Git。

## 3.1 强制 schema 升级后的前向恢复（事故专用）

若违反常规顺序，先升级数据库再完成 inventory/message migration/cutover，**不得**尝试启动旧版本后端或伪造 inventory 成功。优先从升级前备份恢复；没有这种备份时，唯一允许的前向恢复路径是：

1. 停止前后端写入并创建、校验升级后紧急备份；在独立临时库完成恢复演练。
2. 在克隆库重放 message migration，记录不可收敛原因；若不能无损收敛，取得明确的 Agent message history 丢失授权。
3. 确认前后端、worker、定时任务和任何其他数据库写入方均已停止后，用新版本后端执行事故恢复工具，并传入 `--offline-confirmed`。生产 MySQL 上工具会在盘点前对数据库中全部应用表取得 `WRITE` 锁，避免盘点和删除之间出现新的 target/unknown runtime 或新格式消息；不能取得锁即失败，不能绕过。它只会删除已分类的 legacy Agent checkpoint、所有 Customer Intelligence run 均为终态时的 Customer Intelligence checkpoint，以及完全未迁移的 Agent message history；它不会删除 Customer Intelligence run 业务记录、相邻 workflow checkpoint、target runtime 或 unknown runtime。遇到 target/unknown/部分迁移消息/非终态 Customer Intelligence run/被其他表引用的 Agent message 必须失败。
4. 保存恢复工具的 JSON evidence 和 SHA-256；然后再次运行标准 checkpoint cutover，让标准 journal 验证最终空 legacy post-state。
5. 仅在新版本健康检查与关键业务验收后清理旧应用镜像。

示例（只在已获明确数据丢失授权的维护窗口中执行）：

```bash
cd CRM-Server
PYTHONPATH=. .venv/bin/python scripts/recover_agent_runtime_after_forced_schema_upgrade.py \
  --output /absolute/path/agent-forced-schema-recovery.json \
  --execute \
  --offline-confirmed \
  --accept-legacy-agent-runtime-loss \
  --accept-agent-message-history-loss \
  --reset-terminal-customer-intelligence-checkpoints
```

该命令通过独立 `agent-forced-schema-recovery-v1` journal 防止被误当作常规 cutover。完成证据会在同一数据库事务提交前先写入临时文件，提交后重新核验 journal 与 post-state 再原子发布；证据目录和文件权限分别为 `0700`、`0600`。恢复报告和备份只保存到服务器受限 evidence 目录，不提交到 Git。

## 4. 只读 Inventory

### 4.1 调查模式

调查模式允许 blocker 存在并返回退出码 `0`：

```bash
cd CRM-Server
PYTHONPATH=. .venv/bin/python scripts/inventory_agent_migration_data.py \
  --as-of '2026-08-23T23:59:59+08:00' \
  --report-only \
  --output /absolute/path/agent-inventory.json
```

`--report-only` 只用于本地或预发布调查，不能作为生产放行命令。

### 4.2 正式门禁模式

```bash
cd CRM-Server
set +e
PYTHONPATH=. .venv/bin/python scripts/inventory_agent_migration_data.py \
  --as-of '2026-08-23T23:59:59+08:00' \
  --output "$EVIDENCE_DIR/agent-inventory.final.json"
INVENTORY_EXIT_CODE=$?
set -e
printf '%s\n' "$INVENTORY_EXIT_CODE" > "$EVIDENCE_DIR/agent-inventory.final.exit-code"
```

通过条件：

- 退出码为 `0`；
- `schema_version=crm.agent.migration-inventory.v2`；
- `blocking_unknowns=[]`；
- `unknown` checkpoint 数量为 `0`；
- message role/event/payload shape 均无 unknown 或 invalid；
- 不存在 `legacy_task:active`、`legacy_checkpoint:active`；
- 不存在 owner mismatch、未知 serde、Customer Intelligence ownership/physical integrity blocker；
- inventory 使用的代码、数据库和最终待发布制品一致。

任一 blocker 都必须通过业务收口、确定性数据修复或明确的目标 schema 迁移解决。禁止增加 allowlist、忽略异常行或恢复旧 Runtime 只为了让报告变绿。

## 5. 当前本地 dev 基线

2026 年 8 月 23 日使用固定业务时间执行只读 inventory，结果为：

| 指标 | 数量 |
|---|---:|
| checkpoint rows | 30,949 |
| latest checkpoint identities | 5,499 |
| target Root | 0 |
| target Workflow | 0 |
| legacy Root | 5,381 rows / 626 latest |
| legacy Query | 509 rows / 78 latest |
| legacy Workflow | 6,865 rows / 1,441 latest |
| legacy Pending/Confirmed | 1,024 rows / 215 latest |
| legacy Helper | 11,384 rows / 2,278 latest |
| Customer Intelligence | 4,055 rows / 607 latest |
| Adjacent Workflow | 1,731 rows / 254 latest |
| active legacy tasks | 41 |

任务状态：`WAITING_USER=22`、`SUSPENDED=19`、`COMPLETED=89`、`FAILED=3`。

当前 blocker：

```text
customer_intelligence:physical_ownership_invalid
legacy_checkpoint:active
legacy_root:owner_mismatch
legacy_task:active
```

因此本地 dev 数据库当前不允许执行 destructive checkpoint cutover。以上数字是调查证据，不是生产数据结论。

## 6. 数据库备份与恢复演练

在停流后的最终 inventory 之前先确定维护窗口，在任何写库命令之前完成数据库备份和独立恢复演练。至少覆盖：

```text
crm_agent_sessions
crm_agent_tasks
crm_agent_messages
crm_agent_ui_actions
crm_agent_review_cases
crm_customer_intelligence_runs
crm_langgraph_checkpoints
crm_langgraph_checkpoint_blobs
crm_langgraph_checkpoint_writes
crm_agent_checkpoint_migration_journal
```

恢复演练必须导入到独立临时数据库，比较上述表的 row count，并记录备份 SHA-256。Alembic downgrade 不能替代数据恢复。

## 7. 维护窗口执行顺序

### 7.1 停止 Agent 写入

停止 Web/IM Agent 入口、异步 Agent worker、Customer Intelligence 调度与任何会写入 LangGraph checkpoint 的任务。普通 CRM 业务是否停流由发布方案决定，但不得继续产生 Agent message、action、review 或 checkpoint。

停流后重新执行正式 inventory。报告不通过时立即结束维护，不执行后续写入。

### 7.2 历史消息迁移

```bash
PYTHONPATH=. .venv/bin/python scripts/migrate_agent_messages.py \
  --batch-size 1000 \
  --start-after-id 0 \
  --output "$EVIDENCE_DIR/agent-message-migration.json" \
  --execute
```

通过条件：报告 `status=COMPLETED`，每批 `source_row_count=target_row_count=schema_validated_count`，无 `failure_code`。失败时不要手工改 payload；修复根因后从报告中的 `last_id` 明确恢复。

### 7.3 Checkpoint 单事务 Cutover

仅当最终 inventory 的 `blocking_unknowns=[]` 时执行：

```bash
PYTHONPATH=. .venv/bin/python scripts/cutover_agent_checkpoints.py \
  --as-of '2026-08-23T23:59:59+08:00' \
  --output "$EVIDENCE_DIR/agent-checkpoint-cutover.json" \
  --execute
```

CLI 行为：

1. 对输出路径加非阻塞文件锁；
2. 先 durable 写入 `IN_PROGRESS`；
3. 在同一数据库事务中重跑完整 ownership matrix；
4. blocker 非空则不删除任何数据，报告 `FAILED/RELEASE_GATE_BLOCKED`，退出码 `2`；
5. 删除已证明静默的 legacy checkpoint writes、blobs、checkpoints；
6. 验证旧所有权清空、保留数据 checksum 未变化；
7. 在同一事务写入唯一 cutover journal；
8. commit 前 durable stage `COMPLETED` 报告；
9. commit 后从数据库 journal 和 retained rows 重建证据，匹配后原子发布报告。

如果进程在 commit acknowledgment 附近中断，不得删除隐藏的 staged report 或手工补 journal。使用完全相同的 `--as-of` 和 `--output` 重跑同一命令；CLI 会拒绝业务截止时间与本次调用不一致的 staged/completed report。若 journal 已存在，CLI 验证 committed DB；若 staged report 存在但原事务已回滚，CLI 会在新事务中安全重跑 cutover，并严格比较删除计数、retained SHA 与 evidence SHA。只有全部匹配才原子发布完成报告，任一不一致均回滚并保留 staged evidence 供调查。

通过条件：

- 退出码 `0`；
- `scope_status=COMPLETED`；
- `result.schema_version=crm.agent.checkpoint-cutover.v2`；
- `result.already_completed` 为 `false`，或在中断恢复重跑时为已验证的 `true`；
- legacy checkpoint/blob/write 删除计数与停流后的最终 inventory 一致；
- target Root/Workflow、Customer Intelligence、Adjacent Workflow 的数量和 retained SHA 与报告一致；
- journal evidence SHA 与报告一致。

### 7.4 部署与验收

Checkpoint cutover 成功后部署同一目标制品并执行：

- Alembic current/head 校验；
- Agent contracts golden/conformance；
- Root NEW/CONTINUE/SWITCH；
- Query 城市/行业/负责人/时间/分页/空结果；
- Workflow interrupt、Action Registry、resume 与幂等；
- Customer Intelligence active run/review resume；
- Agent UI Web/IM 渲染；
- 多租户权限和 Result Set ownership；
- 固定模型配置下的真实 HTTP API 验收。

本地单元测试或 mock model 通过不能替代真实模型和真实 HTTP API 验收。

## 8. 失败终止与恢复

出现以下任一情况立即终止：

- inventory 非零退出或 blocker 非空；
- active legacy task/checkpoint 仍存在；
- Customer Intelligence 物理链、owner、review barrier 或 serde 无法证明；
- retained checkpoint/blob/write 的 row count 或 SHA 变化；
- message migration 报告失败；
- cutover 报告、staged report、journal 或 committed DB 不一致；
- 新 Root、Query、Workflow 或 Agent UI 需要旧 Runtime fallback 才能工作；
- 权限、幂等、resume、真实模型或 HTTP API 验收失败。

恢复必须由已登记的失败终止责任人批准，使用本次已验证的完整数据库备份和上一完整应用版本。不得在目标版本中临时恢复旧代码路径。

## 9. 一次性设施删除条件

完成生产切换、观察窗口和恢复演练证据验收后，在后续明确的 schema cleanup 变更中删除：

- `inventory_agent_migration_data.py`；
- `migrate_agent_messages.py`；
- `cutover_agent_checkpoints.py`；
- 对应离线 service 与测试；
- `crm_agent_checkpoint_migration_journal` 表。

删除前不得让这些设施进入请求运行时；删除时不得保留 forwarding module、alias 或兼容 wrapper。

## 2026-08-27 实施收口补充

本地目标架构的 Query 路径已按当前 typed Agent UI 合同完成一轮收口：

- Root Orchestrator 负责 Session/Turn 任务关系、上下文策略和 Query/Workflow 路由；Pending Case 不作为普通新输入的隐式 Workflow 上下文。
- Query Agent 使用 LangChain `create_agent`，只使用 CRM 只读工具；CRM Query Executor 负责 catalog、权限范围、分页、结果集和权威 API 适配。
- Workflow 使用 LangGraph 原生可恢复 subgraph；跨轮等待、确认和写入不得退化为 Query 或无 checkpoint 的恢复。
- Agent UI 是唯一前端语义协议；客户列表项只携带服务端签发的 `entity_ref`，由前端自行渲染并打开客户详情 Sheet。
- 模型传输重试只发生在 `ChatOpenAI` 调用边界，默认 `max_retries=2`；不会重放整个 Agent Turn。
- Query Executor 对 CRM API 408 返回 `UPSTREAM_TIMEOUT`，对 429/5xx 返回 `UPSTREAM_UNAVAILABLE`，对权限、查询错误和结构化响应错误保持独立分类。

真实 Dev API 记录见：
`CRM-Docs/development/agent-api-acceptance/2026-08-27/agent-query-20260827-1621/report.md`

本地 API 验收新增的会话、消息和结果集均保留，未执行测试数据清理。上述验证不等于生产发布；生产仍需完成停流、inventory、备份恢复演练、单版本 checkpoint cutover、全量回归和用户明确授权。

## 2026-10-23 Agent 1.0 遗留审计（CRM-27）

### 审计固定点与结论边界

本轮初始代码固定点是 `46e3a0070dd82bb4227b3d1d7b7b565dee9e5584`，不是对远程最新状态或任一数据库状态的声明。对该快照的 2,464 个跟踪路径做引用盘点，并在实现探索中实读 40 个产品源码文件，覆盖入口、配置消费者、前后端协议、持久化、共享工具和离线迁移设施；测试与部署说明另行核对。下表中的“本次已清理”指本次代码差异，不表示已经发布。

**结论：legacy workflow 清理已进入该主线快照；仍有 13 项无消费者配置需要退出 Settings 契约。完整 Agent retirement 尚无足够执行证据，不能据此宣布完成。** 当前 `/v1/agent`、`/agent`、Root + Workflow + Query、Agent UI 和 IM 仍承担当前业务职责；`/v1/assistant` 与 `/assistant` 是销售助手 2.0，不纳入本次清理。

### 可复核清单

| 对象 | 分类 | 代码或引用证据 | 处理与边界 |
|---|---|---|---|
| 旧 workflow 执行器、撤销入口、进度组件及其测试 | 已主线生效 | `a87aff053d780170e48ea7f1d0601a4cbf26c40c` 是上述固定点的祖先；该提交删除 `app/services/workflow/`、`api/workflow_undo.py`、`WorkflowProgress.vue` 等 | 不重建、不重复删除；不将这一提交等同于完整 Agent 退役 |
| retirement inventory 实现 | 仅 reflog 可追溯、无引用包含 | 审计时 `55ef18822f70c6dddb7afdb371097585dae3885c` 可读，但 `git for-each-ref --contains` 无结果；包含 inventory schema、CLI 和测试等 5 个文件 | 不是主线交付，不据此声称迁移或退役已执行；未来对象被回收后可能不可读 |
| `agent-retirement-20261016` 中的 retirement CLI、archive/restore/delete 和混合业务改动 | 仅 dirty worktree 草稿 | 草稿仍有未提交差异；其运行时关闭和业务改动超出本任务已批准范围 | 不复制整包、不覆盖他人改动；计划勾选、源码和 `.pyc` 都不是执行 receipt |
| 以下 13 项 Settings 字段 | 本次已清理 | 在初始快照的跟踪文本中均仅有 `app/core/config.py` 定义，没有调用方 | 删除字段，不留 alias、adapter、fallback、双读双写或迁移期开关 |
| 12 项现行 Agent 配置 | 仍保留 | `application.py`、`orchestrator/runtime.py`、`orchestrator/decision.py`、`query/semantic_intent.py`、`structured_model_call.py`、`tools/api_client.py`、`tasks/agent_turn_execution_recovery.py` 有实际读取 | 保留总超时、Root/Query 超时、流式分块超时、token 上限、内部 API 地址、lease/recovery/worker 参数及其原默认值 |
| 当前 Web/API/IM 入口、Root/Query/Workflow、Agent UI、会话/消息/action/result-set 模型和 schema | 仍保留 | `main.py` 无条件注册 Agent 路由；`api/agent.py` → `application.py` → `orchestrator/runtime.py`；前端 router、`api/agent.ts`、`AgentChat.vue` 与 IM adapter 仍连接此协议 | 现行业务路径，不按 Agent 或 legacy 名称退役；团队权限、只读查询、确认与写入原子不变 |
| `langchain_runtime.py`、`tool_registry.py` 及共享 CRM 工具 | 仍保留，有当前消费者 | 客户问答、事实提取等模块导入共享 LangChain helper；当前 `workflow/execution.py` 直接使用工具 registry | 当前职责未被替代，不扩大到共享工具重构；可选依赖导入不等于旧 Runtime fallback |
| `runtime.py` 中的 `AgentToolRuntime` wrapper | 待确认，保守保留 | 跟踪文本中的类名、singleton 和模块引用搜索仅命中其自身声明/实例化，尚未找到外部消费者；这不证明其历史职责或动态加载情况 | 已批准清单只删除13项配置；未证明该 helper 属于可退役旧实现，不猜测性删除，也不声称已证实当前消费者 |
| 共享 checkpoint saver、客户活动/客户智能及相邻 Workflow | 仍保留 | `agent/checkpointer.py` 使用 `customer_activity_ai/checkpointer.py`；所有权矩阵区分 Agent 与相邻业务 | 不删除共享数据，不改变 Activity Revision、后台任务和独立原子 |
| Alembic `100` / `101` / `102` 等历史迁移 | 已有主线代码；目标环境状态尚无本轮执行证据 | journal、旧 workflow ledger 和 AgentTask compatibility 有正式 revision 与链关系 | 不重写历史，不重复执行；migration 文件存在不证明目标库已升级或 contract 完成 |
| inventory / message migration / checkpoint cutover CLI、service 与对应测试 | 仍保留，有退出条件 | 本文第 1、4、7、9 节及 `scripts/` 中显式离线入口 | 只服务受控切换，不进入请求运行时；完成目标环境证据验收后，另行批准 schema cleanup 删除 |
| 事故恢复工具 | 仍保留，有严格授权边界 | 本文第 3.1 节及 `recover_agent_runtime_after_forced_schema_upgrade.py` | 仅用于已定义事故和数据丢失授权；不是常规切换替代或运行时兼容层 |
| 历史计划、旧文档中的完成描述、本地 mock/SQLite 测试 | 仅文档或代码可执行性证据 | 只能证明对应提交、计划内容或隔离测试行为 | 不替代目标环境 migration 状态、journal、receipt、备份或恢复演练 |

本次删除的完整配置清单：

- `MULTI_TOOL_ENABLED`、`REACT_ENABLED`、`AGENT_ENABLED`、`WORKFLOW_ENABLED`；
- `REACT_MAX_ROUNDS`、`REACT_SINGLE_ROUND_TIMEOUT`、`REACT_TOTAL_TIMEOUT`；
- `AGENT_SESSION_TIMEOUT`、`WORKFLOW_SESSION_TIMEOUT`；
- `AGENT_THREAD_POOL_SIZE`、`AGENT_MAX_CONCURRENT`；
- `AGENT_USER_RATE_LIMIT`、`AGENT_GLOBAL_RATE_LIMIT`。

旧 `.env` 或进程环境残留这些键时，沿用 Settings 既有 `extra="ignore"` 策略，不再校验或导出它们；即使其旧值类型非法，也不会阻止配置加载。当前有效字段仍按原类型规则加载、覆盖和校验。`AGENT_ENABLED=False` 原本并不能关闭当前入口，删除该假开关也不改变现行路由。仓库外的配置反射消费者不在本次引用证据范围内，运维应移除旧键，不能继续依赖它们控制服务。

### 生产执行与保留设施退出门禁

本轮没有取得可核验的目标环境 Alembic current/head、最终 inventory、历史消息迁移报告、cutover journal/receipt、seal/drain、archive、restore、delete 或 contract 执行记录，也没有获得维护窗口、备份恢复演练或破坏性操作授权。**本轮均未执行；目标环境历史状态记为“尚无执行证据”，不等于断言“从未执行”。** 本文第 5 节的历史本地 dev 盘点和旧计划不能补足这些证据。

继续保留一次性设施，直到具名负责人在明确目标环境中补齐：

1. 维护窗口和停流确认，固定代码制品及业务截止时间，最终 inventory 无 blocker；
2. 校验过的完整数据库备份与独立恢复演练；
3. 历史消息迁移成功报告，以及与 committed DB、保留数据校验和一致的 checkpoint cutover journal 和 receipt；
4. 单版本业务验收、观察窗口和失败恢复证据；
5. 对 archive/restore/delete/contract 或后续 schema cleanup 的独立明确批准。

满足前四项并取得第五项批准后，按第 9 节移除对应离线脚本、service、测试和 journal 表；表结构仍必须通过 Alembic。不能用本次配置清理替代这些门禁，不能把草稿 CLI 的命令存在当成已执行，也不能为拿到绿色报告引入运行时兼容路径。

### 后续确认的测试退役边界（2026-10-23）

主线提交 `3fed3dfe506cad31050920fa4e9365ea2ef38e77`（2026-10-10）已经删除客户档案运行时及其发布、证据解析、readiness、watermark 和后台调度实现。经逐项核查，本次退役直接依赖这些已删除实现的 12 个完整测试模块，并拆分混合测试：合同文件事务和失败回滚、团队隔离、来源上下文快照、来源验证、durable run 租约以及 Agent 异步操作晚绑定/终态投影的现行保证仍保留。旧来源进度递增断言不再代表当前实现；内容快照哈希仍需随业务事实变化。客户档案 API 不恢复，现行根路径和子路径对已注册方法统一返回 `410 CUSTOMER_PROFILE_REMOVED`。

**后续受限修复（不恢复客户档案）：**保留断言暴露的三类现行契约已按边界修复：通用来源检查重新校验公开任务/承诺 ID、别名和成对提示的一致性，并始终按团队和客户定位来源；现行业务事件只登记 durable run，使用已有客户记忆 graph 执行，保留租约、重试及 Agent 异步操作投影，不再读写已删除的档案投影。空流、结构化错误或缺少记忆写入凭证不能被记成成功；旧档案请求仍拒绝执行，不恢复发布、readiness 或来源进度机制。

`scripts/audit_legacy_profile_versions.py` 不再导入已删除的档案证据解析和版本认证模块。离线盘点保留原聚合字段、归属先验校验和只读事务，只对原支持的活记录重新检查当前来源；删除墓碑不能让已删除引用变成可用。旧认证器已退出，盘点不能验证任何历史认证，因此有有效归属的版本一律计为未认证并阻塞，不能相信缓存的签名、可用性或正文。该工具不是新认证器，也不是历史档案的可读入口。保护其只读、无私有内容输出和跨团队拒绝的两项原测试未修改，并补充缓存伪证、已删除来源与坏引用的安全用例。

上述结论来自隔离 SQLite、内存 checkpoint 和替身依赖下的单元/运行时验证；本轮没有连接真实数据库、执行离线审计 CLI 或认证目标环境历史数据。完整质量门槛结果另行如实记录，定向断言通过不代表全仓库 lint、类型、测试或覆盖率通过。
### 复核方法

在相同审计固定点执行以下只读 Git 检查，可复核已落地与未被引用包含的区别：

```bash
git merge-base --is-ancestor a87aff053d780170e48ea7f1d0601a4cbf26c40c 46e3a0070dd82bb4227b3d1d7b7b565dee9e5584
git show --stat a87aff053d780170e48ea7f1d0601a4cbf26c40c
git for-each-ref --contains 55ef18822f70c6dddb7afdb371097585dae3885c --format='%(refname)'
git show --stat 55ef18822f70c6dddb7afdb371097585dae3885c
```

配置复核应使用精确符号搜索，区分生产读取、回归测试和本节审计引用；同时检查动态属性读取、直接环境变量读取和当前调用闭包，不能只搜 Agent 前缀。新增 `tests/unit/test_agent_settings_contract.py` 从公开 Settings 构造、临时 `.env`、进程环境及导出行为验证旧键退出和现行字段保留，不读取源码字符串。

验证报告必须分别列出断言结果、命令退出码和全量质量门槛结果；定向断言通过不等于全仓库覆盖率或完整测试通过。上述 Git 检查和本地单元测试均不是生产执行证据。最终运行记录及正式 receipt 仍按第 3 节保存在受限证据目录或任务附件，不提交业务数据、密钥或运行 receipt 到 Git。
