# P2-PKG-01 列表视图状态透明化与渐进披露 TRD

- **文档类型**：TRD（Technical Requirements Document）
- **对应 PRD**：P2-PKG-01 列表视图状态透明化与渐进披露 PRD
- **版本**：v1.0
- **日期**：2026-09-04
- **范围**：非 Agent
- **实施原则**：复用现有 DataTable、筛选、排序、字段配置、自定义视图和错误反馈能力，不新增后端查询能力，不改变现有业务数据范围与权限规则。

---

## 1. 技术结论

本改造包不是重做列表，也不是新增一套“视图系统”。当前 CRMWolf 已经具备本需求所需的基础能力：

- `DataTable.vue` 已统一承载筛选、排序、字段配置、分页、刷新、固定高度、表头固定、内部滚动和移动端 Card；
- `ListFilterPopover.vue` 已支持多条件筛选、条件删除、清空和应用；
- `ListSortPopover.vue` 已支持多字段排序、方向和优先级；
- `ColumnConfigPopover.vue` 已支持显示/隐藏、拖拽排序、个人/团队配置和恢复默认；
- `useCustomFilterViews.ts` 已支持内置 Tab、自定义视图、视图配置持久化及视图管理；
- `DataViewState` 与 `FeedbackError` 已提供统一读取状态和失败反馈语义。

因此技术改造重点应放在**状态投影和交互编排**：

1. 从页面实际生效的 Tab、筛选、排序、最终列配置计算一个统一的 `EffectiveListViewState`；
2. 在 `DataTable` 顶部增加稳定的状态摘要层，而不是把条件只放在 Popover 内；
3. 将低频的排序、字段配置、保存/管理视图等工具收进可发现的“更多设置”，保留搜索、刷新和高频筛选入口；
4. 将筛选、排序、视图切换的请求编排统一为“更新状态 → 回到第 1 页 → 请求列表”；
5. 对自定义视图应用增加 applying、竞态丢弃、旧数据保留、失败回滚和局部重试。

**本 TRD 不建议**让 `DataTable` 直接调用业务列表 API，也不建议立即引入复杂全局 Store。页面继续拥有业务查询参数和分页，`useCustomFilterViews` 负责视图配置和状态快照，`DataTable` 负责展示和事件转发。

---

## 2. 当前系统实现与 PRD 映射

### 2.1 已实现、不得重复建设的能力

| PRD 能力 | 当前实现 | 本次处理 |
| --- | --- | --- |
| 筛选弹层 | `ListFilterPopover.vue` | 保留，增加摘要投影及单项移除事件 |
| 排序弹层 | `ListSortPopover.vue` | 保留，增加摘要投影 |
| 字段配置 | `ColumnConfigPopover.vue` + `viewPreferenceApi` | 保留，增加最终隐藏列数量投影 |
| 自定义视图 | `useCustomFilterViews.ts` + view preference API | 保留，补充应用状态、回滚和竞态控制 |
| 列表刷新/错误 | `DataTable.vue` + `DataViewState` | 保留，视图应用复用 refreshing/error 语义 |
| 分页 | 各列表页面本地 pagination | 保留，条件变化时统一归 1 |
| 固定高度/内部滚动 | `DataTable` 的 `height`、`heightStrategy`、`scrollMode` | 禁止改变 |
| 移动端 Card | `DataTable mobileMode="card"` | 禁止改变 |

### 2.2 PRD 仍缺少的技术承载

| 问题 | 当前表现 | 技术缺口 |
| --- | --- | --- |
| 条件不可持续确认 | 关闭 Popover 后仅能看到按钮上的数量 | 缺少统一摘要模型和展示区域 |
| 摘要与请求不一致 | Tab 固定范围、页面隐式范围不在 `activeFilters` 中 | 缺少“业务范围”和“用户筛选”分层 |
| 视图切换无独立反馈 | `applyCustomViewTab()` 立即改引用并 `void refresh()` | 缺少 applying、请求序列和事务式状态提交 |
| 失败无法恢复 | 失败主要 Toast，activeTab/filters/sorts/columns 已被修改 | 缺少 snapshot、回滚和局部重试 |
| 清除筛选语义不清 | 主要在空状态提供清除入口 | 缺少顶部稳定入口及“只清筛选”的明确语义 |
| 隐藏列不可见 | 字段配置按钮可能显示数量，但顶部没有最终生效摘要 | 缺少有效列配置到摘要的统一计算 |
| 页面行为不一致 | 9 个页面处理重置、Tab、视图更新的代码略有差异 | 缺少统一 helper/约定和验收矩阵 |

