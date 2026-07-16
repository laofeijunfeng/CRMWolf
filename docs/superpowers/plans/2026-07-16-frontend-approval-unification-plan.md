# 前端审批系统统一重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一审批系统入口，实现发票和 License 的两段式审批流程（审批通过后执行业务动作）

**Architecture:** 在 ApprovalProcessGeneric.vue 组件中新增 APPROVED 状态下的操作区，通过两个新对话框（InvoiceMarkIssuedDialog、LicenseIssueDialog）实现开票和 License 发放功能。删除废弃的旧审批入口和旧 API 方法。

**Tech Stack:** Vue 3 + TypeScript + Pinia + shadcn-vue + Zod + V2 Design Tokens

## Global Constraints

- 使用 V2 Design Tokens：`@use '@/styles/variables-v2.scss' as *`
- 使用 shadcn-vue 组件，禁用 Element Plus 新组件
- TypeScript 严格模式：禁止 `any` / `as any` / `@ts-ignore` / `!`
- 表单校验使用 Zod schema
- 触控目标最小 44×44pt
- 审批操作使用通用接口 `/v1/approvals/{entity_type}/{entity_id}/*`
- 无匹配审批流程时显示后端 400 错误，不提供"跳过审批"选项

---

## File Structure

### 需创建的文件
- `CRM-Client/src/components/dialogs/InvoiceMarkIssuedDialog.vue` — 发票开票对话框
- `CRM-Client/src/components/dialogs/LicenseIssueDialog.vue` — License 发放对话框
- `CRM-Client/tests/components/InvoiceMarkIssuedDialog.spec.ts` — 开票对话框单元测试
- `CRM-Client/tests/components/LicenseIssueDialog.spec.ts` — License 发放对话框单元测试

### 需修改的文件
- `CRM-Client/src/api/invoice.ts` — 新增 `markIssued` 方法
- `CRM-Client/src/api/licenseApplication.ts` — 新增 `issueLicense` 方法，删除旧审批方法
- `CRM-Client/src/api/approvalFlow.ts` — business_type 补充 LICENSE
- `CRM-Client/src/api/approvalGeneric.ts` — 删除免审批注释
- `CRM-Client/src/stores/approval.ts` — 删除免审批注释
- `CRM-Client/src/components/ApprovalProcessGeneric.vue` — 新增操作区
- `CRM-Client/src/views/ApprovalFlowForm.vue` — V2 重构 + business_type 必填
- `CRM-Client/src/router/index.ts` — 删除废弃路由

### 需删除的文件
- `CRM-Client/src/views/FinanceInvoiceApprovals.vue` — 废弃的发票审批入口
- `CRM-Client/src/components/InvoiceFileUpload.vue` — 使用旧 approve-with-file 接口

---

## Phase 1: API 层准备

### Task 1: 新增发票开票 API 方法

**Files:**
- Modify: `CRM-Client/src/api/invoice.ts`
- Test: `CRM-Client/tests/api/invoice.spec.ts`

**Interfaces:**
- Consumes: 无
- Produces: `markIssued(applicationId: number, data: { file?: File; invoice_number?: string }): Promise<InvoiceApplicationResponse>`

- [ ] **Step 1: 编写 API 方法**

在 `CRM-Client/src/api/invoice.ts` 末尾添加：

```typescript
/**
 * 发票开票（审批通过后调用）
 * @param applicationId 发票申请 ID
 * @param data 开票数据（文件和发票号均为可选）
 */
markIssued: (applicationId: number, data: { 
  file?: File
  invoice_number?: string 
}): Promise<InvoiceApplicationResponse> => {
  const formData = new FormData()
  if (data.file) {
    formData.append('file', data.file)
  }
  if (data.invoice_number) {
    formData.append('invoice_number', data.invoice_number)
  }
  return request.post<InvoiceApplicationResponse>(
    `/v1/invoice-applications/${applicationId}/mark-issued`,
    formData,
    {
      headers: { 'Content-Type': 'multipart/form-data' }
    }
  )
}
```

- [ ] **Step 2: 导出到 invoiceApi 对象**

在 `invoiceApi` 对象中添加 `markIssued` 方法：

```typescript
const invoiceApi = {
  // ... 现有方法
  markIssued // 新增
}
```

