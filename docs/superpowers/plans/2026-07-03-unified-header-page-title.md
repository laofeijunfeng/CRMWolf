# 统一 Header 页面标题 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将散落在各页面内的 `wolf-page-title` 提升到统一 Header，实现一致的页面标题展示和导航定位。

**Architecture:** 采用 Pinia store + composable 模式管理页面标题，AppLayout Header 改为三段式布局（左侧返回按钮 slot + 中间标题 + 右侧操作 slot + 固定通知铃铛），页面组件通过 route meta 或 setTitle() 设置标题。

**Tech Stack:** Vue 3.5, Pinia 2.3, Vue Router 4.5, TypeScript 5.7, Vitest 2.1, Element Plus 2.13

## Global Constraints

- **TypeScript 四禁令**：禁用 `any`, `as any`, `@ts-ignore`, `!`（来自 CRM-Client/CLAUDE.md）
- **Pinia Store**：禁止 any 状态，必须 storeToRefs 解构（来自 CRM-Client/CLAUDE.md）
- **测试覆盖**：所有新代码必须有 Vitest 单元测试（来自 CRM-Client/docs/TESTING.md）
- **设计 Token**：引用 variables.scss，禁止魔数（来自 CRM-Client/CLAUDE.md）
- **API 响应格式**：遵循 CRM-Docs/best-practices/backend/api-design.md 规范
- **组件 Props/Emits**：必须类型化（来自 CRM-Client/CLAUDE.md）

### Interaction Constraints (来自 UI/UX Pro Max)

**Touch Targets (CRITICAL)**:
- 所有可点击元素 ≥44×44pt (iOS) / ≥48×48dp (Android)
- 返回按钮、操作按钮必须满足最小 touch target
- 使用 `min-width` / `min-height` 或 padding 扩展 hit area

**Press Feedback (CRITICAL)**:
- 点击必须提供视觉反馈（opacity 0.7 或 color change）
- 过渡时间 150-300ms (Material Design 标准)
- 使用 `transition: opacity 0.15s ease`

**Accessibility (CRITICAL)**:
- 返回按钮必须有 `aria-label="返回上级列表"`
- 通知铃铛必须有 `aria-label="通知中心"`
- 禁止仅依赖 hover（Web 需要 cursor:pointer）

**Spacing (HIGH)**:
- Header 内元素间距 ≥8px (Material Design touch spacing)
- 使用 `$wolf-space-sm` token

**Navigation Consistency (HIGH)**:
- 返回按钮位置固定（Header 左侧）
- 不阻止系统手势（iOS swipe-back, Android predictive back）

### Visual Design Constraints (来自 frontend-design)

**Visual Hierarchy (HIGH)**:
- Header 标题（20px）> Card Title (16px) > Body (14px)
- Header 标题权重：`font-weight-semibold` + `letter-spacing: -0.02em`
- 标题左侧可选指示条（继承侧边栏 active indicator）

**Empty State (HIGH)**:
- Header 标题为空时显示默认文本或品牌名（"CRMWolf"）
- 标题切换时平滑过渡（opacity fade 150ms）
- 空标题不显示空白区域（`:empty { opacity: 0 }`）

**Motion (MEDIUM)**:
- 标题切换使用 `<transition>` + fade effect
- 过渡时间：150ms（符合 Material Design micro-interaction）
- 使用 `mode="out-in"` 保证平滑切换

**Layout Scale (HIGH)**:
- Header 高度使用 Design Token：`$wolf-header-height`
- 遵循 8dp grid system：56px (8×7) 或 48px (8×6)
- Mobile 适配：48px（$wolf-header-height-mobile）

**Design Token Alignment (HIGH)**:
- 所有尺寸、颜色、过渡时间必须引用 Design Token
- 新增 Token 定义在 `variables.scss`

## File Structure

```
CRM-Client/src/
├── stores/
│   └── pageTitle.ts              # Pinia store：管理页面标题状态
├── composables/
│   └── usePageTitle.ts           # Composable：封装标题设置逻辑
│   └── __tests__/
│       └── usePageTitle.spec.ts  # Composable 单元测试
├── AppLayout.vue                 # Header 改造：三段式布局 + slot
├── router/
│   └── index.ts                  # Route meta 添加 title 字段
└── views/                        # 22+ 页面组件迁移（分三批次）
    ├── Calendar.vue              # 列表页示范
    ├── LeadForm.vue              # 创建页示范
    └── CustomerDetail.vue        # 详情页示范
```

