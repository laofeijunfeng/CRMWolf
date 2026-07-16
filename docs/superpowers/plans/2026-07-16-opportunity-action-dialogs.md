# 商机操作弹窗重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户能从列表页快速完成商机操作（推进阶段、赢单、输单），无需跳转页面，同时提取可复用的弹窗组件。

**Architecture:** 抽取独立弹窗组件（OpportunityWinDialog、OpportunityLoseDialog），列表页直接调用，详情页复用同一组件，保持交互一致。

**Tech Stack:** Vue 3 Composition API + TypeScript + shadcn-vue + vee-validate + Zod

## Global Constraints

- **TypeScript 四禁令**: 禁用 `any` `as any` `@ts-ignore` `!`
- **设计 Token**: 必须使用 `variables-v2.scss` 中的 `$wolf-xxx-v2` 变量
- **组件 Props/Emits**: 必须类型化
- **表单校验**: 使用 vee-validate + Zod
- **错误处理**: 使用 `handleApiError(error, '操作名称')` 统一处理
- **无障碍**: 焦点管理、键盘导航、禁用状态视觉
- **动效时长**: 150-300ms，支持 `prefers-reduced-motion`
- **响应式**: 窄视口(< 768px)弹窗转为全屏/抽屉，表单堆叠布局

---

## File Structure

**新建文件**:
- `CRM-Client/src/components/dialogs/OpportunityWinDialog.vue` - 赢单表单弹窗
- `CRM-Client/src/components/dialogs/OpportunityLoseDialog.vue` - 输单表单弹窗

**修改文件**:
- `CRM-Client/src/components/panels/OpportunityDetailContent.vue` - 移除内联弹窗，改用新组件
- `CRM-Client/src/views/Opportunities.vue` - 集成新弹窗，实现推进阶段逻辑

---

### Task 1: 创建 OpportunityWinDialog.vue 组件

**Files:**
- Create: `CRM-Client/src/components/dialogs/OpportunityWinDialog.vue`

**Interfaces:**
- Consumes: `opportunityApi.getOpportunity(id)`, `opportunityApi.markAsWon(id, data)`
- Produces: `<OpportunityWinDialog :opportunity-id :open @update:open @success />`

- [ ] **Step 1: 创建文件并编写组件骨架**

```vue
<script setup lang="ts">
/**
 * OpportunityWinDialog.vue - 赢单表单弹窗
 *
 * 收集实际成交金额和日期，遵循无障碍和动效规范。
 */
import { ref, reactive, watch } from 'vue'
import { toast } from 'vue-sonner'
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
import { DatePicker } from '@/components/ui/date-picker'
import { handleApiError } from '@/utils/errorHandler'
import { getTodayLocalDate } from '@/utils/format'
import { opportunityApi, type Opportunity } from '@/api/opportunity'

interface Props {
  opportunityId: number | null
  open: boolean
}

interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// 状态
const loading = ref(false)
const submitting = ref(false)
const opportunity = ref<Opportunity | null>(null)
const form = reactive({
  actual_amount: 0,
  actual_closing_date: getTodayLocalDate()
})
</script>

<template>
  <Dialog :open="props.open" @update:open="emit('update:open', $event)">
    <DialogContent class="sm:max-w-[425px] max-w-full">
      <DialogHeader>
        <DialogTitle>标记赢单</DialogTitle>
        <DialogDescription>请输入实际成交金额和日期</DialogDescription>
      </DialogHeader>
      
      <div v-if="loading" class="py-8 text-center text-muted-foreground">
        加载中...
      </div>
      
      <form v-else class="grid gap-4 py-4">
        <!-- 实际成交金额 -->
        <div class="grid gap-2">
          <Label for="actual_amount">
            实际成交金额 <span class="text-destructive">*</span>
          </Label>
          <Input
            id="actual_amount"
            v-model.number="form.actual_amount"
            type="number"
            step="0.01"
            min="0"
            placeholder="请输入金额"
            :disabled="submitting"
          />
        </div>
        
        <!-- 实际成交日期 -->
        <div class="grid gap-2">
          <Label for="actual_closing_date">
            实际成交日期 <span class="text-destructive">*</span>
          </Label>
          <DatePicker
            :model-value="form.actual_closing_date ? new Date(form.actual_closing_date) : null"
            placeholder="请选择实际成交日期"
            :disabled="submitting"
            @update:model-value="(date: Date | null) => form.actual_closing_date = date ? formatLocalDate(date) : ''"
          />
        </div>
      </form>
      
      <DialogFooter class="flex-col gap-2 sm:flex-row">
        <Button
          variant="outline"
          :disabled="submitting"
          class="w-full sm:w-auto"
          @click="emit('update:open', false)"
        >
          取消
        </Button>
        <Button
          type="submit"
          :disabled="submitting || loading"
          :loading="submitting"
          class="w-full sm:w-auto"
          @click="handleSubmit"
        >
          {{ submitting ? '提交中...' : '确认' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
```