- [ ] **Step 3: 提交更改**

```bash
git add CRM-Client/src/api/invoice.ts
git commit -m "feat(api): add markIssued method for invoice post-approval action"
```

---

### Task 2: 新增 License 发放 API 方法

**Files:**
- Modify: `CRM-Client/src/api/licenseApplication.ts`
- Test: `CRM-Client/tests/api/licenseApplication.spec.ts`

**Interfaces:**
- Consumes: 无
- Produces: `issueLicense(applicationId: number, data: { license_info: string; comment?: string }): Promise<LicenseApplicationResponse>`

- [ ] **Step 1: 编写 API 方法**

在 `CRM-Client/src/api/licenseApplication.ts` 中添加：

```typescript
/**
 * 发放 License（审批通过后调用）
 * @param applicationId License 申请 ID
 * @param data 发放数据（license_info 必填）
 */
issueLicense: (applicationId: number, data: { 
  license_info: string
  comment?: string 
}): Promise<LicenseApplicationResponse> => {
  return request.post<LicenseApplicationResponse>(
    `/v1/license-applications/${applicationId}/issue`,
    data
  )
}
```

- [ ] **Step 2: 导出到 licenseApplicationApi 对象**

```typescript
const licenseApplicationApi = {
  // ... 现有方法
  issueLicense // 新增
}
```

- [ ] **Step 3: 提交更改**

```bash
git add CRM-Client/src/api/licenseApplication.ts
git commit -m "feat(api): add issueLicense method for license post-approval action"
```

---

### Task 3: 补充 approvalFlow 类型定义

**Files:**
- Modify: `CRM-Client/src/api/approvalFlow.ts`

**Interfaces:**
- Consumes: 无
- Produces: `business_type: 'CONTRACT' | 'PAYMENT' | 'INVOICE' | 'LICENSE'`

- [ ] **Step 1: 更新 ApprovalFlow 接口**

修改 `CRM-Client/src/api/approvalFlow.ts` 第 21 行：

```typescript
// 修改前
business_type: 'CONTRACT' | 'PAYMENT' | 'INVOICE' // 业务类型：合同/回款/发票

// 修改后
business_type: 'CONTRACT' | 'PAYMENT' | 'INVOICE' | 'LICENSE' // 业务类型：合同/回款/发票/License
```

- [ ] **Step 2: 提交更改**

```bash
git add CRM-Client/src/api/approvalFlow.ts
git commit -m "feat(api): add LICENSE to approvalFlow business_type"
```

---

### Task 4: 删除免审批注释

**Files:**
- Modify: `CRM-Client/src/api/approvalGeneric.ts`
- Modify: `CRM-Client/src/stores/approval.ts`

- [ ] **Step 1: 清理 approvalGeneric.ts 注释**

删除 `CRM-Client/src/api/approvalGeneric.ts` 中的注释：
- 第 45-46 行：删除 "PAYMENT/INVOICE 未匹配流程时后端直通返回 approval_id=0, status=APPROVED"
- 第 69-70 行：删除类似注释

- [ ] **Step 2: 清理 approval.ts 注释**

删除 `CRM-Client/src/stores/approval.ts` 中的注释：
- 第 67-68 行：删除 "PAYMENT/INVOICE 未匹配流程时后端直通返回 approval_id=0, status=APPROVED"

- [ ] **Step 3: 提交更改**

```bash
git add CRM-Client/src/api/approvalGeneric.ts CRM-Client/src/stores/approval.ts
git commit -m "refactor: remove bypass approval comments (backend no longer supports)"
```

---

## Phase 2: 新增对话框组件

### Task 5: 创建发票开票对话框

**Files:**
- Create: `CRM-Client/src/components/dialogs/InvoiceMarkIssuedDialog.vue`
- Create: `CRM-Client/tests/components/InvoiceMarkIssuedDialog.spec.ts`

**Interfaces:**
- Consumes: `invoiceApi.markIssued(applicationId, data)`
- Produces: emit `issued` 事件、emit `close` 事件

- [ ] **Step 1: 创建对话框组件骨架**

创建 `CRM-Client/src/components/dialogs/InvoiceMarkIssuedDialog.vue`：

