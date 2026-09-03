# 客户活动 Agent Workflow 验收矩阵

- **日期：**2026-09-02
- **状态：**实施中验收基线；已落地能力必须保留代码、迁移和测试证据，未完成项不得标记为通过
- **对应规格：**[客户活动 Agent Workflow Parity 实施规格](./customer-activity-workflow-parity-spec.md)
- **目的：**通过确定性测试、公共 API、真实模型和部署恢复证据证明旧流程能力已经完整迁移，且新流程没有重复评分、重复写入或业务原子性破坏。

## 1. 测试层级

| 层级 | 目的 |
|---|---|
| L1 领域单元测试 | 评分门禁、下一步行动、客户绑定、商机决策、状态转换、幂等键 |
| L2 事务集成测试 | 写入服务、唯一约束、revision、Job 入队、提交与回滚 |
| L3 Workflow 测试 | interrupt/resume、单问题补充、客户选择、取消和重复 resume |
| L4 公共 API 测试 | HTTP 响应、数据库副作用、消息投影、后台任务 |
| L5 Worker/部署测试 | lease、重试、重启、删除竞态、切换迁移和恢复 |
| L6 真实模型测试 | 质量判断、补充问题、下一步行动和商机语义质量 |

核心事务、幂等和权限不得只依赖非确定性真实模型测试。

## 2. Agent 活动

| ID | 场景 | 期望 | 禁止行为 |
|---|---|---|---|
| A01 | 完整高质量跟进 | 唯一客户、评分通过、行动门禁通过、创建一条最终活动 | AIJob、重复评分、重复活动 |
| A02 | 低于 60 | 不写活动，只问一个关键问题 | 确认、PostCommit、商机建议 |
| A03 | 低分补充后通过 | 合并全部用户原文后重新解析/整理/评分，保存唯一最终分 | 只评最后一句、保存第一次低分 |
| A04 | 补充后仍低分 | 继续阻塞并问当前最关键问题 | 为推进流程降低门禁 |
| A05 | 评分通过但无下一步 | 追问下一步行动 | 因分数通过直接写入 |
| A06 | 明确动作无时间 | 允许保存，时间为空 | 猜测明天/周五等日期 |
| A07 | 明确暂无下一步 | 保存原因或复查条件 | 强制编造行动 |
| A08 | “继续跟进/再看看” | 判为模糊并追问 | 当作有效行动 |
| A09 | 明确时间 | 使用现有时间解析保存 | 模型自由猜日期 |
| A10 | evaluator 超时/非法输出 | fail-closed，不写活动 | 绕过评分 | ✅ evaluator/Agent finalized 边界测试；真实模型待验收 |
| A11 | 用户取消 | Workflow 终止，无业务写入 | 残留活动或任务 |
| A12 | 重复确认 | 返回同一活动结果 | 两条活动 |
| A13 | 成功响应丢失后重试 | 通过 command 幂等返回原结果 | 重新评分或写入 |
| A14 | Agent 会议纪要 | 共用相同评分、门禁和最终写入 | 另一套评分流程 |

Agent 成功活动数据库断言：

```text
activity_count += 1
processing_status=COMPLETED
effectiveness_status=COMPLETED
final_score is not null
CustomerActivityAIJob=0
PostCommitJob=1
```

## 3. 客户解析与跨轮恢复

| ID | 场景 | 期望 |
|---|---|---|
| C01 | 唯一客户 | customer_id 写入 checkpoint |
| C02 | 没有匹配 | 只告知没有匹配，不自动创建客户 |
| C03 | 多候选 | Agent UI 客户选择，选择后继续 |
| C04 | 质量/行动补充 | 复用 customer_id，Resolver 调用次数仍为 1 |
| C05 | 明确切换客户 | 清理旧绑定和上下文，重新解析新客户 |
| C06 | 正文提到另一个案例客户 | 不自动切换主客户 |
| C07 | resume 前权限被撤销 | 复用 ID 但重新授权，禁止写入 |
| C08 | resume 前客户删除 | 不写入，不猜测替代客户 |
| C09 | 页面刷新 | 恢复到原 interaction，不重新开始 |
| C10 | 重复 resume_event_id | 只消费一次补充 |

