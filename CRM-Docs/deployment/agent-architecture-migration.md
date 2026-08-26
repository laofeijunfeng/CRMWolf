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
| `target_root` | `crm_agent:{team_id}:{user_id}:{session_id}` + 根 namespace | 保留并严格校验 Root state/metadata |
| `target_workflow` | 新 Root thread + `workflow_subgraph:*` | 保留并校验 interrupt、Workflow continuation、Action Registry |
| `legacy_root` | 旧 5 段 `crm_agent:{team_id}:{user_id}:{session_id}:{session_key}` | 静默后删除 |
| `legacy_query` | 旧 `query_agent:*` child | 删除；查询连续性只由 message/canonical query/result set 提供 |
| `legacy_workflow` | 旧 `workflow_graph:*`、`crm_agent_new_flow:*` 等 | 静默后删除；可恢复业务状态直接阻断 |
| `legacy_pending_confirmed` | 旧 pending/confirmed child 或独立 thread | 静默后删除；等待、挂起、interrupt 或未提交 write 直接阻断 |
| `legacy_helper` | 已删除 planner/helper runtime | 静默后删除 |
| `customer_intelligence` | `crm_agent_customer_intelligence:*` | 保留；校验物理链、active run、review case 和 interrupt barrier |
| `adjacent_workflow` | customer activity 等非本次 Agent 所有权 | 字节级保留并纳入 checksum |
| `unknown` | 无法归属的 thread/runtime/namespace/state/serde | 整体阻断 |

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
3. 确认前后端、worker、定时任务和任何其他数据库写入方均已停止后，用新版本后端执行事故恢复工具，并传入 `--offline-confirmed`。生产 MySQL 上工具会在盘点前对全部 `crm_*` 表取得 `WRITE` 锁，避免盘点和删除之间出现新的 target/unknown runtime 或新格式消息；不能取得锁即失败，不能绕过。它只会删除已分类的 legacy Agent checkpoint、所有 Customer Intelligence run 均为终态时的 Customer Intelligence checkpoint，以及完全未迁移的 Agent message history；它不会删除 Customer Intelligence run 业务记录、相邻 workflow checkpoint、target runtime 或 unknown runtime。遇到 target/unknown/部分迁移消息/非终态 Customer Intelligence run/被其他表引用的 Agent message 必须失败。
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
