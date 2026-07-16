# 商机操作弹窗重构设计文档

**日期**: 2026-07-16
**状态**: 设计完成，待实施
**影响范围**: 商机列表页、商机详情页

---

## 一、背景与目标

### 1.1 当前问题

商机列表页（`Opportunities.vue`）的"推进阶段"、"赢单"、"输单"按钮功能未完整实现：
- 点击后跳转到不存在的路由（`/opportunities/{id}/advance-stage`、`/opportunities/{id}/win`、`/opportunities/{id}/lose`）
- 用户无法从列表页快速完成这些操作

商机详情页（`OpportunityDetailContent.vue`）已实现弹窗方式，但代码内联在组件中，无法复用。

### 1.2 目标

1. 让用户能从列表页快速完成商机操作，无需跳转页面
2. 提取可复用的弹窗组件，避免代码重复
3. 保持详情页和列表页交互一致

---

## 二、设计方案

### 2.1 架构设计

#### 组件结构
```
src/components/dialogs/
├── OpportunityWinDialog.vue      # 新建：赢单表单弹窗
└── OpportunityLoseDialog.vue     # 新建：输单表单弹窗

src/components/panels/
└── OpportunityDetailContent.vue  # 重构：改用新弹窗组件

src/views/
└── Opportunities.vue              # 修改：集成新弹窗组件
```

#### 数据流
```
列表页（Opportunities.vue）
  ↓ 点击"赢单/输单"
打开弹窗组件（传入 opportunityId）
  ↓ 弹窗内部调用 API
opportunityApi.getOpportunity(opportunityId)  # 加载详情
opportunityApi.markAsWon/markAsLost()         # 提交操作
  ↓ 成功后
emit('success') → 父组件刷新列表
```

---

### 2.2 操作方式

| 操作 | 列表页实现方式 | 详情页实现方式 |
|------|----------------|----------------|
| **推进阶段** | `confirmDialog` 确认弹窗 | 已实现，保持不变 |
| **赢单** | `OpportunityWinDialog` 表单弹窗 | 改用 `OpportunityWinDialog` |
| **输单** | `OpportunityLoseDialog` 表单弹窗 | 改用 `OpportunityLoseDialog` |

---

## 三、组件接口设计

### 3.1 OpportunityWinDialog.vue

**用途**: 赢单表单弹窗，收集实际成交金额和日期

**Props**:
```typescript
interface Props {
  opportunityId: number | null    // 商机ID（null时不显示）
  open: boolean                   // 弹窗显示状态
}
```

**Emits**:
```typescript
interface Emits {
  (e: 'update:open', value: boolean): void  // 弹窗状态变化
  (e: 'success'): void                       // 操作成功
}
```

**内部状态**:
```typescript
const loading = ref(false)              // 加载商机详情
const submitting = ref(false)           // 提交中
const opportunity = ref<Opportunity | null>(null)
const form = reactive({
  actual_amount: 0,
  actual_closing_date: getTodayLocalDate()
})
```

**核心逻辑**:
1. 监听 `open` 变化，加载商机详情
2. 预填充预计金额
3. 表单校验（金额>0，日期必填）
4. 调用 `opportunityApi.markAsWon()` 提交
5. 成功后 emit('success')，刷新父组件列表

---

### 3.2 OpportunityLoseDialog.vue

**用途**: 输单表单弹窗，收集输单原因

**Props**:
```typescript
interface Props {
  opportunityId: number | null
  open: boolean
}
```

**Emits**:
```typescript
interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success'): void
}
```

**内部状态**:
```typescript
const loading = ref(false)
const submitting = ref(false)
const opportunity = ref<Opportunity | null>(null)
const form = reactive({
  loss_reason: ''
})
```

**核心逻辑**:
1. 监听 `open` 变化，加载商机详情
2. 表单校验（输单原因 1-500 字符）
3. 调用 `opportunityApi.markAsLost()` 提交
4. 成功后 emit('success')，刷新父组件列表

---

## 四、列表页集成

### 4.1 Opportunities.vue 修改

**新增导入**:
```typescript
import OpportunityWinDialog from '@/components/dialogs/OpportunityWinDialog.vue'
import OpportunityLoseDialog from '@/components/dialogs/OpportunityLoseDialog.vue'
import { confirmDialog } from '@/utils/confirmDialog'
```