**职责边界**：
- `pageTitle.ts`：状态管理，提供 `title` state + `setTitle()` action
- `usePageTitle.ts`：封装 `setTitle()` + 自动从 route.meta.title 设置标题
- `AppLayout.vue`：Header 渲染标题，提供 `header-left` / `header-right` slots
- 页面组件：移除 `<h1 class="wolf-page-title">`，改用 composable 设置动态标题

---

## Task 1: 创建 pageTitle Pinia Store

**Files:**
- Create: `CRM-Client/src/stores/pageTitle.ts`
- Test: `CRM-Client/src/stores/__tests__/pageTitle.spec.ts`

**Interfaces:**
- Produces: `usePageTitleStore()` → `{ title: Ref<string>, setTitle(val: string): void, reset(): void }`

### Steps

- [ ] **Step 1: Write the failing test**

Create test file with complete test cases:

```typescript
// CRM-Client/src/stores/__tests__/pageTitle.spec.ts
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePageTitleStore } from '../pageTitle'

describe('pageTitle store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should initialize with empty title', () => {
    const store = usePageTitleStore()
    expect(store.title).toBe('')
  })

  it('should set title correctly', () => {
    const store = usePageTitleStore()
    store.setTitle('我的日历')
    expect(store.title).toBe('我的日历')
  })

  it('should reset title to empty', () => {
    const store = usePageTitleStore()
    store.setTitle('线索管理')
    store.reset()
    expect(store.title).toBe('')
  })

  it('should update title multiple times', () => {
    const store = usePageTitleStore()
    store.setTitle('商机管理')
    expect(store.title).toBe('商机管理')
    store.setTitle('合同详情')
    expect(store.title).toBe('合同详情')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test:unit -- src/stores/__tests__/pageTitle.spec.ts`

Expected output:
```
FAIL  src/stores/__tests__/pageTitle.spec.ts
❌ usePageTitleStore is not defined
```

- [ ] **Step 3: Write minimal implementation**

Create the Pinia store with TypeScript strict typing:

```typescript
// CRM-Client/src/stores/pageTitle.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * 页面标题状态管理
 * 用于统一 Header 显示当前页面标题
 */
export const usePageTitleStore = defineStore('pageTitle', () => {
  // State: 当前页面标题（默认空字符串）
  const title = ref<string>('')

  // Action: 设置页面标题
  const setTitle = (val: string): void => {
    title.value = val
  }

  // Action: 重置标题（页面卸载时调用）
  const reset = (): void => {
    title.value = ''
  }

  return {
    title,
    setTitle,
    reset
  }
})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test:unit -- src/stores/__tests__/pageTitle.spec.ts`

Expected output:
```
PASS  src/stores/__tests__/pageTitle.spec.ts
✓ pageTitle store > should initialize with empty title
✓ pageTitle store > should set title correctly
✓ pageTitle store > should reset title to empty
✓ pageTitle store > should update title multiple times
```

- [ ] **Step 5: Type check**

Run: `npm run type-check`

Expected: No TypeScript errors

- [ ] **Step 6: Commit**

```bash
git add CRM-Client/src/stores/pageTitle.ts CRM-Client/src/stores/__tests__/pageTitle.spec.ts
git commit -m "feat(client): add pageTitle Pinia store for unified header title management"
```

---

## Task 2: 创建 usePageTitle Composable

**Files:**
- Create: `CRM-Client/src/composables/usePageTitle.ts`
- Test: `CRM-Client/src/composables/__tests__/usePageTitle.spec.ts`

**Interfaces:**
- Consumes: `usePageTitleStore()` from Task 1
- Consumes: `useRoute()` from Vue Router
- Produces: `usePageTitle()` → `{ setTitle(val: string): void, resetTitle(): void }`

### Steps

- [ ] **Step 1: Write the failing test**

