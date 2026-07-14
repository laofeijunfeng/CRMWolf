# 线索 Sheet 内转化客户设计

## 目标

将线索转化统一为详情 Sheet 内的直接创建流程，避免跳转到独立转化页；删除失效的 `LeadConvert.vue` 和对应路由，从根源消除其对已删除 `@/utils/errorMessages` 模块的导入错误。

## 范围

- 在 `LeadDetailSheet.vue` 中实现客户转化 Dialog。
- 将 `Leads.vue` 的“转化为客户”入口统一到该 Sheet 流程。
- 删除独立转化页面及两条不再使用的路由。
- 不改动 `MyLeads.vue` 现有的独立旧转化弹窗。

## 交互流程

1. 用户在线索详情 Sheet 或线索列表中点击“转化为客户”。
2. 打开线索详情 Sheet；点击转化操作时，Sheet 保持打开并展示客户转化 Dialog。
3. Dialog 展示以下字段：
   - 客户公司名称：必填，默认线索名称。
   - 所在城市：必填，默认线索城市。
   - 默认采购方式：必选，打开 Dialog 时加载选项。
   - 公司地址：选填。
4. 用户取消时只关闭 Dialog，不改变线索数据。
5. 用户确认时先执行前端校验，再调用 `customerApi.convertLeadToCustomer`。
6. 提交期间禁用取消和确认，防止重复提交。
7. 成功后显示成功提示，关闭 Dialog 与 Sheet，向父级发出 `refresh`，并进入新建客户的详情页。
8. 失败时保留表单与 Sheet，使用 `handleApiError(error, '转化线索')` 提示原因，方便用户修改后重试。

## 架构与数据流

- `LeadDetailSheet` 持有转化表单、提交状态和采购方式选项。
- Sheet 打开并加载到线索详情后，转化按钮仅初始化/显示 Dialog；不立即路由跳转。
- 转化请求包含 `lead_id`、`account_name`、`address`、`default_procurement_method_id`。城市用于表单确认与必填校验；当前客户转化接口不接收城市字段。
- `Leads.vue` 的转化菜单复用它已有的详情 Sheet 状态，设置选中线索 ID 并打开 Sheet。用户随后在 Sheet 中完成转换。
- `LeadConvert.vue` 不再被引用，因此删除该文件；路由表同步删除 `leads/:id/convert` 与 `leads/convert` 条目。

## 错误处理

- 采购方式选项加载失败时显示统一 API 错误，并禁止用户提交，避免创建缺少必填采购方式的客户。
- 提交 API 失败时不关闭 Dialog、不清空表单；`handleApiError` 给出标准化提示。
- 已转化线索不展示转化按钮，沿用当前状态条件。

## 验证

- 单元/类型检查覆盖删除失效路由后的编译与类型完整性。
- 通过前端构建确认不存在 `@/utils/errorMessages` 解析错误。
- 手动验收：从列表打开详情 Sheet，填写四项字段并转化，观察防重复提交、成功提示、列表刷新和客户详情跳转；再模拟/观察请求失败时 Dialog 与填写内容保留。