```vue
<!--
  InvoiceMarkIssuedDialog — 发票开票对话框

  功能：
  - 文件上传（可选）
  - 发票号码输入（可选）
  - 调用 markIssued API
  - 成功后 emit issued 事件

  设计规范：
  - V2 Design Tokens
  - shadcn-vue 组件
  - 触控目标 ≥44pt
-->
<script setup lang="ts">
import { ref, computed } from 'vue'
import { toast } from 'vue-sonner'
import { FileUp, Loader2 } from 'lucide-vue-next'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription } from '@/components/ui/alert'
import invoiceApi from '@/api/invoice'

const props = defineProps<{
  open: boolean
  applicationId: number
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  issued: []
}>()

// 表单状态
const selectedFile = ref<File | null>(null)
const invoiceNumber = ref<string>('')
const submitting = ref<boolean>(false)
const error = ref<string>('')

// 文件校验
const ACCEPTED_TYPES = ['application/pdf', 'image/jpeg', 'image/png', 'application/ofd']
const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB

const handleFileChange = (event: Event): void => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  
  if (!file) return
  
  // 校验文件类型
  if (!ACCEPTED_TYPES.includes(file.type) && !file.name.endsWith('.ofd')) {
    error.value = '仅支持 PDF、JPG、PNG、OFD 格式'
    return
  }
  
  // 校验文件大小
  if (file.size > MAX_FILE_SIZE) {
    error.value = '文件大小不能超过 10MB'
    return
  }
  
  error.value = ''
  selectedFile.value = file
}

const clearFile = (): void => {
  selectedFile.value = null
  error.value = ''
}

const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// 提交
const handleSubmit = async (): Promise<void> => {
  if (submitting.value) return
  
  submitting.value = true
  error.value = ''
  
  try {
    await invoiceApi.markIssued(props.applicationId, {
      file: selectedFile.value || undefined,
      invoice_number: invoiceNumber.value.trim() || undefined
    })
    
    toast.success('已开票，发票文件已上传')
    emit('issued')
    emit('update:open', false)
    
    // 重置表单
    selectedFile.value = null
    invoiceNumber.value = ''
  } catch (err) {
    const e = err as { response?: { data?: { detail?: string } } }
    error.value = e.response?.data?.detail || '开票失败，请重试'
  } finally {
    submitting.value = false
  }
}

const handleClose = (): void => {
  emit('update:open', false)
}

// 计算属性
const canSubmit = computed<boolean>(() => !submitting.value && !error.value)
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="sm:max-w-[480px]">
      <DialogHeader>
        <DialogTitle>开票</DialogTitle>
        <DialogDescription>
          审批已通过，可进行开票操作
        </DialogDescription>
      </DialogHeader>

      <div class="space-y-4">
        <!-- 文件上传区 -->
        <div class="space-y-2">
          <Label class="flex items-center gap-2">
            发票文件
            <span class="text-muted-foreground text-xs">（可选）</span>
          </Label>
          
          <div v-if="!selectedFile" class="border-2 border-dashed rounded-lg p-6 text-center">
            <input
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.ofd"
              class="hidden"
              id="invoice-file"
              @change="handleFileChange"
            />
            <label
              for="invoice-file"
              class="cursor-pointer flex flex-col items-center gap-2"
            >
              <FileUp class="h-8 w-8 text-muted-foreground" />
              <span class="text-sm text-muted-foreground">
                点击或拖拽上传发票文件
              </span>
              <span class="text-xs text-muted-foreground">
                支持 PDF、JPG、PNG、OFD，最大 10MB
              </span>
            </label>
          </div>
          
          <div v-else class="flex items-center gap-2 p-3 bg-muted rounded-lg">
            <FileUp class="h-5 w-5 text-primary" />
            <span class="flex-1 text-sm truncate">{{ selectedFile.name }}</span>
            <span class="text-xs text-muted-foreground">{{ formatFileSize(selectedFile.size) }}</span>
            <Button variant="ghost" size="sm" @click="clearFile">移除</Button>
          </div>
        </div>

        <!-- 发票号码 -->
        <div class="space-y-2">
          <Label class="flex items-center gap-2">
            发票号码
            <span class="text-muted-foreground text-xs">（可选）</span>
          </Label>
          <Input
            v-model="invoiceNumber"
            placeholder="输入发票号码便于查询"
            maxlength="100"
          />
        </div>

        <!-- 错误提示 -->
        <Alert v-if="error" variant="destructive">
          <AlertDescription>{{ error }}</AlertDescription>
        </Alert>

        <!-- 提示信息 -->
        <p class="text-xs text-muted-foreground">
          ℹ️ 开票后状态将变更为"已开票"，此操作不可撤销
        </p>
      </div>

      <DialogFooter>
        <Button variant="ghost" @click="handleClose">取消</Button>
        <Button 
          :disabled="!canSubmit" 
          @click="handleSubmit"
        >
          <Loader2 v-if="submitting" class="mr-2 h-4 w-4 animate-spin" />
          确认开票
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
```

