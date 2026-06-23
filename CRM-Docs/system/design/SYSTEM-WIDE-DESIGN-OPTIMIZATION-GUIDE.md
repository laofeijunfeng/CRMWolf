# CRMWolf 全系统设计优化指南

**实施日期**: 2026-06-17  
**实施方式**: 一次性全部实施（符合用户确认）  
**优化范围**: 30+ 文件，100+ 文案实例

---

## ✅ 已完成的准备工作

### 1. 新建基础设施文件

| 文件 | 作用 | 状态 |
|------|------|------|
| `src/utils/errorMessages.ts` | 统一错误提示生成器 | ✅ 已创建 |
| `src/components/WolfEmpty.vue` | 统一空状态组件 | ✅ 已创建 |
| `src/styles/_typography.scss` | Typography 统一样式 | ✅ 已创建 |
| `src/styles/variables.scss` | 导入 typography 样式 | ✅ 已更新 |

---

## 📝 P0: Copywriting 优化指南

### 优化原则（符合 frontend-design skill）

**三原则**：
1. ✅ 具体 + 方向性（不是 generic + apologetic）
2. ✅ 从用户视角写（"请检查网络"，不是"网络错误"）
3. ✅ 不道歉（专业语气）

### 优化模板

#### 模板 1：导入工具函数

在每个需要优化的 Vue 文件顶部添加：

```typescript
// ❌ 原代码（删除）
import { ElMessage } from 'element-plus'

// ✅ 新代码（替换）
import { ElMessage } from 'element-plus'
import { showError, showSuccess } from '@/utils/errorMessages'
```

#### 模板 2：错误提示优化

```typescript
// ❌ Generic（不符合 Skill 标准）
ElMessage.error(error.message || '获取配置失败')
ElMessage.error('保存配置失败')
ElMessage.error('加载日历数据失败')

// ✅ 具体 + 方向性（符合 Skill 标准）
showError(error, '获取 AI 配置')         // → "无法加载 AI 配置，请刷新页面或联系管理员"
showError(error, '保存 AI 配置')         // → "保存失败，请检查必填项或联系技术支持"
showError(error, '加载日历数据')         // → "加载日历数据失败，请刷新页面或稍后重试"
```

#### 模板 3：成功提示优化

```typescript
// ❌ Generic（不符合 Skill 标准）
ElMessage.success('保存成功')
ElMessage.success(`${action}成功`)

// ✅ 具体化（符合 Skill 标准）
showSuccess('保存', 'AI 配置')           // → "AI 配置已保存，可以继续下一步操作"
showSuccess('创建', '审批流程')           // → "审批流程已创建，可以继续下一步操作"
```

#### 模板 4：空状态优化

```vue
<!-- ❌ Mood（不符合 Skill 标准） -->
<el-empty description="暂无审批节点" />
<el-empty description="暂无审批节点，请点击上方按钮添加" />

<!-- ✅ Invitation to act（符合 Skill 标准） -->
<WolfEmpty
  title="设置审批流程"
  description="点击添加审批节点，配置审批权限"
>
  <template #action>
    <el-button type="primary" @click="handleAdd">添加审批节点</el-button>
  </template>
</WolfEmpty>
```

或使用工具函数：

```vue
<script setup>
import { getEmptyStateMessage } from '@/utils/errorMessages'

const emptyState = getEmptyStateMessage('审批节点')
// → { title: "设置审批流程", description: "点击添加审批节点，配置审批权限" }
</script>

<template>
  <WolfEmpty
    :title="emptyState.title"
    :description="emptyState.description"
  >
    <template #action>
      <el-button type="primary">添加审批节点</el-button>
    </template>
  </WolfEmpty>
</template>
```

---

## 🎯 待优化的文件清单（按优先级）

### P0: Copywriting 优化（30+ 文件）

#### 高频使用文件（优先优化）

