# 发票文件下载功能修复 + UI 优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复发票文件下载按钮不显示的 bug，并为销售人员提供便捷的下载入口（列表页 + 详情页）。

**Architecture:** 
- 后端：修复 `_populate_application_info()` 函数，返回 `InvoiceApplicationResponse` 类型并包含缺失字段
- 前端：列表页申请单号列增加下载徽章（ISSUED 状态）；详情页 ISSUED 状态下显示高亮文件区域

**Tech Stack:** Python 3.11 / FastAPI / Pydantic / Vue 3 / TypeScript / Element Plus / SCSS

## Global Constraints

- **team_id 必传**：所有 CRUD 操作必须传 team_id（CRM-Server/CLAUDE.md 红线）
- **Pydantic 强制校验**：所有外部输入必须校验，禁止裸 dict
- **TypeScript 四禁令**：前端禁用 `any` `as any` `@ts-ignore` `!`
- **UX touch-target-size**：下载徽章最小 44×44px
- **UX aria-labels**：下载徽章必须有 aria-label

---

## File Structure

**后端修改**
- `CRM-Server/app/api/invoices.py` — `_populate_application_info()` 返回类型改为 `InvoiceApplicationResponse`

**前端修改**
- `CRM-Client/src/views/Invoices.vue` — 申请单号列增加下载徽章
- `CRM-Client/src/views/InvoiceDetail.vue` — ISSUED 状态下添加高亮文件区域

---

## Phase A — 后端 Bug 修复

### Task 1: 修复 `_populate_application_info()` 返回缺失字段

**Files:**
- Modify: `CRM-Server/app/api/invoices.py:421-486`

**Interfaces:**
- Consumes: `InvoiceApplicationResponse` Schema（已存在于 `app/schemas/invoice.py`）
- Produces: `_populate_application_info()` 返回 `InvoiceApplicationResponse`，包含 `invoice_file_path`, `invoice_number`, `issued_time`

- [ ] **Step 1: 添加 import**

```python
# 在文件顶部 import 区域添加（如果尚未存在）
from app.schemas.invoice import InvoiceApplicationResponse
```

- [ ] **Step 2: 修改函数返回类型声明**

```python
# 将 line 421 的函数签名改为：
def _populate_application_info(db: Session, application, team_id: Optional[int] = None) -> InvoiceApplicationResponse:
    """填充发票申请完整响应信息
    
    Changes:
    - 返回 InvoiceApplicationResponse（而非 dict）类型安全
    - 添加 invoice_file_path / invoice_number / issued_time（修复 bug）
    """
```

- [ ] **Step 3: 添加申请人/审批人名称查询逻辑**

```python
# 替换 lines 476-484 的查询逻辑（改为提前查询）
# 查询申请人/审批人名称
applicant_name = None
reviewer_name = None
if application.applicant_id:
    applicant = db.query(User).filter(User.id == int(application.applicant_id)).first()
    if applicant:
        applicant_name = applicant.name
if application.reviewer_id:
    reviewer = db.query(User).filter(User.id == int(application.reviewer_id)).first()
    if reviewer:
        reviewer_name = reviewer.name
```

- [ ] **Step 4: 替换 dict 返回为 Pydantic Schema**

```python
# 替换 lines 442-474 的 result = {...} 为：
return InvoiceApplicationResponse(
    id=application.id,
    application_number=application.application_number,
    customer_id=application.customer_id,
    contract_id=application.contract_id,
    opportunity_id=application.opportunity_id,
    payment_plan_id=application.payment_plan_id,
    invoice_title_id=application.invoice_title_id,
    invoice_amount=float(application.invoice_amount),
    invoice_type=application.invoice_type,
    status=application.status,
    applicant_id=application.applicant_id,
    reviewer_id=application.reviewer_id,
    review_comment=application.review_comment,
    reviewed_time=application.reviewed_time,
    payment_record_id=application.payment_record_id,
    invoice_title_type=application.invoice_title_type,
    invoice_title_text=application.invoice_title_text,
    invoice_taxpayer_id=application.invoice_taxpayer_id,
    invoice_bank_name=application.invoice_bank_name,
    invoice_bank_account=application.invoice_bank_account,
    invoice_address=application.invoice_address,
    invoice_phone=application.invoice_phone,
    created_time=application.created_time,
    last_modified_time=application.last_modified_time,
    
    # 🐛 Bug 修复：添加三个缺失字段
    invoice_file_path=application.invoice_file_path,
    invoice_number=application.invoice_number,
    issued_time=application.issued_time,
    
    # 关联业务信息
    customer_name=customer.account_name if customer else None,
    contract_name=contract.contract_name if contract else None,
    opportunity_name=opportunity.opportunity_name if opportunity else None,
    payment_plan_stage_name=payment_plan.stage_name if payment_plan else None,
    invoice_title_title=application.invoice_title_text,
    applicant_name=applicant_name,
    reviewer_name=reviewer_name,
)
```

