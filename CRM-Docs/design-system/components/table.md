# 表格

- **用途：**展示可比较、可扫描的信息密集型记录。
- **适用范围：**components 领域。
- **权威性：**本主题是表格表头、行、对齐与交互的唯一事实来源。
- **相关规范：**[组件索引](README.md) · [列表卡片](list-card.md)（受限空间替代方案） · [列表页](../patterns/list-page.md) · [浮层表面](overlay.md) · [间距与布局](../foundations/spacing-layout.md) · [排版](../foundations/typography.md) · [颜色令牌](../foundations/color-tokens.md) · [动效与性能](../foundations/motion-performance.md) · [无障碍](../foundations/accessibility.md)

## 结构与内容

表头说明每列的含义；列标题简短、稳定，并与单元格内容一一对应。记录名称和主要识别信息置于便于扫描的位置。桌面行操作采用分层入口：当前业务状态下的 1～2 个主操作在行尾轻量显示，其余操作进入可见的“更多”菜单；右键仍保留为熟练用户快捷入口，键盘用菜单键或 Shift+F10 打开同一份完整菜单。查看详情由行点击承担，不再重复显示“查看”按钮。行菜单与筛选、排序、字段配置浮层遵循[浮层表面](overlay.md)。

表格仅用于跨行比较有价值的数据。内容较长时允许行随内容扩展，不得以固定行高截断关键信息。无记录、加载、失败和筛选无结果必须呈现明确状态及后续动作。列表页中列、筛选与排序的字段来源由[列表页](../patterns/list-page.md)定义。

## 表头、行与对齐

表头、数据行和单元格的高度与内边距使用[间距与布局](../foundations/spacing-layout.md)的表格令牌。表头以辅助信息层级区分于数据；行之间以轻量分隔组织，不使用竖向分隔线制造网格。

表格容器使用 `--card` 背景、`--border` 描边和 `rounded-lg`（内容表面圆角）建立边界，不使用卡片阴影。用边框和行分隔表达结构，而不是通过浮起阴影制造层级。

文本按阅读方向对齐；数值、金额、百分比与日期在同列保持一致对齐方式，并使比较重点容易扫读。行悬停仅用于可指向环境的可交互反馈，使用中性表格悬停背景；不应让悬停成为发现操作的唯一方式。

## 操作与响应式

排序、选择、展开和行级操作必须有可理解的名称、状态和键盘路径。桌面 DataTable 不恢复完整的多按钮操作列；行尾保留紧凑操作区，仅显示当前状态下最多两个主操作及可见的「更多」按钮。右键和键盘菜单键 / Shift+F10 作为同一套操作的快捷入口。查看详情由行点击承担，高风险操作必须通过明确入口进入统一确认流程。遵循[无障碍](../foundations/accessibility.md)的表格语义、焦点和动态反馈规则。

窄视口优先保留任务所需列，行操作改到卡片底部，不依赖桌面操作列。超出空间时仅表格容器可横向滚动，页面主体不得横向滚动。遵循[响应式与移动端](../foundations/responsive-mobile.md)。悬停与状态变化遵循[动效与性能](../foundations/motion-performance.md)。

## 数值引用

表格行与表头最小高度、单元格内边距、行悬停 `--wash-hover`、选中 `--wash-selected` 均见[令牌数值](../foundations/token-values.md#间距与布局)；数值列用 `tabular-nums`（或 `td[data-numeric]`）。行尾仅图标按钮只限编辑、更多、删除等通用动作，必须带 `aria-label`，见[按钮](button.md)。

## 实现契约

页面表格只用 crmwolf `DataTable`；`ui/table` 已删除，见[删除清单](registry.md#删除清单)。

- **字段：**`fields`（列、筛选、排序、字段配置的唯一来源）、`data`、`rowKey`、`total`、`page`、`pageSize`。不再接收 `columns`、`filterFields`、`sortFields`。
- **读取状态：**优先 `viewState`（loading / error / empty / ready）配合 `loadError`、`emptyReason`；`loading` 布尔值仅为兼容。空、错、加载由内置的 [DataViewStatePanel](data-view-state-panel.md) 呈现，页面不另写状态块。
- **行操作：**`getRowActions` 返回当前行动作集，同时驱动行尾操作区与右键 / 键盘菜单；`rowInteractive` + `row-click` 承担查看详情。
- **筛选、排序、搜索、视图：**`filters`·`sorts`·`search` 受控，配合 `update:filters`、`filter-apply`、`update:sorts`、`sort-apply`、`update:search`、`search-apply` 等事件；字段配置走 `viewKey`、`columnConfigEnabled`。
- **高度与滚动：**新页面用 `heightStrategy` 与 `scrollMode`，不写固定 `height`。
- **插槽：**`cell-<key>`（`row`、`value`）、`mobile-card`、`mobile-actions`、`tableTools`、`replacement`。
- **分页与选择：**`update:page`、`update:page-size`、`update:selectedRowKeys`；`retry` 由失败状态触发。
