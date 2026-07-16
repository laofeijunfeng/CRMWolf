# 前端审批系统统一重构设计

- **日期**：2026-07-16
- **状态**：待实现
- **影响范围**：审批中心、审批流程配置、发票审批、License 审批

---

## 一、背景

后端已完成通用审批机制的统一重构：
- 统一使用 `entity_type + entity_id` 定位审批实例
- 支持 CONTRACT / PAYMENT / INVOICE / LICENSE 四类业务
- 删除"免审批"逻辑，未匹配流程时返回 400 错误
- 发票和 License 采用两段式：审批通过后执行业务动作（开票/发放）

前端需要同步调整以适配新架构。

---

## 二、总体架构

### 2.1 统一审批入口

```
旧架构（多入口）：
  - FinanceInvoiceApprovals.vue（发票审批）
  - 客户详情页 LicenseManagement.vue（License 审批）
  - ApprovalCenter.vue（审批中心）

新架构（统一入口）：
  - ApprovalCenter.vue（统一审批中心）
    - 审批通过后，发票显示"开票"按钮
    - 审批通过后，License 显示"发放 License"按钮
```

### 2.2 统一审批接口

所有审批操作统一走通用接口：

| 操作 | 接口 |
|------|------|
| 提交审批 | `POST /v1/approvals/{entity_type}/{entity_id}/submit` |
| 审批通过/拒绝 | `POST /v1/approvals/{entity_type}/{entity_id}/approve` |
| 撤回审批 | `POST /v1/approvals/{entity_type}/{entity_id}/cancel` |
| 审批详情 | `GET /v1/approvals/{entity_type}/{entity_id}/detail` |
| 审批列表 | `GET /v1/approvals` |

`entity_type` 支持：`CONTRACT` | `PAYMENT` | `INVOICE` | `LICENSE`

---

## 三、业务流程

### 3.1 发票流程

```
DRAFT -> 提交审批 -> PENDING_REVIEW -> 审批通过 -> APPROVED -> 开票 -> ISSUED
```

审批通过后调用开票接口：
```
POST /v1/invoice-applications/{application_id}/mark-issued
Content-Type: multipart/form-data

参数：
  file: File（可选，发票文件）
  invoice_number: string（可选，发票号码）

校验：
  - 发票申请必须存在
  - 通用审批实例必须是 APPROVED
  - 发票申请状态必须是 APPROVED

成功后：
  - 状态更新为 ISSUED
  - 写入 invoice_file_path、invoice_number、issued_time
```

### 3.2 License 流程

```
DRAFT -> 提交审批 -> PENDING_REVIEW -> 审批通过 -> APPROVED -> 发放 -> ISSUED
```

审批通过后调用发放接口：
```
POST /v1/license-applications/{application_id}/issue
Content-Type: application/json

请求体：
{
  "license_info": "完整 License 信息文本",
  "comment": "可选备注"
}

校验：
  - License 申请必须存在
  - 通用审批实例必须是 APPROVED
  - License 申请状态必须是 APPROVED
  - 未发放过

成功后：
  - 解析 license_info
  - 状态更新为 ISSUED
```

---

## 四、前端改动清单

### 4.1 需修改的文件

| 文件 | 改动内容 |
|------|----------|
| `ApprovalProcessGeneric.vue` | 新增 APPROVED 状态下的"开票"/"发放 License"操作区 |
| `approvalGeneric.ts` | 删除免审批注释，确保使用通用接口 |
| `approval.ts` (store) | 删除免审批注释 |
| `approvalFlow.ts` | business_type 类型补充 LICENSE |
| `ApprovalFlowForm.vue` | 升级 V2 设计规范，business_type 必填无默认值 |
| `invoice.ts` | 新增 `markIssued` 方法 |
| `licenseApplication.ts` | 新增 `issueLicense` 方法，删除旧审批方法 |

### 4.2 需删除的文件/代码

