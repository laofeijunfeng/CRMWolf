# 组件选型

- **用途：**登记可复用组件的状态、替代关系与受限原件，作为选型入口。
- **适用范围：**components 领域；覆盖 `components/crmwolf` 全部导出与助手页的业务组合。
- **权威性：**本主题是组件状态与替代关系的唯一事实来源；状态流转见[组件生命周期](../governance/component-lifecycle.md)。
- **相关规范：**[组件索引](README.md) · [组件生命周期](../governance/component-lifecycle.md) · [令牌数值](../foundations/token-values.md#控件与版式)
## 状态

`stable` 契约满足[契约要求](../governance/component-lifecycle.md#契约要求)并经评审，可直接使用；`candidate` 已在用、契约缺失或未达标；`restricted` 仅允许在 `ui/**`、`crmwolf/**` 内使用；`deprecated` 不再新增引用；`remove` 计划删除；`removed` 已删除。契约列「待补」表示尚无组件契约。阶段 1 的 DataTable、DetailSheet、Field 系列、ConfirmDialog、DataViewStatePanel、StatusBadge 契约已补，评审通过后转 `stable`。本表只做索引与分层，规则以契约文档为准。
## 字段与输入

| 组件 | 层 | 状态 | 用途 | 替代 | 契约 |
| --- | --- | --- | --- | --- | --- |
| TouchInput | crmwolf | removed | 旧触控输入 | InputField | — |
| TouchCard | crmwolf | removed | 旧触控卡片 | ListCard | — |
| InputField | crmwolf | candidate | 单行输入字段 | — | [输入](input.md#实现契约) |
| SelectField | crmwolf | candidate | 下拉选择字段 | — | [输入](input.md#实现契约) |
| TextareaField | crmwolf | candidate | 多行输入字段 | — | [输入](input.md#实现契约) |
| DateField | crmwolf | candidate | 日期字段 | — | [输入](input.md#实现契约) |
| CheckboxField | crmwolf | candidate | 复选字段 | — | [输入](input.md#实现契约) |
| MultiSelectField | crmwolf | candidate | 多选字段 | — | [输入](input.md#实现契约) |
| SegmentedChoiceControl | crmwolf | candidate | 分段单选；可带说明行、分组、逐项禁用与多选 | — | [助手页](../patterns/assistant-page.md#选项) |
| ProductIntentPicker | crmwolf | candidate | 产品意向选择 | — | 待补 |
| SelectionSummary | crmwolf | candidate | 已选项摘要 | — | 待补 |
| SearchableSelectField | crmwolf | candidate | 可搜索选择字段 | — | [输入](input.md#实现契约) |
| IndustryHierarchySelectField | crmwolf | candidate | 行业层级选择 | — | 待补 |
## 导航

| 组件 | 层 | 状态 | 用途 | 替代 | 契约 |
| --- | --- | --- | --- | --- | --- |
| ContextTabs | crmwolf | candidate | 上下文标签页 | — | [标签页](tabs.md) |
| DetailContextHeader | crmwolf | candidate | 详情上下文头部 | — | 待补 |
| DetailContextHost | crmwolf | candidate | 详情上下文容器 | — | 待补 |
| TopBarTabs | crmwolf | candidate | 顶部栏标签页 | — | [标签页](tabs.md) |
## 数据展示

| 组件 | 层 | 状态 | 用途 | 替代 | 契约 |
| --- | --- | --- | --- | --- | --- |
| DataTable | crmwolf | candidate | 数据表格 | — | [表格](table.md#实现契约) |
| DataTableSearch | crmwolf | candidate | 表格搜索 | — | 待补 |
| DataTableExportDialog | crmwolf | candidate | 表格导出 | — | 待补 |
| TableToolbarButton | crmwolf | candidate | 表格工具栏按钮 | — | 待补 |
| TableToolbarBuilderPanel | crmwolf | candidate | 工具栏配置面板 | — | 待补 |
| TableRowActions | crmwolf | candidate | 行操作 | — | 待补 |
| DesktopTableRowActions | crmwolf | candidate | 宽视口行操作 | — | 待补 |
| ListFilterPopover | crmwolf | candidate | 列表筛选 | — | 待补 |
| ListSortPopover | crmwolf | candidate | 列表排序 | — | 待补 |
| ColumnConfigPopover | crmwolf | candidate | 列配置 | — | 待补 |
| MultiSelect | crmwolf | candidate | 多选 | — | 待补 |
| ListCard | crmwolf | candidate | 列表卡片 | — | [列表卡片](list-card.md) |
| MetricCard | crmwolf | candidate | 指标卡片 | — | 待补 |
| AreaTrendChart | crmwolf | candidate | 趋势图 | — | 待补 |
| AmountText | crmwolf | candidate | 金额文本 | — | 待补 |
| CopyableText | crmwolf | candidate | 可复制文本 | — | 待补 |
| FileAttachment | crmwolf | candidate | 附件 | — | 待补 |
| FilePreviewDialog | crmwolf | candidate | 文件预览 | — | 待补 |
| HoverInfo | crmwolf | candidate | 悬停说明 | — | 待补 |
| StatusBadge | crmwolf | candidate | 业务状态 | — | [状态徽标](status-badge.md) |
| ApprovalStatusBadge | crmwolf | candidate | 审批状态（带图标） | — | [状态徽标](status-badge.md) |
| DetailSheet | ui | candidate | 详情抽屉（`ui/detail-sheet`），页面可直接使用 | `ui/sheet` | [详情抽屉](detail-sheet.md) |
## 反馈

| 组件 | 层 | 状态 | 用途 | 替代 | 契约 |
| --- | --- | --- | --- | --- | --- |
| DataViewStatePanel | crmwolf | candidate | 空、错、加载状态 | 手写状态块、EmptyState | [状态面板](data-view-state-panel.md) |
| ErrorState | crmwolf | candidate | 错误、无权限状态块 | — | 待补 |
| LoadingSkeleton | crmwolf | candidate | 加载骨架 | — | 待补 |
| LiveRegion | crmwolf | candidate | 读屏播报 | — | 待补 |
| ConfirmDialog | crmwolf | candidate | 确认操作 | 原生 `confirm()` | [确认对话框](confirm-dialog.md) |
| ActionOptionCard | crmwolf | candidate | 弹窗内带说明的下一步操作 | 手写整卡按钮 | [操作选项卡片](action-option-card.md) |
| RenameDialog | crmwolf | candidate | 重命名 | — | 待补 |
| FormErrorSummary | crmwolf | candidate | 表单错误汇总 | — | 待补 |
## 业务组合

| 组件 | 层 | 状态 | 用途 | 替代 | 契约 |
| --- | --- | --- | --- | --- | --- |
| AgentUIMessage、AgentUIInteractionBlock、AgentUICompactTaskList、AgentUIProcessBlock | 业务组合 | candidate | 助手页：消息分发、待办卡片、选项、表单、执行过程 | — | [助手页](../patterns/assistant-page.md) |
| AgentUIBanner、AgentUITextBlock、AgentUINoticeBlock、AgentUIErrorBlock、AgentUIActionResultBlock、AgentUITableBlock、AgentUIEntityListBlock、AgentUIEntityCardBlock、AgentUIMetricGroupBlock、AgentUITimelineBlock、AgentUIPaginationBlock、AgentUIActionBar | 业务组合 | candidate | 助手页：反馈条、文本与数据块 | — | [助手页](../patterns/assistant-page.md) |
## 受限原件

| 原件 | 状态 | 页面改用 |
| --- | --- | --- |
| `ui/alert-dialog` | restricted | [确认对话框](confirm-dialog.md)的 `confirm*` 函数 |
| `ui/sheet` | restricted | DetailSheet（`ui/detail-sheet`） |
| `ui/table` | removed | DataTable |
| `ui/form` | restricted | [`*Field` 系列](input.md#实现契约) |
## 已知问题

- `crmwolf/index.ts` 只导出 crmwolf 组件；`ui` 原件从 `@/components/ui/*` 直接引用。FeedbackAlert、ListAdvancedTools、ListViewStateSummary、TableRowContextMenuContent 存在但未导出，按需登记。
## 删除清单

以下组件已在阶段 3 删除（状态 `removed`），删除前已确认无动态导入与全局注册；不得重新引入。

- crmwolf：TouchInput、TouchCard。
- ui：`app-drawer`、`toggle-group`、`table`、`drawer`、`bubble`、`message`、`message-scroller`。
- 业务组件：CustomerDetailSidebar、HoverPreviewTooltip、`panels/PaymentRecordsPanel`、BusinessJourneyListTools、`agent/CRMAgentChat`（已由销售助手替代）。