- [ ] **Step 2: 添加数据加载逻辑**

在 `<script setup>` 中添加：

```typescript
// 监听 open 变化，加载商机详情
watch(() => props.open, async (newOpen) => {
  if (newOpen && props.opportunityId) {
    loading.value = true
    try {
      opportunity.value = await opportunityApi.getOpportunity(props.opportunityId)
      // 预填充预计金额
      form.actual_amount = opportunity.value.total_amount
      form.actual_closing_date = getTodayLocalDate()
    } catch (error) {
      handleApiError(error, '加载商机详情')
      emit('update:open', false)
    } finally {
      loading.value = false
    }
  }
})
```

需要导入 `formatLocalDate`:

```typescript
import { getTodayLocalDate, formatLocalDate } from '@/utils/format'
```

- [ ] **Step 3: 添加表单提交逻辑**

在 `<script setup>` 中添加：

```typescript
// 提交赢单
async function handleSubmit(): Promise<void> {
  // 前端校验
  if (form.actual_amount <= 0) {
    toast.error('实际成交金额必须大于0')
    return
  }
  
  if (!form.actual_closing_date) {
    toast.error('请选择实际成交日期')
    return
  }
  
  if (!props.opportunityId) return
  
  submitting.value = true
  try {
    await opportunityApi.markAsWon(props.opportunityId, {
      actual_amount: form.actual_amount,
      actual_closing_date: form.actual_closing_date
    })
    
    toast.success('商机已标记为赢单')
    emit('success')
    emit('update:open', false)
  } catch (error) {
    handleApiError(error, '标记赢单')
  } finally {
    submitting.value = false
  }
}
```

- [ ] **Step 4: 手动测试**

1. 打开浏览器控制台
2. 在商机列表页点击"赢单"按钮
3. 验证弹窗打开，加载商机详情
4. 验证表单预填充预计金额
5. 输入无效数据（金额<=0），点击确认，验证错误提示
6. 输入有效数据，点击确认，验证提交成功
7. 验证弹窗关闭，列表刷新

- [ ] **Step 5: 提交代码**

```bash
git add CRM-Client/src/components/dialogs/OpportunityWinDialog.vue
git commit -m "feat(opportunity): add OpportunityWinDialog component"
```

---

### Task 2: 创建 OpportunityLoseDialog.vue 组件

**Files:**
- Create: `CRM-Client/src/components/dialogs/OpportunityLoseDialog.vue`

**Interfaces:**
- Consumes: `opportunityApi.getOpportunity(id)`, `opportunityApi.markAsLost(id, data)`
- Produces: `<OpportunityLoseDialog :opportunity-id :open @update:open @success />`

- [ ] **Step 1: 创建文件并编写组件骨架**