- [ ] **Step 5: 删除原有的 result["applicant_name"] / result["reviewer_name"] 赋值逻辑**

```python
# 删除 lines 476-484 的以下代码（已在上一步提前查询）：
# if application.applicant_id:
#     applicant = db.query(User)...
#     result["applicant_name"] = applicant.name
# if application.reviewer_id:
#     reviewer = db.query(User)...
#     result["reviewer_name"] = reviewer.name
# return result
```

- [ ] **Step 6: 验证后端类型检查**

Run: `cd CRM-Server && mypy app/api/invoices.py --no-error-summary`
Expected: 无类型错误

- [ ] **Step 7: Commit**

```bash
git add CRM-Server/app/api/invoices.py
git commit -m "fix(invoice): add missing invoice_file_path fields in _populate_application_info - Task 1"
```

---

## Phase B — 前端列表页增强

### Task 2: 申请单号列增加下载徽章（模板）

**Files:**
- Modify: `CRM-Client/src/views/Invoices.vue:73-77`

**Interfaces:**
- Consumes: `InvoiceApplicationResponse` 类型（已存在），`getInvoiceFileUrl` 函数（已存在于 `@/api/fileUpload.ts`）
- Produces: 下载徽章组件（`<span class="download-badge">`）

- [ ] **Step 1: 添加 Download icon import**

```typescript
// 在 script setup 的 import 区域添加
import { Download } from '@element-plus/icons-vue'
import { getInvoiceFileUrl } from '@/api/fileUpload'
import { ElMessage } from 'element-plus'
```

- [ ] **Step 2: 修改申请单号列模板**

```vue
<!-- 替换 lines 73-77 的 el-table-column -->
<el-table-column label="申请单号" min-width="220">
  <template #default="{ row }">
    <div class="application-number-cell">
      <span class="link-text" @click="handleViewDetail(row)">
        {{ row.application_number }}
      </span>
      <!-- ISSUED 状态 + 有文件：显示下载入口 -->
      <span 
        v-if="row.status === 'ISSUED' && row.invoice_file_path" 
        class="download-badge"
        role="button"
        aria-label="下载发票文件"
        tabindex="0"
        @click.stop="downloadInvoiceFile(row)"
        @keydown.enter="downloadInvoiceFile(row)"
      >
        <el-icon class="download-icon"><Download /></el-icon>
        <span class="download-link">下载</span>
      </span>
    </div>
  </template>
</el-table-column>
```

- [ ] **Step 3: Commit**

```bash
git add CRM-Client/src/views/Invoices.vue
git commit -m "feat(invoices): add download badge template in application_number column - Task 2"
```

---

### Task 3: 添加下载函数 + Toast 提示

**Files:**
- Modify: `CRM-Client/src/views/Invoices.vue` (script setup 区域)

**Interfaces:**
- Consumes: `getInvoiceFileUrl(row.id)` 返回下载 URL
- Produces: `downloadInvoiceFile(row)` 函数

- [ ] **Step 1: 添加下载函数**

```typescript
// 在 script setup 中添加函数（在 handleMarkInvoiced 之后）
/**
 * 直接下载发票文件（列表页）
 * UX: loading-states - 添加 Toast 提示
 */
const downloadInvoiceFile = (row: InvoiceApplicationResponse): void => {
  ElMessage.success({
    message: '正在下载发票文件',
    duration: 1500
  })
  const url = getInvoiceFileUrl(row.id)
  window.open(url, '_blank')
}
```

- [ ] **Step 2: 验证 TypeScript 类型检查**

Run: `cd CRM-Client && npm run type-check`
Expected: 无类型错误

- [ ] **Step 3: Commit**

