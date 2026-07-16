# 新建商机弹窗所属客户锁定显示优化设计

日期：2026-07-15

## 背景

`OpportunityFormDialog.vue` 已经包含“所属客户”字段。该字段在普通商机创建入口中允许用户下拉选择客户，在客户详情 Sheet 和客户管理列表行操作中应锁定为当前客户。

当前问题不是缺少字段，而是锁定入口只传入 `customerId`，没有传入当前客户名称；同时 `customer_id` 表单值和 Select 选项值存在 number/string 不一致风险。结果是锁定下拉可能已经有客户 ID，但无法稳定显示当前客户名称。

## 目标

1. 从客户详情 Sheet 的“新建商机”入口打开弹窗时，“所属客户”显示当前客户名称，且不可修改。
2. 从客户管理列表行操作“新建商机”打开弹窗时，“所属客户”显示该行客户名称，且不可修改。
3. 商机管理页面等普通入口继续保留下拉选择客户能力，不被锁定逻辑影响。
4. 提交给后端的 `customer_id` 仍为 number，且等于用户所选或锁定的客户 ID。

## 非目标

- 不新增第二个“所属客户”字段。
- 不移除普通入口的客户下拉、远程搜索或可选客户能力。
- 不重构商机创建弹窗之外的业务流程。

## 方案

采用兼容式扩展方案：`OpportunityFormDialog.vue` 保留现有 Select 字段，新增可选 `customerName` prop，并将锁定客户逻辑限定在 `customerLocked=true && customerId` 场景。

### OpportunityFormDialog.vue

- 新增可选 prop：`customerName?: string`。
- `customer_id` 表单值按 Select 组件习惯统一为 string：
  - 普通入口初始值为 `''`。
  - 锁定入口初始值为 `String(props.customerId)`。
- Zod 校验保证 `customer_id` 非空且可转为正整数。
- 提交时转换为后端需要的 number：`customer_id: Number(formValues.customer_id)`。
- 当 `customerLocked=true` 且存在 `customerId`：
  - 弹窗打开时先用 `customerId + customerName` 注入当前客户选项，保证禁用 Select 立即显示客户名称。
  - 再请求客户详情，成功后用详情结果更新客户选项，并继续填充默认商机名称、默认采购方式、默认商机配置等现有逻辑。
  - 如果客户详情请求失败，保留传入的 `customerName` 作为展示兜底，避免锁定下拉空白。
- 当 `customerLocked=false`：
  - 保持现有客户列表加载和搜索逻辑。
  - Select 不禁用，用户可打开下拉选择客户。
  - 不注入锁定客户，不使用 `customerName`。

### Customers.vue

- 行操作“新建商机”点击时，同时保存当前客户 ID 和名称。
- 渲染 `OpportunityFormDialog` 时传入：
  - `:customer-id="opportunityCustomerId"`
  - `:customer-name="opportunityCustomerName"`
  - `:customer-locked="true"`
- 弹窗关闭或创建成功后清理当前客户 ID 和名称，避免切换客户时显示残留。

### CustomerDetailSheet.vue

- 继续复用当前 `opportunityDialogOpen`。
- 给 `OpportunityFormDialog` 补传 `:customer-name="customer?.account_name"`。
- Sheet 页脚入口和商机面板入口都打开同一个弹窗，显示同一个当前客户。

## 兼容性

商机管理页面 `Opportunities.vue` 使用 `OpportunityFormDialog` 时只传 `open`，不传 `customerId` 和 `customerLocked`。由于 `customerLocked` 默认是 `false`，该入口仍走普通选择客户流程：打开时加载客户列表，用户可下拉选择或搜索客户。

因此方案只改变已明确客户上下文的锁定入口，不影响普通创建商机入口。

## 错误处理

- 获取客户详情失败时，沿用现有 `handleApiError(error, '获取客户详情')`。
- 如果调用方传了 `customerName`，失败后仍显示该名称。
- 如果既没有详情也没有名称兜底，则显示 `客户 #<customerId>`，避免空白。
- 普通入口客户列表加载失败时保持现有错误处理。

## 测试与验证

1. 客户详情 Sheet 页脚点击“新建商机”：所属客户立即显示当前客户名称，字段禁用不可改。
2. 客户详情 Sheet 商机面板点击“新建商机”：行为与页脚一致。
3. 客户管理列表某一行点击“新建商机”：所属客户显示该行客户名称，字段禁用不可改。
4. 商机管理页面点击“新建商机”：所属客户仍可下拉选择和搜索。
5. 提交创建请求：锁定入口的 `customer_id` 为当前客户 ID，普通入口的 `customer_id` 为用户选择的客户 ID，类型为 number。
6. 先打开客户 A 的弹窗，关闭后打开客户 B 的弹窗，不显示客户 A 的名称。
