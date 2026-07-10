# Leads.vue 优化实施计划

**基于设计规范 + navigation-redesign-v3.html + 审查报告**

---

## 一、审查发现

### 1.1 违规项汇总

| 优先级 | 问题 | 位置 | 规范依据 |
|--------|------|------|---------|
| **P0 CRITICAL** | 使用旧版 `variables.scss` | Line 560 | MASTER.md 二、Design Token 强制规范 |
| **P1 HIGH** | 按钮位置错误（应在 TopBar） | Line 4-24 | list-page.md 2.2 操作按钮规范 |
| **P1 HIGH** | `el-pagination` | Line 146-155 | §1.5 shadcn-vue 优先原则 |
| **P1 HIGH** | `ElMessageBox` | Line 169, 480, 526 | §1.5 shadcn-vue 优先原则 |
| **P2 HIGH** | Emoji 作为图标 | Line 313-317 | §4 no-emoji-icons |
| **P2 HIGH** | 硬编码颜色 | Line 321-325, 799 | MASTER.md 二、Design Token 强制规范 |

---

## 二、核心优化：TopBar 按钮布局

### 2.1 当前问题

**错误布局**：按钮在 `.page-header`（页面内容区域）

```vue
<!-- 当前（错误） - Line 4-24 -->
<div class="page-header">
  <div class="header-actions">
    <Button @click="showAILeadCreate = true">AI 创建线索</Button>
    <Button variant="outline" @click="router.push('/leads/create')">手动创建</Button>
  </div>
</div>
```

### 2.2 设计规范依据

**list-page.md 2.2 操作按钮规范**：

| 按钮 | 类型 | 优先级 | 位置 |
|------|------|--------|------|
| **新建** | Primary | 最高 | 右侧最左 |
| **导出** | Default | 中等 | 新建按钮右侧 |
| **审批铃铛** | Icon | 低 | 最右侧（固定） |

**三段式布局**：

| 区域 | 内容 | 示例 |
|------|------|------|
| **左侧（48px）** | 空白或返回按钮 | 无（列表页无返回） |
| **中间（居中）** | 页面标题 | "线索管理" |
| **右侧（自适应）** | 操作按钮 + 审批铃铛 | "AI 创建" + "手动创建" + 🔔 |

### 2.3 修复方案

**方案 A（推荐）：使用 `headerStore` 配置 TopBar**

```typescript
// Leads.vue - onMounted
import { useHeaderStore } from '@/stores/header'
import { WandSparkles, Edit } from 'lucide-vue-next'

const headerStore = useHeaderStore()

onMounted(() => {
  // 配置 TopBar 操作按钮
  headerStore.setActions([
    {
      id: 'ai-create',
      label: 'AI 创建线索',
      icon: WandSparkles,
      type: 'primary',
      handler: () => showAILeadCreate.value = true,
      visible: canCreateLead.value
    },
    {
      id: 'manual-create',
      label: '手动创建',
      icon: Edit,
      type: 'default',
      handler: () => router.push('/leads/create'),
      visible: canCreateLead.value
    }
  ])
})

onUnmounted(() => {
  headerStore.clear()
})
```

**方案 B（备选）：直接修改 AppLayout.vue TopBar**

> 注：方案 A 更符合设计模式（中央状态管理），推荐使用。

### 2.4 视觉效果对比

**Before（错误）**：
```
┌─────────────────────────────────────────────────┐
│ TopBar: [线索管理]               [🔔 审批]      │
├─────────────────────────────────────────────────┤
│ Content:                                        │
│ ┌──────────────────────────────────────┐        │
│ │ [AI 创建线索] [手动创建]              │ ← 按钮在内容区
│ └──────────────────────────────────────┘        │
│ [搜索栏]                                         │
│ [列表]                                           │
└─────────────────────────────────────────────────┘
```

**After（正确）**：
```
┌─────────────────────────────────────────────────┐
│ TopBar: [线索管理]  [AI 创建] [手动创建] [🔔]   │ ← 按钮在 TopBar
├─────────────────────────────────────────────────┤
│ Content:                                        │
│ [搜索栏]                                         │
│ [列表]                                           │
└─────────────────────────────────────────────────┘
```

---

## 三、详细实施步骤

### Phase 1：Design Token 迁移（P0 CRITICAL）