## 4. 客户创建与部分成功

| ID | 场景 | 期望 |
|---|---|---|
| CC01 | 明确要求创建客户 | 调客户 API，不创建线索 |
| CC02 | API 返回唯一已有客户 | 直接复用，不再确认 |
| CC03 | API 返回多候选 | 让用户选择 |
| CC04 | 客户成功、活动失败 | 返回部分成功，客户保留 |
| CC05 | 重试 CC04 | 跳过客户 command，只重试活动 |
| CC06 | 客户创建失败 | 不执行活动 command |

## 5. 页面表单活动

| ID | 场景 | 期望 | 数据断言 |
|---|---|---|---|
| F01 | 提交跟进 | 立即保存并返回 | activity=1、AIJob=1、PostCommit=0 | ✅ API 定向测试 |
| F02 | 提交会议纪要 | 与跟进共用 durable pipeline | 不走独立旧评分 | 代码路径已统一，待补会议纪要 API case |
| F03 | AIJob 成功 | 一次性最终化 | 两状态 COMPLETED、PostCommit=1 | ✅ AIJob service 测试 |
| F04 | 最终评分 45 | 保留低分活动 | 状态 COMPLETED、PostCommit=1、商机任务=0 |
| F05 | 首次技术失败后成功 | RETRY_PENDING 后恢复 | 最终只写一次评分 |
| F06 | 重试耗尽 | 原始活动保留 | AIJob EXHAUSTED、活动投影 FAILED |
| F07 | 重复 submission_id | 返回原结果 | activity=1、AIJob=1 |
| F08 | 完成响应丢失后重放 | 最终化幂等 | revision 和 PostCommit 不重复 |

## 6. 评分收拢

| ID | 场景 | 期望 |
|---|---|---|
| S01 | Agent 路径 | Agent evaluator=1，后台 evaluator=0 |
| S02 | 页面路径 | Agent evaluator=0，AIJob evaluator=1 |
| S03 | 旧评论/详情评分入口 | 不再存在独立评分触发 |
| S04 | 补充和重试 | 只保存最终成功评分 |
| S05 | 评分对象一致性 | evaluator 输入与最终整理稿一致 |
| S06 | 页面低分 | 有效完成，不标记技术 FAILED |
| S07 | Agent evaluator 错误 | 不写活动 |

## 7. CustomerActivityAIJob

| ID | 场景 | 期望 |
|---|---|---|
| J01 | 相同自然键重复 enqueue | 数据库只有一条 Job | ✅ service/migration 测试 |
| J02 | 两 Worker 并发 claim | 只有一个获得 lease |
| J03 | 非 lease owner 完成 | 条件更新失败，不写活动 |
| J04 | Worker 崩溃 | lease 过期后恢复 |
| J05 | 活动执行前已删除 | SKIPPED/SOURCE_ACTIVITY_DELETED |
| J06 | LLM 期间活动删除 | 最终事务检查后 SKIPPED |
| J07 | revision 变化 | 不覆盖，SKIPPED |
| J08 | transient failure | RETRY_PENDING，按退避恢复 |
| J09 | 最大重试耗尽 | EXHAUSTED，活动原文保留 |
| J10 | Agent 来源活动 | 永远不存在 AIJob |

## 8. PostCommitJob

| ID | 场景 | 期望 |
|---|---|---|
| P01 | Agent 最终活动 | 同事务创建一条 PostCommitJob |
| P02 | 页面原始保存 | 不创建 PostCommitJob |
| P03 | 页面 AI 最终化 | 为最终 revision 创建一条 Job |
| P04 | 重复 enqueue | 唯一键返回已有任务 |
| P05 | Worker 崩溃 | lease 恢复，副作用一次 |
| P06 | 活动删除 | 任务保留并 SKIPPED |
| P07 | 旧 revision | SKIPPED，不覆盖新状态 |
| P08 | Job 失败 | 不修改活动内容和评分 |
| P09 | 页面低分 | PostCommit 仍执行 |
| P10 | 外键检查 | 删除活动不级联删除任务证据 |

## 9. 商机