- [ ] **Step 2: 提交更改**

```bash
git add CRM-Client/src/components/dialogs/InvoiceMarkIssuedDialog.vue
git commit -m "feat(dialog): add InvoiceMarkIssuedDialog for post-approval invoice action"
```

---

### Task 6: 创建 License 发放对话框

**Files:**
- Create: `CRM-Client/src/components/dialogs/LicenseIssueDialog.vue`
- Create: `CRM-Client/tests/components/LicenseIssueDialog.spec.ts`

**Interfaces:**
- Consumes: `licenseApplicationApi.issueLicense(applicationId, data)`
- Produces: emit `issued` 事件、emit `close` 事件

- [ ] **Step 1: 创建对话框组件**

创建 `CRM-Client/src/components/dialogs/LicenseIssueDialog.vue`：

```vue
<!--
  LicenseIssueDialog — License 发放对话框

  功能：
  - License 信息文本框（必填）
  - 备注输入（可选）
  - 调用 issueLicense API
  - 成功后 emit issued 事件

  设计规范：
  - V2 Design Tokens
  - shadcn-vue 组件
  - 触控目标 ≥44pt
-->
<script setup lang="ts">
import { ref, computed } from 'vue'
import { toast } from 'vue-sonner'
import { Loader2 } from 'lucide-vue-next'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription } from '@/components/ui/alert'
import licenseApplicationApi from '@/api/licenseApplication'

const props = defineProps<{
  open: boolean
  applicationId: number
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  issued: []
}>()

// 表单状态
const licenseInfo = ref<string>('')
const comment = ref<string>('')
const submitting = ref<boolean>(false)
const error = ref<string>('')

// 提交
const handleSubmit = async (): Promise<void> => {
  if (submitting.value) return
  if (!licenseInfo.value.trim()) {
    error.value = '请输入 License 信息'
    return
  }
  
  submitting.value = true
  error.value = ''
  
  try {
    await licenseApplicationApi.issueLicense(props.applicationId, {
      license_info: licenseInfo.value.trim(),
      comment: comment.value.trim() || undefined
    })
    
    toast.success('已发放 License，License 信息已写入')
    emit('issued')
    emit('update:open', false)
    
    // 重置表单
    licenseInfo.value = ''
    comment.value = ''
  } catch (err) {
    const e = err as { response?: { data?: { detail?: string } } }
    error.value = e.response?.data?.detail || '发放失败，请重试'
  } finally {
    submitting.value = false
  }
}

const handleClose = (): void => {
  emit('update:open', false)
}

// 计算属性
const canSubmit = computed<boolean>(() => 
  !submitting.value && licenseInfo.value.trim().length > 0
)
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="sm:max-w-[520px]">
      <DialogHeader>
        <DialogTitle>发放 License</DialogTitle>
        <DialogDescription>
          审批已通过，可进行发放操作
        </DialogDescription>
      </DialogHeader>

      <div class="space-y-4">
        <!-- License 信息 -->
        <div class="space-y-2">
          <Label>
            License 信息
            <span class="text-destructive">*</span>
          </Label>
          <Textarea
            v-model="licenseInfo"
            placeholder="粘贴完整的 License 信息..."
            :rows="6"
            :maxlength="10000"
            class="font-mono text-xs"
          />
          <p class="text-xs text-muted-foreground text-right">
            {{ licenseInfo.length }} / 10000
          </p>
        </div>

        <!-- 备注 -->
        <div class="space-y-2">
          <Label class="flex items-center gap-2">
            备注
            <span class="text-muted-foreground text-xs">（可选）</span>
          </Label>
          <Textarea
            v-model="comment"
            placeholder="输入备注..."
            :rows="2"
            :maxlength="500"
          />
        </div>

        <!-- 错误提示 -->
        <Alert v-if="error" variant="destructive">
          <AlertDescription>{{ error }}</AlertDescription>
        </Alert>

        <!-- 提示信息 -->
        <p class="text-xs text-muted-foreground">
          ℹ️ 发放后状态将变更为"已发放"，此操作不可撤销
        </p>
      </div>

      <DialogFooter>
        <Button variant="ghost" @click="handleClose">取消</Button>
        <Button 
          :disabled="!canSubmit" 
          @click="handleSubmit"
        >
          <Loader2 v-if="submitting" class="mr-2 h-4 w-4 animate-spin" />
          确认发放
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
```