```bash
git add CRM-Client/src/views/Invoices.vue
git commit -m "feat(invoices): add downloadInvoiceFile function with toast feedback - Task 3"
```

---

### Task 4: 添加下载徽章样式（含 UX 规则）

**Files:**
- Modify: `CRM-Client/src/views/Invoices.vue` (style 区域)

**Interfaces:**
- Consumes: `$wolf-*` Design Tokens
- Produces: `.download-badge` 样式类

- [ ] **Step 1: 添加 application-number-cell 样式**

```scss
// 在 style 区域末尾添加（在 .amount 之后）

// 下载徽章容器
.application-number-cell {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;  // UX: touch-spacing ≥ 8px
}
```

- [ ] **Step 2: 添加 download-badge 样式（含 UX 规则）**

```scss
// 下载徽章（含 UX 规则）
.download-badge {
  // UX: touch-target-size (CRITICAL) - 最小 44px 高度
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 44px;  // 扩展 hitSlop
  min-width: 44px;
  padding: 8px 12px;  // 增大 padding 以满足 44px
  background: $wolf-success-bg;
  border-radius: $wolf-radius-sm;
  font-size: $wolf-font-size-caption;
  cursor: pointer;  // UX: cursor-pointer
  transition: all 0.15s ease-out;  // UX: duration-timing 150ms
  
  .download-icon {
    color: $wolf-success-text;
    font-size: 14px;
  }
  
  .download-link {
    color: $wolf-success-text;
    font-weight: $wolf-font-weight-medium;
  }
  
  // UX: hover-vs-tap (HIGH) - hover 状态
  &:hover {
    background: $wolf-success-border;
    transform: translateY(-1px);
  }
  
  // UX: press-feedback (HIGH) - active/pressed 状态
  &:active {
    transform: scale(0.95);
    opacity: 0.9;
  }
  
  // UX: focus-states (CRITICAL) - focus ring
  &:focus-visible {
    outline: 2px solid $wolf-primary;
    outline-offset: 2px;
  }
  
  // UX: reduced-motion (MEDIUM)
  @media (prefers-reduced-motion: reduce) {
    transition: none;
    transform: none;
    
    &:hover, &:active {
      transform: none;
    }
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add CRM-Client/src/views/Invoices.vue
git commit -m "feat(invoices): add download-badge styles with UX rules - Task 4"
```

---

## Phase C — 前端详情页优化

### Task 5: ISSUED 状态下添加高亮文件区域（模板）

**Files:**
- Modify: `CRM-Client/src/views/InvoiceDetail.vue:97-99`

**Interfaces:**
- Consumes: `invoiceInfo.invoice_file_path`, `invoiceInfo.invoice_number`
- Produces: `.issued-file-highlight` 高亮区域组件

- [ ] **Step 1: 添加 CircleCheckFilled, Picture icon import**

```typescript
// 在 script setup 的 import 区域修改（添加 Picture）
import {
  User,
  Document,
  Clock,
  Avatar,
  Calendar,
  Ticket,
  OfficeBuilding,
  Key,
  CreditCard,
  Wallet,
  Location,
  Phone,
  Download,
  CircleCheckFilled,
  Picture
} from '@element-plus/icons-vue'
```

- [ ] **Step 2: 在 info-bottom 区域之后添加高亮文件区域**

```vue
<!-- 在 line 99 (</div> of info-bottom) 之后添加 -->

<!-- ISSUED 状态专属：已开票文件高亮区域 -->
<div 
  v-if="invoiceInfo?.status === 'ISSUED' && invoiceInfo?.invoice_file_path" 
  class="issued-file-highlight"
>
  <div class="highlight-header">
    <el-icon class="success-icon"><CircleCheckFilled /></el-icon>
    <span class="highlight-title">已开票</span>
    <span v-if="invoiceInfo?.invoice_number" class="invoice-number-badge">
      {{ invoiceInfo.invoice_number }}
    </span>
  </div>
  <div class="file-download-area">
    <el-icon :class="['file-type-icon', getFileIconClass(invoiceInfo.invoice_file_path)]">
      <Document v-if="isPdf(invoiceInfo.invoice_file_path)" />
      <Picture v-else />
    </el-icon>
    <span class="file-type-label">{{ getFileTypeLabel(invoiceInfo.invoice_file_path) }}</span>
    <el-button 
      type="primary" 
      class="download-btn" 
      aria-label="下载发票文件"
      @click="handleDownloadWithFeedback"
    >
      <el-icon><Download /></el-icon>
      下载发票文件
    </el-button>
  </div>
</div>
```