---

## 3. 覆盖页面与业务范围约束

首批覆盖以下页面及 `viewKey`：

| 页面 | viewKey | 业务范围注意事项 |
| --- | --- | --- |
| Customers | `customers.list` | Tab 可能代表客户状态/归属范围；不能只用 filters 判断全部范围 |
| CustomerTracking | `customer-tracking.list` | 跟进状态 Tab 与 `status_label` 筛选存在字段剔除逻辑 |
| Leads | `leads.list` | 线索阶段/来源等枚举摘要需显示业务 label |
| Opportunities | `opportunities.list` | Tab 状态可能在 API 参数中生效，同时页面会剔除 `status` 筛选 |
| Contracts | `contracts.list` | Tab 与 `status` 条件存在互斥/剔除规则 |
| PaymentPlans | `payment-plans.list` | 金额、日期、状态摘要需区分格式与单位 |
| PaymentRecords | `payment-records.list` | 回款记录状态和日期筛选需保持查询序列化一致 |
| Invoices | `invoices.list` | 发票状态、开票日期等字段使用 catalog label |
| ApprovalCenter | `approval-center.list` | 内置 Tab 是审批角色/处理状态；没有 `useCustomFilterViews`，不得强行套用自定义视图管理 |

每个页面仍负责：

- 业务 Tab 的固定范围参数；
- API 查询参数拼装；
- 分页与列表请求；
- 不适用筛选字段的剔除；
- 业务动作和权限判断。

`DataTable` 不能推断后端未显式返回的业务范围，也不能为了显示摘要而复制各页面的业务规则。

---

## 4. 总体技术架构

### 4.1 分层职责

```text
页面 View
  ├─ activeTab / activeFilters / activeSorts / activeColumns
  ├─ 业务 Tab 范围解析
  ├─ API 查询参数与 pagination
  └─ fetchList() / retryListLoad()
          │
          ▼
useCustomFilterViews
  ├─ 自定义视图配置读取/保存
  ├─ 视图应用 snapshot
  ├─ applying / request sequence
  ├─ 失败回滚
  └─ 触发页面 refresh
          │
          ▼
DataTable
  ├─ 状态摘要展示
  ├─ 筛选摘要单项移除/清除事件
  ├─ 工具分层展示
  ├─ Popover 复用
  └─ loading / refreshing / error / empty 展示
```

### 4.2 关键原则

1. **单一事实来源**：摘要使用页面传入的最终有效状态，不从 DOM、按钮文字或请求 URL 反向解析。
2. **状态先于请求**：用户操作先形成标准化目标状态，再由页面归一化并发起请求。
3. **请求不可反向污染状态**：旧请求返回时必须丢弃，不能覆盖当前最新视图。
4. **应用失败不破坏上下文**：旧 Tab、旧条件、旧列配置和旧数据保持可见，并提供局部重试。
5. **展示与业务解耦**：DataTable 只消费摘要数据/回调，不知道具体 CRM 业务 API。
6. **渐进披露而非隐藏**：低频工具移入“更多设置”，但入口始终有明确名称、状态数量和键盘路径。

---

## 5. 有效视图状态模型

### 5.1 类型定义

建议在 `CRM-Client/src/components/crmwolf/listViewState.ts` 新增纯类型与计算函数；若团队已有更合适的 `utils` 目录，可放置于该目录，但不要散落在 9 个页面中。

```ts
export type ListViewType = 'built-in' | 'custom'

export interface EffectiveListViewState {
  viewKey: string
  viewType: ListViewType
  viewLabel: string
  scopeLabel?: string
  filters: ListFilterCondition[]
  sorts: ListSortCondition[]
  columns: DataTableColumn[]
  visibleColumnKeys: string[]
  hiddenColumnCount: number
  filterCount: number
  sortCount: number
  isApplying: boolean
  applyError: FeedbackError | null
}
```

摘要项目：

```ts
export interface FilterSummaryItem {
  id: string
  field: string
  fieldLabel: string
  operator: ListFilterOperator
  operatorLabel: string
  valueLabel?: string
  removable: boolean
}

export interface SortSummaryItem {
  id: string
  field: string
  fieldLabel: string
  direction: ListSortDirection
  directionLabel: string
  priority: number
}
```