- [ ] **Step 2: 提交更改**

```bash
git add CRM-Client/src/components/dialogs/LicenseIssueDialog.vue
git commit -m "feat(dialog): add LicenseIssueDialog for post-approval license action"
```

---

## Phase 3: 核心组件改造

### Task 7: 改造 ApprovalProcessGeneric.vue

**Files:**
- Modify: `CRM-Client/src/components/ApprovalProcessGeneric.vue`

**Interfaces:**
- Consumes: `InvoiceMarkIssuedDialog`、`LicenseIssueDialog`
- Produces: 显示 APPROVED 状态下的操作按钮

- [ ] **Step 1: 导入新对话框组件**

在 `<script setup>` 顶部添加导入：

```typescript
import InvoiceMarkIssuedDialog from '@/components/dialogs/InvoiceMarkIssuedDialog.vue'
import LicenseIssueDialog from '@/components/dialogs/LicenseIssueDialog.vue'
```

- [ ] **Step 2: 添加计算属性**

在现有计算属性后添加：

```typescript
// 发票开票按钮显示条件
const showMarkIssued = computed<boolean>(() =>
  props.entityType === 'INVOICE' &&
  status.value === 'APPROVED' &&
  props.canApprove
)

// License 发放按钮显示条件
const showIssueLicense = computed<boolean>(() =>
  props.entityType === 'LICENSE' &&
  status.value === 'APPROVED' &&
  props.canApprove
)
```

- [ ] **Step 3: 添加对话框状态**

```typescript
// 开票对话框
const markIssuedDialogVisible = ref<boolean>(false)

// License 发放对话框
const issueLicenseDialogVisible = ref<boolean>(false)

// 打开对话框方法
const openMarkIssuedDialog = (): void => {
  markIssuedDialogVisible.value = true
}

const openIssueDialog = (): void => {
  issueLicenseDialogVisible.value = true
}

// 对话框成功回调
const onMarkIssuedSuccess = (): void => {
  markIssuedDialogVisible.value = false
  emit('approved') // 复用 approved 事件刷新状态
  loadDetail()
}

const onIssueSuccess = (): void => {
  issueLicenseDialogVisible.value = false
  emit('approved')
  loadDetail()
}
```

- [ ] **Step 4: 添加模板内容**

在 `approval-process-generic__actions` div 内的操作按钮后添加：

```vue
<!-- 发票开票区 -->
<div v-if="showMarkIssued" class="mark-issued-section">
  <p class="text-sm text-muted-foreground mb-2">审批已通过，可进行开票操作</p>
  <Button 
    data-testid="mark-issued-btn"
    aria-label="开票，审批已通过"
    @click="openMarkIssuedDialog"
  >
    开票
  </Button>
</div>

<!-- License 发放区 -->
<div v-if="showIssueLicense" class="issue-license-section">
  <p class="text-sm text-muted-foreground mb-2">审批已通过，可进行发放操作</p>
  <Button 
    data-testid="issue-license-btn"
    aria-label="发放 License，审批已通过"
    @click="openIssueDialog"
  >
    发放 License
  </Button>
</div>

<!-- 发票开票对话框 -->
<InvoiceMarkIssuedDialog
  v-model:open="markIssuedDialogVisible"
  :application-id="entityId"
  @issued="onMarkIssuedSuccess"
/>

<!-- License 发放对话框 -->
<LicenseIssueDialog
  v-model:open="issueLicenseDialogVisible"
  :application-id="entityId"
  @issued="onIssueSuccess"
/>
```

