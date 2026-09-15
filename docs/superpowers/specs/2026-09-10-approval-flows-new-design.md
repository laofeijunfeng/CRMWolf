# 审批流程管理新页面设计

- 日期：2026-09-10
- 状态：待用户审阅
- 范围：`/settings/approval-flows-new` 独立列表页原型

## 1. 背景与目标

CRMWolf 已建立 `/settings/approval-flows-new` 入口，但当前页面整体复用 `ApprovalFlowSheet.vue`。本阶段先把新入口变成独立的页面容器和列表体验，同时保留现有传统审批流程 API 与表单能力，降低后续接入 Vue Flow、Automation DSL 和 Activepieces 的迁移成本。

本阶段不把传统审批流程误标为 Activepieces 自动化，也不提前引入尚未确定的 DSL 或执行层协议。

## 2. 方案选择

采用“独立列表页，复用现有表单和 API”的方案。

相比同时实现 Vue Flow 编辑器，该方案先稳定页面信息架构、权限边界、列表状态和新建/编辑入口，避免把页面独立化与 DSL、节点 schema、Activepieces Adapter 耦合。相比只做 Vue Flow，该方案保留用户可验证的流程管理闭环。

## 3. 页面与组件边界

新增页面：

```text
CRM-Client/src/views/ApprovalFlowsNew.vue
```

路由保持：

```text
/settings/approval-flows-new
```

页面负责：

- 页面标题、说明和手动创建入口；
- 审批流程列表加载；
- loading、error、empty、success 状态；
- 新建、编辑表单打开状态；
- 启用/停用确认与提交；
- 操作后的列表刷新。

继续复用：

```text
CRM-Client/src/components/system-config/ApprovalFlowFormDialog.vue
```

表单继续负责字段校验、节点编辑、创建和更新提交。新页面不复制这些逻辑。

旧页面 `/settings/approval-flows` 行为不变。

## 4. 数据契约

复用 `CRM-Client/src/api/approvalFlow.ts`：

```text
GET    /v1/approvals/flows
GET    /v1/approvals/flows/{flow_id}
POST   /v1/approvals/flows
PUT    /v1/approvals/flows/{flow_id}
```

页面使用现有 `ApprovalFlowDetail` 类型，不新增平行数据模型。

展示映射：

| 页面字段 | API 字段 | 规则 |
|---|---|---|
| 流程名称 | `flow_name` | 原样展示 |
| 流程编码 | `flow_code` | 次要标识 |
| 业务类型 | `business_type` | 使用现有中文标签 |
| 状态 | `is_active` | `1` 启用，否则停用 |
| 节点数量 | `nodes` | 数组长度 |
| 描述 | `description` | 空值显示“暂无描述” |
| 最近运行状态 | 无 | 显示“暂未接入” |
| Activepieces 同步 | 无 | 显示“暂未接入” |

没有 API 字段时不伪造运行结果、同步结果或更新时间。

## 5. 交互流程

### 新建

```text
手动创建 → 打开表单(create) → 提交 POST → 成功提示 → 关闭 → 刷新列表
```

### 编辑

```text
编辑 → 打开表单(edit + flow-id) → 加载详情 → 提交 PUT → 成功提示 → 关闭 → 刷新列表
```

### 启用/停用

```text
启用或停用 → 确认 → PUT 仅更新 is_active → 成功刷新列表
```

同一条记录操作期间禁止重复提交。失败时保留原列表展示，并通过 `handleApiError` 呈现错误。

## 6. 页面状态与权限

页面状态至少包括：

```ts
const flows = ref<ApprovalFlowDetail[]>([])
const loading = ref(false)
const errorMessage = ref<string | null>(null)
const formOpen = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const editingFlowId = ref<number | null>(null)
const togglingFlowId = ref<number | null>(null)
```

列表由单一 `loadFlows()` 刷新函数管理。表单成功后重新加载，不在前端手动拼接记录。

继续沿用设置模块团队访问控制与权限：

- 查看：`approval:flow:view`
- 新建：`approval:flow:create`
- 编辑、启停：`approval:flow:edit`

## 7. 页面布局与设计规范

页面结构：

```text
页面容器
  ├── Header：标题、说明、手动创建
  ├── 状态提示区
  └── 内容区：加载、错误、空状态或流程卡片列表
```

使用 V2 设计系统、shadcn-vue 语义类和现有组件模式。卡片展示名称、编码、业务类型、启用状态、节点数量、描述、最近运行状态占位和 Activepieces 同步占位，并提供编辑及启停操作。

操作支持键盘焦点、明确按钮名称和操作中禁用状态。窄视口下卡片内容可折叠或纵向排列，页面主体不产生不必要的横向滚动。

## 8. 不在本阶段实现

- Vue Flow 画布；
- Automation DSL 持久化；
- Activepieces Flow 创建、更新或同步；
- 商机阶段变化事件；
- `create_follow_up_task` API；
- Activepieces Webhook 投递；
- 旧审批路由替换；
- 运行历史、重试和审计数据接入。

## 9. 验证策略

实现后验证：

1. 成功加载显示流程名称、业务类型和状态；
2. 空数组显示空状态和创建入口；
3. 请求失败显示错误状态，重新加载会再次请求；
4. 手动创建打开创建表单；
5. 编辑传递正确流程 ID；
6. 启停确认后只提交目标流程的状态字段；
7. 启停失败不改变展示状态；
8. 表单成功后重新加载列表。

建议命令：

```bash
cd CRM-Client
npm run type-check
npm run test:unit -- --run src/settingsNavigation.test.ts src/views/__tests__/ApprovalFlowsNew.test.ts
git diff --check
```

## 10. 自审结果

- 未包含 `TODO`、`TBD` 或未决占位要求；
- “最近运行状态”和“Activepieces 同步状态”明确标记为未接入，不会伪造数据；
- 页面、表单、API 和未来执行层边界一致；
- 本阶段范围足够聚焦，可由一个实现计划交付；
- 未要求替换旧路由，也未隐含 Vue Flow 或 Activepieces 实现；
- 权限、团队隔离和现有 API 复用关系已明确。