### 5.2 状态来源和优先级

- `viewType`：由页面/`useCustomFilterViews` 明确传入，不通过 `activeTab` 字符串猜测；
- `viewLabel`：自定义视图取视图名称，内置 Tab 取 Tab label；
- `scopeLabel`：取页面业务范围或固定 Tab 的语义，例如“我的客户”“待审批”，不是简单写“全部”；
- `filters`：取**已生效且经过页面业务规则剔除后的筛选**；
- `sorts`：取实际用于查询的排序条件；
- `columns`：取最终有效列配置，不是 Popover draft；
- `hiddenColumnCount`：只统计可隐藏且最终 `visible !== true` 的业务列，不把 actions、固定识别列、不可隐藏列算入隐藏数量；
- `filterCount`、`sortCount`：以标准化后有效条件计数，不计空值和无效字段。

### 5.3 不把 Tab 伪装成筛选条件

内置 Tab 往往通过额外 API 参数表达范围，不能为了凑数量把它伪造成 `ListFilterCondition`。摘要应分两层：

```text
当前视图：待跟进客户
范围：我的客户
筛选：状态属于“进行中” × 1
排序：跟进时间 ↓
列：已隐藏 2 列
```

如果页面无法给出可靠范围 label，应至少显示内置 Tab label，并在实现说明中将范围标为页面默认范围；不得显示一个与请求不一致的“全部数据”。

---

## 6. 状态摘要层设计

### 6.1 DataTable 接口建议

在 `DataTable.vue` 增加可选的状态摘要 props/events，保持旧调用方兼容：

```ts
interface ViewSummaryConfig {
  viewLabel: string
  scopeLabel?: string
  filterItems: FilterSummaryItem[]
  sortItems: SortSummaryItem[]
  hiddenColumnCount: number
  isApplying?: boolean
  applyError?: FeedbackError | null
}

interface Props {
  viewSummary?: ViewSummaryConfig | null
  advancedToolsEnabled?: boolean
}

interface Emits {
  'remove-filter': [filterId: string]
  'clear-filters': []
  'retry-view-apply': []
}
```

也可以由 DataTable 直接接收字段 catalog、filters、sorts、columns 并内部计算；但字段 label/值 label 规则应抽成纯函数，避免组件同时承担页面业务范围判断。优先推荐“页面/composable 计算摘要，DataTable 展示”的方案。

### 6.2 桌面布局

表格卡片内部顺序保持：

1. 页面已有标题/Tab/批量操作区域；
2. DataTable toolbar：搜索、刷新、高频筛选；
3. 状态摘要行；
4. 表格内容区；
5. 分页。

状态摘要行应是紧凑、可换行的中性信息层，不新增大卡片，不挤压表格主体。建议结构：

```text
[当前视图：全部客户] [筛选 2] 条件标签… [排序：更新时间 ↓] [已隐藏 1 列]          [清除筛选]
```

- 视图名称/范围是定位信息；
- 筛选标签支持单项移除；
- 排序和隐藏列只展示状态，不在摘要行内提供复杂编辑控件；
- 无筛选时不展示空标签，显示“无额外筛选”；
- `clear filters` 只清除用户筛选，不能清空排序、列配置或删除已保存视图；
- 应用视图时摘要行显示 spinner/“正在应用视图”，不要隐藏旧表格。

### 6.3 移动端布局

移动端继续使用 Card 行模式，不改变 DataTable 高度策略。摘要行应：

- 允许多行换行；
- 优先保留当前视图和筛选数量；
- 具体条件标签可横向滚动或折叠到“筛选条件”按钮，但必须有可达入口；
- 不遮挡搜索、刷新和主要业务操作；
- 不让页面主体产生横向滚动，横向滚动仅允许出现在摘要标签容器（若采用）。

### 6.4 摘要值格式化

必须通过字段 catalog 的 `label` 和 `options` 进行展示：

| 类型 | 示例展示 |
| --- | --- |
| text | 客户名称 包含 “Acme” |
| enum 单选 | 客户状态 属于 “跟进中” |
| enum 多选 | 客户状态 属于 “跟进中、已签约” |
| number | 合同金额 大于 “10,000” |
| date | 创建日期 晚于 “2026-09-01” |
| 空值操作 | 联系电话 为空 |

