# 数据视图状态面板

- **用途：**统一页面与区块的加载、失败、空状态呈现。
- **适用范围：**components 领域；`crmwolf/DataViewStatePanel.vue` 及全部读取型视图。
- **权威性：**本主题是读取状态呈现的实现契约；可访问播报规则由[无障碍](../foundations/accessibility.md)拥有。
- **相关规范：**[组件索引](README.md) · [组件选型](registry.md) · [表格](table.md) · [列表页](../patterns/list-page.md) · [按钮](button.md) · [无障碍](../foundations/accessibility.md)

## 属性

| 属性 | 说明 | 默认 |
| --- | --- | --- |
| `state` | `loading` / `error` / `empty` / `ready`；ready 渲染默认插槽 | 必填 |
| `loadingType` · `loadingRows` | 默认骨架类型（list / card / table）与行数 | card · 3 |
| `errorTitle` · `errorDescription` | 失败文案 | 「加载失败」·「请检查网络连接后重试。」 |
| `emptyTitle` · `emptyDescription` | 空状态文案 | 「暂无数据」· 空 |
| `class` | 外层样式，不得覆盖页面滚动容器 | — |

事件：`retry`，由默认「重新加载」按钮触发。

## 插槽

- `loading`：替换默认骨架。
- `error-action`：替换默认「重新加载」按钮。
- `empty-action`：空状态下的后续动作。
- 默认插槽：ready 时的内容。

## 使用约束

- 页面不得另建 EmptyState 或手写空、错、加载块；DataTable 已内置本组件，见[表格](table.md#实现契约)。
- 空状态区分无数据、筛选无结果与无权限，文案说明原因与下一步。
- 空状态主 CTA 用 lg 尺寸，每个空状态只有一个主操作，见[按钮](button.md)。
- 加载区域带 `role="status"` 与 `aria-busy`，骨架本身对读屏隐藏。

[返回组件契约](README.md)