| 文件 | 删除内容 | 原因 |
|------|----------|------|
| `FinanceInvoiceApprovals.vue` | 整个文件 | 废弃的发票审批入口 |
| `InvoiceFileUpload.vue` | 整个文件 | 使用旧 approve-with-file 接口 |
| `fileUpload.ts` | `approveInvoiceWithFile`、`approveInvoiceWithFileProgress`、`getInvoiceFileUrl` | 旧接口 410 Gone |
| `licenseApplication.ts` | `approveApplication`、`approveApplicationFull`、`rejectApplication` | 旧接口 410 Gone |

### 4.3 需新增的文件

| 文件 | 内容 |
|------|------|
| `InvoiceMarkIssuedDialog.vue` | 发票开票对话框（文件上传 + 发票号输入） |
| `LicenseIssueDialog.vue` | License 发放对话框（License 信息输入） |

---

## 五、组件设计

### 5.1 ApprovalProcessGeneric.vue 增强

新增计算属性：

```typescript
// 发票开票按钮显示条件
const showMarkIssued = computed<boolean>(() =>
  props.entityType === 'INVOICE' &&
  status.value === 'APPROVED' &&
  props.canApprove // 实际应判断是否有开票权限
)

// License 发放按钮显示条件
const showIssueLicense = computed<boolean>(() =>
  props.entityType === 'LICENSE' &&
  status.value === 'APPROVED' &&
  props.canApprove // 实际应判断是否有发放权限
)
```

模板新增：

```vue
<!-- 发票开票区 -->
<div v-if="showMarkIssued" class="mark-issued-section">
  <p class="hint">审批已通过，可进行开票操作</p>
  <Button @click="openMarkIssuedDialog">开票</Button>
</div>

<!-- License 发放区 -->
<div v-if="showIssueLicense" class="issue-license-section">
  <p class="hint">审批已通过，可进行发放操作</p>
  <Button @click="openIssueDialog">发放 License</Button>
</div>
```

### 5.2 InvoiceMarkIssuedDialog.vue

功能：
- 文件上传（可选）
- 发票号码输入（可选）
- 调用 `POST /v1/invoice-applications/{id}/mark-issued`
- 成功后 emit `issued` 事件

设计规范：
- 使用 V2 Design Tokens
- 使用 shadcn-vue 组件
- 表单校验使用 Zod

### 5.3 LicenseIssueDialog.vue

功能：
- License 信息文本框（必填）
- 备注输入（可选）
- 调用 `POST /v1/license-applications/{id}/issue`
- 成功后 emit `issued` 事件

设计规范：
- 使用 V2 Design Tokens
- 使用 shadcn-vue 组件
- 表单校验使用 Zod

---

## 六、ApprovalFlowForm.vue V2 重构

### 6.1 组件替换

| 旧组件 | 新组件 |
|--------|--------|
| `el-card` | `Card` (shadcn-vue) |
| `el-form` | `Form` (shadcn-vue) |
| `el-input` | `Input` (shadcn-vue) |
| `el-radio-group` | `RadioGroup` (shadcn-vue) |
| `el-select` | `Select` (shadcn-vue) |
| `el-button` | `Button` (shadcn-vue) |
| `el-steps` | 自定义 Stepper 或保留 |

### 6.2 样式迁移

```scss
// 旧
@use '@/styles/variables.scss' as *;

// 新
@use '@/styles/variables-v2.scss' as *;
```

### 6.3 business_type 必填化

```typescript
// 旧代码
const form = ref({
  business_type: 'CONTRACT',  // 有默认值
  // ...
})

// 新代码
const form = ref({
  business_type: '' as EntityType | '',  // 无默认值，必须选择
  // ...
})

const rules = {
  business_type: [
    { required: true, message: '请选择适用单据类型', trigger: 'change' }
  ]
}
```

---

## 七、API 层改动

### 7.1 approvalFlow.ts 类型补充

```typescript
export interface ApprovalFlow {
  // ...
  business_type: 'CONTRACT' | 'PAYMENT' | 'INVOICE' | 'LICENSE'  // 新增 LICENSE
  // ...
}
```

### 7.2 invoice.ts 新增方法

