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

**功能：**
- 文件上传（可选）
- 发票号码输入（可选）
- 调用 `POST /v1/invoice-applications/{id}/mark-issued`
- 成功后 emit `issued` 事件

**设计规范：**
- 使用 V2 Design Tokens
- 使用 shadcn-vue 组件
- 表单校验使用 Zod

**UI 结构：**
```
┌─────────────────────────────────────────────────────┐
│  开票                                          [×]  │
├─────────────────────────────────────────────────────┤
│                                                     │
│  发票文件（可选）                                   │
│  ┌─────────────────────────────────────────────┐   │
│  │  📄 点击或拖拽上传发票文件                    │   │
│  │     支持 PDF/JPG/PNG/OFD，最大 10MB          │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  发票号码（可选）                                   │
│  ┌─────────────────────────────────────────────┐   │
│  │  输入发票号码便于查询...                      │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ℹ️ 开票后状态将变更为"已开票"，此操作不可撤销      │
│                                                     │
├─────────────────────────────────────────────────────┤
│                        [取消]  [确认开票]           │
└─────────────────────────────────────────────────────┘
```

**交互规范：**
- 文件选择后显示文件名 + 大小 + 移除按钮
- 上传中显示进度条（大文件 >1MB）
- 提交时按钮显示 loading 状态
- 成功后显示 toast 并关闭对话框
- 失败时显示错误信息，保留已填内容

### 5.3 LicenseIssueDialog.vue

**功能：**
- License 信息文本框（必填）
- 备注输入（可选）
- 调用 `POST /v1/license-applications/{id}/issue`
- 成功后 emit `issued` 事件

**设计规范：**
- 使用 V2 Design Tokens
- 使用 shadcn-vue 组件
- 表单校验使用 Zod

**UI 结构：**
```
┌─────────────────────────────────────────────────────┐
│  发放 License                                  [×]  │
├─────────────────────────────────────────────────────┤
│                                                     │
│  License 信息 *                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │  粘贴完整的 License 信息...                   │   │
│  │                                              │   │
│  │                                              │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  备注（可选）                                       │
│  ┌─────────────────────────────────────────────┐   │
│  │  输入备注...                                  │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ℹ️ 发放后状态将变更为"已发放"，此操作不可撤销      │
│                                                     │
├─────────────────────────────────────────────────────┤
│                        [取消]  [确认发放]           │
└─────────────────────────────────────────────────────┘
```

**交互规范：**
- License 信息为必填，空值时禁用提交按钮
- 提交时按钮显示 loading 状态
- 成功后显示 toast 并关闭对话框
- 失败时显示后端返回的错误信息

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

## 八、错误状态与边界情况处理

### 8.1 无匹配审批流程

**触发场景：** 提交审批时，后端未找到匹配的审批流程

**后端响应：**
```json
{
  "detail": "未找到匹配的发票审批流程，请联系管理员创建或完善审批流程"
}
```

**前端处理：**
- 使用 `ErrorState` 组件展示
- 显示后端返回的 `detail` 原文
- 提供"重新加载"按钮（刷新页面）
- 不提供"跳过审批"或"直接通过"选项

### 8.2 审批冲突（409）

**触发场景：** 审批操作时乐观锁检测到状态已变更

**前端处理：**
- 显示 toast："该审批已被他人处理，已刷新最新状态"
- 自动重新加载审批详情
- 保留用户已输入的内容（如驳回理由）
- 如果审批已不再是 PENDING，显示提示："该审批已由他人处理，无需重复操作"

### 8.3 重复开票/发放

**触发场景：** 发票已开票或 License 已发放时再次调用接口

**后端响应：**
```json
{
  "detail": "发票申请已开票，不可重复操作"
}
// 或
{
  "detail": "License 申请已发放，不可重复操作"
}
```

**前端处理：**
- 显示错误 toast
- 刷新详情以更新状态
- 隐藏操作按钮（状态已变更）

### 8.4 文件上传错误

**触发场景：** 文件格式不支持、文件过大、上传失败

| 错误类型 | 前端处理 |
|----------|----------|
| 格式不支持 | 即时校验，显示"仅支持 PDF/JPG/PNG/OFD 格式" |
| 文件过大 | 即时校验，显示"文件大小不能超过 10MB" |
| 网络错误 | 显示"上传失败，请重试"+ 重试按钮 |

### 8.5 License 信息格式错误