#### Step 1.1：替换 variables.scss → variables-v2.scss

```scss
// 当前（错误）
@use '@/styles/variables.scss' as *;

// 修复为
@use '@/styles/variables-v2.scss' as *;
```

#### Step 1.2：更新所有变量引用

| 旧变量 | 新变量 | 示例位置 |
|--------|--------|---------|
| `$wolf-bg-page` | `$wolf-bg-page-v2` | Line 564 |
| `$wolf-bg-card` | `$wolf-bg-card-v2` | Line 591, 639 |
| `$wolf-bg-hover` | `$wolf-bg-hover-v2` | Line 597, 602 |
| `$wolf-text-tertiary` | `$wolf-text-tertiary-v2` | Line 589, 706 |
| `$wolf-text-secondary` | `$wolf-text-secondary-v2` | Line 598, 712 |
| `$wolf-border-light` | `$wolf-border-light-v2` | Line 685, 722 |
| `$wolf-warning-bg` | `$wolf-warning-bg-v2` | Line 759 |
| `$wolf-warning-text` | `$wolf-warning-text-v2` | Line 760 |
| `$wolf-success-bg` | `$wolf-success-bg-v2` | Line 764 |
| `$wolf-success-text` | `$wolf-success-text-v2` | Line 765 |
| `$wolf-danger-bg` | `$wolf-danger-bg-v2` | Line 768 |
| `$wolf-danger-text` | `$wolf-danger-text-v2` | Line 769 |

---

### Phase 2：TopBar 按钮迁移（P1 HIGH）

#### Step 2.1：移除 page-header

```vue
<!-- 删除 Line 4-24 -->
<div class="page-header">
  <div class="header-actions">
    ...旧按钮代码...
  </div>
</div>
```

#### Step 2.2：使用 headerStore 配置

```typescript
// Leads.vue <script setup>
import { useHeaderStore } from '@/stores/header'
import { onMounted, onUnmounted } from 'vue'
import { WandSparkles, Edit } from 'lucide-vue-next'

const headerStore = useHeaderStore()

onMounted(() => {
  headerStore.configure({
    actions: [
      {
        id: 'ai-create',
        label: 'AI 创建线索',
        icon: WandSparkles,
        type: 'primary',
        handler: () => showAILeadCreate.value = true,
        visible: canCreateLead.value
      },
      {
        id: 'manual-create',
        label: '手动创建',
        icon: Edit,
        type: 'default',
        handler: () => router.push('/leads/create'),
        visible: canCreateLead.value
      }
    ]
  })
})

onUnmounted(() => {
  headerStore.clear()
})
```

#### Step 2.3：响应式按钮权限

```typescript
// 使用 computed 确保权限变化时按钮更新
watchEffect(() => {
  headerStore.configure({
    actions: [
      {
        ...actions[0],
        visible: canCreateLead.value  // 权限变化时自动更新
      },
      {
        ...actions[1],
        visible: canCreateLead.value
      }
    ]
  })
})
```

---

### Phase 3：Element Plus 替换（P1 HIGH）

#### Step 3.1：替换 el-pagination

**当前代码**（Line 146-155）：

```vue
<el-pagination
  v-model:current-page="pagination.current"
  v-model:page-size="pagination.pageSize"
  :page-sizes="[10, 20, 50, 100]"
  :total="pagination.total"
  layout="sizes, prev, pager, next, jumper"
/>
```

**方案 A**：使用 shadcn-vue Pagination（如果可用）

```vue
<Pagination
  v-model:page="pagination.current"
  v-model:pageSize="pagination.pageSize"
  :total="pagination.total"
  :pageSizes="[10, 20, 50, 100]"
/>
```

**方案 B**：自定义 Pagination（如果 shadcn-vue 无此组件）

```vue
<!-- 保留原生实现，但使用 V2 tokens -->
<div class="pagination-bar">
  <span class="total-text">共 {{ pagination.total }} 条</span>
  <div class="pagination-controls">
    <Button variant="outline" size="sm" :disabled="pagination.current === 1" @click="pagination.current--">
      上一页
    </Button>
    <span class="page-indicator">{{ pagination.current }} / {{ totalPages }}</span>
    <Button variant="outline" size="sm" :disabled="pagination.current === totalPages" @click="pagination.current++">
      下一页
    </Button>
  </div>
</div>
```

