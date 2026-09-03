# 客户活动 Workflow 实施状态

- **更新时间：**2026-09-02
- **权威规格：**[客户活动 Agent Workflow Parity 实施规格](./customer-activity-workflow-parity-spec.md)
- **验收基线：**[客户活动 Workflow 验收矩阵](./customer-activity-workflow-acceptance-matrix.md)
- **用途：**记录已经进入正式代码、迁移和测试的能力，以及尚未完成的实施项。对话中的讨论只有同步到权威规格、验收矩阵或本状态页后才视为可执行基线。

## 1. 总体状态

| Ticket | 状态 | 已落地内容 | 下一步 |
| --- | --- | --- | --- |
| T11 统一活动数据契约和状态定义 | 已完成 | canonical contract、ORM、schema、迁移 118、响应字段和契约测试已落地 | 迁移实跑时复核历史数据计数 |
| T12 深化 `CustomerActivityWriteService` | 已完成 | `create_pending_from_form()`、`create_final_from_agent()`、`finalize_pending_from_ai()` 三个正式入口及事务测试已落地；旧活动修改写入入口已删除 | 完成全量静态残留门禁 |
| T13 新增 `CustomerActivityAIJob` | 已完成 | model、CRUD、migration 119、claim/lease/retry/skip/exhausted、recovery scheduler 和测试已落地 | 完成真实 worker/迁移验收 |
| T14 AI Workflow 计算与写入分离 | 已完成 | 图内持久化节点、`mode="evaluate"` 分支和 Workflow 内写入已删除；Workflow 只计算最终整理稿和评分 | 补齐全链路真实模型/部署验收 |
| T15 Agent Workflow 接入质量和行动门禁 | 已完成（代码与专项测试） | Planner 已接入 canonical evaluator、60 分门禁、低分单问题、补充后完整语义重解析、客户 checkpoint 复用和空泛下一步行动门禁；Agent finalized 入口已切换；schema、工具输入和写入服务均 fail-closed 拒绝缺少/低于 60 分或无效评分 | 纳入真实模型 Golden Cases 与全链路验收 |
| T16 页面表单接入 AIJob | 已完成（代码） | 页面创建和 submit-and-complete-tracking 已改用 durable AIJob；接口立即返回，不提前创建 PostCommitJob；跟进记录和会议纪要共用后台 pipeline | 接入真实 worker 全链路验收 |
| T17 收拢 PostCommit、删除和跳过逻辑 | 已完成（核心实现） | revision fence、AIJob/PostCommitJob 删除前统一标记 `SKIPPED`、`SOURCE_ACTIVITY_DELETED` 任务证据、非级联外键迁移 120 和删除竞态测试已落地 | 纳入全链路 Worker/部署验收 |
| T18 清理旧入口和双轨 | 已完成（代码、静态检查与回归测试） | PUT/PATCH/process/evaluate API、旧 processing service、旧活动修改入口和 Workflow `mode="evaluate"` 已清理；MagicWand 已改走 FORM durable pipeline；旧路由未注册回归已补齐；历史待办确认已收敛为完成确认，延期保留为独立任务操作，旧延期文案采用读时兼容 | 纳入最终发布门禁 |
| T19 商机建议与商机 Workflow | 进行中（代码闭环已接入，真实联调待完成） | 已落地 Agent-only durable suggestion job、修订号/租约/重试/跳过/证据保留、AgentAsyncOperation 投影、Agent UI 是/否 action、Root server trigger、商机建议 Workflow 的创建/推进/取消规划、内嵌商机表单补充、创建/推进命令复用、商机状态变化静默忽略及专项测试 | 完成真实 API/Worker/Agent UI 联调、补齐 MOVE stale 及 replay 全链路验收 |
| T20 一次性数据迁移 | 代码、SQLite 行为测试和本地 MySQL `117 → 122` 升级已完成；生产 dry-run 待完成 | migration 122 已落地：固定 watermark、未完成活动接管、AIJob/PostCommitJob 孤儿处理、证据表和固定运行幂等键；旧客户活动运行时不再依赖旧 method，线索迁移边界保留显式适配器 | 完成 disposable 数据库、生产 dry-run、备份/恢复与中断重跑演练 |
| T21 全链路验收和上线切换 | 未开始 | 验收矩阵、发布阻断条件和 ADR 已建立 | 完成全量测试、真实迁移、部署 readiness 和 code review |

## 1.1 T19 当前已落地文件