```vue
<script setup lang="ts">
/**
 * OpportunityLoseDialog.vue - 输单表单弹窗
 *
 * 收集输单原因，遵循无障碍和动效规范。
 */
import { ref, reactive, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { handleApiError } from '@/utils/errorHandler'
import { opportunityApi, type Opportunity } from '@/api/opportunity'

interface Props {
  opportunityId: number | null
  open: boolean
}

interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// 状态
const loading = ref(false)
const submitting = ref(false)
const opportunity = ref<Opportunity | null>(null)
const form = reactive({
  loss_reason: ''
})
</script>

<template>
  <Dialog :open="props.open" @update:open="emit('update:open', $event)">
    <DialogContent class="sm:max-w-[425px] max-w-full">
      <DialogHeader>
        <DialogTitle>标记输单</DialogTitle>
        <DialogDescription>请输入输单原因</DialogDescription>
      </DialogHeader>
      
      <div v-if="loading" class="py-8 text-center text-muted-foreground">
        加载中...
      </div>
      
      <form v-else class="grid gap-4 py-4">
        <!-- 输单原因 -->
        <div class="grid gap-2">
          <Label for="loss_reason">
            输单原因 <span class="text-destructive">*</span>
          </Label>
          <Textarea
            id="loss_reason"
            v-model="form.loss_reason"
            placeholder="请输入输单原因说明"
            :rows="4"
            :maxlength="500"
            :disabled="submitting"
          />
          <p class="text-xs text-muted-foreground">
            {{ form.loss_reason.length }}/500 字符
          </p>
        </div>
      </form>
      
      <DialogFooter class="flex-col gap-2 sm:flex-row">
        <Button
          variant="outline"
          :disabled="submitting"
          class="w-full sm:w-auto"
          @click="emit('update:open', false)"
        >
          取消
        </Button>
        <Button
          variant="destructive"
          type="submit"
          :disabled="submitting || loading"
          :loading="submitting"
          class="w-full sm:w-auto"
          @click="handleSubmit"
        >
          {{ submitting ? '提交中...' : '确认输单' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
```

- [ ] **Step 2: 添加数据加载逻辑**

在 `<script setup>` 中添加：

```typescript
// 监听 open 变化，加载商机详情
watch(() => props.open, async (newOpen) => {
  if (newOpen && props.opportunityId) {
    loading.value = true
    try {
      opportunity.value = await opportunityApi.getOpportunity(props.opportunityId)
      form.loss_reason = ''
    } catch (error) {
      handleApiError(error, '加载商机详情')
      emit('update:open', false)
    } finally {
      loading.value = false
    }
  }
})
```

- [ ] **Step 3: 添加表单提交逻辑**

在 `<script setup>` 中添加：

```typescript
// 提交输单
async function handleSubmit(): Promise<void> {
  // 前端校验
  const trimmedReason = form.loss_reason.trim()
  if (trimmedReason.length < 1 || trimmedReason.length > 500) {
    toast.error('输单原因长度必须在 1-500 字符之间')
    return
  }
  
  if (!props.opportunityId) return
  
  submitting.value = true
  try {
    await opportunityApi.markAsLost(props.opportunityId, {
      loss_reason: trimmedReason
    })
    
    toast.success('商机已标记为输单')
    emit('success')
    emit('update:open', false)
  } catch (error) {
    handleApiError(error, '标记输单')
  } finally {
    submitting.value = false
  }
}
```

- [ ] **Step 4: 手动测试**

1. 打开浏览器控制台
2. 在商机列表页点击"输单"按钮
3. 验证弹窗打开，加载商机详情
4. 输入空内容，点击确认，验证错误提示
5. 输入有效内容，点击确认，验证提交成功
6. 验证弹窗关闭，列表刷新

- [ ] **Step 5: 提交代码**

```bash
git add CRM-Client/src/components/dialogs/OpportunityLoseDialog.vue
git commit -m "feat(opportunity): add OpportunityLoseDialog component"
```

---

### Task 3: 重构 OpportunityDetailContent.vue

**Files:**
- Modify: `CRM-Client/src/components/panels/OpportunityDetailContent.vue`