**新增状态**:
```typescript
// 赢单弹窗
const winDialogOpen = ref(false)
const selectedOpportunityIdForWin = ref<number | null>(null)

// 输单弹窗
const loseDialogOpen = ref(false)
const selectedOpportunityIdForLose = ref<number | null>(null)
```

**操作处理函数**:
```typescript
// 推进阶段（直接实现）
const handleAdvanceStage = async (record: Opportunity): void => {
  // 1. 获取可推进阶段
  // 2. 找到下一阶段或默认起始阶段
  // 3. confirmDialog 确认
  // 4. 调用 API 推进
  // 5. 刷新列表
}

// 赢单（打开弹窗）
const handleMarkAsWon = (record: Opportunity): void => {
  selectedOpportunityIdForWin.value = record.id
  winDialogOpen.value = true
}

// 输单（打开弹窗）
const handleMarkAsLost = (record: Opportunity): void => {
  selectedOpportunityIdForLose.value = record.id
  loseDialogOpen.value = true
}
```

---

## 五、详情页重构

### 5.1 OpportunityDetailContent.vue 修改

**移除内联弹窗逻辑**:
- 移除 `winForm`、`loseForm` 状态
- 移除内联 `<Dialog>` 模板代码（约 60 行）
- 保留 `winDialogOpen`、`loseDialogOpen` 状态

**改用新组件**:
```vue
<OpportunityWinDialog
  :opportunity-id="opportunity?.id ?? null"
  :open="winDialogOpen"
  @update:open="winDialogOpen = $event"
  @success="handleWinSuccess"
/>

<OpportunityLoseDialog
  :opportunity-id="opportunity?.id ?? null"
  :open="loseDialogOpen"
  @update:open="loseDialogOpen = $event"
  @success="handleLoseSuccess"
/>
```

---

## 六、错误处理

### 6.1 API 调用错误
- 所有 API 调用使用 `handleApiError(error, '操作名称')` 统一处理
- 显示用户友好的错误信息

### 6.2 表单校验
- **赢单**: 金额>0，日期必填
- **输单**: 输单原因 1-500 字符
- 前端校验失败时显示 toast 提示

### 6.3 加载状态
- 弹窗打开时加载商机详情，显示加载中状态
- 加载失败时自动关闭弹窗

### 6.4 边界情况
- **新商机（无当前阶段）**: 自动选择默认起始阶段
- **已是最终阶段**: 提示用户无法继续推进
- **未配置默认起始阶段**: 提示配置错误

---

## 七、测试要点

### 7.1 OpportunityWinDialog
1. 弹窗打开时加载商机详情
2. 表单预填充预计金额
3. 表单校验正常工作
4. 提交成功后关闭弹窗并刷新列表
5. 提交失败时显示错误信息

### 7.2 OpportunityLoseDialog
1. 弹窗打开时加载商机详情
2. 表单校验正常工作
3. 提交成功后关闭弹窗并刷新列表
4. 提交失败时显示错误信息

### 7.3 列表页操作
1. 推进阶段确认弹窗显示正确
2. 新商机设置起始阶段正常
3. 已是最终阶段时提示
4. 赢单/输单弹窗正确打开
5. 操作成功后列表自动刷新

---

## 八、实施步骤

### 阶段 1: 创建弹窗组件
1. 创建 `OpportunityWinDialog.vue`
2. 创建 `OpportunityLoseDialog.vue`

### 阶段 2: 重构详情页
1. 修改 `OpportunityDetailContent.vue`
2. 移除内联弹窗逻辑
3. 集成新弹窗组件
4. 测试详情页功能

### 阶段 3: 集成列表页
1. 修改 `Opportunities.vue`
2. 实现推进阶段逻辑
3. 集成赢单/输单弹窗
4. 测试列表页功能

### 阶段 4: 验证和清理
1. 运行类型检查
2. 运行 lint 检查
3. 手动测试所有场景
4. 清理废弃代码

---

## 九、预期效果

### 用户体验提升
- ✅ 列表页可直接操作，无需跳转页面
- ✅ 操作流程简化，减少点击次数
- ✅ 详情页和列表页交互一致

### 代码质量提升
- ✅ 弹窗逻辑复用，避免重复代码
- ✅ 组件职责清晰，易于维护
- ✅ 符合 Vue 3 组件化最佳实践

### 维护成本降低
- ✅ 单一修改点（弹窗组件）
- ✅ 新增操作只需扩展组件
- ✅ 测试覆盖更集中

---

**设计完成日期**: 2026-07-16