#### Step 3.2：替换 ElMessageBox

**当前代码**（Line 480, 526）：

```typescript
import { ElMessageBox } from 'element-plus'

await ElMessageBox.confirm('确定退回公海？', '确认', {
  confirmButtonText: '确定',
  cancelButtonText: '取消',
  type: 'warning'
})
```

**替换为 vue-sonner toast（轻量确认）**：

```typescript
import { toast } from 'vue-sonner'

// 方案 A：使用 toast.confirm（如果 vue-sonner 支持）
toast.confirm('确定退回公海？', {
  action: {
    label: '确定',
    onClick: async () => {
      await leadApi.returnLead(id)
      toast.success('线索已退回公海')
      fetchLeadList()
    }
  },
  cancel: {
    label: '取消'
  }
})
```

**或使用 shadcn-vue AlertDialog**：

```vue
<script setup>
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
</script>

<template>
  <AlertDialog v-model:open="showReturnConfirm">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>确认操作</AlertDialogTitle>
        <AlertDialogDescription>
          确定要退回公海吗？此操作不可撤销。
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel>取消</AlertDialogCancel>
        <AlertDialogAction @click="handleConfirmReturn">确定</AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>
```

---

### Phase 4：Emoji 图标替换（P2 HIGH）

#### Step 4.1：替换 getScoreIcon

**当前代码**（Line 313-317）：

```typescript
const getScoreIcon = (score: number | null | undefined) => {
  if (score === null || score === undefined) return '❓'
  if (score >= 80) return '🔥'
  if (score >= 60) return '⚡'
  if (score >= 40) return '✅'
  return '❄️'
}
```

**修复为 Lucide icons**：

```typescript
import { Flame, Zap, CheckCircle, Snowflake, HelpCircle } from 'lucide-vue-next'
import type { Component } from 'vue'

const getScoreIcon = (score: number | null | undefined): Component => {
  if (score === null || score === undefined) return HelpCircle
  if (score >= 80) return Flame
  if (score >= 60) return Zap
  if (score >= 40) return CheckCircle
  return Snowflake
}
```

#### Step 4.2：更新模板

```vue
<!-- 当前 -->
<span class="score-icon">{{ getScoreIcon(lead.score) }}</span>

<!-- 修复为 -->
<component
  :is="getScoreIcon(lead.score)"
  class="score-icon"
  :style="{ color: getScoreColor(lead.score) }"
/>
```

---

### Phase 5：硬编码颜色修复（P2 HIGH）

#### Step 5.1：替换 getScoreColor

**当前代码**（Line 321-325）：

```typescript
const getScoreColor = (score: number | null | undefined) => {
  if (score === null || score === undefined) return '#d9d9d9'
  if (score >= 80) return '#ff4d4f'
  if (score >= 60) return '#faad14'
  if (score >= 40) return '#52c41a'
  return '#d9d9d9'
}
```

**修复为 CSS class 绑定**：

```typescript
const getScoreColorClass = (score: number | null | undefined): string => {
  if (score === null || score === undefined) return 'score-unknown'
  if (score >= 80) return 'score-high'
  if (score >= 60) return 'score-medium'
  if (score >= 40) return 'score-low'
  return 'score-unknown'
}
```

```scss
// 在 <style> 中添加 V2 token 样式
.score-high { color: $wolf-danger-v2; }      // #DC2626
.score-medium { color: $wolf-warning-v2; }   // #F59E0B
.score-low { color: $wolf-success-v2; }      // #10B981
.score-unknown { color: $wolf-text-tertiary-v2; }  // #94A3B8
```

#### Step 5.2：修复硬编码颜色（Line 799）

```scss
// 当前（错误）
.action-danger {
  &:hover { color: #A83232; }
}

// 修复为
.action-danger {
  &:hover { color: darken($wolf-danger-v2, 10%); }
}
```

---

### Phase 6：Accessibility（P1 CRITICAL）

> **新增**：基于 UI/UX Pro Max §1 Accessibility

#### Step 6.1：TopBar 按钮 aria-labels

**当前代码**（Phase 2）：

```typescript
headerStore.setActions([
  {
    id: 'ai-create',
    label: 'AI 创建线索',
    icon: WandSparkles,
    type: 'primary',
    handler: () => showAILeadCreate.value = true,
    visible: canCreateLead.value
  }
])
```

