# DataTable 首列业务数据统一视觉设计

- 日期：2026-10-09
- 状态：已确认，实施中
- 范围：统一所有桌面端 `DataTable` 首个可见业务数据列的默认文字视觉
- 非范围：不修改移动端卡片、不修改选择框和操作列、不改动各页面显式语义样式或业务逻辑

## 1. 问题

客户管理列表的“客户名称”使用 `$wolf-text-primary-v2` 与 `$wolf-font-weight-semibold-v2`，其他复用 `DataTable` 的列表首列仍继承通用单元格的次级文字色与普通字重。由于列可隐藏、重排，逐页面给固定字段补样式容易遗漏并会重复维护。

## 2. 决策

在统一组件 `CRM-Client/src/components/crmwolf/DataTable.vue` 的桌面表格渲染中，从最终可见的 `processedColumns` 中筛选 `role === undefined` 的业务列，并给其中第一列增加 `data-table-cell--primary` class。

该 class 使用：

```scss
color: $wolf-text-primary-v2;
font-weight: $wolf-font-weight-semibold-v2;
```

这样首列定义来自最终显示顺序，而不是字段注册表顺序：

- 选择框单元格不参与判断，因为它由独立的 `.data-table-selection-cell` 渲染。
- `role` 非空的投影列（关键字、装饰、字段级操作）不属于业务数据列，不参与判断。
- 操作列不参与判断，因为它在 `processedColumns` 之后单独渲染。
- `export-only` 字段不参与判断，因为它不会投影到 `processedColumns`。
- 列隐藏与用户列顺序调整后，新的首个可见业务列自动获得该 class。

## 3. 自定义 slot 兼容策略

只改变首列单元格自身的继承色和字重，不强制覆盖首列 slot 子元素已有的显式语义样式：

- 普通文本和没有显式颜色/字重的内容继承主色与 semibold。
- 链接、单号、按钮、徽章和次级元信息继续保留各自的链接色、等宽字、交互字重、状态色或辅助色。
- 不为每个页面新增首列样式，避免与统一组件规则形成第二套维护入口。

该取舍保留链接和状态元素的语义反馈，同时让默认 DataTable 文本与客户名称保持一致。

## 4. 响应式行为

只新增桌面表格数据单元格 class。移动端默认卡片标题已经使用 `$wolf-text-primary-v2` 与 `$wolf-font-weight-semibold-v2`，继续保持现状，不新增移动端规则或改变卡片 slot。

## 5. 文件边界

### 修改

- `CRM-Client/src/components/crmwolf/DataTable.vue`
  - 在桌面业务单元格 class 中标记首个可见 `role === undefined` 的业务列。
  - 增加首列主信息色与 semibold 样式。
- `CRM-Client/src/components/crmwolf/listFieldCatalog.ts`
  - 将字段 `role` 传递到投影表格列，供公共组件区分业务列与关键字、装饰、操作列。
- `CRM-Client/src/components/crmwolf/__tests__/DataTableInteraction.test.ts`
  - 验证首列获得 class、后续列不获得 class。
  - 验证选择框不被算作首列。
  - 验证隐藏首列后下一可见业务列成为首列。
  - 验证列重排和非业务 role 列不改变业务首列判断。

### 不修改

- 各业务页面的字段注册表、业务逻辑和移动端卡片。
- 各页面已有显式链接、按钮、徽章和次级文案样式。
- 后端 API、schema、数据库与迁移。
- DataTable 默认其他单元格的颜色和字重。

## 6. 验收标准

1. 没有选择框时，首个可见业务数据 `<td>` 有 `data-table-cell--primary`，第二列没有。
2. 有选择框时，选择框 `<td>` 没有首列 class，首个业务数据 `<td>` 有该 class。
3. 首个业务列隐藏后，下一可见业务列有该 class。
4. 该 class 的计算基于最终 `processedColumns` 顺序，支持列偏好排序；`role` 非空的投影列不占用业务首列位置。
5. 首列默认文本解析为 `$wolf-text-primary-v2` 和 `$wolf-font-weight-semibold-v2`。
6. 自定义 slot 中显式设置的链接色、次级色、徽章色和按钮样式不被公共规则强制覆盖。
7. 移动端卡片标题和 DataTable 其他列行为不变。

## 7. 验证

- 先运行新增组件测试确认在生产代码修改前因缺少 class 失败。
- 修改后运行 `CRM-Client` 定向 Vitest。
- 运行前端 `npm run type-check`、`npm run lint` 和 `npm run lint:style`。
- 使用已运行的真实前端在桌面端打开至少一个使用 DataTable 的列表，确认首列视觉、列配置/隐藏和选择框布局；移动端确认卡片标题未回归。