- [ ] **Step 5: 添加样式**

在 `<style>` 块中添加：

```scss
// 开票/发放操作区
.mark-issued-section,
.issue-license-section {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: $wolf-space-sm-v2;
  padding-top: $wolf-space-md-v2;
  border-top: 1px solid $wolf-border-light-v2;
  margin-top: $wolf-space-md-v2;
}
```

- [ ] **Step 6: 提交更改**

```bash
git add CRM-Client/src/components/ApprovalProcessGeneric.vue
git commit -m "feat(approval): add mark-issued and issue-license actions for APPROVED status"
```

---

### Task 8: 删除废弃的 licenseApplication 方法

**Files:**
- Modify: `CRM-Client/src/api/licenseApplication.ts`

- [ ] **Step 1: 删除旧审批方法**

删除以下方法：
- `approveApplication`
- `approveApplicationFull`
- `rejectApplication`

在文件中找到并删除：

```typescript
// 删除这些方法
approveApplication: (applicationId: number, data: LicenseApplicationApprove) => {
  return request.post<LicenseApplicationResponse>(`/v1/license-applications/${applicationId}/approve`, data)
},

approveApplicationFull: (applicationId: number, data: LicenseApplicationApproveFull) => {
  return request.post<LicenseApplicationResponse>(`/v1/license-applications/${applicationId}/approve-full`, data)
},

rejectApplication: (applicationId: number, reason: string) => {
  return request.post<LicenseApplicationResponse>(`/v1/license-applications/${applicationId}/reject`, null, {
    params: { reason }
  })
},
```

同时删除对应的类型定义：

```typescript
// 删除这些类型
export interface LicenseApplicationApprove {
  license_code: string
}

export interface LicenseApplicationApproveFull {
  license_info: string
  comment?: string | null
}
```

- [ ] **Step 2: 提交更改**

```bash
git add CRM-Client/src/api/licenseApplication.ts
git commit -m "refactor(api): remove deprecated license approval methods (use generic approval API)"
```

---

## Phase 4: 配置页重构

### Task 9: 重构 ApprovalFlowForm.vue 到 V2 规范

**Files:**
- Modify: `CRM-Client/src/views/ApprovalFlowForm.vue`

**Interfaces:**
- Consumes: 无变化
- Produces: V2 设计规范表单，business_type 必填无默认值

- [ ] **Step 1: 更新 business_type 默认值**

找到 `form` 的初始化，修改：

```typescript
// 修改前
const form = ref<ApprovalFlow & { nodes: NodeWithRequired[] }>({
  flow_name: '',
  flow_code: '',
  description: '',
  min_amount: null,
  max_amount: null,
  license_type: '',
  business_type: 'CONTRACT',  // 删除默认值
  is_active: 1,
  nodes: []
})

// 修改后
const form = ref<ApprovalFlow & { nodes: NodeWithRequired[] }>({
  flow_name: '',
  flow_code: '',
  description: '',
  min_amount: null,
  max_amount: null,
  license_type: '',
  business_type: '' as 'CONTRACT' | 'PAYMENT' | 'INVOICE' | 'LICENSE' | '',  // 无默认值
  is_active: 1,
  nodes: []
})
```

- [ ] **Step 2: 更新表单校验规则**

在 `rules` 对象中添加 business_type 校验：

```typescript
const rules = {
  flow_name: [
    { required: true, message: '请输入流程名称' }
  ],
  flow_code: [
    { required: true, message: '请输入流程编码' },
    { pattern: /^[A-Z_][A-Z0-9_]*$/, message: '流程编码只能包含大写字母、数字和下划线，且必须以字母或下划线开头' }
  ],
  // 新增 business_type 校验
  business_type: [
    { required: true, message: '请选择适用单据类型', trigger: 'change' }
  ]
}
```

- [ ] **Step 3: 更新模板中的 RadioGroup**

确保 `business_type` 的 RadioGroup 没有预选值：