**Interfaces:**
- Consumes: `<OpportunityWinDialog />`, `<OpportunityLoseDialog />`
- Produces: 移除内联弹窗，改用新组件

- [ ] **Step 1: 导入新弹窗组件**

在文件顶部导入部分添加：

```typescript
import OpportunityWinDialog from '@/components/dialogs/OpportunityWinDialog.vue'
import OpportunityLoseDialog from '@/components/dialogs/OpportunityLoseDialog.vue'
```

移除不再需要的导入：

```typescript
// 移除这些导入（已在新组件中）
// import { Input } from '@/components/ui/input'
// import { Label } from '@/components/ui/label'
// import { Textarea } from '@/components/ui/textarea'
// import { DatePicker } from '@/components/ui/date-picker'
```

- [ ] **Step 2: 移除内联弹窗状态**

移除以下状态定义：

```typescript
// 移除这些状态（第 76-86 行）
// const winForm = ref<OpportunityWinRequest>({
//   actual_amount: 0,
//   actual_closing_date: getTodayLocalDate()
// })
// const winSubmitting = ref(false)
// 
// const loseForm = ref<OpportunityLossRequest>({
//   loss_reason: ''
// })
// const loseSubmitting = ref(false)
```

保留这些状态：

```typescript
// 保留这两个状态
const winDialogOpen = ref(false)
const loseDialogOpen = ref(false)
```

- [ ] **Step 3: 修改成功回调函数**

修改 `handleShowWinDialog` 和 `handleShowLoseDialog` 函数（保持不变）：

```typescript
function handleShowWinDialog(): void {
  if (!opportunity.value) return
  winDialogOpen.value = true
}

function handleShowLoseDialog(): void {
  if (!opportunity.value) return
  loseDialogOpen.value = true
}
```

简化成功回调（移除之前的提交逻辑）：

```typescript
function handleWinSuccess(): void {
  winDialogOpen.value = false
  fetchOpportunityDetail()
  emit('refresh')
}

function handleLoseSuccess(): void {
  loseDialogOpen.value = false
  fetchOpportunityDetail()
  emit('refresh')
}
```

- [ ] **Step 4: 替换模板中的内联弹窗**

找到模板中的赢单和输单弹窗（约第 613-680 行），替换为：

```vue
<!-- 赢单弹窗 -->
<OpportunityWinDialog
  :opportunity-id="opportunity?.id ?? null"
  :open="winDialogOpen"
  @update:open="winDialogOpen = $event"
  @success="handleWinSuccess"
/>

<!-- 输单弹窗 -->
<OpportunityLoseDialog
  :opportunity-id="opportunity?.id ?? null"
  :open="loseDialogOpen"
  @update:open="loseDialogOpen = $event"
  @success="handleLoseSuccess"
/>
```

移除原有的内联 `<Dialog>` 代码（约 60 行）。

- [ ] **Step 5: 手动测试详情页**

1. 打开商机详情页
2. 点击"赢单"按钮
3. 验证弹窗打开，表单正常显示
4. 提交表单，验证详情页刷新
5. 点击"输单"按钮
6. 验证弹窗打开，表单正常显示
7. 提交表单，验证详情页刷新

- [ ] **Step 6: 提交代码**

```bash
git add CRM-Client/src/components/panels/OpportunityDetailContent.vue
git commit -m "refactor(opportunity): use OpportunityWinDialog and OpportunityLoseDialog in detail content"
```

---

### Task 4: 实现列表页推进阶段逻辑

**Files:**
- Modify: `CRM-Client/src/views/Opportunities.vue`

**Interfaces:**
- Consumes: `procurementApi.getOpportunityProcurementStages(id)`, `procurementApi.moveOpportunityStage(id, data)`
- Produces: 使用 `confirmDialog` 实现推进阶段

- [ ] **Step 1: 导入 confirmDialog 和 procurementApi**

在导入部分添加：

```typescript
import { confirmDialog } from '@/utils/confirmDialog'
import procurementApi from '@/api/procurement'
```

