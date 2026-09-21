# 业务旅程统一下钻上下文与面包屑设计

- 日期：2026-09-21
- 状态：待评审
- 范围：业务旅程详情内的合同、回款计划、回款记录下钻；面包屑、返回、关闭、焦点与刷新语义
- 非范围：不修改后端 API、权限、业务旅程列表/看板、合同/回款写操作、审批规则或通用 Sheet 视觉

## 1. 问题

当前 `DealJourneyDetailHost` 通过多个嵌套 Sheet 打开合同、回款计划和回款记录：

```text
DealJourneyDetailSheet
  └─ DealJourneyDetailHost
       ├─ DealJourneyDetailContent
       ├─ ContractDetailSheet
       ├─ PaymentPlanDetailSheet
       └─ PaymentRecordDetailSheet
```

这会产生两个问题：

1. `ContractDetailSheet` 不知道父级业务旅程，无法显示正确面包屑。
2. 各子 Sheet 分别管理层级、关闭和焦点，合同 → 回款计划 → 回款记录无法形成连续、可跳转的上下文链。

`ContractDetailContent`、`OpportunityDetailContent` 和 `DealJourneyDetailContent` 内置的旧面包屑只支持固定文案「客户详情 > 当前对象」，不能表达「业务旅程 > 合同 > 回款计划」，因此不能直接重新启用。

## 2. 决策

采用单个 Sheet 内的统一详情上下文：

```text
DealJourneyDetailSheet
  └─ DealJourneyDetailHost
       └─ DetailContextHost
            ├─ DealJourneyDetailContent
            ├─ ContractDetailContent
            ├─ PaymentPlanDetailContent
            └─ PaymentRecordDetailContent
```

`DealJourneyDetailHost` 成为业务旅程子树唯一的导航与业务编排所有者。合同、回款计划和回款记录不再打开新的 Sheet，而是在当前 Sheet 的内容区域切换。

复用现有：

- `useDetailContextStack`
- `DetailContextHost`
- `DetailContextHeader`
- 各现有 DetailContent
- 现有合同/回款 API、确认、审批、刷新和错误处理

不新增第二套面包屑组件或导航状态。

## 3. 上下文模型

### 3.1 Host 输入

```ts
interface Props {
  customerId: string
  customerName?: string
  journeyId: string
  journeyName?: string
  journey?: DealJourney | null
  embedded?: boolean
  canEditCustomerContext?: boolean | null
  contextPrefix?: readonly DetailContextNode[]
}
```

- 独立业务旅程 Sheet：`contextPrefix=[]`。
- 客户详情中的业务旅程：`contextPrefix=[customerNode]`。
- `journeyName` 由列表/看板当前行提供；缺失时使用 `journey?.name`，最后回退为「业务旅程」。

### 3.2 内部栈与显示节点

Host 内部 `useDetailContextStack` 只保存业务旅程子树：

```text
journey → contract → payment-plan → payment-record
```

`contextPrefix` 不进入内部栈。Header 展示节点为：

```ts
const displayNodes = computed(() => [
  ...contextPrefix,
  ...detailContextStack.nodes.value,
])
```

这样点击客户前缀时由外层页面处理，不会让 Host 进入无法渲染的 `customer` 节点。

### 3.3 节点标签

```text
journey        label = journeyName || journey.name || 业务旅程
contract       label = contract_name || 合同详情
payment-plan   label = plan_number || stage_name || 回款计划详情
payment-record label = record_number || 回款记录 #<id>
```

完整路径示例：

```text
华东续约旅程 > 年度服务合同
华东续约旅程 > 年度服务合同 > PAY-2026-001
华东续约旅程 > 年度服务合同 > PAY-2026-001 > 回款记录 #51
```

客户详情嵌入时：

```text
示例客户 > 华东续约旅程 > 年度服务合同
```

## 4. 渲染规则