**添加 aria-label**：

```typescript
headerStore.setActions([
  {
    id: 'ai-create',
    label: 'AI 创建线索',
    icon: WandSparkles,
    ariaLabel: '使用 AI 智能创建新线索',  // 新增：详细描述
    type: 'primary',
    handler: () => showAILeadCreate.value = true,
    visible: canCreateLead.value
  },
  {
    id: 'manual-create',
    label: '手动创建',
    icon: Edit,
    ariaLabel: '手动填写表单创建新线索',  // 新增
    type: 'default',
    handler: () => router.push('/leads/create'),
    visible: canCreateLead.value
  }
])
```

**更新 headerStore 类型**：

```typescript
// src/stores/header.ts
export interface HeaderAction {
  id: string
  label: string
  handler: () => void
  type?: 'primary' | 'success' | 'danger' | 'default'
  icon?: Component
  disabled?: boolean
  visible?: boolean
  ariaLabel?: string  // 新增
}
```

#### Step 6.2：AlertDialog focus management

**shadcn-vue AlertDialog 内置支持**：

```vue
<AlertDialog>
  <AlertDialogContent>
    <!-- 自动聚焦到 AlertDialogAction -->
    <AlertDialogAction>确定</AlertDialogAction>
  </AlertDialogContent>
</AlertDialog>
```

**手动添加 focus-visible**：

```scss
// AlertDialog focus ring
.alert-dialog-action:focus-visible {
  outline: 2px solid $wolf-primary-v2;
  outline-offset: 2px;
}
```

#### Step 6.3：Keyboard navigation

**Escape 键支持**（shadcn-vue 内置）：

```vue
<!-- AlertDialog 自动处理 Escape 键关闭 -->
<AlertDialog v-model:open="showReturnConfirm">
  ...
</AlertDialog>
```

**TouchCard keyboard navigation**：

```vue
<TouchCard
  clickable
  tabindex="0"
  role="button"
  :aria-label="`查看线索：${lead.lead_name}`"
  @click="handleViewDetail(lead)"
  @keydown.enter="handleViewDetail(lead)"
>
```

---

### Phase 7：Touch & Interaction（P1 CRITICAL）

> **新增**：基于 UI/UX Pro Max §2 Touch & Interaction

#### Step 7.1：loading-buttons

**规范依据**：§2 loading-buttons - Disable button during async operations; show spinner or progress

**AI 创建按钮**：

```vue
<script setup>
const isCreating = ref(false)

async function handleAICreate() {
  isCreating.value = true
  try {
    await leadApi.createWithAI(...)
    toast.success('线索创建成功')
  } finally {
    isCreating.value = false
  }
}
</script>

<template>
  <Button
    :disabled="isCreating"
    @click="handleAICreate"
  >
    <Loader2 v-if="isCreating" class="w-4 h-4 mr-2 animate-spin" />
    <WandSparkles v-else class="w-4 h-4 mr-2" />
    AI 创建线索
  </Button>
</template>
```

#### Step 7.2：TouchCard press feedback

**规范依据**：§2 press-feedback - Visual feedback on press (ripple/highlight; MD state layers)

```scss
// 添加 pressed 状态
.lead-card {
  cursor: pointer;
  transition: transform $wolf-transition-v2;

  &:active {
    transform: scale(0.98);  // Pressed feedback
  }
}

// reduced-motion 支持
@media (prefers-reduced-motion: reduce) {
  .lead-card {
    transition: none;
    &:active {
      transform: none;
      background: $wolf-bg-active-v2;  // Fallback: 背景变化
    }
  }
}
```

---

### Phase 8：Animation（P2 MEDIUM）

> **新增**：基于 UI/UX Pro Max §7 Animation

#### Step 8.1：reduced-motion 支持

**规范依据**：§7 reduced-motion - Respect prefers-reduced-motion; reduce/disable animations when requested

```scss
// 全局 reduced-motion
@media (prefers-reduced-motion: reduce) {
  // TouchCard
  .lead-card {
    transition-duration: $wolf-reduced-motion-duration-v2;  // 0.01ms
  }

  // Pagination
  .pagination-controls button {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }

  // AlertDialog
  .alert-dialog-content {
    animation-duration: $wolf-reduced-motion-duration-v2;
  }

  // Status Badge
  .status-tag {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
```

