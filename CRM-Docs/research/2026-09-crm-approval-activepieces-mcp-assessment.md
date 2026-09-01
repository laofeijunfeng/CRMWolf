# CRMWolf 审批流程接入 Activepieces / MCP 评估

- **评估日期：**2026-09-01
- **范围：**将现有审批流程的配置与编排迁移到 Activepieces，并评估 MCP 在其中的作用。
- **结论：**可行，整体为中高难度；难点不在 MCP，而在审批状态、身份映射、事务提交和存量迁移。

## 一、推荐结论

从第一天开始采用 Activepieces 作为审批工作流的编排运行时是可行的，但不建议让 MCP 直接替代审批 API，也不建议让 Activepieces 直接访问 CRM 数据库。

推荐分工：

- Activepieces：审批 Flow 定义、节点顺序、条件分支、等待、通知、外部动作和运行历史；
- CRMWolf：业务单据、审批决定、审批人解析、权限、审批审计、业务状态变更和最终事务提交；
- MCP：可选的 AI 辅助配置/发现通道，以及受控工具调用协议；不是审批状态机。

## 二、当前 CRMWolf 的迁移基础

当前已有较好的接入 seam：

- `ApprovalFlow`：团队、流程编码、业务类型、金额范围、授权类型、启用状态；
- `ApprovalNode`：节点名称、顺序、审批角色、通知用户、是否必需；
- `Approval`：审批实例、业务类型/业务 ID、当前节点、状态、提交人；
- `ApprovalRecord`：审批操作历史；
- `ApprovalTransactionManager`：业务单据与审批提交的事务边界；
- 通用 `/v1/approvals/{entity_type}/{entity_id}/submit|approve|cancel` 接口；
- `approval_adapter`：不同业务类型在提交、通过、拒绝、撤回时的状态联动。

因此不是从零开发审批，而是要把当前“流程模板配置”和“流程实例执行”的拥有者重新划分。

## 三、必须先做出的状态归属决策

不能让 Activepieces 和 CRMWolf 同时维护同一套“当前审批节点/是否等待/是否完成”的最终真相。应选择以下模式之一。

### 推荐模式：Activepieces 编排，CRMWolf 掌握审批决定

```text
业务单据提交
  → 启动 Activepieces Approval Flow
  → Activepieces 选择条件和节点
  → CRMWolf Piece 创建/更新业务审批任务
  → CRMWolf 解析审批人并记录审批决定
  → CRM 审批中心 approve/reject
  → 回调 Activepieces 恢复 Flow
  → Activepieces 执行后续动作
  → CRMWolf 提交最终业务状态变更
```

语义分工：

- Activepieces 的 Flow Run 是“自动化编排”的真相；
- CRMWolf 的 Approval/ApprovalRecord 是“业务审批决定和审计”的真相；
- `current_node` 等旧字段可以先作为兼容投影，稳定后再评估退休；
- 最终客户、合同、回款、发票和 License 状态仍由 CRMWolf API 事务性更新。

### 不推荐模式

Activepieces 保存一套节点状态，CRMWolf 又保存另一套独立 pending 状态，并互相猜测谁是最新状态。这会导致：

- 重复审批；
- 回调丢失后无法恢复；
- 用户在两个系统看到不同状态；
- 撤回、驳回重提和超时催办逻辑分叉；
- 审计无法回答“谁在什么时候做出了最终决定”。

## 四、当前模型到 Activepieces 的映射

| CRMWolf 当前概念 | Activepieces 侧概念 | 迁移难度 |
|---|---|---|
| `ApprovalFlow.business_type` | Flow 触发器/模板参数 | 低 |
| `min_amount` / `max_amount` | 条件或分支 | 低 |
| `license_type` | 条件或分支 | 低 |
| `ApprovalNode.node_order` | Flow 步骤顺序 | 低 |
| `approve_role` | CRMWolf 审批人解析 Action | 中 |
| `notify_user_ids` | Notification Action | 低 |
| `Approval.status` | CRM 审批结果 + Flow 分支 | 中高 |
| `current_node_id` | Flow 等待位置的业务投影 | 中高 |
| `ApprovalRecord` | CRM 审计记录；可关联 Flow Run | 中 |
| `on_approved` / `on_rejected` | CRMWolf Finalize Approval Action | 高 |
| 单据创建 + 提交审批事务 | Flow 启动与 CRM 事务 API | 高 |