```typescript
// 发票开票
markIssued: (applicationId: number, data: { 
  file?: File
  invoice_number?: string 
}): Promise<InvoiceApplicationResponse> => {
  const formData = new FormData()
  if (data.file) formData.append('file', data.file)
  if (data.invoice_number) formData.append('invoice_number', data.invoice_number)
  return request.post(`/v1/invoice-applications/${applicationId}/mark-issued`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}
```

### 7.3 licenseApplication.ts 新增/删除

```typescript
// 新增：License 发放
issueLicense: (applicationId: number, data: { 
  license_info: string
  comment?: string 
}): Promise<LicenseApplicationResponse> => {
  return request.post(`/v1/license-applications/${applicationId}/issue`, data)
}

// 删除：以下方法不再使用
// - approveApplication
// - approveApplicationFull
// - rejectApplication
```

### 7.4 删除免审批注释

删除以下位置的"免审批"相关注释：
- `approvalGeneric.ts`: 删除 "PAYMENT/INVOICE 未匹配流程时后端直通返回 approval_id=0"
- `approval.ts` (store): 同上

---

## 八、路由调整

### 8.1 废弃路由

```typescript
// 删除或重定向
{ path: '/finance/invoice-approvals', redirect: '/approvals' }
```

### 8.2 保留路由

```typescript
// 审批中心
{ path: '/approvals', name: 'Approvals', component: ApprovalCenter }

// 审批流程配置
{ path: '/approval-flows', name: 'ApprovalFlows', component: ApprovalFlows }
{ path: '/approval-flows/create', name: 'ApprovalFlowCreate', component: ApprovalFlowForm }
{ path: '/approval-flows/:id/edit', name: 'ApprovalFlowEdit', component: ApprovalFlowForm }
```

---

## 九、测试要点

### 9.1 发票流程

1. 创建发票申请 → 状态 DRAFT
2. 提交审批 → 状态 PENDING_REVIEW
3. 审批通过 → 状态 APPROVED
4. 开票（上传文件 + 发票号） → 状态 ISSUED
5. 验证文件可下载

### 9.2 License 流程

1. 创建 License 申请 → 状态 DRAFT
2. 提交审批 → 状态 PENDING_REVIEW
3. 审批通过 → 状态 APPROVED
4. 发放 License（输入 license_info） → 状态 ISSUED
5. 验证 License 信息已写入

### 9.3 审批流程配置

1. 创建流程时不选 business_type → 提交失败，提示必填
2. 选择 LICENSE 类型 → 可正常创建
3. 编辑流程 → 正常保存

### 9.4 错误处理

1. 无匹配审批流程 → 显示后端错误提示
2. 重复开票/发放 → 显示业务错误
3. 网络错误 → 显示通用错误提示

---

## 十、实施顺序

1. **Phase 1: API 层准备**
   - 新增 `markIssued`、`issueLicense` 方法
   - 补充 `business_type` 类型定义
   - 删除免审批注释

2. **Phase 2: 新增组件**
   - 创建 `InvoiceMarkIssuedDialog.vue`
   - 创建 `LicenseIssueDialog.vue`

3. **Phase 3: 核心组件改造**
   - 改造 `ApprovalProcessGeneric.vue`
   - 改造 `ApprovalCenter.vue`

4. **Phase 4: 配置页重构**
   - 重构 `ApprovalFlowForm.vue` 到 V2 规范

5. **Phase 5: 清理废弃代码**
   - 删除 `FinanceInvoiceApprovals.vue`
   - 删除 `InvoiceFileUpload.vue`
   - 删除 `fileUpload.ts` 中废弃方法
   - 删除 `licenseApplication.ts` 中废弃方法

6. **Phase 6: 测试验证**
   - 端到端测试
   - 回归测试

---

## 十一、设计规范参考

- 基础规范：`CRM-Docs/design-system/foundations/README.md`
- 组件契约：`CRM-Docs/design-system/components/README.md`
- 页面模式：`CRM-Docs/design-system/patterns/README.md`
- 审批中心：`CRM-Docs/design-system/patterns/approval-center.md`
- 审批通知：`CRM-Docs/design-system/components/approval-notification.md`