`DealJourneyDetailHost` 始终渲染一个 `DetailContextHost`。视觉上始终只有一个当前内容；为保留父级状态，旅程根内容保持挂载并在子层隐藏：

| current.type | 内容组件 | 挂载规则 | 关键 props |
|---|---|---|---|
| `journey` | `DealJourneyDetailContent` | 始终挂载；根层显示、子层 `v-show=false` | `embedded`, `showBreadcrumb=false` |
| `contract` | `ContractDetailContent` | 当前节点为 contract 时挂载 | `embedded`, `showBreadcrumb=false` |
| `payment-plan` | `PaymentPlanDetailContent` | 当前节点为 payment-plan 时挂载 | `embedded`, `visible=true` |
| `payment-record` | `PaymentRecordDetailContent` | 当前节点为 payment-record 时挂载 | `embedded`, `visible=true` |

- 各内容组件继续负责自身数据和业务动作。
- `DetailContextHost` 只负责面包屑、返回、关闭和内容承载。
- 所有内容组件的旧固定面包屑保持关闭，防止双面包屑。
- 原 `ContractDetailSheet`、`PaymentPlanDetailSheet`、`PaymentRecordDetailSheet` 保留给其他页面使用，但 `DealJourneyDetailHost` 不再导入或渲染它们。
- Context Header 与内容 Header 同时存在：前者表达路径，后者表达当前对象状态、金额和摘要。

### 4.1 Header 显示

```ts
const showContextHeader = computed(() =>
  contextPrefix.length > 0 || detailContextStack.depth.value > 1
)
const canGoBack = computed(() => showContextHeader.value)
```

- 独立 Sheet 停留在旅程根节点时：隐藏 Context Header，保留现有旅程标题区和 Sheet 自带关闭按钮。
- 进入合同、回款计划或回款记录时：显示 Context Header。
- 客户详情嵌入时：存在 customer 前缀，因此旅程根节点也显示 `客户 > 业务旅程`，并显示可返回客户根的左箭头。

`DetailContextHost` 增加向后兼容的可选 prop：

```ts
showHeader?: boolean // default true
```

`showHeader=false` 只隐藏 Header，不替换 Host 或 body，避免根内容重挂载。

### 4.2 根旅程保活

`DealJourneyDetailContent` 在 Host 生命周期内只创建一次。进入子详情时使用 `v-show` 或等效方式隐藏根内容，返回后恢复同一实例，以保留：

- 滚动位置
- Accordion 展开状态
- 已加载数据
- 业务操作中的局部 UI 状态

子内容按当前节点挂载和卸载。

## 5. 进入下一级

### 5.1 旅程 → 合同

`DealJourneyDetailContent` 的事件从只传 ID 调整为传完整现有摘要：

```ts
'view-contract': [contract: ContractListResponse]
```

Host 使用 `contract.id` 和 `contract.contract_name` 创建节点，不为面包屑增加额外请求。

### 5.2 旅程/合同 → 回款计划

Host 收到 `PaymentPlanResponse` 后：

1. 根据 `plan.contract_id` 和 `plan.contract_name` 确保正确的合同节点在当前路径中。
2. push 回款计划节点。

即使用户从旅程内容直接点击回款计划，路径仍为：

```text
业务旅程 > 合同 > 回款计划
```

### 5.3 回款计划 → 回款记录

记录节点使用可用的 `record_number`；缺失时使用 `回款记录 #<id>`。`record-click` 和 `view-approval` 都进入同一 payment-record 节点。

### 5.4 回款计划 → 合同

- 目标合同已在前级路径：截断回该合同节点。
- 目标为另一合同：截断到 journey 后 push 新合同节点。
- 路径中不得出现同一对象的重复节点。

## 6. 返回、跳转与焦点

### 6.1 Header index 映射与返回

`DetailContextHeader.navigate(index)` 的 index 基于 `displayNodes`：

