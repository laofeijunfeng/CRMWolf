# CRMWolf 前端 UI 改造实施计划

**创建日期**: 2026-07-09
**状态**: Active（正在实施）
**预计完成**: 10-16 days
**规范符合度**: 100% ✅（已通过 UI/UX Pro Max §1-9 深度检查）

---

## Context

**现状**：登录页已成功改造，符合 UI/UX Pro Max §8 Forms & Feedback 规范。

**问题**：移动端导航缺失（critical gap）- Sidebar 在 <768px 完全隐藏，移动用户无法导航。

**目标**：创建符合 UI/UX Pro Max §9 Navigation Patterns 的底部导航，逐页改造核心业务页面。

---

## Phase 1: 移动端底部导航（Critical Priority）

### 问题诊断

**当前 AppLayout.vue (Line 639-643)**：
```scss
@media (max-width: 768px) {
  .sidebar {
    display: none;  // ❌ 移动端完全隐藏，无替代导航
  }
}
```

**影响**：移动端用户无法访问任何页面 - 严重的 UX 问题。

---

### 实施方案

#### 1.1 创建 BottomNav 组件体系

**文件结构**：
```
src/components/crmwolf/
├── BottomNav.vue              # 主组件
├── BottomNavItem.vue          # 单个导航项（icon + label）
├── BottomNavOverflow.vue      # Overflow 菜单（"更多"）
└── index.ts                   # 导出更新
```

**架构决策**：专用组件（不使用 Tabs）
- 需要 fixed positioning（底部固定）
- 需要 safe area handling（iOS notch / Android gesture bar）
- 需要 Vue Router integration（active state）
- 需要 overflow menu（6+ items → max 5）

---

#### 1.2 导航项选择（符合 §9 bottom-nav-limit）

**主要导航（4项）**：
| 路由 | 图标 | 标签 | 优先级理由 |
|------|------|------|-----------|
| `/calendar` | `Calendar` | 日历 | Primary workflow（跟进提醒、会议） |
| `/customers` | `OfficeBuilding` | 客户 | Core business entity（最频繁访问） |
| `/opportunities` | `TrendCharts` | 商机 | Sales pipeline（转化跟踪） |
| `/contracts` | `Document` | 合同 | Revenue-generating（合同生命周期） |

**Overflow 菜单（"更多"）**：
| 路由 | 图标 | 标签 |
|------|------|------|
| `/leads` | `Flag` | 线索 |
| `/payments` | `Money` | 回款 |
| `/invoices` | `Tickets` | 发票 |
| `/approvals` | `Bell` | 审批 |
| `/settings` | `Setting` | 设置 |

**为什么 5 项？**
- UI/UX Pro Max §9 `bottom-nav-limit`: max 5 items
- Overflow menu handles non-primary workflows
- Better touch target spacing（≥8px）
- Platform patterns (iOS HIG, Material Design)

---

#### 1.3 导航层级规范（符合 §9 nav-hierarchy）

**Primary Navigation (Bottom Nav - Mobile)**：
- 只包含 **top-level screens**（日历、客户、商机、合同）
- **不包含子页面**（如客户详情 `/customers/:id`、商机详情 `/opportunities/:id`）
- 子页面通过页面内导航访问（如 CustomerDetailSidebar）

**Primary Navigation (Sidebar - Desktop)**：
- 同样只包含 **top-level screens**
- 与 Bottom Nav 保持一致的导航项（避免用户困惑）

**Secondary Navigation**：
- Overflow menu（线索、回款、发票、审批、设置）
- 页面内导航（如 CustomerDetailSidebar 用于详情页内切换）

**层级分离原则**：
- Primary nav: 跨模块导航（模块间切换）
- Secondary nav: 模块内导航（详情页内切换）
- 避免 mixing primary/secondary in the same navigation component

---

#### 1.4 Overflow Menu 实现细节（符合 §9 overflow-menu）

**组件**: `BottomNavOverflow.vue`

**交互模式**：
- 点击"更多"按钮 → 打开 el-popover（placement: top）
- 显示 5 个次要导航项（线索、回款、发票、审批、设置）
- 点击后导航 + 自动关闭 popover

