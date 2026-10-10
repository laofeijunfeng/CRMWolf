# DataTable 首列业务数据统一视觉实施计划

> **目标：**让所有桌面端 `DataTable` 的首个可见业务数据单元格默认使用客户名称同款主色与 semibold 字重，同时保留自定义 slot 的显式语义样式。

## 约束

- 设计依据：`docs/superpowers/specs/2026-10-09-datatable-first-column-styling-design.md`
- 只修改 `DataTable` 公共组件和其交互测试；不逐页面复制样式。
- 选择框、操作列和 export-only 字段不参与首列判断。
- 只处理桌面表格；移动端卡片保持现状。
- 生产代码遵循红—绿：已有测试先扩展并确认失败，再写模板/样式。
- 不运行或修改与本任务无关的 dirty worktree 文件。

## 实施步骤

### 1. 扩展行为测试并确认 RED

文件：`CRM-Client/src/components/crmwolf/__tests__/DataTableInteraction.test.ts`

增加测试覆盖：

- 两个可见业务列：第一列有 `data-table-cell--primary`，第二列没有。
- `selectable: true`：选择框不占用首列位置，第一业务列仍有 class。
- 第一业务列设置 `visible: false` 的列偏好后，下一可见列获得 class。
- 自定义列偏好重排后，最终顺序中的首个业务列获得 class。
- `role: keyword/action/decoration` 的投影列不参与业务首列判断。

运行：

```bash
cd CRM-Client
npm run test:unit -- src/components/crmwolf/__tests__/DataTableInteraction.test.ts
```

预期当前新增断言因 class 尚不存在失败，既有测试保持通过。

### 2. 实现最小公共组件修改

文件：`CRM-Client/src/components/crmwolf/DataTable.vue`

- 在桌面 `v-for="col in processedColumns"` 的 `<td>` class 数组中加入：
  - `col.key === primaryColumnKey ? 'data-table-cell--primary' : ''`
- `primaryColumnKey` 从最终可见的 `processedColumns` 中选择第一个 `role === undefined` 的列。
- `DataTableColumn` 传递字段 `role`，使关键字、装饰和字段级操作列可以被排除。
- 在 `.data-table-cell` 附近增加 `.data-table-cell--primary`：
  - `color: $wolf-text-primary-v2;`
  - `font-weight: $wolf-font-weight-semibold-v2;`
- 不修改移动卡片模板，不对子元素使用深度选择器或 `!important`，确保 slot 的显式语义样式优先。

### 3. GREEN 与 focused regression

重复运行 DataTable 交互测试，确认全部通过；必要时补充列偏好/选择框断言，确保 class 依据 `processedColumns` 最终可见顺序。

### 4. 项目验证

按项目要求运行：

```bash
cd CRM-Client
npm run test:unit -- src/components/crmwolf/__tests__/DataTableInteraction.test.ts
npm run type-check
npm run lint
npm run lint:style
```

### 5. 真实界面核对与 review

使用当前 `crm-client-dev` 浏览器页面核对桌面列表首列、选择框和移动卡片标题；确认没有影响显式链接色、徽章或按钮。完成后请求代码 review，review 只关注本计划涉及文件与验收标准。