- [ ] **Step 3: Commit**

```bash
git add CRM-Client/src/views/InvoiceDetail.vue
git commit -m "feat(invoice-detail): add issued-file-highlight template - Task 5"
```

---

### Task 6: 添加文件类型判断辅助函数

**Files:**
- Modify: `CRM-Client/src/views/InvoiceDetail.vue` (script setup 区域)

**Interfaces:**
- Consumes: `invoiceInfo.invoice_file_path` 字符串
- Produces: `isPdf(filePath)`, `getFileIconClass(filePath)`, `getFileTypeLabel(filePath)` 函数

- [ ] **Step 1: 添加辅助函数**

```typescript
// 在 script setup 中添加（在 downloadInvoiceFile 函数之后）

/**
 * 判断是否为 PDF 文件
 */
const isPdf = (filePath: string | null): boolean => {
  if (!filePath) return false
  return filePath.toLowerCase().endsWith('.pdf')
}

/**
 * 获取文件图标类名
 */
const getFileIconClass = (filePath: string | null): string => {
  if (!filePath) return 'default-icon'
  const ext = filePath.toLowerCase().split('.').pop()
  const classMap: Record<string, string> = {
    'pdf': 'pdf-icon',
    'jpg': 'image-icon',
    'jpeg': 'image-icon',
    'png': 'image-icon',
    'ofd': 'ofd-icon',
  }
  return classMap[ext ?? ''] ?? 'default-icon'
}

/**
 * 获取文件类型标签
 */
const getFileTypeLabel = (filePath: string | null): string => {
  if (!filePath) return '发票文件'
  const ext = filePath.toLowerCase().split('.').pop()
  const labelMap: Record<string, string> = {
    'pdf': 'PDF 发票',
    'jpg': '图片发票 (JPG)',
    'jpeg': '图片发票 (JPEG)',
    'png': '图片发票 (PNG)',
    'ofd': 'OFD 电子发票',
  }
  return labelMap[ext ?? ''] ?? '发票文件'
}

/**
 * 下载发票文件（带 Toast 反馈）
 * UX: success-feedback - 下载成功有提示
 */
const handleDownloadWithFeedback = (): void => {
  if (!invoiceInfo.value) return
  
  ElMessage.success({
    message: '发票文件下载成功',
    duration: 2000
  })
  
  downloadInvoiceFile()
}
```

- [ ] **Step 2: 验证 TypeScript 类型检查**

Run: `cd CRM-Client && npm run type-check`
Expected: 无类型错误

- [ ] **Step 3: Commit**

```bash
git add CRM-Client/src/views/InvoiceDetail.vue
git commit -m "feat(invoice-detail): add file type helper functions - Task 6"
```

---

### Task 7: 添加高亮文件区域样式

**Files:**
- Modify: `CRM-Client/src/views/InvoiceDetail.vue` (style 区域)

**Interfaces:**
- Consumes: `$wolf-*` Design Tokens
- Produces: `.issued-file-highlight`, `.file-download-area` 样式类

- [ ] **Step 1: 在 style 区域末尾添加样式**