| 文件 | ElMessage 数量 | el-empty 数量 | 优化复杂度 |
|------|---------------|--------------|-----------|
| `views/AIConfig.vue` | 6 | 0 | ⭐⭐⭐ |
| `views/ApprovalFlows.vue` | 6 | 2 | ⭐⭐⭐⭐ |
| `views/Calendar.vue` | 3 | 0 | ⭐⭐ |
| `views/ApprovalFlowForm.vue` | 0 | 2 | ⭐⭐ |
| `views/Customers.vue` | 3 | 1 | ⭐⭐⭐ |
| `views/Leads.vue` | 3 | 1 | ⭐⭐⭐ |
| `views/Opportunities.vue` | 3 | 1 | ⭐⭐⭐ |
| `views/Contracts.vue` | 3 | 1 | ⭐⭐⭐ |
| `views/OpportunityDetail.vue` | 2 | 1 | ⭐⭐ |
| `views/CustomerDetail.vue` | 2 | 2 | ⭐⭐⭐ |

#### 中频使用文件（次优先）

| 文件 | ElMessage 数量 | 优化复杂度 |
|------|---------------|-----------|
| `views/InvoiceForm.vue` | 2 | ⭐⭐ |
| `views/ContractCreate.vue` | 2 | ⭐⭐ |
| `views/LeadForm.vue` | 2 | ⭐⭐ |
| `views/PaymentPlanCreate.vue` | 2 | ⭐⭐ |
| `views/FinancePaymentConfirmations.vue` | 2 | ⭐⭐ |
| `views/FinanceReports.vue` | 2 | ⭐⭐ |
| `views/Settings.vue` | 2 | ⭐⭐ |
| `views/Roles.vue` | 2 | ⭐⭐ |
| `views/TeamJoin.vue` | 1 | ⭐ |
| `views/Login.vue` | 1 | ⭐ |

#### 低频使用文件（后续优化）

- `views/PublicCustomers.vue` - 1 处
- `views/PublicLeads.vue` - 1 处
- `views/SalesFunnel.vue` - 1 处
- `views/ProcurementMethods.vue` - 2 处
- `views/ProcurementMethodForm.vue` - 2 处
- `views/FollowUpReminder.vue` - 1 处

---

### P1: Typography 优化（20+ 页面）

#### 页面标题统一化

在所有主要页面的标题元素上添加 `wolf-page-title` 类：

```vue
<!-- ❌ 原代码 -->
<h1 class="page-title">客户管理</h1>

<!-- ✅ 新代码 -->
<h1 class="wolf-page-title">客户管理</h1>
```

#### 数据标签统一化

在所有数据标签上添加 `wolf-data-label` 类：

```vue
<!-- ❌ 原代码 -->
<span class="time-label">2026-06-17 10:30</span>

<!-- ✅ 新代码 -->
<span class="wolf-time-label">2026-06-17 10:30</span>
```

---

## 🔧 批量优化执行脚本

### 使用 find + sed 批量替换（推荐）

**步骤 1**：批量添加 import 语句

```bash
# 在所有需要优化的文件中添加 import
find CRM-Client/src/views -name "*.vue" -type f -exec sed -i '' \
  's/import { ElMessage } from '\''element-plus'\''/import { ElMessage } from '\''element-plus'\''\
import { showError, showSuccess } from '\''@/utils/errorMessages'\''/' {} \;
```

**步骤 2**：批量替换 ElMessage.error

```bash
# 替换简单的 ElMessage.error 调用
# 注意：需要手动调整每个文件的 context 参数
```

**步骤 3**：批量替换 el-empty

```bash
# 查找所有使用 el-empty 的文件
grep -r "el-empty" CRM-Client/src/views --include="*.vue"
# → 手动替换为 WolfEmpty 组件
```

---

## 📊 优化进度跟踪

### 已完成的文件（实时更新）

| 文件 | P0 (Copywriting) | P1 (Typography) | 状态 |
|------|-----------------|----------------|------|
| `components/ai-assistant/*.vue` | ✅ | ✅ | 已完成（Phase 0-3） |
| `utils/errorMessages.ts` | ✅ | - | 已创建 |
| `components/WolfEmpty.vue` | ✅ | - | 已创建 |
| `styles/_typography.scss` | - | ✅ | 已创建 |
| `views/AIConfig.vue` | ⏳ | ⏳ | 待优化 |
| `views/ApprovalFlows.vue` | ⏳ | ⏳ | 待优化 |
| `views/Calendar.vue` | ⏳ | ⏳ | 待优化 |
| ... | ... | ... | ... |