```vue
<el-form-item label="适用单据" prop="business_type" required>
  <el-radio-group v-model="form.business_type">
    <el-radio value="CONTRACT">合同</el-radio>
    <el-radio value="PAYMENT">回款登记</el-radio>
    <el-radio value="INVOICE">发票申请</el-radio>
    <el-radio value="LICENSE">License申请</el-radio>
  </el-radio-group>
  <div class="form-item-extra">
    <div style="color: var(--el-text-color-secondary); font-size: 12px;">
      选择该流程适用的业务单据类型
    </div>
  </div>
</el-form-item>
```

- [ ] **Step 4: 提交更改**

```bash
git add CRM-Client/src/views/ApprovalFlowForm.vue
git commit -m "feat(approval-flow): make business_type required without default, add LICENSE option"
```

---

### Task 10: 迁移 ApprovalFlowForm.vue 样式到 V2

**Files:**
- Modify: `CRM-Client/src/views/ApprovalFlowForm.vue`

- [ ] **Step 1: 更新样式导入**

```scss
// 修改前
@use '@/styles/variables.scss' as *;

// 修改后
@use '@/styles/variables-v2.scss' as *;
```

- [ ] **Step 2: 更新样式变量**

替换所有旧变量为新变量：

| 旧变量 | 新变量 |
|--------|--------|
| `$wolf-bg-page` | `$wolf-bg-page-v2` |
| `$wolf-bg-card` | `$wolf-bg-card-v2` |
| `$wolf-border-light` | `$wolf-border-light-v2` |
| `$wolf-text-primary` | `$wolf-text-primary-v2` |
| `$wolf-text-secondary` | `$wolf-text-secondary-v2` |
| `$wolf-text-tertiary` | `$wolf-text-tertiary-v2` |
| `$wolf-space-xs` | `$wolf-space-xs-v2` |
| `$wolf-space-sm` | `$wolf-space-sm-v2` |
| `$wolf-space-md` | `$wolf-space-md-v2` |
| `$wolf-space-lg` | `$wolf-space-lg-v2` |
| `$wolf-card-padding` | `$wolf-card-padding-v2` |
| `$wolf-radius-md` | `$wolf-radius-md-v2` |
| `$wolf-shadow-card` | `$wolf-shadow-card-v2` |
| `$wolf-font-size-caption` | `$wolf-font-size-caption-v2` |
| `$wolf-font-weight-medium` | `$wolf-font-weight-medium-v2` |
| `$wolf-font-weight-semibold` | `$wolf-font-weight-semibold-v2` |

- [ ] **Step 3: 提交更改**

```bash
git add CRM-Client/src/views/ApprovalFlowForm.vue
git commit -m "style(approval-flow): migrate to V2 design tokens"
```

---

## Phase 5: 清理废弃代码

### Task 11: 删除 FinanceInvoiceApprovals.vue

**Files:**
- Delete: `CRM-Client/src/views/FinanceInvoiceApprovals.vue`

- [ ] **Step 1: 删除文件**

```bash
git rm CRM-Client/src/views/FinanceInvoiceApprovals.vue
```

- [ ] **Step 2: 提交更改**

```bash
git commit -m "refactor: remove deprecated FinanceInvoiceApprovals page (use ApprovalCenter)"
```

---

### Task 12: 删除 InvoiceFileUpload.vue

**Files:**
- Delete: `CRM-Client/src/components/InvoiceFileUpload.vue`

- [ ] **Step 1: 删除文件**

```bash
git rm CRM-Client/src/components/InvoiceFileUpload.vue
```

- [ ] **Step 2: 提交更改**

```bash
git commit -m "refactor: remove deprecated InvoiceFileUpload (uses old approve-with-file API)"
```

---

### Task 13: 清理 fileUpload.ts 废弃方法

**Files:**
- Modify: `CRM-Client/src/api/fileUpload.ts`

- [ ] **Step 1: 删除废弃方法**

删除以下函数：
- `approveInvoiceWithFile`
- `approveInvoiceWithFileProgress`
- `getInvoiceFileUrl`

```typescript
// 删除这些函数
export async function approveInvoiceWithFile(...) { ... }
export async function approveInvoiceWithFileProgress(...) { ... }
export function getInvoiceFileUrl(...) { ... }
```

- [ ] **Step 2: 提交更改**

