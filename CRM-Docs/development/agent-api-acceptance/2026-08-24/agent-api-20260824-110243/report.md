# CRM Agent 新架构 API 验收报告

> 结论：基础 Query、显式客户查询、结构化确认、Workflow 中切换 Query、空结果、取消与幂等可用；页面 selected entity、Entity Action → Workflow、挂起 Workflow 恢复、直接跟进写入与错误投影仍有 P0 缺口。严格结果为 **7 PASS / 4 PARTIAL / 7 FAIL**，尚未达到完整 PRD API 验收或实施收口标准。

## 运行信息

- 日期：2026-08-24
- 批次：`agent-api-20260824-110243`
- 隔离数据：初始 90 条业务记录；AC-06 验收后新增 1 条客户
- 公共链路：`POST /api/v1/agent/chat/stream` + `GET /api/v1/agent/sessions/{id}/messages`
- 原始证据：`events/*.json`、`execution-index.json`、`database-evidence.json`

## 验收矩阵

| 编号 | 状态 | 结论 |
|---|---|---|
| AC-01 | PASS | route=QUERY，返回 20 条上海客户和服务端签发的 Result Set；RootDecision 为 NEW_TASK/IGNORE。 |
| AC-02 | FAIL | Agent 继承上海条件，但说明系统没有“重点客户”内置规则并要求补充标准。 |
| AC-03 | PARTIAL | Session 866 曾真实成功绑定第一项并返回 2026-08-23 跟进；本轮 Session 872 连续两次发生模型服务瞬态失败。 |
| AC-04 | FAIL | route=CLARIFY，reason_code=MISSING_CUSTOMER_CONTEXT；没有读取 Session.context_json 中的 selected_entity_ref。 |
| AC-05 | PASS | route=QUERY，正确返回显式命名客户及负责人“Agent API 验收 110243”。 |
| AC-06 | PASS | confirmation interaction 经 interaction_submission 恢复并创建客户；数据库仅 1 条，customer id=203，城市上海。 |
| AC-07 | PASS | 待确认创建杭州客户时输入上海查询，route=QUERY，task_relation=SWITCH_TASK，active_workflow=SUSPEND，返回 21 条上海客户。 |
| AC-08 | FAIL | RootDecision 为 WORKFLOW/RESUME，但 Workflow 未恢复原创建杭州客户确认上下文，反而要求说明任务操作；UI 还投影为 INTERNAL_ERROR。 |
| AC-09 | FAIL | Result Set 与 Entity Action 校验后，被转换成普通 TextTurnInput，再次由 Root 分类为 CLARIFY，未进入 Workflow 补字段。 |
| AC-10 | PASS | route=QUERY，entity_list=0，返回“当前权限范围内未找到符合条件的客户”，无系统错误。 |
| AC-11 | FAIL | 没有泄漏 Team 1 客户，但把无权访问结果显示为普通空结果。 |
| AC-12 | FAIL | “介绍一下这个客户”因 MISSING_CUSTOMER_REFERENCE 失败；显式客户名称控制组可正确组合档案、联系人、活动、风险等事实。 |
| AC-13 | PARTIAL | 真实模型瞬态失败时返回可重试错误，未生成虚假业务答案，failure diagnostics 已持久化。 |
| AC-14 | FAIL | Root 正确路由 CREATE_FOLLOW_UP，但 Planner 只认 selected_entity，未从显式客户名称建立权威绑定，返回“需要先明确一个客户”；数据库无新增匹配活动。 |
| AC-15 | PARTIAL | 取消正常；相同 client_request_id 重放返回同一 message_id=2294，未重复写入。字段修改与 Workflow 恢复失败。 |
| AC-16 | PASS | Agent UI/协议定向前端回归 4 files、21 tests 全部通过；TypeScript 类型检查通过。 |
| AC-17 | PASS | IM conversation 定向后端测试通过，验证 IM 复用统一 typed Application 与 agent_ui final 投影。 |
| AC-18 | PARTIAL | 统一 Agent UI 主运行路径未发现旧 SSE 双协议消费；但仓库仍存在 checkpoint_cutover、migration_inventory、message_migration 等一次性迁移设施及 legacy 分类。 |

## 关键阻断

1. Text Agent 未接入页面 `selected_entity_ref`，AC-04/AC-12 原场景失败。
2. Entity Action 在 Application 层被降级为文本，AC-09 无法确定性进入 Workflow。
3. Workflow 的 RESUME 只停留在 RootDecision，未恢复原 checkpoint，AC-08 与 AC-15 修改/恢复失败。
4. Workflow Planner 不能从显式客户名称形成权威实体绑定，AC-14 失败。
5. 缺字段/业务澄清被投影为 `INTERNAL_ERROR`；真实错误的 `trace_id` 仍为空。
6. “重点客户”缺少业务定义，当前实现与 PRD AC-02 冲突。

## 自动化回归

- 后端关键组合：113 passed。
- 后端 Agent 专项：见 `regression-results.json`（本轮重跑）。
- 前端 Agent UI/协议：4 files、21 tests passed。
- 前端 `npm run type-check`：PASS。
- MySQL integration：12 skipped（未显式启用环境变量）。
- Real-model integration：1 skipped（未显式启用环境变量）；公共 HTTP API 验收本身真实调用了当前模型。

## 数据库副作用

- AC-06 创建客户仅 1 条：`API验收-110243-结构确认客户有限公司`。
- AC-14 未新增包含验收跟进内容的客户活动。
- AC-15 取消客户未创建；重复提交复用同一结果消息，无重复副作用。

## 发布判断

当前仅能判定为 **基础链路可用、完整验收未通过**。在上述 P0 缺口关闭并重新执行全套公共 API 验收前，不应宣称架构改造已全面完成，也不应进入生产发布。禁止通过恢复旧 Runtime、fallback、双协议或兼容 adapter 绕过问题。