- `CRM-Server/app/models/customer_opportunity_suggestion_job.py`
  - Agent-only 来源约束；活动修订号唯一；活动 ID 使用快照而非外键，保证删除后保留执行证据
  - QUEUED/RUNNING/RETRY_PENDING/COMPLETED/SKIPPED/EXHAUSTED 生命周期、租约和结果证据
- `CRM-Server/app/crud/customer_opportunity_suggestion_job.py`
  - 入队幂等、租约抢占、完成/重试/耗尽、删除前跳过和系统恢复候选扫描
- `CRM-Server/migrations/versions/121_customer_opportunity_suggestion_jobs.py`
  - 创建独立商机建议任务表，不级联删除活动，也不与活动写入共用商机事务
- `CRM-Server/tests/unit/test_customer_opportunity_suggestion_job.py`
- `CRM-Server/tests/unit/test_customer_opportunity_suggestion_jobs_migration.py`
- `CRM-Server/app/services/customer_opportunity_suggestion_job_service.py`
  - durable claim/lease/retry/exhausted；活动删除、revision 过期、来源非法时跳过；只生成建议，不直接创建/推进商机
  - 已有商机精确 ID/名称/结构化字段保守匹配，命中时静默 `NO_ACTION`
- `CRM-Server/app/tasks/customer_opportunity_suggestion_recovery.py`
  - 已接入应用 startup/shutdown，恢复 `QUEUED`、过期 `RUNNING`、到期 `RETRY_PENDING`
- `CRM-Server/app/services/customer_opportunity_suggestion_operation_projector.py`
  - 将建议任务 authoritative snapshot 投影到 Agent 异步操作；`CREATE_OPPORTUNITY`/`MOVE_OPPORTUNITY_STAGE` 进入 `WAITING_USER`，高置信度已有商机命中保持静默完成，删除源活动转为取消且保留证据
- `CRM-Server/app/services/agent/durable_work_contracts.py`、`durable_work.py`
  - Agent 活动 durable receipt 增加可选商机建议任务 ID；late bind/recovery 创建独立 `customer_opportunity_suggestion` 操作，不与活动后处理操作共用幂等键
- `CRM-Server/app/api/agent.py`
  - 会话操作读取和单操作读取增加商机建议投影 read-repair
- `CRM-Server/app/services/customer_activity_write_service.py`
  - Agent final 活动成功后独立登记商机建议任务；入队失败只回滚建议任务 savepoint，不回滚活动/PostCommit
- `CRM-Server/tests/unit/test_customer_opportunity_suggestion_job_service.py`
- `CRM-Server/tests/unit/test_customer_opportunity_suggestion_recovery.py`

已验证：

```text
T19 数据模型/CRUD/迁移专项：9 passed；活动写入/删除、建议服务/恢复、Agent durable bind、建议操作投影专项已纳入最近定向回归；本轮商机 Workflow + Root/Workflow 专项共 78 passed
```

### 1.2 T19 商机建议 Workflow 闭环（2026-09-02）

本轮已把“建议结果”接入独立 Workflow，关键边界如下：

1. `WorkflowOpportunitySuggestionStart` 只携带服务端签发的 `job_public_id` 和动作，不重新做自然语言解析、客户搜索或 LLM 判断。
2. 首次点击 Agent UI 的“是”是本商机操作的确认边界；后续创建/推进使用 `RESUME_AUTHORIZED`，不再弹第二次确认。
3. 创建商机缺字段时返回 Agent 页面内嵌 `collect_opportunity_fields` 表单；表单补充只合并允许的商机字段，客户 ID 永远取源活动绑定客户。
4. 商机创建复用既有采购方式解析和 `create_opportunity` command；商机推进复用既有阶段 resolver 和 `move_opportunity_stage` command。
5. Agent UI 的“否”使用无 command 的 terminal cancel plan；不伪造取消 tool，不修改活动或商机。
6. 推进动作执行前再次校验商机/阶段；建议来源的状态变化返回成功忽略，不覆盖最新状态、不重复执行、不向用户抛 stale 错误。
7. 源活动被删除、修订号变化、来源不为 `AGENT`、建议任务非 `COMPLETED` 或客户无权访问时，Workflow fail-closed，不执行商机写入。
8. Root action resolver 使用签名交互解析后的 typed `confirm/reject` 协议值，不依赖“确认/取消”等展示文案；同一 `client_request_id` 只返回 replay，不同请求不能再次 claim。

本轮新增/修改的主要代码：