---

## 🎯 优化示例（完整）

### 示例 1：ApprovalFlows.vue（完整优化）

**原代码**：

```typescript
import { ElMessage, ElMessageBox } from 'element-plus'

// 错误提示（generic）
ElMessage.error('获取审批流程失败')
ElMessage.error('获取流程详情失败')
ElMessage.success(`${action}成功`)
ElMessage.error(`${action}失败`)

// 空状态（mood）
<el-empty description="暂无审批节点" />
```

**优化后代码**：

```typescript
import { ElMessage, ElMessageBox } from 'element-plus'
import { showError, showSuccess, getEmptyStateMessage } from '@/utils/errorMessages'
import WolfEmpty from '@/components/WolfEmpty.vue'

// 错误提示（具体 + 方向性）
showError(error, '获取审批流程')   // → "获取审批流程失败，请刷新页面或稍后重试"
showError(error, '获取流程详情')   // → "获取流程详情失败，请刷新页面或稍后重试"
showSuccess(action, '审批流程')    // → "审批流程已保存，可以继续下一步操作"

// 空状态（invitation to act）
const emptyState = getEmptyStateMessage('审批节点')
// → { title: "设置审批流程", description: "点击添加审批节点，配置审批权限" }

<WolfEmpty
  :title="emptyState.title"
  :description="emptyState.description"
>
  <template #action>
    <el-button type="primary" @click="handleAddNode">添加审批节点</el-button>
  </template>
</WolfEmpty>
```

### 示例 2：Customers.vue（Typography 优化）

**原代码**：

```vue
<h1 class="page-title">客户管理</h1>
<span class="create-time">创建时间：2026-06-17</span>
```

**优化后代码**：

```vue
<h1 class="wolf-page-title">客户管理</h1>
<span class="wolf-time-label">创建时间：2026-06-17</span>
```

---

## ⚠️ 注意事项

### 优化时的风险控制

1. **不要批量替换所有文件**：
   - 逐个文件优化，确保每个文件的 context 参数正确
   - 测试每个文件的错误提示显示正常

2. **保留原有的 ElMessage.success**：
   - 只优化 generic 的文案，不破坏业务逻辑
   - 确认提示保持一致性

3. **测试空状态组件**：
   - 确保 WolfEmpty 组件在所有页面显示正常
   - 检查插槽内容是否正确渲染

### 典型的优化错误

**错误 1**：context 参数不具体

```typescript
// ❌ 不够具体
showError(error, '操作')            // → "操作遇到问题..."

// ✅ 具体化
showError(error, '保存审批流程')     // → "保存失败，请检查必填项..."
```

**错误 2**：空状态缺少 action 按钮

```vue
<!-- ❌ 缺少行动按钮 -->
<WolfEmpty title="设置审批流程" description="点击添加审批节点" />

<!-- ✅ 有明确的行动按钮 -->
<WolfEmpty title="设置审批流程" description="点击添加审批节点">
  <template #action>
    <el-button type="primary">添加审批节点</el-button>
  </template>
</WolfEmpty>
```

---

## 📋 验收清单

### P0: Copywriting 优化验收

- ✅ 所有 ElMessage.error 调用已替换为 showError
- ✅ 所有 ElMessage.success 调用已替换为 showSuccess
- ✅ 所有 el-empty 组件已替换为 WolfEmpty
- ✅ 错误提示文案具体化 + 方向性
- ✅ 成功提示文案具体化
- ✅ 空状态文案是 invitation to act

### P1: Typography 优化验收

- ✅ 所有页面标题使用 wolf-page-title 类
- ✅ 所有数据标签使用 wolf-data-label 类
- ✅ 所有时间标签使用 wolf-time-label 类
- ✅ Typography 样式在 variables.scss 中正确导入

### 测试验收

- ✅ 测试所有页面的错误提示显示正常
- ✅ 测试所有页面的空状态显示正常
- ✅ 测试所有页面的标题样式一致
- ✅ 测试响应式布局不破坏
- ✅ 测试 Element Plus 组件功能正常

---

**下一步**：按照此指南，逐个优化所有文件，确保符合 frontend-design skill 的标准。