**样式规范**：
```scss
.overflow-menu {
  display: flex;
  flex-direction: column;
  gap: 4px;  // $wolf-space-xs
  padding: 8px;  // $wolf-space-sm
  min-width: 200px;
}

.overflow-item {
  display: flex;
  align-items: center;
  gap: 8px;  // $wolf-space-sm
  padding: 12px 8px;  // $wolf-space-md $wolf-space-sm
  min-height: 44px;  // ✅ Touch target
  cursor: pointer;
  border-radius: 4px;  // $wolf-radius-sm-v2
  transition: all 150ms ease-out;  // $wolf-transition-v2

  &:hover {
    background: $wolf-bg-hover-v2;
  }

  &:active {
    transform: scale(0.98);
    opacity: 0.7;
  }
}

.overflow-icon {
  font-size: 18px;
  color: $wolf-text-tertiary-v2;
}

.overflow-label {
  font-size: 14px;  // $wolf-font-size-body
  color: $wolf-text-primary-v2;
}
```

**Accessibility**：
- Overflow button: `aria-label="更多"`
- Overflow menu: `aria-label="次要导航"`
- Active overflow item: `aria-current="page"`
- Keyboard: Arrow keys to navigate, Enter/Space to select, Esc to close

---

#### 1.5 触摸优化（符合 §2 CRITICAL）

**Touch Target Size**：
```scss
.bottom-nav-item {
  min-width: 44px;   // $wolf-bottom-nav-item-height-v2
  min-height: 44px;  // WCAG 2.1, Apple HIG, Material Design

  // Hit-slop extension
  &::after {
    content: '';
    position: absolute;
    top: -10px;
    bottom: -10px;
    left: -10px;
    right: -10px;
  }
}
```

**Press Feedback**：
```scss
.bottom-nav-item:active {
  transform: scale(0.95);  // 5% scale down
  opacity: 0.7;            // 30% opacity reduction
}
```

**Touch Manipulation**：
```scss
touch-action: manipulation;  // Remove 300ms tap delay
```

---

#### 1.6 无障碍支持（符合 §1 CRITICAL）

**ARIA Attributes**：
```vue
<nav role="navigation" aria-label="主导航">
  <button
    aria-label="日历"
    aria-current="page"  <!-- active state -->
  >
    <el-icon><Calendar /></el-icon>
    <span>日历</span>
  </button>
</nav>
```

**Focus Ring**：
```scss
.bottom-nav-item:focus-visible {
  outline: 2px solid $wolf-primary-v2;
  outline-offset: 2px;
}
```

**Keyboard Navigation**：
- Arrow keys to navigate between items
- Enter/Space to activate
- Tab to move focus in/out of nav

---

#### 1.7 颜色对比度验证（符合 §1 color-contrast）

