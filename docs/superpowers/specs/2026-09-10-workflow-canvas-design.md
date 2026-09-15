# 工作流画布创建能力设计（审批流程管理-新页面内）

- 日期：2026-09-10
- 状态：已确认（用户批准范围、存储、节点集、交互约束）
- 上游：`CRM-Docs/requirements/2026-09-04-crmwolf-activepieces-automation-prd.md`（UI-01/UI-02 方向，本设计为其前端先行切片）
- 关联：`docs/superpowers/specs/2026-09-10-approval-flows-new-design.md`（新页面容器）

## 1. 目标与非目标

### 目标

在 `/settings/approval-flows-new` 页面内提供通用工作流创建能力：

- Vue Flow 画布（拖拽节点、连线、缩放、平移）；
- 五类节点与各自的 shadcn-vue 配置面板；
- CRMWolf 自有 Workflow DSL 持久化（草稿/发布/暂停状态）；
- 团队隔离、细粒度权限、基础图校验。

用户可自由搭建任意测试工作流（例如商机审批工作流），不预置具体业务 Flow。

### 非目标（本阶段明确不做）

- 执行引擎、Activepieces 同步（AP-03 Adapter）、事件投递（CRM-02/CRM-03）；
- 运行历史真实数据（展示位仍为"暂未接入"）；
- 模板中心、版本 diff/回滚、undo/redo、复制粘贴、自动布局；
- 表达式条件引擎（条件分支仅字段+操作符+值）；
- 子流程、多触发器编排。

## 2. 方案选择

- 位置：编辑器放在"审批流程管理（新）"页面（用户决策），不新建独立自动化模块。
- 存储：新 DSL 存储（用户决策），不投影为传统 ApprovalFlow；`schema_version` 为 AP-03 预留。
- 节点集：扩展集五节点（用户决策）。

## 3. 数据模型

### 新表 `crm_workflows`（Alembic migration 131）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BigInteger PK autoincrement | 主键 |
| team_id | BigInteger, index | 团队隔离；NULL=系统级 |
| name | String(100) not null | 工作流名称 |
| description | Text null | 描述 |
| status | String(20) not null default 'draft' | draft / published / paused |
| dsl | JSON（sqlite 变体 Text） | CRMWolf Workflow DSL 完整图 |
| created_by | BigInteger null | 创建人 |
| created_time | DateTime default business_now | |
| last_modified_time | DateTime onupdate business_now | 兼作乐观锁版本 |

索引：`team_id`、`status`。

### Workflow DSL（schema_version 1）

```jsonc
{
  "schema_version": 1,
  "nodes": [
    {
      "id": "n1",                          // 前端生成，图内唯一
      "type": "trigger.opportunity_stage_changed",
      "position": { "x": 100, "y": 200 },
      "config": { "from_stage": null, "to_stage": "QUOTE" }
    }
  ],
  "edges": [ { "id": "e1", "source": "n1", "target": "n2" } ]
}
```

约束：

- `nodes[].id` 图内唯一；`type` 必须在服务端已知注册表内；
- `edges` 的 source/target 必须指向存在节点；无自环；目标不得为 trigger 类型；
- trigger 类型节点全图至多 1 个。

服务端仅做结构与类型注册表校验，不校验业务配置语义（首版）。

## 4. API

新建 `CRM-Server/app/api/workflows.py`，Pydantic schema 边界（`app/schemas/workflow.py`）：

```text
GET    /v1/workflows                  列表（当前团队；字段投影，不含全量 DSL）
POST   /v1/workflows                  创建（name/description/dsl）
GET    /v1/workflows/{id}             详情（含 DSL）
PUT    /v1/workflows/{id}             更新（name/description/dsl；带 expected_last_modified_time 乐观锁）
DELETE /v1/workflows/{id}             删除（仅 draft 可删）
PUT    /v1/workflows/{id}/status      状态流转 draft→published、published→paused、paused→published
```

规则：

- team 隔离：所有读写按当前用户团队过滤；不允许跨团队访问（404）；
- 乐观锁：PUT 携带 `expected_last_modified_time`，不匹配返回 409；
- DELETE 仅 draft；published/paused 拒绝（409）；
- 状态流转非法迁移返回 422；
- DSL 校验失败返回 422 + 字段级错误。

### 权限

注册权限 code（权限种子同步）：

- `automation:read` — 列表/详情；
- `automation:create` — 创建；
- `automation:edit` — 更新/删除草稿；
- `automation:publish` — 状态流转。

沿用现有权限校验模式；导航入口要求 read 或 create。

## 5. 前端结构

### 依赖

新增 `@vue-flow/core`、`@vue-flow/background`、`@vue-flow/controls`。不引入其余 vue-flow 生态包。