**触发场景：** 提交的 License 信息无法被后端解析

**后端响应：**
```json
{
  "detail": "License 信息格式无效，请检查后重试"
}
```

**前端处理：**
- 显示后端错误信息
- 保留已填内容
- 聚焦到 License 信息输入框

### 8.6 网络超时

**触发场景：** 请求超时无响应

**前端处理：**
- 显示"网络超时，请检查网络连接后重试"
- 提供重试按钮
- 不自动重试（避免重复提交）

---

## 九、路由调整

### 9.1 废弃路由

```typescript
// 删除或重定向
{ path: '/finance/invoice-approvals', redirect: '/approvals' }
```

### 9.2 保留路由

```typescript
// 审批中心
{ path: '/approvals', name: 'Approvals', component: ApprovalCenter }

// 审批流程配置
{ path: '/approval-flows', name: 'ApprovalFlows', component: ApprovalFlows }
{ path: '/approval-flows/create', name: 'ApprovalFlowCreate', component: ApprovalFlowForm }
{ path: '/approval-flows/:id/edit', name: 'ApprovalFlowEdit', component: ApprovalFlowForm }
```

---

## 十、测试要点

### 10.1 发票流程

1. 创建发票申请 → 状态 DRAFT
2. 提交审批 → 状态 PENDING_REVIEW
3. 审批通过 → 状态 APPROVED
4. 开票（上传文件 + 发票号） → 状态 ISSUED
5. 验证文件可下载

### 10.2 License 流程

1. 创建 License 申请 → 状态 DRAFT
2. 提交审批 → 状态 PENDING_REVIEW
3. 审批通过 → 状态 APPROVED
4. 发放 License（输入 license_info） → 状态 ISSUED
5. 验证 License 信息已写入

### 10.3 审批流程配置

1. 创建流程时不选 business_type → 提交失败，提示必填
2. 选择 LICENSE 类型 → 可正常创建
3. 编辑流程 → 正常保存

### 10.4 错误处理

1. 无匹配审批流程 → 显示后端错误提示
2. 重复开票/发放 → 显示业务错误
3. 网络错误 → 显示通用错误提示

---

## 十一、实施顺序

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

## 十二、用户旅程与交互设计补充

### 12.1 无匹配审批流程错误处理

当提交审批时，后端返回 400 错误提示"未找到匹配的审批流程"：

```
┌─────────────────────────────────────────────────────┐
│  ⚠️ 无法提交审批                                    │
│                                                     │
│  未找到匹配的发票审批流程，请联系管理员创建或完善    │
│  审批流程。                                         │
│                                                     │
│  [关闭]                                             │
└─────────────────────────────────────────────────────┘
```

**实现要求：**
- 使用 `ErrorState` 组件展示
- 展示后端返回的 `detail` 字段原文
- 不提供"跳过审批"或"直接通过"选项

### 12.2 审批状态过渡动画

状态变化时的视觉反馈：

| 状态变化 | 动画 | 持续时间 |
|----------|------|----------|
| DRAFT → PENDING | 状态徽章淡入 + 微脉冲 | 200ms |
| PENDING → APPROVED | 成功色脉冲 + 勾选图标淡入 | 300ms |
| PENDING → REJECTED | 危险色脉冲 + 警告图标淡入 | 300ms |
| APPROVED → ISSUED | 成功徽章强化 + 完成提示 | 300ms |

**遵循 `motion-performance.md`：**
- 使用 `transform` 和 `opacity` 动画
- 支持 `prefers-reduced-motion`
- 不阻断用户操作

### 12.3 开票/发放成功反馈

成功后的 Toast 提示：

```
发票：已开票，发票文件已上传
License：已发放 License，License 信息已写入
```

**反馈规范：**
- 使用 `toast.success()`
- 持续时间 3000ms
- 提供"查看详情"链接（可选）

### 12.4 确认对话框

对于不可逆操作，使用确认对话框：

**开票确认：**
```
┌─────────────────────────────────────────────────────┐
│  确认开票                                           │
│                                                     │
│  开票后发票申请状态将变更为"已开票"，此操作不可     │
│  撤销。                                             │
│                                                     │
│            [取消]  [确认开票]                       │
└─────────────────────────────────────────────────────┘
```