- 未找到枚举 label 时降级显示原始值，不显示 `[object Object]`；
- 日期和数字格式化只影响展示，不改变请求值；
- 文本值过长时截断并通过 title/tooltip 提供完整值；
- 摘要 id 必须稳定，例如 `${field}:${op}:${serializedValue}:${index}`，以便单项移除和测试。

---

## 7. 工具栏渐进披露

### 7.1 默认可见

默认保持可见：

- 搜索（页面已经存在时）；
- 刷新；
- 页面最高频、最能改变工作队列的筛选入口；
- 当前视图/Tab 本身。

### 7.2 更多设置

排序、字段配置、另存为视图、视图管理等低频工具归入“更多设置”或等价入口。入口要求：

- 文字命名为“更多设置”，不要只放齿轮图标；
- 内含工具有 active/count 状态时，在入口显示汇总 badge，例如“排序 2”“已隐藏 3 列”；
- 入口可通过键盘聚焦，Popover 内焦点可循环/可返回触发器；
- 不影响已有 `filter-view-save-enabled`、`column-config-enabled` 的权限和可用性；
- ApprovalCenter 的批量审批操作必须继续位于高优先级区域，不被高级工具遮挡或折叠。

不建议第一阶段为此引入新的路由或后端配置；先在 DataTable toolbar 组合层实现统一排列。

### 7.3 组件改造建议

可新增轻量组件：

- `ListViewStateSummary.vue`：只负责摘要渲染和摘要交互；
- `ListAdvancedTools.vue`：组合排序、字段配置、保存/管理视图；
- `listViewState.ts`：纯计算、格式化和稳定 id。

如果现有 DataTable 已提供 toolbar slot，应优先通过 slot 组合，避免把所有业务视图管理逻辑塞入 DataTable。若默认工具目前由 DataTable 内部直接平铺，则将内部工具拆成可复用的 toolbar group，但保持现有事件协议兼容。

---

## 8. 筛选摘要与单项移除

### 8.1 事件流程

```text
点击摘要中的移除
  ↓
根据稳定 filterId 找到条件
  ↓
页面生成 nextFilters（只删除该条件）
  ↓
activeFilters = nextFilters
  ↓
pagination.current = 1
  ↓
按页面规则生成 effectiveFilters
  ↓
fetchList()
  ↓
成功：摘要和列表同步
失败：保留原数据，展示可重试错误
```

不允许由 `ListViewStateSummary` 直接修改页面 ref，也不允许组件内部直接请求 API。

### 8.2 清除筛选

- 顶部摘要和无结果状态均可提供入口；
- 清除前不需要二次确认，属于低风险可逆操作；
- 清除后必须回到第 1 页；
- 排序、列配置、当前已保存自定义视图名称不变；
- 对自定义视图：是否将空筛选持久化到当前视图，按现有产品规则统一处理。若产品要求“仅当前列表清除”，则不得调用 `updateActiveCustomViewConfig()`；若要求“同步更新当前自定义视图”，则必须显式调用并在失败时提示“列表已清除，但视图保存失败”，不能静默产生分裂状态。

建议第一阶段采用当前页面既有规则并补齐一致性，不在本改造包中重新定义保存语义。

### 8.3 页面业务剔除

`CustomerTracking`、`Opportunities`、`Contracts` 等页面会根据 Tab 剔除 `status` 或 `status_label`。摘要应展示页面真正生效的条件：

- 用户选择但被 Tab 规则剔除的条件不得显示为已生效；
- 用户刚移除摘要中的条件后，页面仍需经过同一套 effective filter 规则；
- 需要将 `activeFilters` 与 `effectiveFilters` 明确区分，避免摘要显示 draft/逻辑上未发送的条件。

---

## 9. 视图应用事务、竞态和失败恢复

### 9.1 当前风险

现有 `applyCustomViewTab()` 的行为是立即写入 `activeTab`、`activeFilters`、`activeSorts`、`activeColumns`，然后异步调用 `refresh()`。这会造成：

- 请求失败时上下文已切换，用户无法确认旧状态；
- 连续快速切换时，后发请求可能先返回，旧请求随后覆盖数据；
- `refresh()` 返回类型过宽，调用方无法可靠判断成功/失败；
- 内置 Tab 切换和自定义视图切换的 loading 语义不一致。

### 9.2 推荐状态机

