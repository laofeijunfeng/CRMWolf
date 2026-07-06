# 发票文件下载功能修复 + UI 优化设计文档

> **Created:** 2026-07-06
> **Status:** Approved by user
> **Scope:** Bug fix + UI enhancement for invoice file download

---

## 问题描述

**用户反馈：** 销售人员在发票详情页和审批中心看不到发票文件下载按钮。

**根因分析：** 后端 `_populate_application_info()` 函数返回的 dict 缺失 `invoice_file_path`, `invoice_number`, `issued_time` 字段，导致 API 响应永远不包含这些值，前端条件渲染 `v-if="invoiceInfo?.invoice_file_path"` 永远为 false。

---

## 影响范围

| 层级 | 文件 | 状态 | 问题 |
|------|------|------|------|
| **数据库 Model** | `InvoiceApplication` | ✅ 正确 | 三个字段已定义 |
| **后端 Schema** | `InvoiceApplicationResponse` | ✅ 正确 | 三个字段已定义 |
| **API 响应构造** | `_populate_application_info()` | ❌ **Bug** | 返回 dict 缺失三个字段 |
| **前端 TypeScript** | `InvoiceApplicationResponse` | ✅ 正确 | 三个字段已定义 |
| **前端显示组件** | `InvoiceDetail.vue` | ✅ 正确 | 有下载按钮（依赖 `invoice_file_path`） |
| **前端显示组件** | `FinanceInvoiceApprovals.vue` | ✅ 正确 | 有下载按钮（依赖 `invoice_file_path`） |
| **销售发票列表页** | `Invoices.vue` | ❌ **缺失功能** | ISSUED 状态无下载入口 |

---

## 设计方案

### 方案 B：全面重构响应构造 + UI 增强

**核心改动：**

1. **后端修复：** `_populate_application_info()` 返回 Pydantic Schema 并包含缺失字段
2. **前端列表页增强：** ISSUED 状态发票在申请单号列显示下载入口
3. **前端详情页优化：** ISSUED 状态下文件区域提升至信息区顶部 + 文件类型图标差异化

---

## 设计章节 1：后端响应重构

### 1.1 修复 `_populate_application_info()`

**文件：** `CRM-Server/app/api/invoices.py`

**改动：**
- 返回类型从 `dict` 改为 `InvoiceApplicationResponse`
- 添加三个缺失字段：`invoice_file_path`, `invoice_number`, `issued_time`

```python
def _populate_application_info(db: Session, application, team_id: Optional[int] = None) -> InvoiceApplicationResponse:
    """填充发票申请完整响应信息
    
    Changes:
    - 返回 InvoiceApplicationResponse（而非 dict）类型安全
    - 添加 invoice_file_path / invoice_number / issued_time（修复 bug）
    """
    # 关联查询（逻辑不变）
    customer_query = db.query(Customer).filter(Customer.id == application.customer_id)
    if team_id is not None:
        customer_query = customer_query.filter(Customer.team_id == team_id)
    customer = customer_query.first()

    contract_query = db.query(Contract).filter(Contract.id == application.contract_id)
    if team_id is not None:
        contract_query = contract_query.filter(Contract.team_id == team_id)
    contract = contract_query.first()

    opportunity_query = db.query(Opportunity).filter(Opportunity.id == application.opportunity_id)
    if team_id is not None:
        opportunity_query = opportunity_query.filter(Opportunity.team_id == team_id)
    opportunity = opportunity_query.first()

    payment_plan_query = db.query(PaymentPlan).filter(PaymentPlan.id == application.payment_plan_id)
    if team_id is not None:
        payment_plan_query = payment_plan_query.filter(PaymentPlan.team_id == team_id)
    payment_plan = payment_plan_query.first()
    
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
    
    # 返回 Pydantic Schema（类型安全）
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

---

## 设计章节 2：前端列表页增强

### 2.1 申请单号列增加下载徽章

**文件：** `CRM-Client/src/views/Invoices.vue`

**设计理由：**
- 发票文件与发票单号天然关联——"Structure is information"
- 下载入口紧邻发票单号，用户扫描列表时自然发现
- 不挤占操作列空间
- 仅 ISSUED 状态显示，其他状态保持原样

**改动：** 申请单号列（line 73-77）增加下载徽章

```vue
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
      >
        <el-icon class="download-icon"><Download /></el-icon>
        <span class="download-link" @click.stop="downloadInvoiceFile(row)">下载</span>
      </span>
    </div>
  </template>