| ID | 场景 | 期望 |
|---|---|---|
| O01 | 明确新商机 | 跟进先成功；建议任务完成后投影为独立 `WAITING_USER` 操作，显示是否创建建议 | ✅ durable job、Agent receipt、异步操作投影、Agent UI choice projection |
| O02 | 点击“是” | Agent 页面内嵌商机表单；提交后进入独立创建 Workflow | ✅ server trigger、内嵌 form interaction、RESUME_AUTHORIZED command planning；待真实前端联调 |
| O03 | 点击“否”或取消 | 只结束商机流程，跟进保留，不产生商机写入 | ✅ terminal cancel plan，无 cancel tool |
| O04 | 高置信度已有商机 | 静默忽略重复创建，不询问 |
| O05 | 证据不足/冲突 | 不自动创建，不强迫用户选择 |
| O06 | 明确要求推进 | 独立阶段推进 Workflow，不混入跟进写入 | ✅ suggestion MOVE server trigger、阶段 resolver 和 move command 规划；待真实联调 |
| O07 | 只是描述阶段 | 不自动修改阶段 |
| O08 | 提交时状态已变化 | 静默忽略，不覆盖、不重复执行、不提示 stale 错误 | ✅ suggestion planner/executor stale guard；待竞态集成验收 |
| O09 | 商机创建失败 | 跟进和 PostCommit 不回滚 |
| O10 | 页面表单活动 | 不生成商机建议任务 |
| O11 | Agent 低分活动 | 不生成商机建议任务 |
| O12 | 建议任务失败 | 只重试建议，不修改活动 |

## 10. 删除

| ID | 场景 | 期望 |
|---|---|---|
| D01 | 删除未处理页面活动 | AIJob SKIPPED |
| D02 | 删除正在处理活动 | 最终化事务不写回 |
| D03 | 删除已完成活动 | 未完成三类任务静默 SKIPPED |
| D04 | 重复删除请求 | 不产生重复副作用 |
| D05 | 删除后 Worker 重启 | 不恢复业务执行 |

## 11. 旧入口删除

以下公共接口必须返回 404/405，生产代码不得保留转发：

```text
PUT /v1/customer-activities/{activity_id}
PATCH /v1/customer-activities/{activity_id}/next-time
POST /v1/customer-activities/{activity_id}/process
POST /v1/customer-activities/{activity_id}/evaluate
```

静态门禁：

```bash
grep -R "trigger_processing" CRM-Server/app
grep -R "trigger_evaluation" CRM-Server/app
grep -R "post_commit_mode" CRM-Server/app
```

完成后业务运行时代码应为零命中；不再使用的方法和 service 应删除，不留 wrapper。当前仍需完成全量静态检查与发布前回归。

## 12. 迁移与部署

| ID | 场景 | 期望 | 证据/门禁 |
|---|---|---|---|
| M01 | 已完成历史活动 | 内容、整理稿和最终评分不变，不创建 AIJob | 迁移行为测试 + 迁移前后抽样对账 |
| M02 | 未完成历史活动 | 只接管 watermark 前活动，创建唯一 `CUTOVER_MIGRATION` AIJob | processing/effectiveness 状态计数 |
| M03 | 历史 Agent 活动未完成 | 在切换边界重分类并由 canonical AIJob 接管，不二次评分 | 来源重分类计数 |
| M04 | 未最终化活动已有旧 PostCommitJob | 标记 `SKIPPED/REPLACED_BY_ACTIVITY_AI_JOB`，不与 AIJob 双跑 | replaced 计数 |
| M05 | 已最终化活动已有旧 PostCommitJob | 保留任务，交给新 executor 恢复 | preserved 计数 |
| M06 | 活动已删除但任务仍在 | 任务标记 `SKIPPED/SOURCE_ACTIVITY_DELETED`，保留结果/错误证据 | deleted-skipped 计数 |
| M07 | 旧 `RUNNING` lease | 不恢复旧进程任务；由新 Worker 按新 Job 生命周期接管可恢复任务 | Worker recovery 日志 |
| M08 | 固定运行键重复执行 | no-op，watermark、计数和任务数不变化 | `run_key=customer_activity_cutover:122` |
| M09 | 迁移中断后重跑 | 使用同一 watermark 和自然唯一键继续，无重复 Job | SQLite 行为测试 + 真实 dry-run |
| M10 | 旧 `method` 收口 | 客户活动运行时只使用 `activity_kind`；仅保留线索历史边界适配器 | 静态检查 + schema/API 回归 |
| M11 | 结构迁移失败 | 不启动新服务，恢复备份 | 发布阻断 |
| M12 | 放流前业务验收失败 | 恢复数据库与上一完整版本 | 发布阻断 |
| M13 | 放流后出现问题 | 不启动旧 Runtime，默认前向修复 | 发布操作记录 |