```text
idle
  └─ apply requested → applying
        ├─ request success → ready（提交新状态）
        ├─ request failure → apply-error（恢复旧状态、保留旧数据）
        └─ superseded → ignored（旧请求结果丢弃）
```

建议新增：

```ts
interface ViewApplySnapshot {
  activeTab: string
  filters: ListFilterCondition[]
  sorts: ListSortCondition[]
  columns: ViewPreferenceConfig['columns']
  page: number
}

interface ViewApplyState {
  status: 'idle' | 'applying' | 'error'
  requestId: number
  error: FeedbackError | null
  snapshot: ViewApplySnapshot | null
  targetTab: string | null
}
```

### 9.3 原子应用流程

```text
保存旧状态 snapshot
  ↓
requestId += 1
  ↓
标记 applying（DataTable 进入 refreshing，不清空已有数据）
  ↓
设置目标 tab / filters / sorts / columns
  ↓
page = 1
  ↓
调用 refresh()，refresh 必须返回 Promise<Result>
  ├─ 成功且 requestId 仍为最新：提交新状态，清除错误
  ├─ 失败且 requestId 仍为最新：恢复 snapshot，保留旧数据，记录错误
  └─ 非最新：丢弃结果，不更新状态
```

需要注意“旧数据保留”与“回滚状态”是两个动作：

- 在请求中保持旧数据，表格显示 refreshing；
- 请求成功后展示新数据和新摘要；
- 请求失败后恢复旧摘要/Tab，旧数据继续作为可用上下文；
- 失败提示区提供“重试应用视图”，重试使用保存的 target config，不要求整页刷新。

### 9.4 refresh 合同

建议将 composable 的 `refresh` 从 `void | Promise<void>` 收窄为：

```ts
type RefreshResult =
  | { ok: true }
  | { ok: false; error: FeedbackError }

type RefreshFn = (requestId?: number) => Promise<RefreshResult>
```

若短期无法修改所有页面，可在 `useCustomFilterViews` 内包装现有 `refresh()`：

- Promise resolve 视为成功；
- Promise reject/捕获异常视为失败；
- 页面 fetchList 必须最终将 HTTP/业务错误转换为 `FeedbackError`，不能只 Toast 后 resolve。

### 9.5 失败恢复 UI

视图应用失败时：

- 不显示整页空白；
- 不把新视图名称留在旧数据上；
- 原 Tab、筛选、排序、列配置和旧数据保持一致；
- 在摘要区域或 DataTable refresh error 区显示“视图应用失败”；
- 提供局部“重试”按钮；
- 若失败结果不确定（例如网络断开），沿用 `FeedbackError.outcomeUnknown` 语义，重试前不重复提交持久化动作；本需求中的列表读取重试是幂等的；
- 不要求用户刷新浏览器恢复状态。

---

## 10. 请求、分页与 DataTable 固定高度约束

### 10.1 条件变化统一归 1

以下动作都必须将 `pagination.current = 1`：

- 应用筛选；
- 单项移除筛选；
- 清除筛选；
- 应用排序/清除排序；
- 切换内置 Tab；
- 切换自定义视图；
- 另存为自定义视图后加载新视图。

页大小变化是否归 1 沿用现有分页规则。

### 10.2 摘要必须与实际请求一致

每个页面应明确三套状态：

```ts
activeFilters // 用户当前上下文
activeSorts   // 用户当前排序
queryFilters  // 根据 Tab/业务规则剔除后的实际请求条件
```

摘要至少使用 `queryFilters`；若产品希望同时体现用户选择但暂未生效的内容，应另设“未应用”状态，第一阶段不展示未应用条件。

### 10.3 固定高度与滚动

本改造严禁修改以下既有配置：

```vue
height="calc(100vh - 121px)"
height-strategy="fill"
scroll-mode="contained"
```

以及 ApprovalCenter 的既有高度配置。实现时需确保：

- 摘要层增加的高度从 DataTable 卡片内部消化；
- 表格内容区继续 flex 填充并内部纵向滚动；
- 分页继续固定在表格卡片底部；
- 页面主体不会因 20 条以上数据而整体滚动；
- 横向滚动只发生在表格容器，不扩展页面宽度；
- 移动端仍按 Card 模式展示。

如摘要增加后导致表格内容区高度变小，应调整 DataTable 内部 toolbar/summary/content 的 flex 计算，不得把 `scrollMode` 改成 `page` 作为临时修复。

---