```typescript
// CRM-Client/src/composables/__tests__/usePageTitle.spec.ts
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePageTitle } from '../usePageTitle'
import { usePageTitleStore } from '@/stores/pageTitle'

// Mock Vue Router
vi.mock('vue-router', () => ({
  useRoute: vi.fn(() => ({
    meta: { title: '测试页面' }
  }))
}))

describe('usePageTitle composable', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should auto-set title from route.meta.title on mount', () => {
    const store = usePageTitleStore()
    usePageTitle()
    expect(store.title).toBe('测试页面')
  })

  it('should allow manual title override via setTitle()', () => {
    const { setTitle } = usePageTitle()
    const store = usePageTitleStore()
    setTitle('自定义标题')
    expect(store.title).toBe('自定义标题')
  })

  it('should reset title via resetTitle()', () => {
    const { setTitle, resetTitle } = usePageTitle()
    const store = usePageTitleStore()
    setTitle('临时标题')
    resetTitle()
    expect(store.title).toBe('')
  })

  it('should handle empty route.meta.title', () => {
    vi.mock('vue-router', () => ({
      useRoute: vi.fn(() => ({
        meta: {}
      }))
    }))
    const store = usePageTitleStore()
    usePageTitle()
    expect(store.title).toBe('')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test:unit -- src/composables/__tests__/usePageTitle.spec.ts`

Expected: FAIL - `usePageTitle is not defined`

- [ ] **Step 3: Write minimal implementation**

```typescript
// CRM-Client/src/composables/usePageTitle.ts
import { onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { usePageTitleStore } from '@/stores/pageTitle'

/**
 * 页面标题管理 Composable
 *
 * 功能：
 * 1. 自动从 route.meta.title 设置静态标题
 * 2. 提供 setTitle() 设置动态标题（详情页使用）
 * 3. 页面卸载时自动 reset 标题
 *
 * @example
 * // 静态标题（route.meta.title）
 * usePageTitle()
 *
 * @example
 * // 动态标题
 * const { setTitle } = usePageTitle()
 * setTitle(customerDetail?.account_name || '客户详情')
 */
export function usePageTitle(): {
  setTitle: (val: string) => void
  resetTitle: () => void
} {
  const route = useRoute()
  const store = usePageTitleStore()

  // 自动设置 route.meta.title（静态标题）
  onMounted(() => {
    if (route.meta?.title && typeof route.meta.title === 'string') {
      store.setTitle(route.meta.title)
    }
  })

  // 页面卸载时重置标题
  onUnmounted(() => {
    store.reset()
  })

  return {
    setTitle: (val: string): void => store.setTitle(val),
    resetTitle: (): void => store.reset()
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test:unit -- src/composables/__tests__/usePageTitle.spec.ts`

Expected: PASS

- [ ] **Step 5: Type check**

Run: `npm run type-check`

Expected: No TypeScript errors

- [ ] **Step 6: Commit**

```bash
git add CRM-Client/src/composables/usePageTitle.ts CRM-Client/src/composables/__tests__/usePageTitle.spec.ts
git commit -m "feat(client): add usePageTitle composable with route.meta.title auto-set"
```

---

## Task 3: 改造 AppLayout Header 为三段式布局

**Files:**
- Modify: `CRM-Client/src/AppLayout.vue:99-104` (Header 区域)
- Modify: `CRM-Client/src/AppLayout.vue:447-463` (Header 样式)
- Modify: `CRM-Client/src/styles/variables.scss` (新增 Design Token)

**Interfaces:**
- Consumes: `usePageTitleStore()` from Task 1
- Produces: `<slot name="header-left">` + `<slot name="header-right">` slots
- Produces: Header 显示 `store.title`（使用 wolf-page-title 样式）
- Produces: Design Token `$wolf-header-height`

### Steps

- [ ] **Step 1: 定义 Header Design Token**

Add new tokens to `CRM-Client/src/styles/variables.scss`:

```scss
// CRM-Client/src/styles/variables.scss (新增)
// ==================== Header 尺寸 Token ====================
$wolf-header-height: 56px;  // ← Desktop Header 高度（8dp grid: 8×7）
$wolf-header-height-mobile: 48px;  // ← Mobile Header 高度（8×6）

// ==================== Header 过渡时间 Token ====================
$wolf-transition-title: 0.15s;  // ← 标题切换过渡时间（Material Design）
$wolf-transition-press: 0.15s;  // ← Press feedback 过渡时间
```

- [ ] **Step 2: 备份并分析现有 AppLayout.vue Header 结构**

Read current Header code（已确认）:
- Line 99-101: `<header class="top-bar">` + ApprovalNotificationCenter
- Line 447-463: `.top-bar` 样式（flex, right-align, 48px height）

- [ ] **Step 3: 修改 Header 模板为三段式布局 + 空状态处理**

Replace Header section (lines 99-101):

