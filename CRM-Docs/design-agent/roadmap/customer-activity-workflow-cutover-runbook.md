# 客户活动 Workflow Cutover Runbook

- **日期：**2026-09-02
- **适用迁移：**`122_customer_activity_cutover`
- **状态：**代码、SQLite 行为测试和本地 MySQL `117 → 122` 升级/幂等重跑已完成；disposable/生产 dry-run、备份恢复和发布演练完成前不得宣称上线完成。

## 1. 迁移目的

把切换时仍未完成的客户跟进记录/会议纪要交给统一 durable `CustomerActivityAIJob`，同时处理旧 PostCommitJob 的竞态和孤儿任务。已完成历史活动不重新整理、不重新评分、不改变最终评分。

## 2. 运行前检查

1. 备份数据库，并确认可以在 disposable 数据库恢复。
2. 确认 118、119、120、121 已按顺序成功，当前 head 为 122。
3. 停止旧的客户活动进程内 task / graph 恢复器，避免旧路径与切换同时消费。
4. 确认新的 AIJob recovery worker 已部署但可观测。
5. 记录切换前活动、AIJob、PostCommitJob 数量，作为对账基线。

## 3. 执行

```bash
cd CRM-Server
PYTHONPATH=. uv run alembic check
PYTHONPATH=. uv run alembic heads
PYTHONPATH=. uv run alembic upgrade head
```

本地 MySQL 已于 2026-09-02 实跑通过：`117 → 118 → 119 → 120 → 121 → 122`；再次执行 `alembic upgrade head` 为 no-op。注意：当前仓库存在迁移范围外的历史 schema/index 漂移，`alembic check` 会报告这些全量差异；该结果不能替代 migration 122 的升级结果，也不能直接作为本轮失败证据。

迁移会创建 `crm_customer_activity_cutover_runs`，并以固定运行键 `customer_activity_cutover:122` 记录第一次运行的 watermark 和计数。不要手工修改 watermark 或删除证据行。

## 4. 接管规则

- 目标活动：`created_time <= cutover_watermark` 且 processing 为 `PENDING/PROCESSING`，或 effectiveness 为 `PENDING/GENERATING`。
- 每个活动修订只允许一个 AIJob，自然键为 `team_id + activity_id + activity_revision + job_type`。
- 历史 Agent 未完成活动切换为 `CUTOVER_MIGRATION`，避免旧 Agent 双重评分。
- 已完成活动完全保留。
- 未完成旧 PostCommitJob 标记 `SKIPPED/REPLACED_BY_ACTIVITY_AI_JOB`；已最终化的保留恢复；源活动不存在的标记 `SKIPPED/SOURCE_ACTIVITY_DELETED`。
- 不恢复旧进程内 task 或旧 Agent checkpoint。

## 5. 中断、重跑和对账

- DML 在支持事务的数据库中与 Alembic 迁移保持同一事务；失败时按部署平台事务语义处理，不以“服务已启动”代替迁移成功。
- 证据仍为 `RUNNING` 时可重跑；固定自然键保证不重复创建 AIJob。
- 证据为 `COMPLETED` 时重跑为 no-op，watermark、计数和任务数不变化。
- 对账至少验证：活动最终状态、AIJob 数量/自然键唯一、PostCommitJob 三类处理计数、孤儿任务数、worker recovery 可见。
- 本地 MySQL 已验证固定证据行 `customer_activity_cutover:122` 为 `COMPLETED`，接管 21 条活动并创建 21 个 AIJob；重跑未产生重复证据或重复 AIJob。
- 任何计数不一致、重复 Job、旧 worker 仍消费或 JSON/时间字段不兼容，均阻断发布并恢复备份。

## 6. 迁移后门禁

1. 新 Agent 活动不创建 AIJob。
2. 页面表单活动立即返回并创建一个 AIJob，不提前创建 PostCommitJob。
3. 活动删除后任务只保留证据，不会重试写回。
4. `activity_kind` 为客户活动唯一 canonical 字段；旧 `method` 只在 LeadFollowUp 历史边界转换。
5. 完成 worker 重启、真实模型 Golden Cases、商机独立 Workflow 和前端 Agent UI 联调后，才可关闭 T21。