## 11. 各页面实施策略

### 11.1 Customers / CustomerTracking / Leads / Opportunities / Contracts / PaymentPlans / PaymentRecords / Invoices

统一接入：

1. 页面提供 `viewSummary` 所需的 `viewLabel/scopeLabel`；
2. 页面将业务规则处理后的 filters/sorts/columns 投影为摘要；
3. DataTable 接收摘要并转发 `remove-filter`、`clear-filters`、`retry-view-apply`；
4. 页面统一归一页码并触发 fetch；
5. `useCustomFilterViews` 改为异步应用视图，维护 snapshot 与 applying 状态；
6. 页面切换内置 Tab 时也走同一套 refresh/竞态控制；
7. 当前自定义视图更新逻辑与摘要更新保持同一成功/失败策略。

迁移时按风险分两批：

- **第一批**：Customers、Opportunities、Contracts，验证普通 CRM 列表、状态 Tab 和自定义视图组合；
- **第二批**：CustomerTracking、Leads、PaymentPlans、PaymentRecords、Invoices，验证日期/金额/枚举摘要及字段剔除规则。

### 11.2 ApprovalCenter

ApprovalCenter 没有 `useCustomFilterViews`，其内置 Tab 是审批状态/角色语义，实施时只接入：

- 当前 Tab/审批范围摘要；
- filters/sorts 摘要；
- 清除筛选、单项移除；
- 高级工具分层。

不得增加自定义视图 Tab，不得改变批量审批操作区，不得把审批状态 Tab 转为普通用户筛选条件。

### 11.3 兼容策略

- 新增 props 均为可选，旧页面未传摘要时 DataTable 行为不变；
- 现有 emits 保留；
- `filters`、`sorts` 的 v-model 语义保留；
- 旧的按钮 count 可继续显示，但最终以摘要层为主要状态表达；
- 一次只迁移一个页面并回归其业务动作，避免 9 个页面同时改变导致难以定位问题。

---

## 12. 需要修改的代码边界

### 12.1 前端文件

预计涉及：

```text
CRM-Client/src/components/crmwolf/DataTable.vue
CRM-Client/src/components/crmwolf/ListFilterPopover.vue
CRM-Client/src/components/crmwolf/ListSortPopover.vue
CRM-Client/src/components/crmwolf/ColumnConfigPopover.vue
CRM-Client/src/components/crmwolf/TableToolbarButton.vue
CRM-Client/src/composables/useCustomFilterViews.ts
CRM-Client/src/components/crmwolf/listFieldCatalog.ts
CRM-Client/src/components/crmwolf/listFilterTypes.ts
CRM-Client/src/components/crmwolf/listSortTypes.ts
CRM-Client/src/utils/listQuery.ts
CRM-Client/src/types/feedback.ts
```

以及首批 9 个页面的事件接线。具体新增文件应优先控制在：

```text
CRM-Client/src/components/crmwolf/listViewState.ts
CRM-Client/src/components/crmwolf/ListViewStateSummary.vue
CRM-Client/src/components/crmwolf/ListAdvancedTools.vue
```

### 12.2 后端边界

不修改后端 API、数据库、查询 DSL 和 view preference 数据结构。现有：

- 列表 filters/sorts 参数序列化；
- `/v1/view-preferences/...`；
- 自定义视图 CRUD；

全部保持兼容。

只有在现有 API 无法表达读取失败而页面仍错误 resolve 时，才允许修正前端 request/fetch 的错误传播，不新增接口。

### 12.3 不应修改

- DataTable 的默认固定高度策略；
- `heightStrategy="fill"` / `scrollMode="contained"` 的页面配置；
- 移动端 Card 结构；
- 权限、业务 Tab 的含义；
- 现有后端筛选、排序、列偏好和自定义视图 schema；
- 与本改造无关的表单、详情、Agent 代码。

---

## 13. 错误、竞态与可观测性

### 13.1 错误分类

| 错误 | 用户行为 | 状态处理 |
| --- | --- | --- |
| 列表首次加载失败 | 重试 | 无旧数据时显示 ErrorState |
| 列表刷新失败且有旧数据 | 重试 | 保留旧数据，显示 refresh error |
| 视图应用失败 | 重试应用视图 | 回滚旧上下文，保留旧数据 |
| 字段配置读取失败 | 重试打开/刷新配置 | 不改变当前有效列 |
| 字段配置保存失败 | 重新保存 | draft 不应覆盖已生效配置 |
| 自定义视图更新失败 | 重试保存 | 当前列表可继续使用，显示保存失败 |
| 快速切换产生旧响应 | 无需用户操作 | 丢弃非最新 requestId 的结果 |