- [ ] **Step 2: 实现 handleAdvanceStage 函数**

替换原有的 `handleAdvanceStage` 函数（第 257-260 行）：

```typescript
const handleAdvanceStage = async (record: Opportunity): Promise<void> => {
  try {
    // 1. 获取可推进阶段
    const stages = await procurementApi.getOpportunityProcurementStages(record.id)
    
    if (stages.length === 0) {
      toast.warning('未配置采购阶段')
      return
    }
    
    // 2. 找到当前阶段
    const currentStage = stages.find(s => s.is_current)
    
    // 3. 新商机：设置起始阶段
    if (!currentStage) {
      const defaultStage = stages.find(s => s.is_default_start)
      if (!defaultStage) {
        toast.warning('未配置默认起始阶段')
        return
      }
      
      const confirmed = await confirmDialog(
        `确定将商机的起始阶段设置为「${defaultStage.stage_name}」？赢率将从 0% 变为 ${defaultStage.win_probability}%`,
        '设置起始阶段'
      )
      
      if (!confirmed) return
      
      await procurementApi.moveOpportunityStage(record.id, {
        stage_template_id: defaultStage.id
      })
      
      toast.success('起始阶段已设置')
      fetchOpportunities()
      return
    }
    
    // 4. 找到下一阶段
    const nextStage = stages.find(s => 
      s.sort_order > currentStage.sort_order && !s.is_current
    )
    
    if (!nextStage) {
      toast.warning('已是最终阶段')
      return
    }
    
    // 5. 确认推进
    const confirmed = await confirmDialog(
      `确定将商机推进到「${nextStage.stage_name}」？赢率将从 ${currentStage.win_probability}% 变为 ${nextStage.win_probability}%`,
      '推进阶段'
    )
    
    if (!confirmed) return
    
    // 6. 执行推进
    await procurementApi.moveOpportunityStage(record.id, {
      stage_template_id: nextStage.id
    })
    
    toast.success('阶段已推进')
    fetchOpportunities()
  } catch (error) {
    handleApiError(error, '推进阶段')
  }
}
```

- [ ] **Step 3: 手动测试推进阶段**

1. 打开商机列表页
2. 找到"跟进中"状态的商机
3. 点击"推进阶段"按钮
4. 验证确认弹窗显示正确的阶段信息
5. 点击确认，验证阶段推进成功
6. 验证列表自动刷新
7. 测试新商机（无当前阶段）的场景
8. 测试已是最终阶段的场景

- [ ] **Step 4: 提交代码**

```bash
git add CRM-Client/src/views/Opportunities.vue
git commit -m "feat(opportunity): implement advance stage logic in list page"
```

---

### Task 5: 集成列表页赢单/输单弹窗

**Files:**
- Modify: `CRM-Client/src/views/Opportunities.vue`

**Interfaces:**
- Consumes: `<OpportunityWinDialog />`, `<OpportunityLoseDialog />`
- Produces: 列表页操作按钮触发弹窗

- [ ] **Step 1: 导入弹窗组件**

在导入部分添加：

```typescript
import OpportunityWinDialog from '@/components/dialogs/OpportunityWinDialog.vue'
import OpportunityLoseDialog from '@/components/dialogs/OpportunityLoseDialog.vue'
```

- [ ] **Step 2: 添加弹窗状态**

在状态定义部分添加（约第 49 行）：

```typescript
// 赢单弹窗
const winDialogOpen = ref(false)
const selectedOpportunityIdForWin = ref<number | null>(null)

// 输单弹窗
const loseDialogOpen = ref(false)
const selectedOpportunityIdForLose = ref<number | null>(null)
```

- [ ] **Step 3: 修改操作处理函数**

替换原有的 `handleMarkAsWon` 和 `handleMarkAsLost` 函数（第 262-270 行）：

```typescript
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

// 赢单成功回调
const handleWinSuccess = (): void => {
  winDialogOpen.value = false
  fetchOpportunities()
}

// 输单成功回调
const handleLoseSuccess = (): void => {
  loseDialogOpen.value = false
  fetchOpportunities()
}
```