迁移证据至少记录：

```text
run_key
cutover watermark
status
active/pending/processing/generating activity counts
agent activity reclassified count
ai jobs created/skipped counts
post-commit replaced/preserved/deleted-skipped counts
```

迁移文件：`CRM-Server/migrations/versions/122_customer_activity_cutover.py`。真实数据库执行前必须完成备份、disposable restore、118→119→120→121→122 顺序校验，以及 worker 重启和中断重跑演练。

## 13. 前端和当前体验非回归

| ID | 场景 | 期望 |
|---|---|---|
| UI01 | 活动列表/详情 | 沿用当前展示，不显示 Job 内部字段 |
| UI02 | 低质量 | 一次只显示一个补充问题 |
| UI03 | 商机建议 | 使用 Agent UI 是/否组件 |
| UI04 | 点击“是” | 页面内嵌表单，不使用旧弹窗 |
| UI05 | interaction 刷新恢复 | 回到原客户选择/补充/商机确认或表单状态 | ✅ WAITING_USER 首次转换和初始恢复前端单测；真实浏览器联调待完成 |
| UI06 | 重复点击 | 后端幂等，只执行一次 |
| UI07 | 活动删除 | 当前体验保持，不额外要求评分处理 |
| UI08 | PostCommit 产生的现有跟进任务 | 行为不回归 |
| UI09 | 客户智能刷新 | 活动成功后继续触发，失败不阻塞活动 |
| UI10 | 普通 Query/其他 Workflow | 不受本次活动改造影响 |

当前前端已有通用 Agent UI choice/form/interaction 能力；后端已新增商机建议任务到 `AgentAsyncOperation` 的 authoritative snapshot 投影，并以 `WAITING_USER` + `continuation_kind` 表达后续动作。前端已补齐 `WAITING_USER` 首次转换/初始恢复后的消息刷新，以及商机建议 operation 标题映射，并有 6 个确定性前端回归用例；真实浏览器、Worker、CRM API 和重复点击全链路验收仍待完成。

### 13.1 当前前端确定性验证证据

```text
CRM-Client/src/composables/__tests__/useAgentAsyncOperations.test.ts：3 passed
CRM-Client/src/components/agent/__tests__/agentAsyncOperations.test.ts：1 passed
CRM-Client/src/components/agent-ui/__tests__/AgentUIInteractionBlock.test.ts：2 passed
npm run type-check：通过
本轮触及文件 ESLint：通过
```

以上不替代真实 Agent UI 浏览器联调和发布环境验收。

## 14. 真实模型 Golden Cases

建议最小语料：

| 类型 | 数量 |
|---|---:|
| 高质量跟进 | 20 |
| 低质量跟进 | 20 |
| 55～65 临界样例 | 20 |
| 缺下一步行动 | 15 |
| 模糊行动 | 15 |
| 明确暂无下一步 | 10 |
| 动作无时间 | 10 |
| 明确时间表达 | 15 |
| 明确新商机 | 15 |
| 高置信度已有商机 | 15 |
| 商机证据不足 | 15 |
| 描述阶段但未授权推进 | 10 |
| 明确推进 | 10 |
| 客户名歧义 | 15 |
| 会议纪要 | 15 |

每条固定：

```text
expected_quality_gate
expected_next_action_gate
expected_customer_resolution
expected_opportunity_decision
must_not_do
```

不要求模型每次输出完全相同分数，验收门禁、问题类型和允许/禁止动作。