### 13.2 埋点/日志

前端可在现有日志体系下增加低噪声事件：

- `list_view_apply_start`
- `list_view_apply_success`
- `list_view_apply_failure`
- `list_filter_remove`
- `list_filter_clear`
- `list_view_apply_superseded`

字段至少包含：`viewKey`、页面、viewType、filterCount、sortCount、hiddenColumnCount、requestId、duration、errorCode（如有）。不记录客户敏感字段值。

### 13.3 性能预算

- 点击筛选/排序/视图后 100ms 内出现可感知 pressed/loading 反馈；
- 请求超过 300ms 显示 refreshing 状态；
- 不因摘要计算引入逐行深度遍历或重复 API 请求；
- 摘要计算使用 computed/纯函数，字段 catalog 预索引为 Map；
- 切换视图不重复加载列配置 API，优先复用视图配置中的 columns。

---

## 14. 无障碍与响应式要求

- 摘要容器使用有意义的区域标签，例如 `aria-label="当前列表视图状态"`；
- 每个筛选标签的移除按钮提供完整名称：`移除筛选：客户状态属于跟进中`；
- 清除筛选按钮提供明确 accessible name；
- applying 状态通过 `aria-live="polite"` 通知，避免每次普通刷新都重复播报；
- 失败区域具备 `role="alert"` 或复用现有 ErrorState 语义；
- 键盘顺序遵循搜索 → 刷新 → 高频筛选 → 更多设置 → 摘要操作；
- 不依赖颜色区分 active、错误或数量；
- 遵循 design system 的 44px 表格行/表头令牌、触控最小尺寸、焦点环和对比度要求；
- 遵循减少动效偏好，应用状态的 spinner/过渡不得成为唯一反馈。

---

## 15. 测试方案

### 15.1 纯函数单测

针对 `listViewState.ts`：

- 字段 label、操作符 label、枚举 value label 正确映射；
- text/enum/date/number/is_empty 格式化；
- 多选值格式化；
- 无效字段/空值被过滤；
- hidden column count 不包含 actions 和不可隐藏列；
- filter summary id 稳定且唯一；
- 内置 Tab 与自定义视图的 viewType/viewLabel 正确。

### 15.2 组件测试

针对 `ListViewStateSummary` / `DataTable`：

- 无筛选时显示默认语义；
- 单条件、多条件显示并可单项移除；
- 清除筛选只发出 `clear-filters`；
- 排序和隐藏列摘要可见；
- applying 时保留旧表格并显示轻量状态；
- 失败时显示重试并能发出 `retry-view-apply`；
- 窄屏换行/折叠不遮挡主要操作；
- 键盘可访问和 aria 文案正确。

### 15.3 composable 单测

针对 `useCustomFilterViews`：

- 应用自定义视图成功后提交目标状态；
- 应用失败后回滚 snapshot；
- 快速切换时旧 requestId 结果不覆盖新状态；
- 从自定义视图回到内置 Tab 恢复快照；
- 视图应用期间不会发起重复刷新；
- 重试使用目标视图配置；
- 视图保存失败不破坏当前已生效列表状态。

### 15.4 页面回归

每个页面至少验收：

1. 进入页面首次加载；
2. 应用筛选、单项移除、清除筛选；
3. 应用多字段排序；
4. 隐藏/恢复字段；
5. 切换内置 Tab；
6. 切换自定义视图（有/无筛选、排序和列配置）；
7. 20 条以上数据时页面不整体滚动；
8. 请求失败后局部重试；
9. 移动端 Card；
10. 页面刷新/路由切换后状态不出现旧视图残留。

---

## 16. 验收矩阵