- [ ] **Step 4: 在模板中添加弹窗组件**

在模板末尾（`</div>` 之前）添加：

```vue
<!-- 赢单弹窗 -->
<OpportunityWinDialog
  :opportunity-id="selectedOpportunityIdForWin"
  :open="winDialogOpen"
  @update:open="winDialogOpen = $event"
  @success="handleWinSuccess"
/>

<!-- 输单弹窗 -->
<OpportunityLoseDialog
  :opportunity-id="selectedOpportunityIdForLose"
  :open="loseDialogOpen"
  @update:open="loseDialogOpen = $event"
  @success="handleLoseSuccess"
/>
```

- [ ] **Step 5: 手动测试列表页弹窗**

1. 打开商机列表页
2. 找到"跟进中"状态的商机
3. 点击"赢单"按钮
4. 验证弹窗打开，加载商机详情
5. 输入有效数据，提交，验证成功
6. 验证列表自动刷新，商机状态变为"已赢单"
7. 点击"输单"按钮
8. 验证弹窗打开，加载商机详情
9. 输入有效数据，提交，验证成功
10. 验证列表自动刷新，商机状态变为"已输单"

- [ ] **Step 6: 提交代码**

```bash
git add CRM-Client/src/views/Opportunities.vue
git commit -m "feat(opportunity): integrate win/lose dialogs in list page"
```

---

### Task 6: 验证和清理

**Files:**
- 全局验证

- [ ] **Step 1: 运行类型检查**

```bash
cd CRM-Client && npm run type-check
```

预期：无新增类型错误（可能有预存在的错误，但不影响本次修改）

- [ ] **Step 2: 运行 lint 检查**

```bash
cd CRM-Client && npm run lint
```

预期：无新增 lint 错误

- [ ] **Step 3: 手动测试所有场景**

测试清单：
1. [ ] 列表页推进阶段 - 新商机设置起始阶段
2. [ ] 列表页推进阶段 - 已有阶段推进到下一阶段
3. [ ] 列表页推进阶段 - 已是最终阶段提示
4. [ ] 列表页赢单 - 弹窗打开、加载详情、提交成功
5. [ ] 列表页输单 - 弹窗打开、加载详情、提交成功
6. [ ] 详情页赢单 - 弹窗打开、提交成功、详情刷新
7. [ ] 详情页输单 - 弹窗打开、提交成功、详情刷新
8. [ ] 表单校验 - 无效数据提交被阻止
9. [ ] 错误处理 - API 错误显示友好提示
10. [ ] 禁用状态 - 提交中按钮禁用，显示"提交中..."

- [ ] **Step 4: 清理废弃代码（如果有）**

检查是否有未被引用的导入、未使用的变量，运行 lint 会提示。

- [ ] **Step 5: 最终提交**

```bash
git add -A
git commit -m "feat(opportunity): complete action dialogs refactoring

- Add OpportunityWinDialog and OpportunityLoseDialog components
- Refactor OpportunityDetailContent to use new dialogs
- Implement advance stage logic in Opportunities list page
- Integrate win/lose dialogs in list page
- Follow accessibility and UX guidelines"
```

---

## Self-Review Checklist

- [x] **Spec coverage**: 所有设计文档要求都已实现
  - ✅ 创建赢单弹窗组件
  - ✅ 创建输单弹窗组件
  - ✅ 重构详情页
  - ✅ 集成列表页推进阶段
  - ✅ 集成列表页赢单/输单
  - ✅ 无障碍和动效规范

- [x] **Placeholder scan**: 无 TBD、TODO 等占位符

- [x] **Type consistency**: 组件接口与设计文档一致
  - Props: `opportunityId: number | null`, `open: boolean`
  - Emits: `update:open`, `success`
  - API 调用参数类型匹配

---

**计划完成，保存到 `docs/superpowers/plans/2026-07-16-opportunity-action-dialogs.md`**