#### Step 8.2：duration-timing

**规范依据**：§7 duration-timing - Use 150–300ms for micro-interactions

```scss
// 分页切换
.pagination-controls button {
  transition: all 0.15s ease;  // 150ms（V2 token）
}

// AlertDialog
.alert-dialog-content {
  animation: dialog-enter 0.2s ease-out;  // 200ms
}

@keyframes dialog-enter {
  from {
    opacity: 0;
    transform: scale(0.95);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
```

#### Step 8.3：exit-faster-than-enter

**规范依据**：§7 exit-faster-than-enter - Exit animations shorter than enter (~60–70% of enter duration)

```scss
// AlertDialog 退出动画（比进入快 60%）
.alert-dialog-content {
  &.exit {
    animation: dialog-exit 0.12s ease-in;  // 120ms（200ms * 60%）
  }
}

@keyframes dialog-exit {
  from {
    opacity: 1;
    transform: scale(1);
  }
  to {
    opacity: 0;
    transform: scale(0.95);
  }
}
```

---

### Phase 9：Performance（P3 LOW）

> **新增**：基于 UI/UX Pro Max §3 Performance

#### Step 9.1：virtualize-lists

**规范依据**：§3 virtualize-lists - Virtualize lists with 50+ items to improve memory efficiency

**条件渲染**：

```vue
<script setup>
import { RecycleScroller } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'

const needsVirtualization = computed(() => tableData.value.length > 50)
</script>

<template>
  <!-- 超过 50 条：启用虚拟滚动 -->
  <RecycleScroller
    v-if="needsVirtualization"
    class="leads-virtual-list"
    :items="tableData"
    :item-size="88"
    key-field="id"
    :buffer="200"
  >
    <template #default="{ item }">
      <TouchCard
        clickable
        :aria-label="`查看线索：${item.lead_name}`"
        class="lead-card"
        @click="handleViewDetail(item)"
      >
        <!-- TouchCard 内容 -->
      </TouchCard>
    </template>
  </RecycleScroller>

  <!-- 少于 50 条：普通列表 -->
  <div v-else class="leads-cards">
    <TouchCard
      v-for="lead in tableData"
      :key="lead.id"
      ...
    />
  </div>
</template>

<style scoped lang="scss">
.leads-virtual-list {
  height: calc(100vh - 200px);  // 扣除 TopBar + SearchCard + Pagination
  overflow-y: auto;
}
</style>
```

#### Step 9.2：progressive-loading

**规范依据**：§3 progressive-loading - Use skeleton screens / shimmer instead of long blocking spinners

**已实现**（Line 36-40）：

```vue
<LoadingSkeleton
  v-if="loading"
  type="list"
  :rows="10"
  show-avatar
/>
```

**确保骨架屏使用 V2 tokens**：

```scss
// src/components/crmwolf/LoadingSkeleton.vue
.skeleton-row {
  background: linear-gradient(
    90deg,
    $wolf-bg-muted-v2 0%,
    $wolf-bg-card-v2 50%,
    $wolf-bg-muted-v2 100%
  );
  animation: shimmer 1.5s infinite;
}
```

---

## 四、改造优先级与时间预估

| Priority | Phase | 任务 | 预估时间 | 新增/原计划 |
|----------|-------|------|---------|------------|
| **P0 CRITICAL** | Phase 1 | Design Token 迁移 | 10min | 原计划 |
| **P1 HIGH** | Phase 2 | TopBar 按钮迁移 | 15min | 原计划 |
| **P1 HIGH** | Phase 3 | Element Plus 替换 | 20min | 原计划 |
| **P2 HIGH** | Phase 4 | Emoji 图标替换 | 10min | 原计划 |
| **P2 HIGH** | Phase 5 | 硬编码颜色修复 | 5min | 原计划 |
| **P1 CRITICAL** | **Phase 6** | **Accessibility（新增）** | 10min | 新增 |
| **P1 CRITICAL** | **Phase 7** | **Touch & Interaction（新增）** | 5min | 新增 |
| **P2 MEDIUM** | **Phase 8** | **Animation（新增）** | 5min | 新增 |
| **P3 LOW** | **Phase 9** | **Performance（新增）** | 10min | 新增 |
| **总计** | - | - | **90min** | +30min |