</el-table-column>
```

### 2.2 添加下载函数

```typescript
// script setup 中添加
import { Download } from '@element-plus/icons-vue'
import { getInvoiceFileUrl } from '@/api/fileUpload'

/**
 * 直接下载发票文件（列表页）
 */
const downloadInvoiceFile = (row: InvoiceApplicationResponse): void => {
  const url = getInvoiceFileUrl(row.id)
  window.open(url, '_blank')
}
```

### 2.3 样式定义

```scss
// Invoices.vue style 中添加
.application-number-cell {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.download-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: $wolf-success-bg;
  border-radius: $wolf-radius-sm;
  font-size: $wolf-font-size-caption;
  
  .download-icon {
    color: $wolf-success-text;
    font-size: 12px;
  }
  
  .download-link {
    color: $wolf-success-text;
    cursor: pointer;
    font-weight: $wolf-font-weight-medium;
    
    &:hover {
      text-decoration: underline;
    }
  }
}
```

---

## 设计章节 3：前端详情页优化

### 3.1 ISSUED 状态下文件区域提升

**文件：** `CRM-Client/src/views/InvoiceDetail.vue`

**设计理由：**
- 状态决定信息优先级——已开票的核心产出应突出
- 用户无需滚动即可看到下载入口
- 视觉权重与状态匹配

**改动：** 在 `info-bottom` 区域之后添加高亮文件区域

```vue
<!-- InvoiceDetail.vue template -->

<div class="info-bottom">
  <!-- 属性网格（现有内容不变） -->
  <div class="attributes-grid">
    <!-- ... -->
  </div>
</div>

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
    <el-button type="primary" class="download-btn" @click="downloadInvoiceFile">
      <el-icon><Download /></el-icon>
      下载发票文件
    </el-button>
  </div>
</div>
```

### 3.2 添加辅助函数

```typescript
// script setup 中添加
import { CircleCheckFilled, Download, Document, Picture } from '@element-plus/icons-vue'

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
```

### 3.3 样式定义

```scss
// InvoiceDetail.vue style 中添加

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
    
    .download-btn {
      margin-left: auto;
      min-width: 140px;
    }
  }
}

// 隐藏原有文件区域（ISSUED 状态下不再重复显示）
.invoice-file-section {
  // 当 ISSUED 高亮区域显示时，隐藏原文件区域
  // 通过 v-if 条件控制即可，无需额外样式
}
```

---

## 实施计划

### Phase 1: 后端 Bug 修复（必须）

| Task | 文件 | 改动 |
|------|------|------|
| 1.1 | `CRM-Server/app/api/invoices.py` | `_populate_application_info()` 返回 `InvoiceApplicationResponse` + 三个缺失字段 |

### Phase 2: 前端列表页增强（新功能）

| Task | 文件 | 改动 |
|------|------|------|
| 2.1 | `CRM-Client/src/views/Invoices.vue` | 申请单号列增加下载徽章 |
| 2.2 | `CRM-Client/src/views/Invoices.vue` | 添加 `downloadInvoiceFile` 函数 |
| 2.3 | `CRM-Client/src/views/Invoices.vue` | 添加 `.download-badge` 样式 |

### Phase 3: 前端详情页优化（UI 增强）

| Task | 文件 | 改动 |
|------|------|------|
| 3.1 | `CRM-Client/src/views/InvoiceDetail.vue` | ISSUED 状态下添加高亮文件区域 |
| 3.2 | `CRM-Client/src/views/InvoiceDetail.vue` | 添加文件类型判断辅助函数 |
| 3.3 | `CRM-Client/src/views/InvoiceDetail.vue` | 添加 `.issued-file-highlight` 样式 |

---

## 验证清单

### 后端验证

- [ ] `_populate_application_info()` 返回 `InvoiceApplicationResponse` 类型
- [ ] API 响应包含 `invoice_file_path`, `invoice_number`, `issued_time`
- [ ] 已开票发票文件可正常下载（`GET /invoice-applications/{id}/file`）

### 前端验证

- [ ] 列表页：ISSUED 状态发票显示下载徽章
- [ ] 列表页：点击下载徽章可正常打开文件
- [ ] 详情页：ISSUED 状态下高亮文件区域显示在信息区顶部
- [ ] 详情页：文件图标按类型差异化显示
- [ ] 详情页：下载按钮点击可正常打开文件
- [ ] 审批中心：Drawer 详情页显示下载按钮（依赖 bug 修复后自动生效）

---

## 相关记忆

- [[invoice-approval-file-upload-status]] — 发票审批文件上传优化进度
- [[approval-engine-business-rules]] — 审批引擎泛化业务规则