```ts
if (index < contextPrefix.length) {
  emit('view-customer', contextPrefix[index].id)
  return
}

const internalIndex = index - contextPrefix.length
truncateInternalStack(internalIndex)
```

左箭头行为：

```ts
if (detailContextStack.depth.value > 1) {
  popInternalNode()
} else if (contextPrefix.length > 0) {
  emit('view-customer', contextPrefix.at(-1)?.id ?? customerId)
}
```

独立 Sheet 根层没有 Header，因此不存在无父级的 back 操作。从合同返回旅程时恢复同一旅程内容实例。

### 6.2 客户前缀

点击 `contextPrefix` 中的客户节点或在带前缀的旅程根点击返回时，Host 发出：

```ts
'view-customer': [customerId: string]
```

- 独立业务旅程页：关闭旅程 Sheet，打开现有 `CustomerDetailSheet`。
- CustomerDetailSheet 嵌入场景：重置到客户根内容，不关闭 CustomerDetailSheet。

### 6.3 焦点

进入下一级前记录 `document.activeElement`，与新节点关联。

- pop 一层：恢复被移除节点对应的触发元素。
- 点击祖先 crumb：恢复目标之后第一个被移除节点的触发元素。
- 触发元素已不存在：聚焦 Context Header 返回按钮；仍无按钮时聚焦当前内容根。

为此允许对共享组件做向后兼容扩展：

```ts
DetailContextHeader.focusBackButton(): void
DetailContextHost.focusBackButton(): void
```

现有调用方不使用该方法时行为不变。

## 7. 关闭语义

- Context Header 关闭按钮和外层 Sheet 关闭都发出 Host 的 `close`。
- 独立业务旅程页：`close` 关闭整个 `DealJourneyDetailSheet`，外层页面恢复原表格行/看板卡片焦点。
- CustomerDetailSheet 嵌入场景：`close` 沿用现有行为，关闭整个 CustomerDetailSheet。
- 关闭不等于返回；返回只通过左箭头或面包屑。

## 8. 业务动作与刷新

现有业务策略保持不变：

- 合同创建/编辑/删除/提交/撤回审批
- 合同详情审批刷新
- 回款计划与回款记录下钻
- 回款记录编辑/重新提交后的权威详情刷新
- 子动作成功后刷新旅程内容并 emit `refresh`
- 刷新失败保留当前详情与错误反馈

事件由 Host 直接承接：

- `ContractDetailContent`: `refresh`, `approve`, `reject`, `view-payment-plan`
- `PaymentPlanDetailContent`: `refresh`, `record-click`, `view-approval`, `view-contract`, `view-customer`
- `PaymentRecordDetailContent`: `refresh`, `edit`, `resubmit`

异步请求继续使用现有 identity/request guards，旧响应不得覆盖新节点选择。

## 9. CustomerDetailSheet 集成

客户详情已有外部 `DetailContextHost`。为避免双 Header：

- `selectedJourneyId !== null` 时，不再用 CustomerDetailSheet 的外部 `DetailContextHost` 包裹业务旅程。
- 直接渲染 `DealJourneyDetailHost`，并传入当前客户节点作为 `contextPrefix`。
- Host 的 `view-customer` 在目标为当前客户时重置到客户根；其他客户继续向外 emit。
- Host 的 `close` 继续映射到 CustomerDetailSheet 的整体关闭。
- CustomerDetailSheet 的直接合同、回款计划和回款记录入口继续使用原有外部上下文栈，不迁移到 Host。

这样业务旅程子树只有一个上下文所有者，同时不影响客户页直接查看合同的既有路径。

## 10. BusinessJourneys 集成

页面选择状态增加：

```ts
const selectedJourneyName = ref<string | undefined>()
```

- 表格从 `BusinessJourneyListItem.name` 取得。
- 看板从 `BusinessJourneyBoardCard.journey_name` 取得。
- 通过 `DealJourneyDetailSheet → DealJourneyDetailHost` 传递。
- 关闭时与其他选择状态一起清理。