```bash
git add CRM-Client/src/api/fileUpload.ts
git commit -m "refactor(api): remove deprecated invoice approval methods from fileUpload"
```

---

### Task 14: 清理路由配置

**Files:**
- Modify: `CRM-Client/src/router/index.ts`

- [ ] **Step 1: 删除废弃路由**

找到并删除 `FinanceInvoiceApprovals` 相关路由：

```typescript
// 删除这行
{ path: '/finance/invoice-approvals', name: 'FinanceInvoiceApprovals', component: () => import('@/views/FinanceInvoiceApprovals.vue') }
```

- [ ] **Step 2: 确保 ApprovalCenter 路由存在**

```typescript
// 审批中心
{
  path: '/approvals',
  name: 'Approvals',
  component: () => import('@/views/ApprovalCenter.vue'),
  meta: { title: '审批中心' }
}
```

- [ ] **Step 3: 提交更改**

```bash
git add CRM-Client/src/router/index.ts
git commit -m "refactor(router): remove deprecated invoice approvals route"
```

---

## Phase 6: 测试验证

### Task 15: 验证发票审批流程

**Files:**
- Test: 手动端到端测试

- [ ] **Step 1: 创建测试发票申请**

1. 登录系统
2. 进入客户详情页
3. 创建发票申请
4. 确认状态为 DRAFT

- [ ] **Step 2: 提交审批**

1. 点击"提交审批"
2. 确认状态变为 PENDING_REVIEW

- [ ] **Step 3: 审批通过**

1. 切换到有审批权限的账号
2. 进入审批中心
3. 找到该发票审批
4. 点击"同意"
5. 确认状态变为 APPROVED
6. 确认显示"开票"按钮

- [ ] **Step 4: 开票**

1. 点击"开票"
2. 上传发票文件（可选）
3. 输入发票号码（可选）
4. 点击"确认开票"
5. 确认状态变为 ISSUED
6. 确认 toast 显示"已开票"

- [ ] **Step 5: 验证错误处理**

1. 尝试重复开票
2. 确认显示错误提示
3. 尝试上传超过 10MB 的文件
4. 确认显示"文件大小不能超过 10MB"

---

### Task 16: 验证 License 审批流程

**Files:**
- Test: 手动端到端测试

- [ ] **Step 1: 创建测试 License 申请**

1. 进入客户详情页
2. 点击 License 管理 Tab
3. 创建 License 申请
4. 确认状态为 DRAFT

- [ ] **Step 2: 提交审批**

1. 点击"提交申请"
2. 确认状态变为 PENDING

- [ ] **Step 3: 审批通过**

1. 切换到有审批权限的账号
2. 进入审批中心
3. 找到该 License 审批
4. 点击"同意"
5. 确认状态变为 APPROVED
6. 确认显示"发放 License"按钮

- [ ] **Step 4: 发放 License**

1. 点击"发放 License"
2. 输入 License 信息（必填）
3. 输入备注（可选）
4. 点击"确认发放"
5. 确认状态变为 ISSUED
6. 确认 toast 显示"已发放 License"

- [ ] **Step 5: 验证错误处理**

1. 不输入 License 信息点击确认
2. 确认禁用提交按钮
3. 尝试重复发放
4. 确认显示错误提示

---

### Task 17: 验证审批流程配置

**Files:**
- Test: 手动端到端测试

- [ ] **Step 1: 创建新流程**

1. 进入系统配置
2. 点击"审批流程管理"
3. 点击"创建流程"
4. 不选择"适用单据"
5. 点击"创建"
6. 确认显示"请选择适用单据类型"

- [ ] **Step 2: 选择 LICENSE 类型**

1. 选择"适用单据"为"License申请"
2. 填写其他必填项
3. 点击"创建"
4. 确认创建成功

- [ ] **Step 3: 编辑流程**

1. 点击刚创建的流程
2. 修改流程名称
3. 点击"保存"
4. 确认保存成功

---

## 完成确认

所有任务完成后，运行以下检查：

```bash
# 类型检查
cd CRM-Client && npm run type-check

# 代码校验
npm run lint

# 单元测试
npm run test:unit

# 构建验证
npm run build
```

确认无错误后，合并分支到 main。