- `CRM-Server/app/services/agent/workflow/planning.py`：建议任务权威读取、客户/活动/revision 校验、创建表单补充、创建/推进命令规划。
- `CRM-Server/app/services/agent/workflow/contracts.py`：允许 terminal cancelled plan，普通 plan 仍强制至少一个 command。
- `CRM-Server/app/services/agent/workflow/graph.py`：terminal cancel 路由，不进入 effect executor。
- `CRM-Server/app/services/agent/workflow/execution.py`：建议 Workflow 的用户确认授权和 MOVE stale 静默忽略。
- `CRM-Server/tests/unit/test_customer_opportunity_suggestion_workflow.py`：创建、表单补充、取消、推进和 stale 规划测试。

专项验证：

```text
商机建议 Workflow + Root/Workflow 回归：78 passed（含 Agent UI confirm/cancel、action claim/replay 安全回归）
```

仍未宣称完成的部分：disposable/生产数据库切换演练、真实 Worker/CRM API/前端联调和发布前全量验收。


## 1.3 T20 一次性历史数据切换（2026-09-02）

T20 的代码实现已经进入仓库；本地 MySQL 已完成真实 `117 → 122` 升级和一次幂等重跑验证，但在 disposable/生产数据库演练和发布演练完成前，不标记为上线完成。权威迁移文件和证据如下：

- `CRM-Server/migrations/versions/122_customer_activity_cutover.py`
  - 创建 `crm_customer_activity_cutover_runs` 证据表；
  - 使用固定运行键 `customer_activity_cutover:122` 和第一次运行确定的 `cutover_watermark`；
  - 只接管 watermark 之前仍处于 `PENDING`/`PROCESSING`，或评分仍处于 `PENDING`/`GENERATING` 的活动；
  - 每个活动按 `team_id + activity_id + activity_revision + job_type` 创建至多一个 `STRUCTURE_AND_EVALUATE` AIJob，来源为 `CUTOVER_MIGRATION`；
  - 已完成活动不重新整理、不重新评分、不创建 AIJob，已有最终内容和最终评分保持不变；
  - 未完成的历史 Agent 活动只在切换边界重分类为 `CUTOVER_MIGRATION`，由 canonical AIJob finalization gate 接管，不作为新的 Agent 二次评分；
  - 活动已删除但任务证据仍存在时，将未完成 AIJob/PostCommitJob 静默标记为 `SKIPPED`，原因为 `SOURCE_ACTIVITY_DELETED`；
  - 活动仍存在但尚未最终化时，将旧的未完成 PostCommitJob 标记为 `SKIPPED`，原因是 `REPLACED_BY_ACTIVITY_AI_JOB`；活动已经最终化的旧 PostCommitJob 保留，交给新的 executor 恢复；
  - 不恢复旧进程内 task，也不恢复旧 Agent graph/checkpoint；
  - 已完成的固定运行键再次执行直接返回已记录证据，不重复扫描、不重复计数、不修改 watermark。
- `CRM-Server/app/models/customer_activity_cutover_run.py` 已注册到 `app.models`，用于证据表的 schema 对齐。
- `CRM-Server/tests/unit/test_customer_activity_cutover_migration.py` 覆盖接管、保留、孤儿跳过、删除证据、唯一创建和重跑幂等。

### 旧 `method` 的收口边界

`CustomerActivity.activity_kind` 是客户活动的唯一 canonical 字段；客户活动新建、最终化、查询和响应不再保存或读取旧 `method`。旧客户活动表及旧字段不会作为新流程的长期双轨。

由于线索子系统仍有 `LeadFollowUp.method`，`CustomerActivityCRUD.migrate_from_lead()` 只保留一个明确的“线索历史边界适配”步骤，将线索历史值一次性转换为 `activity_kind`；这不是客户活动运行时兼容分支，也不代表保留旧映射关系。Agent 规划阶段对旧语义解析字段的读取同样只作为输入适配，落库前必须产出 canonical `activity_kind`。

本地 MySQL 验证证据（2026-09-02）：`alembic current` 为 `122_customer_activity_cutover (head)`；固定证据行 `customer_activity_cutover:122` 为 `COMPLETED`，接管 21 条活动并创建 21 个 `CUTOVER_MIGRATION` AIJob；再次执行 `alembic upgrade head` 未新增证据行或重复任务。`alembic check` 仍报告仓库既有全量 schema/index 漂移（不局限于本轮 118-122），因此不能把它记为通过，也不能据此判定 122 升级失败。

真实迁移发布前仍必须补齐：disposable 数据库、现网计数核对、备份恢复、worker 重启、迁移中断重跑和 release readiness。

## 2. T11 已落地文件

### 2.1 领域合同