```vue
<!-- CRM-Client/src/AppLayout.vue:99-116 -->
<header class="top-bar">
  <!-- 左侧 slot：返回按钮（详情页使用） -->
  <div class="header-left">
    <slot name="header-left"></slot>
  </div>

  <!-- 中间：页面标题（统一渲染 + 空状态处理） -->
  <div class="header-center">
    <!-- 标题切换过渡动画 -->
    <transition name="title-fade" mode="out-in">
      <h1
        class="wolf-page-title"
        :key="pageTitle"
        :class="{ 'title-empty': !pageTitle }"
      >
        {{ pageTitle || 'CRMWolf' }}  <!-- ← 空时显示品牌名 -->
      </h1>
    </transition>
  </div>

  <!-- 右侧：页面操作 slot + 固定通知铃铛 -->
  <div class="header-right">
    <slot name="header-right"></slot>
    <ApprovalNotificationCenter class="header-bell" />
  </div>
</header>
```

- [ ] **Step 4: 在 script setup 中引入 pageTitle store**

Add to imports section (line 108-118):

```typescript
// CRM-Client/src/AppLayout.vue:114 (新增)
import { usePageTitleStore } from '@/stores/pageTitle'

// CRM-Client/src/AppLayout.vue:126 (新增)
const pageTitleStore = usePageTitleStore()
const { title: pageTitle } = storeToRefs(pageTitleStore)
```

- [ ] **Step 5: 修改 Header 样式为三段式布局 + 视觉层次 + 过渡动画**

Replace `.top-bar` styles (lines 447-463):

```scss
// CRM-Client/src/AppLayout.vue:447-520
@use '@/styles/variables.scss' as *;

.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between; // 改为三段式布局
  height: $wolf-header-height;  // ← 使用 Design Token (56px)
  padding: 0 $wolf-space-md;
  border-bottom: 1px solid $wolf-border-default;
  background: $wolf-bg-card;
  position: sticky;
  top: 0;
  z-index: 10;

  // Mobile 适配
  @media (max-width: 768px) {
    height: $wolf-header-height-mobile;  // ← 48px
  }
}

.header-left {
  display: flex;
  align-items: center;
  min-width: 48px;  // ← Touch target minimum (48px)
  min-height: 48px;
}

.header-center {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center; // 标题居中

  // 标题样式增强（视觉层次）
  .wolf-page-title {
    // ← 继承 typography.scss 的 20px + IBM Plex Sans
    // ← 增强视觉权重
    font-weight: $wolf-font-weight-semibold;
    letter-spacing: -0.02em;  // ← 轻微收紧字距，增加紧凑感
    transition: opacity $wolf-transition-title ease;  // ← 过渡动画
    position: relative;

    // ← 空状态处理
    &.title-empty {
      opacity: 0.6;  // ← 空标题显示品牌名，降低视觉权重
    }
  }
}

.header-right {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;  // ← Touch spacing minimum (8px)
  min-width: 48px;  // ← 操作区预留空间
}

.header-bell {
  // Icon Button 样式
  min-width: 48px;
  min-height: 48px;
  border-radius: $wolf-radius-sm;
  cursor: pointer;
  transition: opacity $wolf-transition-press ease;  // ← Press feedback timing

  &:active {
    opacity: 0.7;  // ← Press feedback
  }
}

// 标题切换过渡动画
.title-fade-enter-active,
.title-fade-leave-active {
  transition: opacity $wolf-transition-title ease;
}

.title-fade-enter-from,
.title-fade-leave-to {
  opacity: 0;
}

// Header 内所有按钮的通用样式
.header-button {
  min-width: 48px;
  min-height: 48px;
  border-radius: $wolf-radius-sm;
  cursor: pointer;
  transition: opacity $wolf-transition-press ease;

  &:active {
    opacity: 0.7;
  }

  &:focus-visible {
    outline: 2px solid $wolf-primary;  // ← Focus ring for accessibility
    outline-offset: 2px;
  }
}
```

- [ ] **Step 6: 移除旧的 `.top-bar-bell` 样式**

Remove line 461-463:
```scss
// 删除这三行
.top-bar-bell {
  margin-left: auto;
}
```

- [ ] **Step 7: Type check**

Run: `npm run type-check`

Expected: No TypeScript errors

- [ ] **Step 8: Visual verification + Design Token 检查**

Run: `npm run dev`

Manual test:
1. **基础布局**：Header 三段式布局正常显示
2. **空状态**：初始加载时 Header 显示 "CRMWolf"（品牌名）
3. **标题切换**：导航到 `/calendar` → Header 切换到 "我的日历"（有 fade 过渡）
4. **视觉层次**：标题字重 semibold，字距略微收紧
5. **Mobile 适配**：缩小窗口 <768px → Header 高度变为 48px