| 编号 | 场景 | 预期 |
| --- | --- | --- |
| P2-01-01 | 无筛选、无排序、默认列 | 显示当前视图/范围和“无额外筛选”，不制造空标签 |
| P2-01-02 | 单个文本筛选 | 顶部显示字段、操作符和值，可单项移除 |
| P2-01-03 | 多条件筛选 | 所有有效条件可识别，筛选数量与标签一致 |
| P2-01-04 | 枚举多选/日期/数字 | 摘要使用用户可读 label 和格式化值 |
| P2-01-05 | 清除筛选 | 列表回第 1 页；排序、列配置、已保存视图不被误清空 |
| P2-01-06 | 多字段排序 | 显示排序数量和主排序方向；不把排序误计为筛选 |
| P2-01-07 | 隐藏列 | 显示最终生效的隐藏列数量，不计不可隐藏列 |
| P2-01-08 | 关闭 Popover | 仍可从摘要理解当前状态 |
| P2-01-09 | 应用自定义视图成功 | 显示新视图摘要，列表与筛选/排序/列配置一致 |
| P2-01-10 | 应用视图失败 | 保留旧数据和旧上下文，显示局部重试 |
| P2-01-11 | 连续快速切换视图 | 只有最新操作生效，旧响应被丢弃 |
| P2-01-12 | 内置 Tab 带隐式范围 | 摘要显示 Tab/范围，不伪造为普通 filters |
| P2-01-13 | ApprovalCenter | 不引入自定义视图；批量审批操作不受影响 |
| P2-01-14 | 20+ 条数据 | 页面主体不滚动，表格内部滚动，分页固定 |
| P2-01-15 | 移动端 | Card 模式不变，摘要不遮挡主要操作 |
| P2-01-16 | 键盘/读屏 | 摘要、移除、清除、重试均可操作且有可读反馈 |

---

## 17. 灰度、发布与回滚

### 17.1 发布顺序

1. 先合入纯类型、摘要格式化和组件测试；
2. 在 DataTable 增加兼容性摘要层，默认关闭或仅由首批页面开启；
3. 迁移 Customers、Opportunities、Contracts；
4. 验证错误、竞态和固定高度后，再迁移其余页面；
5. 最后接入 ApprovalCenter 的非自定义视图部分。

### 17.2 灰度开关

可增加前端页面级 feature flag，例如 `listViewStateSummaryEnabled`，默认按页面开启。开关只控制展示和编排，不改变后端请求格式。

### 17.3 回滚

发生以下问题时关闭页面开关即可回退到旧工具栏和现有 Popover：

- 视图切换请求竞态导致列表错乱；
- 摘要与实际查询条件不一致；
- 表格固定高度/内部滚动回归；
- 移动端主要操作被遮挡；
- 清除筛选误影响保存视图。

关闭摘要开关不应删除或覆盖现有 view preference 数据。

---

## 18. 实施拆分与完成定义

### 实施任务

- **T1**：新增摘要类型、字段/值格式化和稳定 id 纯函数；
- **T2**：新增 `ListViewStateSummary`，接入桌面/移动端和无障碍；
- **T3**：DataTable 工具栏增加高级工具组合与兼容事件；
- **T4**：统一页面摘要投影和筛选移除/清除接线；
- **T5**：增强 `useCustomFilterViews` 的 snapshot、应用状态、竞态和重试；
- **T6**：按两批迁移 9 个页面并处理页面业务范围差异；
- **T7**：完成固定高度、分页、失败恢复和移动端回归。

### 完成定义

- 所有验收矩阵场景通过；
- 9 个页面摘要语义一致，ApprovalCenter 无自定义视图误接入；
- 20 条以上数据时页面不整体滚动；
- 视图应用失败可在原上下文中局部重试；
- 无新增后端接口和 schema 迁移；
- 无 Agent 范围代码变更；
- 相关单测、组件测试、页面回归记录齐全。

---

## 19. 待研发评审确认

1. 现有 DataTable toolbar 的内部组合方式，是直接增加 slot 还是抽出 `ListAdvancedTools`；
2. 清除筛选在自定义视图下是否同步持久化为空筛选；
3. 各页面内置 Tab 的 `scopeLabel` 是否由页面显式提供；
4. `refresh()` 是否可以统一改为 `Promise<RefreshResult>`，还是先由 composable 做兼容包装；
5. 应用视图失败提示放在摘要行、表格 refresh error 区，还是二者组合；
6. 是否启用页面级 feature flag，以及首批灰度页面；
7. 是否将筛选摘要在移动端默认展开，或仅显示数量并由点击进入条件列表。

以上事项不影响 TRD 的核心技术结论：**状态摘要由最终有效状态驱动；视图应用必须可感知、可回滚、可重试；现有 DataTable 的固定高度、内部滚动、分页和移动端 Card 必须保持不变。**
