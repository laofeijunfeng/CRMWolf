# 前端 ApprovalPhase 状态迁移指南

**目标:** 将前端审批状态判断逻辑从 `status` 字段改为 `approval_phase` 字段，实现双字段职责分离。

**影响范围:** 28处状态判断逻辑

**参考设计:** `docs/superpowers/specs/2026-07-08-approval-transaction-manager-redesign.md`

---

## 核心原则

### 双字段职责分离

| 字段 | 用途 | 示例 |
|------|------|------|
| **approval_phase** | 审批流程状态判断（统一使用此字段） | `approval_phase === 'pending_review'` |
| **原有 status** | 业务状态显示（保留业务语义） | `ContractDetail.vue` 显示合同生命周期 |

### 状态映射表

| approval_phase | 含义 | 徽章颜色 | 前端显示 |
|----------------|------|---------|---------|
| `draft` | 草稿/待提交审批 | gray | "草稿" |
| `pending_review` | 待审批（审批流程中） | blue | "审批中" |
| `approved` | 审批通过 | green | "已通过" |
| `rejected` | 审批拒绝 | red | "已拒绝" |

---

## 修改清单

### 1. ContractDetail.vue（审批状态判断）

**当前代码（需修改）:**
```javascript
contractInfo.value?.status === 'PENDING_REVIEW' &&
```

**修改为:**
```javascript
contractInfo.value?.approval_phase === 'pending_review' &&
```

**影响位置:**
- Line 258: 审批信息加载条件判断
- Line 263: 审批信息显示条件判断
- Line 333: 审批状态列表判断
- Line 663: 加载状态提示文本

---

### 2. FinanceInvoiceApprovals.vue（发票审批）

**当前代码（需修改）:**
```javascript
v-if="row.status === 'PENDING_REVIEW'"
```

**修改为:**
```javascript
v-if="row.approval_phase === 'pending_review'"
```

**影响位置:**
- Line 97: 审批按钮显示条件
- Line 103: 审批按钮显示条件
- Line 187: 审批操作显示条件
- Line 273: 状态映射
- Line 430: 状态显示文本
- Line 441: 状态徽章类型
- Line 452: 状态徽章样式

---

### 3. PaymentPlanView.vue（回款审批）

**当前代码（需修改）:**
```javascript
params.status = 'PENDING'
```

**修改为:**
```javascript
params.approval_phase = 'pending_review'
```

**影响位置:**
- Line 124: 回款计划筛选参数
- Line 194: 状态显示文本
- Line 204: 状态徽章样式
- Line 309: 审批按钮显示条件

---

### 4. FinanceDashboard.vue（仪表板统计）

**当前代码（需修改）:**
```javascript
navigateTo('/invoices?status=PENDING_REVIEW')
```

**修改为:**
```javascript
navigateTo('/invoices?approval_phase=pending_review')
```

**影响位置:**
- Line 15: 导航链接
- Line 186: API调用参数

---

## 新增：审批状态徽章统一组件

### 创建 ApprovalPhaseBadge.vue

```vue
<template>
  <el-tag :type="badgeType" :class="badgeClass">
    {{ badgeText }}
  </el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  approvalPhase: string
}

const props = defineProps<Props>()

const badgeType = computed(() => {
  switch (props.approvalPhase) {
    case 'draft': return 'info'
    case 'pending_review': return 'primary'
    case 'approved': return 'success'
    case 'rejected': return 'danger'
    default: return 'info'
  }
})

const badgeClass = computed(() => {
  return `approval-phase-${props.approvalPhase}`
})

const badgeText = computed(() => {
  switch (props.approvalPhase) {
    case 'draft': return '草稿'
    case 'pending_review': return '审批中'
    case 'approved': return '已通过'
    case 'rejected': return '已拒绝'
    default: return '未知'
  }
})
</script>

<style scoped>
.approval-phase-draft {
  background-color: #f0f0f0;
  color: #666;
}

.approval-phase-pending_review {
  background-color: #e6f7ff;
  color: #1890ff;
}

.approval-phase-approved {
  background-color: #f6ffed;
  color: #52c41a;
}

.approval-phase-rejected {
  background-color: #fff2f0;
  color: #ff4d4f;
}
</style>
```

---

## 新增：审批状态判断工具函数

### 创建 approvalPhaseUtils.ts