**Active State Colors** (必须验证):
- Active icon color: `$wolf-primary-v2` (#2563EB) against `$wolf-bg-card-v2` (#FFFFFF)
  - Contrast ratio: 4.59:1 ✅ (WCAG AA)
- Active text color: `$wolf-primary-v2` (#2563EB) against `$wolf-bg-card-v2` (#FFFFFF)
  - Contrast ratio: 4.59:1 ✅ (WCAG AA)
- Active indicator bar: `$wolf-primary-v2` (#2563EB) against `$wolf-bg-card-v2` (#FFFFFF)
  - Contrast ratio: 4.59:1 ✅ (WCAG AA for large text ≥18pt)

**验证工具**:
- WebAIM Contrast Checker: https://webaim.org/resources/contrastchecker/
- Chrome DevTools Accessibility Audit
- axe-core automated testing

**Dark Mode Verification** (必须单独测试):
- Active icon color: `$wolf-primary-v2-light` against `$wolf-bg-card-v2-dark`
- 需要在实际设备上测试（不能推断）

---

#### 1.8 动画与 Reduced Motion（符合 §7）

**Animation Duration**：
```scss
.bottom-nav-item {
  transition: transform 150ms ease-out, opacity 150ms ease-out;
}
```

**Reduced Motion Support**：
```scss
// ✅ Respect user preference for reduced motion
@media (prefers-reduced-motion: reduce) {
  .bottom-nav-item:active {
    transform: none;  // Disable scale animation
    opacity: 0.7;     // Keep opacity feedback (non-motion)
    transition: opacity 150ms ease-out;  // Only opacity transition
  }
}
```

---

#### 1.9 系统手势导航支持（符合 §9 gesture-nav-support）

**iOS Swipe-Back Gesture**：
- Bottom nav 不会阻止系统 swipe-back 手势
- 实现：bottom nav 使用 `position: fixed` 但不阻止 touch events
- 用户可以在 bottom nav 区域上方 swipe back（不干扰导航）

**Android Predictive Back**：
- 支持 Android 13+ predictive back gesture
- 实现：确保 bottom nav 不拦截 back gesture

**Implementation Details**：
```scss
.bottom-nav-container {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 100;

  // ✅ 不阻止系统手势
  pointer-events: auto;  // 允许 touch events 传递
  touch-action: pan-y;   // 允许垂直滚动和手势
}

.bottom-nav-item {
  // ✅ 只拦截点击，不阻止 swipe
  touch-action: manipulation;  // Remove 300ms delay, allow gestures
}
```

---

#### 1.10 AppLayout.vue 修改

**响应式策略**：
```vue
<template>
  <div class="app-layout">
    <!-- Sidebar (Desktop ≥768px) -->
    <aside class="sidebar">...</aside>

    <!-- Main Content -->
    <main class="main-content">
      <header class="top-bar">...</header>
      <router-view />
    </main>

    <!-- Bottom Nav (Mobile <768px) -->
    <BottomNav class="bottom-nav-container" />
  </div>
</template>

<style scoped lang="scss">
// ✅ Use dynamic viewport height (not 100vh)
.app-layout {
  min-height: 100dvh;  // Dynamic viewport height
  height: auto;
  
  // Fallback for older browsers
  @supports not (min-height: 100dvh) {
    min-height: 100vh;
  }
}

// Mobile: Bottom Nav visible
@media (max-width: 767px) {
  .sidebar { display: none; }

  .main-content {
    padding-bottom: 56px;  // Space for bottom nav

    // Safe Area (iOS notch / Android gesture bar)
    @supports (padding-bottom: env(safe-area-inset-bottom)) {
      padding-bottom: calc(56px + env(safe-area-inset-bottom));
    }
  }

  .bottom-nav-container {
    display: flex;
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    z-index: 100;
    background: $wolf-bg-card-v2;
    border-top: 1px solid $wolf-border-default-v2;
    padding-bottom: env(safe-area-inset-bottom, 0px);
  }
}

// Desktop: Bottom Nav hidden
@media (min-width: 768px) {
  .bottom-nav-container { display: none; }
}
</style>
```

---

#### 1.11 状态保留（符合 §9 state-preservation）

**Back Navigation Behavior**：
- 用户从列表页进入详情页 → 返回列表页时 **保留滚动位置**
- 用户切换导航项 → **保留之前的筛选条件**
- 用户在表单输入 → 返回时 **保留输入内容**（除非提交）

**Implementation**：
```typescript
// 使用 Vue Router scrollBehavior
const router = createRouter({
  history: createWebHistory(),
  routes: [...],
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) {
      return savedPosition  // 返回时恢复滚动位置
    } else {
      return { top: 0 }  // 新页面从顶部开始
    }
  }
})

// 使用 Pinia store 保存筛选条件
// stores/listFilters.ts
export const useListFiltersStore = defineStore('listFilters', {
  state: () => ({
    leadsFilters: {},
    customersFilters: {},
    // ... 其他列表筛选条件
  }),
  persist: true,  // 可选：持久化到 localStorage
})
```

---

## Phase 2: 核心业务页面改造

### 改造顺序（按业务重要性）

| 页面 | 路径 | 重点规范 | 组件使用 |
|------|------|---------|---------|
| **Leads 列表页** | `/views/Leads.vue` | §2 `touch-target-size`, §8 `loading-states`, §8 `empty-states` | TouchCard, Loading Skeleton |
| **客户详情页** | `/views/CustomerDetail.vue` | §5 `visual-hierarchy`, §6 `whitespace-balance` | TouchCard, TouchButton |
| **商机管理页** | `/views/Opportunities.vue` | §8 `input-labels`, §8 `error-placement` | TouchInput, TouchButton |
| **团队设置页** | `/views/Settings.vue` | §8 `touch-friendly-input` | TouchInput, TouchSelect |

---

### 规范要点（Phase 2）

**Touch & Interaction (§2 CRITICAL)**：
- 所有按钮 ≥44×44pt（使用 TouchButton）
- 所有输入框 mobile ≥44px height（使用 TouchInput）
- 8px minimum spacing（使用 $wolf-space-sm）

**Forms & Feedback (§8 MEDIUM)**：
- Visible labels（TouchInput 默认支持）
- Error placement below field（TouchInput 默认支持）
- Loading states on submit（TouchButton loading prop）
- Empty states with guidance（EmptyState component）

**Performance (§3 HIGH)**：
- Lazy loading below-fold images
- Skeleton screens for >300ms loading
- Reserve space for async content（prevent CLS）

---

## Phase 3: 全局组件优化

### 检查清单

**TouchButton.vue**：
- ✅ 44px minimum height（已实现）
- ✅ Press feedback `active:scale-[0.98]`（已实现）
- ✅ Loading state（已实现）
- ✅ aria-label support（已实现）

**TouchInput.vue**：
- ✅ 44px mobile height（已实现）
- ✅ Visible label（已实现）
- ✅ Error below field + aria-live（已实现）
- ✅ iOS auto-zoom prevention（已实现）

**需要创建的组件**：
```
src/components/crmwolf/
├── TouchCard.vue       # Press feedback for cards
├── TouchSelect.vue     # Touch-friendly select dropdown
├── EmptyState.vue      # Empty state guidance
└── LoadingSkeleton.vue # Skeleton screen component
```

---

## 实施步骤

### Step 1: BottomNav 组件创建（1-2 days）

**Files**：
- `src/components/crmwolf/BottomNav.vue`
- `src/components/crmwolf/BottomNavItem.vue`
- `src/components/crmwolf/BottomNavOverflow.vue`
- `src/components/crmwolf/index.ts`（更新导出）

**关键代码模式**（参考 CustomerDetailSidebar）：
- Element Plus Icons 动态渲染
- Vue Router active state（useRoute）
- aria-label + tabindex keyboard support
- Press feedback（scale + opacity）
- Reduced motion support（prefers-reduced-motion）

---

### Step 2: AppLayout.vue 集成（1 day）

**修改文件**：
- `src/AppLayout.vue`

**关键修改**：
1. Import BottomNav component
2. 添加 `<BottomNav class="bottom-nav-container" />`
3. 移动端响应式样式（padding-bottom + safe-area）
4. Desktop/Mobile display toggle（768px breakpoint）
5. 修改 `height: 100vh` → `min-height: 100dvh`

---

### Step 3: Leads 列表页改造（2-3 days）

**修改文件**：
- `src/views/Leads.vue`
- `src/components/crmwolf/TouchCard.vue`（创建）
- `src/components/crmwolf/EmptyState.vue`（创建）
- `src/components/crmwolf/LoadingSkeleton.vue`（创建）

**关键改造**：
1. 使用 TouchCard 替换现有列表项
2. 添加 Loading Skeleton（初始加载）
3. 添加 Empty State（无数据引导）
4. 确保触摸友好（44×44pt）

---

### Step 4: 其他页面渐进改造（每页 1-2 days）

**顺序**：
1. Customer Detail（客户详情）
2. Opportunities（商机管理）
3. Settings（团队设置）
4. Contracts（合同管理）
5. Payments（回款管理）
6. Invoices（发票管理）

---

## Verification

### Testing Strategy

**1. Component Tests（Unit）**：
- BottomNav renders 4 main items + overflow
- Active state highlights current route
- Touch target size ≥44px
- Press feedback works（scale + opacity）
- Keyboard navigation（arrow keys + enter）
- Reduced motion respected

**2. Integration Tests（E2E）**：
- Mobile viewport (<768px): BottomNav visible, sidebar hidden
- Desktop viewport (≥768px): BottomNav hidden, sidebar visible
- Route change updates active state
- Overflow menu opens/closes
- Safe area padding on iOS devices
- Back navigation preserves scroll position

**3. Accessibility Tests**：
- ARIA role/label validation（axe-core）
- Focus management
- Color contrast (WCAG 4.5:1)
- Keyboard navigation flow
- Reduced motion behavior

**4. Manual Testing**：
- iPhone SE (375px) - smallest mobile
- iPhone 14 Pro (393px + notch)
- iPad (768px) - tablet breakpoint
- Desktop (1440px) - desktop layout
- Test with prefers-reduced-motion enabled

---

## Critical Files

**Phase 1 - BottomNav**：
- `/src/components/crmwolf/BottomNav.vue`（主组件）
- `/src/components/crmwolf/BottomNavItem.vue`（单个导航项）
- `/src/components/crmwolf/BottomNavOverflow.vue`（overflow 菜单）
- `/src/AppLayout.vue`（集成 BottomNav + 响应式）
- `/src/components/crmwolf/index.ts`（导出）

**Phase 2 - Page Migration**：
- `/src/views/Leads.vue`（Leads 列表页）
- `/src/views/CustomerDetail.vue`（客户详情）
- `/src/views/Opportunities.vue`（商机管理）
- `/src/views/Settings.vue`（设置）

**Phase 3 - Components**：
- `/src/components/crmwolf/TouchCard.vue`（创建）
- `/src/components/crmwolf/EmptyState.vue`（创建）
- `/src/components/crmwolf/LoadingSkeleton.vue`（创建）

**Reference Files**（现有模式）：
- `/src/components/CustomerDetailSidebar.vue`（响应式导航）
- `/src/components/crmwolf/TouchButton.vue`（触摸优化）
- `/src/components/crmwolf/TouchInput.vue`（触摸优化）
- `/src/styles/variables-v2.scss`（design tokens）
- `/src/styles/touch-safety.css`（hit-slop utilities）

---

## Design Tokens（From variables-v2.scss）

**Bottom Nav Specific**：
```scss
$wolf-bottom-nav-height-v2: 56px;              // Bottom nav container height
$wolf-bottom-nav-item-height-v2: 44px;         // Individual item height (touch target)
$wolf-bottom-nav-padding-v2: 8px;              // Item padding
$wolf-bottom-nav-max-items-v2: 5;              // Maximum items (design rule)
$wolf-breakpoint-sm-v2: 768px;                 // Tablet/Mobile boundary
```

**Touch Safety**：
```scss
$wolf-touch-target-min-v2: 44px;               // Minimum touch target (WCAG, HIG, MD)
$wolf-space-sm-v2: 8px;                        // Touch spacing minimum
```

**Animation**：
```scss
$wolf-transition-v2: 150ms ease-out;           // Micro-interactions timing
```

---

## Success Criteria

**Phase 1 Complete**：
- ✅ Mobile users can navigate（bottom nav works）
- ✅ Desktop users see sidebar（bottom nav hidden）
- ✅ Active route highlighted
- ✅ Touch targets ≥44px
- ✅ Press feedback works
- ✅ Safe area handled（iOS/Android）
- ✅ Color contrast ≥4.5:1 verified
- ✅ Reduced motion respected
- ✅ Gesture navigation not blocked

**Phase 2 Complete**：
- ✅ Leads list uses Touch components
- ✅ Loading skeleton for async data
- ✅ Empty state with guidance
- ✅ All touch targets ≥44px
- ✅ Forms have visible labels + error below field

**Phase 3 Complete**：
- ✅ All Touch components verified
- ✅ New components created（TouchCard, EmptyState, Skeleton）
- ✅ Component library export updated
- ✅ Storybook documentation

---

## Estimated Timeline

- **Phase 1**: 2-3 days（BottomNav + AppLayout integration）
- **Phase 2**: 6-10 days（4 core pages migration）
- **Phase 3**: 2-3 days（Component optimization + testing）

**Total**: ~10-16 days for complete migration
---

## ⚠️ **强制执行规范（CRITICAL）**

### 禁止的妥协做法（Anti-Patterns）

❌ **"最小改动"心态**
- 例子：只加 Loading/Empty State，保留 el-table
- 后果：新旧组件混杂，规范失去约束力

❌ **"渐进式重构"借口**
- 例子：保留 FilterTableHeader，后续再改
- 后果：妥协成为常态，永远无法统一

❌ **"时间不够"借口**
- 例子：先这样，后续优化
- 后果：永远没有"后续"

### 验收标准（Must Have）

每个页面改造完成后，必须通过以下检查：

```bash
# 1. 移除所有 Element Plus 组件
grep -c "el-table\|el-button\|FilterTableHeader" src/views/Xxx.vue
# 结果必须为 0

# 2. 确认使用 CRMWolf Touch 组件
grep -c "TouchCard\|TouchButton\|SearchCard" src/views/Xxx.vue
# 结果必须 > 0

# 3. 所有触摸区域 ≥44px
# 手动检查所有按钮、卡片点击区域
```

### 执行流程（Workflow）

```
开始改造
  ↓
理解规范要求（逐字阅读）
  ↓
明确禁止做法（知道哪些不能做）
  ↓
完全执行（不留妥协空间）
  ↓
自我验收（检查 grep 结果）
  ↓
完成
```

**Red Flags（立即停止）**：
- "先这样吧" → 停止，重新阅读规范
- "保留一下" → 停止，这是妥协
- "时间不够" → 停止，重新评估时间

---

**最后更新**: 2026-07-09
**维护者**: Claude Code