### 页面变化

`/settings/approval-flows-new` 页头操作区：

```text
[手动创建]    ← 保留：传统审批流（ApprovalFlowFormDialog）
[新建工作流]  ← 新增：打开空白画布编辑器
```

列表区新增工作流区块，与审批流列表并列：名称、状态徽标（draft 草稿/published 已发布/paused 已暂停）、节点数（DSL nodes 长度）、最近运行（暂未接入）。工作流卡片操作：编辑（打开画布）、发布/暂停、删除（草稿）。

### 组件结构

```text
components/workflow/
  WorkflowEditor.vue            # 画布容器：VueFlow + 工具栏（保存/名称/校验状态）
  WorkflowNodePalette.vue       # 左侧节点面板，拖拽添加
  WorkflowNode.vue              # 自定义节点渲染：类型徽标+名称+配置摘要
  nodeConfigPanels/
    TriggerOpportunityStagePanel.vue
    ApprovalNodePanel.vue
    ConditionBranchPanel.vue
    ActionCreateFollowUpTaskPanel.vue
    ActionNotifyPanel.vue
  workflowNodeRegistry.ts       # type → { label, icon, configPanel, defaults, configSchema }
  workflowValidation.ts         # 图校验：触发器唯一、可达性、config 必填
  api/workflow.ts               # 前端 API 客户端（request 封装 + 类型）
```

点击节点 → 右侧 Sheet 打开对应 configPanel；配置写入节点 `config`。

### 节点注册表（扩展集 5 节点）

| 节点 | type key | 关键配置 | 必填 |
|---|---|---|---|
| 触发：商机阶段变化 | `trigger.opportunity_stage_changed` | 原阶段（可空=任意）、目标阶段 | 目标阶段 |
| 审批节点 | `approval.step` | 节点名称、审批角色 | 名称、角色 |
| 条件分支 | `control.condition` | 字段、操作符(eq/neq/gt/lt/in)、值 | 三者 |
| 动作：创建跟进任务 | `action.create_follow_up_task` | 任务标题、负责人策略、截止偏移天数 | 标题 |
| 动作：通知 | `action.notify` | 通知对象（负责人/角色/指定用户）、消息模板 | 通知对象 |

选项数据源：阶段来自现有 `opportunity_stages` API；角色来自现有角色 API。

### 交互约束

- 拖拽添加/移动节点、连线、删除节点与边；
- trigger 节点全图至多 1 个，达到上限后 palette 中该类置灰；
- 连线校验：目标不得为 trigger、无自环；
- 保存 = 整图 PUT（乐观锁，409 时提示刷新重试）；
- 无 undo/redo、复制粘贴、自动布局。

### 保存前校验（workflowValidation.ts）

1. 名称非空 ≤100 字符；
2. 恰好 1 个 trigger 节点；
3. 从 trigger 可达所有非孤立节点（图遍历）；
4. 每个节点 config 必填项通过。

失败 → 阻止保存，画布上标注问题节点（红色边框 + 原因 tooltip）。

## 6. 错误处理

- 前端统一 `handleApiError`；
- 409 乐观锁冲突：提示"工作流已被他人修改，请刷新后重试"，提供重新加载操作；
- 422 校验错误：展示字段级错误到对应 configPanel 或画布节点；
- 保存中禁用保存按钮，防重复提交。

## 7. 测试策略

### 后端（pytest）

- CRUD：创建/读取/更新/删除往返；
- 状态流转：合法迁移通过、非法迁移 422；
- 删除限制：published 删除 409；
- 乐观锁：过期 expected_last_modified_time → 409；
- team 隔离：跨团队读写 404；
- 权限：无对应 code 拒绝；
- DSL 校验：未知 type、重复节点 id、悬空边、自环、双 trigger、目标为 trigger → 422。

### 前端（Vitest）

- registry：类型注册完整、defaults 结构、trigger 唯一标记；
- workflowValidation：无 trigger/多 trigger/不可达节点/缺必填 config 各失败路径 + 合法图通过；
- WorkflowEditor（mock API）：挂载、加载既有 DSL、拖入节点、连线、保存 payload 形状、校验失败阻止保存。

### 手动冒烟

创建 → 拖 5 类节点 → 连线 → 配置 → 保存 → 重新打开，DSL 完整往返；发布/暂停/删除（草稿）。

## 8. 交付边界

本设计交付"能自由创建工作流"的完整闭环（画布+配置+持久化+状态），执行链路（CRM-01/CRM-02/AP-03）在后续阶段按 PRD 任务表推进，本设计的 `schema_version` 与 DSL 结构为其预留稳定边界。