## 15. 最小真实链路验收

发布前至少跑通：

1. Agent 高质量跟进成功；
2. Agent 低质量不写入；
3. 补充后成功；
4. 补充后仍低分；
5. 缺下一步行动追问；
6. 明确暂无下一步成功；
7. 有动作无时间且不猜日期；
8. 客户唯一匹配并跨轮复用；
9. 客户多候选选择；
10. 客户不存在且不自动创建；
11. Agent 重复确认不重复写；
12. 页面创建 AIJob；
13. 页面 AIJob 成功最终化；
14. 页面低分仍保留并执行 PostCommit；
15. Worker 中断后恢复；
16. 删除活动后三类任务 SKIPPED；
17. 新商机显示是/否与内嵌表单；
18. 已有商机高置信度静默忽略；
19. 商机失败不影响跟进；
20. 迁移脚本重复执行不产生重复任务。

## 16. 当前执行证据

截至 2026-09-02：

- T12-T14 定向测试：29 passed；
- T16 页面表单/API/投影定向测试：9 passed；
- T17 删除任务证据及相关回归测试：60 passed；
- 本轮 parity + 相关 Agent contract/guardrails 回归：180 passed（使用 `PYTHONPATH=. uv run pytest --no-cov`）；
- T15 Agent finalized 合同/工具/写入回归：78 passed，其中低于 60 分或无效评分拒绝写入；
- `CRM-Server/app` 与 `tests` 编译检查：通过；
- 本轮新增商机建议模块 4 个文件 Ruff 与格式检查：通过；
- 前端 WAITING_USER/title/UI interaction 回归：6 passed；`npm run type-check`：通过；本轮触及文件 ESLint：通过；
- `git diff --check`：通过；
- CRM-Server 全量 `tests/unit`：1832 passed，21 failed，20 skipped；失败集中在既有业务/环境测试，不纳入 parity 专项通过判定；
- migration 120 已落地：删除活动不再级联删除 PostCommitJob 任务证据；未完成 AIJob/PostCommitJob 在删除事务中统一标记为 `SKIPPED`，原因是 `SOURCE_ACTIVITY_DELETED`。

Agent 评分门禁专项和旧入口发布门禁已完成；T20 migration 122 的 SQLite 行为测试已完成，但真实 Alembic upgrade、生产 dry-run、商机流程和全链路真实模型验收仍未完成。

## 17. 发布阻断

P0 阻断包括：

- Agent 活动仍创建 AIJob 或触发旧处理服务；
- 低分/缺行动仍写入；
- 页面保存时提前创建 PostCommitJob；
- 内容和评分分步提交；
- 重放产生重复活动或任务；
- 删除后任务重试或任务证据被级联删除；
- 商机失败影响活动；
- 旧 process/evaluate/update/sync 入口仍存在；
- Worker 重启和迁移重跑不幂等。

P1 阻断包括：

- 刷新无法恢复交互；
- 补充轮次重复搜索客户；
- 商机建议强迫用户选择；
- 页面低分活动被删除或标成技术失败；
- 旧 PostCommit 无法安全恢复。

## 18. 测试文件调整建议

重写或替换：

```text
tests/unit/test_agent_create_customer_activity_async.py
→ tests/unit/test_agent_create_customer_activity_final_write.py
```

重构：

```text
tests/unit/test_customer_activity_ai_workflow.py
```

使其验证计算与持久化分离。

扩展：

```text
tests/unit/test_customer_activity_write_service.py
```

覆盖三个明确写入入口。

建议新增：

```text
tests/unit/test_customer_activity_ai_job_service.py
tests/unit/test_customer_activity_ai_job_recovery.py
tests/unit/test_customer_activity_pipeline_migration.py
tests/unit/test_agent_follow_up_quality_workflow.py
tests/unit/test_agent_follow_up_next_action_gate.py
tests/unit/test_customer_opportunity_suggestion_job.py
tests/unit/test_customer_activity_removed_endpoints.py
```

前端建议新增：

```text
Agent 商机是/否 interaction
Agent 内嵌商机表单
interaction 刷新恢复
重复提交与取消
```