- `CRM-Server/app/services/customer_activity_contracts.py`
  - 提交来源：`AGENT`、`FORM`、`CUTOVER_MIGRATION`
  - 活动处理和评分状态
  - AIJob、PostCommit/Suggestion durable 状态词汇
  - 下一步字段 provenance 词汇

### 2.2 数据模型和 API 合同

- `CRM-Server/app/models/customer_activity.py`
  - `activity_revision`
  - `submission_source`
  - `submission_id`
  - 状态和来源约束
  - `(team_id, submission_id)` 唯一约束
- `CRM-Server/app/models/customer_activity_post_commit_job.py`
  - durable job 状态收拢到 canonical 词汇
- `CRM-Server/app/schemas/customer_activity.py`
  - 创建和响应 schema 暴露 submission provenance
- `CRM-Server/app/api/customer_activities.py`
  - 活动响应输出 `submission_source` 和 `submission_id`
- `CRM-Server/app/services/agent/tools/service.py`
  - Agent 创建活动时发送 `submission_source=AGENT`
  - 使用 Agent action key 作为 `submission_id`

### 2.3 数据迁移

- `CRM-Server/migrations/versions/118_customer_activity_workflow_contracts.py`
  - `post_commit_revision` 重命名为 `activity_revision`
  - 新增 submission provenance 和幂等唯一约束
  - 根据历史 Agent origin 回填来源，其余历史活动回填为 `FORM`
  - 增加活动状态与 PostCommitJob 状态数据库约束

### 2.4 自动化测试

- `CRM-Server/tests/unit/test_customer_activity_contracts.py`
- `CRM-Server/tests/unit/test_customer_activity_response.py`
- `CRM-Server/tests/unit/test_customer_activity_workflow_contracts_migration.py`

已验证：

```text
T11 新增契约/响应/迁移结构测试：7 passed
活动相关既有回归组：104 passed（T11 初始改造后）
```

## 3. T11-T16 已落地文件

### 3.1 三个写入入口和页面提交

- `CRM-Server/app/services/customer_activity_write_service.py`
  - `create_pending_from_form()`：原始活动与 AIJob 同事务创建，不提前创建 PostCommitJob。
  - `create_final_from_agent()`：Agent 最终稿和最终评分一次写入，不创建 AIJob。
  - `finalize_pending_from_ai()`：最终稿、最终评分、最终 revision、PostCommitJob、客户智能事件和 AIJob 完成状态同事务提交。
- `CRM-Server/app/crud/customer_activity.py`
  - `apply_finalization()` 只写一次最终整理结果和最终评分。

### 3.2 Durable AIJob

- `CRM-Server/app/models/customer_activity_ai_job.py`
- `CRM-Server/app/crud/customer_activity_ai_job.py`
- `CRM-Server/app/services/customer_activity_ai_job_service.py`
- `CRM-Server/app/tasks/customer_activity_ai_job_recovery.py`
- `CRM-Server/migrations/versions/119_customer_activity_ai_jobs.py`
- `CRM-Server/app/core/config.py`
- `CRM-Server/app/main.py`

已经落地：

- 自然键：`team_id + activity_id + activity_revision + job_type`；
- 来源限制：只允许 `FORM`、`CUTOVER_MIGRATION`，Agent 来源 fail-fast；
- 原子 claim、lease owner 校验、过期 lease 接管；
- 指数退避、`RETRY_PENDING`、最大次数 `EXHAUSTED`；
- 活动删除、revision 变化和非法来源静默 `SKIPPED`；
- 启动/周期 recovery scheduler；
- 重试耗尽时保留原始活动，并把活动 UI 投影置为 `FAILED`。

### 3.3 AI Workflow 纯计算化

- `CRM-Server/app/services/customer_activity_ai/workflow.py`
- `CRM-Server/app/services/customer_activity_ai/schemas.py`

图内已移除 `persist_structured_content` 和 `persist_evaluation_result` 节点。Evaluator 使用最终整理稿作为输入，Workflow 返回 `CustomerActivityAIFinalResult`，业务写入只允许通过 `finalize_pending_from_ai()` 完成。

### 3.4 页面 API 切换

- `CRM-Server/app/api/customer_activities.py`
  - `POST /v1/customer-activities/{customer_id}` 已固定为页面表单来源；
  - `POST /submit-and-complete-tracking` 同样先保存原始活动并登记 AIJob；
  - 返回 `durable_work.ai_job_public_id`；
  - 页面提交不再等待 LLM、不再提前创建 PostCommitJob；
  - 客户活动展示字段和响应结构保持现有兼容字段。