**License 发放确认：**
```
┌─────────────────────────────────────────────────────┐
│  确认发放 License                                   │
│                                                     │
│  发放后 License 申请状态将变更为"已发放"，此操作    │
│  不可撤销。                                         │
│                                                     │
│            [取消]  [确认发放]                       │
└─────────────────────────────────────────────────────┘
```

---

## 十三、可访问性设计

### 13.1 ARIA 标签规范

| 元素 | aria-label |
|------|------------|
| 开票按钮 | `开票，审批已通过` |
| 发放 License 按钮 | `发放 License，审批已通过` |
| 文件上传区域 | `上传发票文件，可选，支持 PDF/JPG/PNG/OFD` |
| License 信息输入框 | `输入完整的 License 信息，必填` |
| 状态徽章 APPROVED | `审批已通过` |
| 状态徽章 ISSUED | `已完成开票` / `已发放 License` |

### 13.2 焦点管理

- 对话框打开时，焦点移入对话框
- 对话框关闭时，焦点返回触发元素
- Tab 顺序遵循视觉顺序
- 使用 `AlertDialog` 组件的内置焦点管理

### 13.3 屏幕阅读器支持

- 状态变化使用 `aria-live="polite"` 通知
- 表单错误使用 `role="alert"` 通知
- 对话框使用 `aria-modal="true"` 和 `aria-labelledby`

---

## 十四、状态徽章语义扩展

### 14.1 新增状态展示

| 状态 | 语义色 | 图标 | 说明文案 |
|------|--------|------|----------|
| APPROVED（发票） | 成功 | ✓ | 审批通过，待开票 |
| APPROVED（License） | 成功 | ✓ | 审批通过，待发放 |
| ISSUED（发票） | 成功 | ✓ | 已开票 |
| ISSUED（License） | 成功 | ✓ | 已发放 |

### 14.2 视觉区分

```
APPROVED（待业务动作）：
  - 成功色背景 + 边框
  - 无填充勾选图标
  - 副标题："审批通过，可进行后续操作"

ISSUED（业务完成）：
  - 成功色填充背景
  - 填充勾选图标
  - 副标题："已完成开票" / "已发放 License"
```

---

## 十五、移动端体验设计

### 15.1 触控目标尺寸

遵循 `touch-target-size` 规范：

| 元素 | 最小尺寸 |
|------|----------|
| 开票按钮 | 44×44pt |
| 发放 License 按钮 | 44×44pt |
| 文件选择按钮 | 44×44pt |
| 确认/取消按钮 | 44×44pt |

### 15.2 移动端对话框适配

- 对话框宽度：`max-w-[90vw]`
- 内容区域滚动：独立滚动区域
- 安全区域：`pb-[env(safe-area-inset-bottom)]`
- 关闭方式：支持下滑关闭

### 15.3 文件上传移动端体验

```
┌─────────────────────────────────────────────────────┐
│  📄 点击选择文件                                     │
│     或拖拽文件到此处                                │
│                                                     │
│     支持 PDF/JPG/PNG/OFD                           │
│     最大 10MB                                       │
└─────────────────────────────────────────────────────┘
```

- 点击触发系统文件选择器
- 支持相机拍照（移动端）
- 上传进度实时显示

---

## 十六、按钮层级与变体

### 16.1 按钮优先级

在 APPROVED 状态下的操作区：

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│  [开票] 主操作                      [撤回] 次要操作 │
│                                                     │
└─────────────────────────────────────────────────────┘
```

| 按钮类型 | 变体 | 视觉权重 |
|----------|------|----------|
| 开票/发放 | `default` | 高（主操作） |
| 撤回 | `outline` | 低（次要操作） |

### 16.2 加载状态

按钮在操作进行中的状态：

- 显示 `Loader2` 旋转图标
- 按钮文案保持不变
- 禁用重复点击
- 使用 `aria-busy="true"` 标记

---

## 十七、设计规范参考

- 基础规范：`CRM-Docs/design-system/foundations/README.md`
- 组件契约：`CRM-Docs/design-system/components/README.md`
- 页面模式：`CRM-Docs/design-system/patterns/README.md`
- 审批中心：`CRM-Docs/design-system/patterns/approval-center.md`
- 审批通知：`CRM-Docs/design-system/components/approval-notification.md`
- 状态徽章：`CRM-Docs/design-system/components/status-badge.md`
- 按钮：`CRM-Docs/design-system/components/button.md`
- 模态框与抽屉：`CRM-Docs/design-system/components/modal-sheet.md`