当前审批模型是线性节点模型，而 Activepieces 是更通用的 Flow 模型，因此从表达能力看没有明显障碍；真正复杂的是把原有业务事务和状态联动安全地接到 Flow 的等待/恢复上。

## 五、CRMWolf Piece 的最小接口

第一版不应把所有内部审批 API 暴露给 Activepieces，而应提供几个深的业务动作：

```text
Triggers
- Approval Submitted
- Approval Approved
- Approval Rejected
- Approval Cancelled

Actions
- Start CRM Approval
- Resolve Approvers
- Create Approval Task
- Record Approval Decision
- Finalize Approved Business Object
- Revert Rejected Business Object
- Get Approval Context
```

每个 Action 内部负责：

- 租户和身份映射；
- 权限检查；
- 业务对象解析；
- 审批人解析；
- 幂等；
- 状态转移；
- 事务提交；
- 审计和 trace 关联。

Activepieces Flow 只组合这些动作，不直接拼装内部数据库字段。

## 六、MCP 在这个方案中的正确位置

MCP 适合两类事情：

### 1. AI 辅助配置 Flow

用户可以对 Agent 说：

```text
帮我创建一个回款超过 10 万元时，先由销售总监审批，再由财务审批的流程。
```

Agent 通过受控 MCP 工具创建一个 Activepieces Flow 草稿，然后要求用户在 Builder 中确认和发布。

这时 MCP 负责“自然语言配置入口”，Activepieces 仍负责 Flow 的定义、校验、保存和执行。

### 2. Flow 调用 CRM 能力

Activepieces 可以通过 CRMWolf Piece 或受控 MCP 工具调用：

- 查询业务对象；
- 创建审批；
- 获取审批上下文；
- 记录审批决定；
- 发起 Agent 分析；
- 完成业务状态变更。

对于正式审批动作，优先使用强类型 Piece/API；MCP 作为动态发现和 Agent 场景的补充，不应成为高风险写入的唯一防线。

## 七、难度评估

### POC：中等

只选一个业务类型，例如合同，保留线性两级审批：

```text
合同提交
→ Activepieces Flow
→ 销售总监审批
→ 财务审批
→ CRM 合同状态变更
```

需要完成：

- Activepieces 部署；
- CRMWolf Piece；
- Flow 启动接口；
- 审批人解析；
- CRM 审批中心回调；
- 最终状态提交；
- 重复回调和失败恢复测试。

### 生产迁移：中高难度

主要成本在：

- 合同、回款、发票、License、商机等多业务类型；
- 金额/授权类型/团队等动态匹配；
- 审批撤回、驳回重提、超时催办；
- 旧流程实例兼容；
- 双系统身份和租户映射；
- 业务创建与审批启动之间的事务一致性；
- Activepieces Flow 版本与审批实例版本绑定；
- 审计、重放、回调丢失和重复动作。

## 八、建议的迁移顺序

1. **先做一个只读 Flow 管理 POC：**Activepieces 创建/发布 Flow，CRMWolf 能识别并关联 Flow ID；
2. **接合同两级审批：**不迁移存量实例，只让新提交的合同走新路径；
3. **验证 CRM 审批中心继续可用：**审批人不必立刻迁移到 Activepieces UI；
4. **加入回调、幂等、撤回、驳回重提和超时；**
5. **再迁移其他业务类型；**
6. **最后决定是否废弃 CRMWolf 内置流程配置页和旧 `ApprovalFlow` 写入接口。**

## 九、最终判断

这不是一次简单的“把现有审批页面换成 Activepieces 页面”，而是一次运行时职责迁移。但它不需要重写 CRM 审批业务：当前的通用审批 API、适配器和事务管理器可以作为迁移基础。

最重要的技术决策是：

> **Activepieces 负责可配置的审批 Flow 编排；CRMWolf 负责审批决定、权限、审计和业务状态最终提交；MCP 负责 AI 辅助配置和动态工具发现，而不是负责审批状态机。**