- `CRM-Server/tests/unit/test_customer_activity_form_submission_api.py`
  - 覆盖 PENDING、FORM 来源、AIJob=1、PostCommitJob=0。
- `CRM-Server/tests/unit/test_customer_activity_task_projection_api.py`
  - 已将页面提交预期改为“等待 AI 最终化后再投影”；删除仍保留删除投影记录。

### 3.5 当前验证证据

```text
T12-T14 定向测试：29 passed
T16 页面表单/API/投影定向测试：9 passed
T17 删除任务证据及相关回归测试：60 passed
T15 Agent finalized 合同/工具/写入回归：78 passed
T15 Workflow resume/客户 checkpoint/评分与下一步门禁专项：44 passed
T18 旧活动 mutation/process/evaluate 路由未注册回归：3 passed
本轮修复后 parity + 相关 Agent contract 回归：180 passed
CRM-Server 全量 `tests/unit`：1832 passed，21 failed，20 skipped；21 项失败均位于本轮范围外的既有业务/环境测试，不能作为 parity 通过证据。
CRM-Server/app 与 tests 编译检查：通过
本轮新增商机建议模块 4 个文件 Ruff：通过（既有 API/schema 文件的历史 lint 不作为本轮回归证据）
git diff --check：通过
```

### 3.6 前端 WAITING_USER 投影刷新（2026-09-02）

本轮补齐了一个真实的 Agent UI 接线缺口：商机建议任务从 `RUNNING/QUEUED` 进入 `WAITING_USER` 后，前端现在会在**首次状态转换**时重新读取会话消息，使后端刚生成的“是/否”组件能够自动出现，不需要用户手工刷新页面。

实现边界：

- `useAgentAsyncOperations` 新增 `onWaitingUser` 回调；
- 仅当同一 operation 从非 `WAITING_USER` 进入 `WAITING_USER` 时通知一次；持续轮询不会重复刷新；
- 初始读取已经是 `WAITING_USER` 的 operation 也会触发一次，支持页面刷新恢复；
- `CRMAgentChat` 按 operation 的 `session_id` 刷新 authoritative session messages；
- 商机建议 operation 在后台任务列表显示为“商机建议分析”，不再回退为“后台任务”。

新增前端测试：

- `CRM-Client/src/composables/__tests__/useAgentAsyncOperations.test.ts`：3 cases；
- `CRM-Client/src/components/agent/__tests__/agentAsyncOperations.test.ts`：1 case。

本轮验证：

```text
前端 WAITING_USER/title/UI interaction 回归：6 passed
CRM-Client npm run type-check：通过
本轮触及文件 ESLint：通过
```

这只证明前端接线和确定性组件行为已覆盖，不等同于真实 Worker、CRM API 和浏览器联调完成。

### 3.7 T17 删除任务证据（已落地）

- `migrations/versions/120_customer_activity_post_commit_job_evidence.py` 已移除活动到 PostCommitJob 的级联外键。
- 删除活动时，在同一事务内将未完成的 AIJob 和 PostCommitJob 标记为 `SKIPPED`，并写入 `SOURCE_ACTIVITY_DELETED`。
- 任务的原始 `result_json`、错误信息和删除前状态证据保留；lease/retry 字段清理，防止删除后继续恢复执行。
- 已完成、已跳过和已耗尽的终态任务不被重复改写。
- 删除竞态、任务证据和迁移结构均有定向测试覆盖。

## 4. 当前仍存在的实施缺口

以下是截至 2026-09-02 的真实状态，不代表目标设计：

1. T15 还需要真实模型 Golden Cases，以及部署环境下的完整 resume/多轮重解析验收。
2. T19 的代码闭环已经接入，但仍需要真实 CRM API、Worker、Agent UI 联调，并补齐 MOVE stale、重复点击和安全 replay 的全链路验收。
3. T20 的 migration 122、证据模型、SQLite 行为测试和本地 MySQL `117 → 122` 升级/幂等重跑已完成；disposable 数据库、生产 dry-run、备份恢复、worker 重启和中断重跑尚未完成。`alembic check` 报告的是仓库既有的全量 schema/index 漂移，不作为本轮 migration 122 的通过证据。
4. T21 全链路验收、部署 readiness 和最终 code review 尚未完成。

## 5. 实施约束

- 已冻结规则不再重复确认。
- 每个 Ticket 完成时必须同步更新本页、权威规格中的实现状态和验收证据。
- 不把未实现能力标记为完成。
- 不保留新旧双轨作为长期兼容方案。
- 不修改无关业务对象或用户工作树中的无关变更。