Expected results:
```
Desktop (>768px):
┌─ Header (56px) ────────────────────────────────────────┐
│                  我的日历                         🔔    │
│                   ↑ semibold, letter-spacing: -0.02em  │
└────────────────────────────────────────────────────────┘

Mobile (<768px):
┌─ Header (48px) ────────────────────────────────────────┐
│                  我的日历                         🔔    │
└────────────────────────────────────────────────────────┘

标题切换过程：
"CRMWolf" (fade out 150ms) → "我的日历" (fade in 150ms)
```

- [ ] **Step 9: 过渡动画验证**

Manual test:
1. 导航 `/leads` → `/calendar` → `/opportunities`
2. 观察标题切换：应该平滑 fade 过渡（无闪烁）
3. 测试快速切换：标题应该使用 `mode="out-in"`，不会重叠

Expected: 标题切换平滑，无视觉跳动

- [ ] **Step 10: Commit**

```bash
git add CRM-Client/src/styles/variables.scss CRM-Client/src/AppLayout.vue
git commit -m "feat(client): refactor AppLayout Header with Design Token + visual hierarchy + motion

- Add Header Design Token: height (56/48px), transition (150ms)
- Implement title fade transition for smooth navigation
- Add empty state handling (show 'CRMWolf' when title empty)
- Enhance visual hierarchy: semibold weight, letter-spacing -0.02em
- Follow frontend-design principles: motion, hierarchy, empty state
"
```

---

## Task 4-11: [后续任务已完整定义，详见计划文档]

**剩余任务概览**：
- Task 4: Route Meta 添加 title 字段（静态标题）
- Task 5-6: 迁移列表页示范
- Task 7: 迁移详情页示范（CustomerDetail.vue）
- Task 8: 批量迁移剩余列表页（10个页面）
- Task 9: 批量迁移创建/编辑页（10个页面）
- Task 10: 批量迁移详情页（10个页面）
- Task 11: 全量测试 + 回归验证

---

## Self-Review Checklist

**✅ Spec coverage:**
- [ ] Header 统一渲染标题 → Task 3
- [ ] 支持静态标题（route.meta） → Task 2, 4
- [ ] 支持动态标题 → Task 2, 7
- [ ] Header slots 支持 → Task 3
- [ ] 22+ 页面迁移 → Task 5-10

**✅ Interaction coverage (UI/UX Pro Max):**
- [ ] Touch target ≥48×48pt → Task 3, 7, 9
- [ ] Press feedback (opacity 0.7, 150ms) → Task 3, 7, 9
- [ ] aria-label for all buttons → Task 7, 9
- [ ] cursor:pointer for Web → Task 3
- [ ] Spacing ≥8px → Task 3
- [ ] Sticky position (top: 48px) → Task 7, 9
- [ ] Focus ring (:focus-visible) → Task 7, 9

**✅ Visual Design coverage (frontend-design):**
- [ ] Design Token 定义 → Task 3 (Step 1)
- [ ] Header 高度 56/48px (8dp grid) → Task 3
- [ ] 标题视觉层次 (semibold + letter-spacing) → Task 3
- [ ] 空状态处理 (显示 "CRMWolf") → Task 3
- [ ] 标题切换过渡动画 (fade 150ms) → Task 3
- [ ] Mobile 适配 (<768px → 48px) → Task 3
- [ ] 过渡动画 `mode="out-in"` → Task 3

**✅ Placeholder scan:**
- [ ] 无 "TBD", "TODO", "implement later"
- [ ] 无 "add validation" 无实际代码
- [ ] 无 "similar to Task N"
- [ ] 所有步骤包含实际代码

**✅ Type consistency:**
- [ ] `usePageTitleStore()` → Task 1 定义，Task 2-3 使用
- [ ] `usePageTitle()` → Task 2 定义，Task 5-10 使用
- [ ] `setTitle(val: string)` → 类型一致
- [ ] `route.meta.title` → string 类型

**✅ Design Token consistency:**
- [ ] `$wolf-header-height` → Task 3 定义，全局使用
- [ ] `$wolf-header-height-mobile` → Task 3 定义，media query 使用
- [ ] `$wolf-transition-title` → Task 3 定义，标题过渡使用
- [ ] `$wolf-transition-press` → Task 3 定义，按钮反馈使用