```typescript
// src/utils/approvalPhaseUtils.ts

/**
 * 判断是否可以提交审批
 * @param approvalPhase 审批流程状态
 * @returns 是否可以提交审批
 */
export function canSubmitApproval(approvalPhase: string): boolean {
  return approvalPhase === 'draft'
}

/**
 * 判断是否可以重新提交审批（驳回后）
 * @param approvalPhase 审批流程状态
 * @returns 是否可以重新提交审批
 */
export function canResubmitApproval(approvalPhase: string): boolean {
  return approvalPhase === 'rejected'
}

/**
 * 判断是否正在审批中
 * @param approvalPhase 审批流程状态
 * @returns 是否正在审批中
 */
export function isApprovalPending(approvalPhase: string): boolean {
  return approvalPhase === 'pending_review'
}

/**
 * 判断审批是否已通过
 * @param approvalPhase 审批流程状态
 * @returns 审批是否已通过
 */
export function isApprovalApproved(approvalPhase: string): boolean {
  return approvalPhase === 'approved'
}

/**
 * 判断审批是否已拒绝
 * @param approvalPhase 审批流程状态
 * @returns 审批是否已拒绝
 */
export function isApprovalRejected(approvalPhase: string): boolean {
  return approvalPhase === 'rejected'
}

/**
 * 获取审批状态徽章颜色
 * @param approvalPhase 审批流程状态
 * @returns Element Plus Tag type
 */
export function getApprovalBadgeType(approvalPhase: string): 'info' | 'primary' | 'success' | 'danger' {
  switch (approvalPhase) {
    case 'draft': return 'info'
    case 'pending_review': return 'primary'
    case 'approved': return 'success'
    case 'rejected': return 'danger'
    default: return 'info'
  }
}

/**
 * 获取审批状态显示文本
 * @param approvalPhase 审批流程状态
 * @returns 显示文本
 */
export function getApprovalPhaseText(approvalPhase: string): string {
  switch (approvalPhase) {
    case 'draft': return '草稿'
    case 'pending_review': return '审批中'
    case 'approved': return '已通过'
    case 'rejected': return '已拒绝'
    default: return '未知'
  }
}
```

---

## API响应变化

### 后端返回数据结构调整

**新增字段:** 所有业务单据 API 响应新增 `approval_phase` 字段

**示例（Contract API）:**
```json
{
  "id": 123,
  "contract_number": "CON-2026-001",
  "contract_name": "测试合同",
  "status": "PENDING_REVIEW",  // 原有字段（合同生命周期）
  "approval_phase": "pending_review",  // 新增字段（审批流程状态）
  "total_amount": 100000,
  "approval_id": 456
}
```

### 前端需要同步修改

1. **类型定义更新** - 在 `src/types/*.ts` 中添加 `approval_phase` 字段
2. **API响应处理** - 确保 API 响应正确解析 `approval_phase` 字段
3. **组件数据绑定** - 将 `status` 判断改为 `approval_phase` 判断

---

## 测试清单

### 功能测试

| 测试场景 | 验证点 |
|---------|-------|
| 创建合同后提交审批 | approval_phase 显示为 `pending_review` |
| 审批通过后 | approval_phase 显示为 `approved` |
| 审批拒绝后 | approval_phase 显示为 `rejected`，可重新提交 |
| 撤回审批后 | approval_phase 显示为 `draft`，可重新提交 |
| 驳回后重新提交 | approval_phase 流转正确 |

### UI测试

| 测试场景 | 验证点 |
|---------|-------|
| 审批状态徽章颜色 | 根据 approval_phase 显示正确颜色 |
| 审批按钮显示 | 根据 approval_phase 正确显示/隐藏按钮 |
| 审批列表筛选 | 使用 approval_phase 参数筛选 |

---

## 注意事项

### 向后兼容

- **原有 status 字段保留** - 业务状态显示仍使用原有 status 字段
- **双字段显示** - 某些场景可能需要同时显示 approval_phase 和原有 status
- **API兼容性** - 确保旧 API 调用仍然工作

### 数据迁移影响

- **历史数据** - 数据库迁移已完成，历史数据 approval_phase 已正确映射
- **缓存清理** - 前端可能需要清理缓存，确保获取最新的 approval_phase 数据

---

## 执行步骤建议

### Phase 1: 基础设施（1天）

1. 创建 `ApprovalPhaseBadge.vue` 组件
2. 创建 `approvalPhaseUtils.ts` 工具函数
3. 更新类型定义文件

### Phase 2: 核心文件修改（1天）

1. ContractDetail.vue - 合同详情页
2. FinanceInvoiceApprovals.vue - 发票审批页面
3. PaymentPlanView.vue - 回款计划页面
4. FinanceDashboard.vue - 仪表板

### Phase 3: 其他文件修改（半天）

1. 其他涉及审批状态判断的文件
2. API响应处理调整

### Phase 4: 测试验证（半天）

1. 功能测试
2. UI测试
3. 回归测试

---

**文档版本:** v1.0
**创建时间:** 2026-07-08
**作者:** Claude
**状态:** 前端工程师实施指南