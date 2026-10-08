# Agent 2.0 跟进绑定业务旅程 TRD

- **版本：**2026-09-29 草案，待审阅；本文不代表功能已实现。
- **范围：**仅恢复“已保存的 2.0 跟进/会议活动 → 绑定进行中的业务旅程并更新最新活动时间”。
- **不在范围：**历史任务自动完成、客户智能、客户档案发布、商机建议、旧 `PostCommitJob` 和旧 Agent。

## 1. 现状

`app/crud/customer_activity.py` 在创建活动时调用 `deal_journey_service.infer_for_customer()`。客户只有一条未完成旅程时，活动写入 `deal_journey_id`。

随后，非 `ASSISTANT_2` 来源会调用 `deal_journey_service.record_event()`，写 `ACTIVITY_ADDED` 事件并更新 `CustomerDealJourney.last_event_at`。2.0 来源目前被显式跳过，所以活动即使已绑定旅程，也不会产生旅程事件，也不会更新最新活动时间。

旧 `CustomerActivityPostCommitWorkflow` 使用 LangGraph，不能作为 2.0 的调用入口。

## 2. 架构边界

调用方向固定为：

`Agent 2.0 活动写入 → 中性活动副作用服务 → deal_journey_service`

约束：

- 中性服务放在客户活动领域，不放在 `app.services.assistant` 或 `app.services.agent`。
- 它只接收 `team_id`、`activity_id`、`expected_activity_revision`。
- 它不接收助手任务、turn、确认卡、提案或模型结果。
- 它不导入 `app.services.assistant` 或 `app.services.agent`。
- `deal_journey_service` 不反向依赖 Agent 2.0。
- 不调用 `CustomerActivityPostCommitWorkflow`、`CustomerActivityPostCommitJobService`、客户智能事件服务或档案发布服务。

因此删除旧 Agent 不会影响这条链路，业务旅程也不会依赖 Agent 2.0。

## 3. 业务规则

活动事务提交前执行：

1. 按 `team_id + activity_id` 读取活动，并校验 `activity_revision`。
2. 活动不存在、已删除或版本不匹配：不写旅程，返回可诊断结果。
3. 客户没有未完成旅程，或有多条未完成旅程：保持 `deal_journey_id = NULL`，不猜测绑定。
4. 恰好一条未完成旅程：写入 `deal_journey_id`。
5. 写一条 `ACTIVITY_ADDED` 旅程事件，来源为 `customer_activity`，`source_id` 为活动 ID。
6. 更新该旅程的 `last_event_at`。
7. 调用 `record_event()` 时传 `enqueue_customer_intelligence=False`，不触发客户智能和档案刷新。

重复保存或事务重试必须复用 `record_event()` 现有的来源幂等：同一旅程、事件类型、来源类型和来源 ID 只保留一条事件。

## 4. 失败语义

- 旅程绑定与活动写入使用同一事务。绑定失败回滚活动，不留下无事件的伪绑定。
- 向量证据写入失败保持现有隔离，不影响活动和旅程事件。
- 不创建旧后台任务，不增加新的恢复队列；事务回滚后由原活动写入重试覆盖。

## 5. 验收

- 客户有一条进行中的旅程：2.0 跟进确认后，活动绑定该旅程，新增一条旅程事件，`last_event_at` 更新。
- 客户没有旅程或有多条未完成旅程：活动仍保存，但不绑定、不产生事件。
- 重复确认不新增第二条旅程事件或第二条活动。
- 不创建 `CustomerActivityPostCommitJob`、客户智能请求、档案发布或旧 Agent 运行记录。
- 静态依赖检查证明新服务和 2.0 调用链不导入 `app.services.agent` 或 LangGraph。

## 6. 待后续总 TRD 决定

以下不在本文件实施：

- 多条未完成旅程时是否询问用户选择。
- 历史跟进任务完成、客户智能、档案发布和商机建议的统一后处理边界。
- 页面活动入口是否迁到这个中性服务。