---

## 五、验收标准

### 5.1 设计规范验收

| 检查项 | 规范来源 | 验收方法 |
|--------|---------|---------|
| **使用 variables-v2.scss** | MASTER.md 二 | `grep "variables-v2" src/views/Leads.vue` → 有匹配 |
| **无 variables.scss** | MASTER.md 二 | `grep "variables.scss" src/views/Leads.vue` → 无匹配 |
| **TopBar 按钮位置正确** | list-page.md 2.2 | 视觉检查（按钮在 TopBar 右侧） |
| **无 el-pagination** | §1.5 | `grep "el-pagination" src/views/Leads.vue` → 无匹配 |
| **无 ElMessageBox** | §1.5 | `grep "ElMessageBox" src/views/Leads.vue` → 无匹配 |
| **无 Emoji 图标** | §4 no-emoji-icons | `grep "🔥\|⚡\|✅\|❄️\|❓" src/views/Leads.vue` → 无匹配 |
| **无硬编码颜色** | MASTER.md 二 | `grep "#[0-9a-fA-F]{6}" src/views/Leads.vue` → 无匹配 |

### 5.2 Accessibility 验收（新增）

| 检查项 | 规范来源 | 验收方法 |
|--------|---------|---------|
| **aria-labels** | §1 aria-labels | axe-core 检查 TopBar 按钮 |
| **focus-states** | §1 focus-states | Tab 键导航 + 视觉检查 |
| **keyboard-nav** | §1 keyboard-nav | Escape 键关闭 AlertDialog |
| **reduced-motion** | §7 reduced-motion | `prefers-reduced-motion: reduce` 测试 |

### 5.3 Touch & Interaction 验收（新增）

| 检查项 | 规范来源 | 验收方法 |
|--------|---------|---------|
| **loading-buttons** | §2 loading-buttons | 点击按钮后显示 spinner |
| **press-feedback** | §2 press-feedback | TouchCard 点击后 scale(0.98) |

### 5.4 Animation 验收（新增）

| 检查项 | 规范来源 | 验收方法 |
|--------|---------|---------|
| **duration-timing** | §7 duration-timing | 动画 150-300ms |
| **exit-faster-than-enter** | §7 exit-faster-than-enter | AlertDialog 关闭动画快于打开 |

### 5.5 功能验收

| 检查项 | 验收方法 |
|--------|---------|
| **AI 创建线索按钮** | 点击后打开 AILeadCreateDialog |
| **手动创建按钮** | 点击后跳转 `/leads/create` |
| **分页功能** | 上一页/下一页/跳转正常 |
| **退回公海确认** | 点击后显示确认对话框 |
| **删除线索确认** | 点击后显示确认对话框 |
| **热力值图标** | 使用 Lucide icons 正确显示 |

---

## 六、风险与替代方案

### 6.1 技术风险

| 风险 | 影响 | 替代方案 |
|------|------|---------|
| **headerStore 响应式更新** | 权限变化时按钮不更新 | 使用 watchEffect 强制更新 |
| **shadcn-vue 无 Pagination** | 分页组件缺失 | 自定义 Pagination 或保留 el-pagination（临时） |
| **vue-sonner 无 confirm** | 确认对话框缺失 | 使用 shadcn-vue AlertDialog |

### 6.2 向后兼容

| 旧实现 | 新实现 | 迁移时间 |
|--------|--------|---------|
| `variables.scss` | `variables-v2.scss` | 立即迁移 |
| `el-pagination` | shadcn-vue Pagination | 待组件可用 |
| `ElMessageBox` | AlertDialog | 立即迁移 |

---

## 七、执行确认

- **是否开始执行优化**：[待用户确认]
- **改造范围**：Phase 1-5 全量优化
- **预估完成时间**：60min

---

**文档版本**：V2.0（新增 Phase 6-9）| **创建日期**：2026-07-09 | **依据规范**：MASTER.md V2.1 + list-page.md + navigation-redesign-v3.html + UI/UX Pro Max

---

## 附录：更新记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| **V2.0** | 2026-07-09 | 新增 Phase 6-9（Accessibility, Touch, Animation, Performance） |
| **V1.0** | 2026-07-09 | 初始版本（Phase 1-5） |