不修改 `BusinessJourneyTableView` / `BusinessJourneyBoardView` 的公共 row-click payload；名称由页面从当前列表或看板数据解析。

`DealJourneyDetailSheet` 增加可选 `journeyName` prop。

## 11. 错误与边界

- 无合同名称：使用「合同详情」。
- 无计划编号：使用 `stage_name`；仍缺失则「回款计划详情」。
- 无记录编号：使用 `回款记录 #<id>`。
- 当前子对象被删除：pop 到最近有效上层并提示。
- `journeyId` 或 `contextPrefix` 变化：重置内部栈、焦点记录和所有子选择状态。
- 上下文栈最大深度继续使用 `useDetailContextStack` 默认上限 5。
- 长名称沿用 `DetailContextHeader` 现有省略显示和完整 `aria-label`。

## 12. 文件边界

主要修改：

- `CRM-Client/src/components/business-journey/DealJourneyDetailHost.vue`
- `CRM-Client/src/views/DealJourneyDetailSheet.vue`
- `CRM-Client/src/views/BusinessJourneys.vue`
- `CRM-Client/src/views/CustomerDetailSheet.vue`
- `CRM-Client/src/components/panels/DealJourneyDetailContent.vue`
- `CRM-Client/src/components/crmwolf/DetailContextHost.vue`
- `CRM-Client/src/components/crmwolf/DetailContextHeader.vue`
- 相关 focused tests

复用且不改业务逻辑：

- `useDetailContextStack.ts`
- `ContractDetailContent.vue`
- `PaymentPlanDetailContent.vue`
- `PaymentRecordDetailContent.vue`

不修改：

- 后端 API / schema / 权限
- 通用 Sheet 外观与层级 token
- 业务旅程表格/看板查询和保存视图

## 13. 测试与验收

### 13.1 Host 行为

1. 根层只存在一份 `DealJourneyDetailContent`。
2. 打开合同后不渲染 `ContractDetailSheet`，而是在同一 Host 内渲染 `ContractDetailContent`。
3. 路径为 `旅程名称 > 合同名称`。
4. 合同 → 回款计划 → 回款记录逐级 push。
5. 直接从旅程打开回款计划时自动补合同节点。
6. 左箭头和任意 crumb 正确截断并恢复焦点。
7. 返回旅程后根内容实例、滚动和展开状态保留。
8. 子动作刷新、审批、编辑和 stale guard 保持。
9. 任意层级只有一个 Sheet portal。

### 13.2 页面集成

1. 表格和看板进入的旅程根名称正确。
2. CustomerDetailSheet 显示 `客户 > 业务旅程 > ...`，没有双 Context Header。
3. 客户 crumb 返回客户根；关闭按钮关闭整个客户 Sheet。
4. 独立旅程中的查看客户仍打开现有 CustomerDetailSheet。
5. 关闭整个独立 Sheet 后焦点返回原行/卡片。

### 13.3 真实浏览器

验证两条入口：

```text
表格 → 旅程 → 合同 → 回款计划 → 回款记录
看板 → 旅程 → 合同 → 回款计划 → 回款记录
```

检查：

- 左箭头
- 点击任意面包屑
- 关闭
- 长名称省略和可读名称
- 键盘焦点
- 父旅程滚动/展开状态保留
- 单一 Sheet 遮罩和内容容器

## 14. 验收标准

- 业务旅程下钻合同时显示正确的业务旅程上下文面包屑。
- 合同、回款计划、回款记录构成连续可跳转链路。
- 不显示错误的「客户详情 > 合同详情」固定面包屑。
- 不再为旅程子对象叠加新的 Sheet。
- 父旅程状态、业务动作、刷新、权限和焦点行为不回归。
- 客户详情里的业务旅程下钻保留客户前缀，且没有双面包屑。