```scss
// 在 style 区域末尾添加（在 .invoice-file-section 之后）

// ISSUED 状态高亮文件区域
.issued-file-highlight {
  margin-top: $wolf-space-lg;
  padding: $wolf-card-padding;
  background: linear-gradient(135deg, $wolf-success-bg 0%, $wolf-bg-card 100%);
  border: 2px solid $wolf-success-border;
  border-radius: $wolf-radius-md;
  
  .highlight-header {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    margin-bottom: $wolf-space-md;
    
    .success-icon {
      font-size: 20px;
      color: $wolf-success-text;
    }
    
    .highlight-title {
      font-size: $wolf-font-size-body;
      font-weight: $wolf-font-weight-semibold;
      color: $wolf-success-text;
    }
    
    .invoice-number-badge {
      font-size: $wolf-font-size-caption;
      padding: 2px 8px;
      background: $wolf-success-text;
      color: $wolf-text-inverse;
      border-radius: $wolf-radius-sm;
      font-weight: $wolf-font-weight-medium;
    }
  }
  
  .file-download-area {
    display: flex;
    align-items: center;
    gap: $wolf-space-md;
    padding: $wolf-space-md;
    background: $wolf-bg-card;
    border-radius: $wolf-radius-sm;
    
    .file-type-icon {
      font-size: 32px;
      
      &.pdf-icon { color: #E53935; }  // PDF 红色
      &.image-icon { color: #43A047; }  // 图片绿色
      &.ofd-icon { color: $wolf-primary; }  // OFD 蓝色
      &.default-icon { color: $wolf-text-tertiary; }
    }
    
    .file-type-label {
      font-size: $wolf-font-size-body;
      color: $wolf-text-secondary;
      font-weight: $wolf-font-weight-medium;
    }
    
    // UX: touch-target-size (CRITICAL) - 最小 44px
    .download-btn {
      margin-left: auto;
      min-width: 140px;
      min-height: 44px;  // 确保满足 touch-target 要求
    }
  }
  
  // UX: reduced-motion (MEDIUM)
  @media (prefers-reduced-motion: reduce) {
    * {
      transition: none;
    }
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add CRM-Client/src/views/InvoiceDetail.vue
git commit -m "feat(invoice-detail): add issued-file-highlight styles - Task 7"
```

---

## Phase D — 端到端验证

### Task 8: 手动验证完整流程

**Files:**
- None (手动测试)

**Interfaces:**
- Consumes: 所有前置 Task 的产物
- Produces: 验证报告

- [ ] **Step 1: 启动后端服务**

Run: `cd CRM-Server && ./run.sh`
Expected: 服务正常启动

- [ ] **Step 2: 启动前端服务**

Run: `cd CRM-Client && npm run dev`
Expected: 前端正常启动

- [ ] **Step 3: 验证后端 API 响应**

使用浏览器或 curl 调用：
```
GET http://localhost:8000/v1/invoice-applications/{已开票发票ID}
```
Expected: 响应包含 `invoice_file_path`, `invoice_number`, `issued_time` 字段

- [ ] **Step 4: 验证列表页下载徽章**

在浏览器中：
1. 登录系统（销售人员账号）
2. 进入 `/invoices` 页面
3. 切换到「已开票」标签页
Expected: ISSUED 状态发票显示下载徽章

- [ ] **Step 5: 验证列表页下载功能**

点击下载徽章
Expected: Toast 提示"正在下载发票文件"，浏览器打开文件下载

- [ ] **Step 6: 验证详情页高亮区域**

点击发票进入详情页
Expected: ISSUED 状态下显示高亮文件区域（绿色渐变背景）

- [ ] **Step 7: 验证详情页下载功能**

点击详情页下载按钮
Expected: Toast 提示"发票文件下载成功"

- [ ] **Step 8: 验证审批中心 Drawer**

进入审批中心，查看已开票发票详情
Expected: Drawer 中显示下载按钮

- [ ] **Step 9: UX 验证清单检查**

按设计文档「UX 验证清单」逐项检查：
- Accessibility (CRITICAL): color-contrast, aria-labels, focus-states
- Touch & Interaction (CRITICAL): touch-target-size, touch-spacing, hover-vs-tap
- Animation (MEDIUM): duration-timing, transform-performance
- Forms & Feedback (MEDIUM): success-feedback

- [ ] **Step 10: Commit verification notes**

```bash
git add docs/superpowers/specs/2026-07-06-invoice-file-download-enhancement-design.md
# 在设计文档的验证清单中打勾 ✅
git commit -m "test(invoice): verify invoice file download enhancement - Task 8"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- ✅ 后端 Bug 修复：Task 1
- ✅ 列表页下载徽章：Task 2-4
- ✅ 详情页高亮区域：Task 5-7
- ✅ UX 规则：集成到 Task 4, 7 的样式定义中
- ✅ 验证：Task 8

**2. Placeholder scan:**
- ✅ 无 TBD/TODO
- ✅ 所有步骤包含完整代码
- ✅ 无"类似 Task N"引用

**3. Type consistency:**
- ✅ `InvoiceApplicationResponse` 类型一致
- ✅ `invoice_file_path: string | null` 类型一致
- ✅ `downloadInvoiceFile(row)` 参数类型一致

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-06-invoice-file-download-enhancement.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**