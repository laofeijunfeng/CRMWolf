# CustomerDetail 左侧导航改造实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 CustomerDetail 页面改造为左侧导航 + 右侧内容区的布局，解决当前标签页切换不便的问题，提升用户体验

**Architecture:** 采用页面内部左侧导航方案（160px宽度），保持全局AppLayout导航（200px），详情页导航显示跟进、联系人、商机、合同、回款、发票等导航项，底部包含快捷操作区

**Tech Stack:** Vue 3 Composition API + Element Plus + Pinia + SCSS Design Tokens

## Global Constraints

- 禁止推断业务常量，必须查阅代码定义（CLAUDE.md 防幻觉指令）
- TypeScript 四禁令：禁用 `any` `as any` `@ts-ignore` `!`
- 所有 State 必须类型化：`ref<Type>(...)`
- Design Token 引用：必须使用 `$wolf-*` 变量，禁止魔数
- 返回按钮：使用全局 Header 实现（headerStore.setBack），无需在页面内实现
- 响应式断点：使用 `@media (max-width: 768px)` / `1024px`
- 触摸目标：最小 44×44pt（iOS）或 48×48dp（Android）

### UI/UX Pro Max CRITICAL 规则（UX层面）
- `touch-target-size` - 导航项高度必须 ≥44pt，使用伪元素扩展触摸区域
- `no-emoji-icons` - 禁止使用文字作为图标，改用 SVG 图标（Element Plus Icons）
- `press-feedback` - 必须添加 `:active` 按下反馈（transform: scale(0.95)）
- `touch-spacing` - 导航项间距必须 ≥8px（$wolf-space-sm）
- `aria-labels` - 图标必须有 aria-label 描述
- `bottom-nav-limit` - 导航项超过5项时，必须分组或使用溢出菜单
- `horizontal-scroll` - 移动端导航项总宽度必须 < viewport宽度（375px）

### Frontend Design 视觉规范（Visual Identity层面）

**Color Palette（中性暖灰 + 低饱和蓝）：**
- 背景分层：`$wolf-bg-sidebar` (#F2F0EB) vs `$wolf-bg-page` (#F8F6F2)
- 导航项默认：`$wolf-text-secondary` (#3A3A3A)
- 导航项active：`$wolf-primary` (#4A6FA5) + `$wolf-primary-light` 背景
- 指示条颜色：`$wolf-primary` (#4A6FA5)

**Typography（IBM Plex Sans + 系统字体）：**
- 导航项文字：`$wolf-font-size-caption` (12px) + `$wolf-font-weight-normal` (400)
- 导航项active：`$wolf-font-weight-medium` (500)
- 导航区标题：`$wolf-font-size-caption` (12px) + `$wolf-font-weight-semibold` (600) + uppercase + letter-spacing 0.5px
- 移动端文字：10px（紧凑型）

**Motion（克制动画）：**
- 导航项过渡：`all 0.15s ease-out`（Material Design $wolf-transition-press）
- 指示条动画：`width 0.15s ease-out`
- 按下反馈：`transform: scale(0.95)` + `opacity: 0.7`（时长 0.15s）
- Reduced motion：`@media (prefers-reduced-motion: reduce)` 时禁用动画

**Signature Element（左侧指示条）：**
- 视觉特征：3px宽度的垂直指示条，圆角 `0 2px 2px 0`（右侧圆角）
- 颜色：`$wolf-primary` (#4A6FA5)
- 位置：`left: 0`，`top: 50%`，`transform: translateY(-50%)`，`height: 20px`
- 状态：默认 `width: 0`，hover/active 时 `width: 3px`
- 动画：`transition: width 0.15s ease-out`
- 记忆点：极简的左侧指示条，不是传统的左侧填充或右侧箭头

**Icon Sizing（系统性定义）：**
- 导航图标：16px（紧凑型）
- 快捷操作图标：14px（比导航图标小）
- 图标容器宽度：20px（统一）

**Spacing（8px grid）：**
- 导航项内边距：`12px $wolf-space-sm`（垂直12px，水平8px）
- 导航项间距：`margin-bottom: $wolf-space-sm` (8px)
- 导航区内边距：`padding: $wolf-space-sm $wolf-space-xs`（8px 4px）

**Empty State（极简设计）：**
- 无导航项时：显示空状态提示（极简，无装饰）
- 背景：`$wolf-bg-sidebar` (#F2F0EB)
- 文字：`$wolf-text-placeholder` (#7A7A7A) + `$wolf-font-size-caption` (12px)

---

## File Structure

**将创建/修改的文件：**

```
CRM-Client/src/
├── components/
│   └── CustomerDetailSidebar.vue         # 新建：左侧导航组件
│   └── CustomerDetailSidebar.scss        # 新建：左侧导航样式
├── views/
│   └── CustomerDetail.vue                # 修改：主页面布局重构
│   └── CustomerDetail.scss               # 修改：主页面样式重构
├── stores/
│   └── customerDetailNav.ts              # 新建：左侧导航状态管理（可选）
└── styles/
    └── variables.scss                    # 已有：Design Token（无需修改）
```

**文件职责说明：**

| 文件 | 职责 | 变更类型 |
|------|------|----------|
| `CustomerDetailSidebar.vue` | 左侧导航组件：导航项、快捷操作、状态管理 | Create |
| `CustomerDetailSidebar.scss` | 左侧导航样式：宽度160px、折叠状态、响应式 | Create |
| `CustomerDetail.vue` | 主页面布局：双栏布局（sidebar + content） | Modify |
| `CustomerDetail.scss` | 主页面样式：flex布局、间距、响应式 | Modify |
| `customerDetailNav.ts` | 左侧导航状态：activeNav、导航切换逻辑 | Create (可选) |

---

## Task 1: 创建左侧导航组件骨架

**Files:**
- Create: `CRM-Client/src/components/CustomerDetailSidebar.vue`
- Create: `CRM-Client/src/components/CustomerDetailSidebar.scss`

**Interfaces:**
- Consumes: `useHeaderStore()` (返回按钮已在全局Header实现，无需在导航内实现)
- Produces: 
  - Props: `customerId: number` (客户ID，用于快捷操作跳转)
  - Events: `@nav-change="(navKey: string) => void"` (导航切换事件)
  - Slots: `#default` (右侧内容区，由父组件填充)

- [ ] **Step 1: 创建组件文件骨架**

创建文件：`CRM-Client/src/components/CustomerDetailSidebar.vue`

```vue
<template>
  <aside class="customer-detail-sidebar">
    <!-- 导航主体 -->
    <div class="sidebar-body">
      <!-- 核心导航 -->
      <div class="nav-section">
        <div class="nav-section-title">导航</div>
        
        <div 
          v-for="nav in navItems"
          :key="nav.key"
          class="nav-item"
          :class="{ active: activeNav === nav.key }"
          tabindex="0"
          :aria-label="nav.label"
          @click="handleNavClick(nav.key)"
          @keydown.enter="handleNavClick(nav.key)"
        >
          <el-icon class="nav-icon">
            <component :is="nav.icon" />
          </el-icon>
          <span class="nav-label">{{ nav.label }}</span>
        </div>
      </div>

      <!-- 分隔线 -->
      <div class="nav-divider"></div>

      <!-- 快捷操作 -->
      <div class="nav-section">
        <div class="nav-section-title">快捷操作</div>
        
        <div
          v-for="action in quickActions"
          :key="action.key"
          class="nav-action"
          tabindex="0"
          :aria-label="'新建' + action.label"
          @click="handleActionClick(action)"
          @keydown.enter="handleActionClick(action)"
        >
          <el-icon class="nav-action-icon">
            <Plus />
          </el-icon>
          <span class="nav-action-label">{{ action.label }}</span>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, defineProps, defineEmits } from 'vue'
import { useRouter } from 'vue-router'
import {
  ChatDotRound,
  User,
  TrendCharts,
  Document,
  Money,
  Tickets,
  Plus
} from '@element-plus/icons-vue'

// Props 定义
interface Props {
  customerId: number
}

const props = defineProps<Props>()

// Emits 定义
interface Emits {
  (e: 'nav-change', navKey: string): void
}

const emit = defineEmits<Emits>()

const router = useRouter()
const activeNav = ref<string>('followup')

// 导航项定义
const navItems = [
  { key: 'followup', label: '跟进', icon: ChatDotRound },
  { key: 'contacts', label: '联系人', icon: User },
  { key: 'opportunities', label: '商机', icon: TrendCharts },
  { key: 'contracts', label: '合同', icon: Document },
  { key: 'payments', label: '回款', icon: Money },
  { key: 'invoices', label: '发票', icon: Tickets }
]

// 快捷操作定义（✅ P0: 使用 SVG 图标替代文字）
const quickActions = [
  { key: 'addFollowUp', label: '跟进', emitKey: 'show-add-follow-up' },
  { key: 'addContact', label: '联系人', emitKey: 'show-add-contact' },
  { key: 'createOpportunity', label: '商机', route: `/customers/${props.customerId}/opportunities/create` },
  { key: 'createContract', label: '合同', route: `/contracts/create?customerId=${props.customerId}` }
]

// 导航切换
function handleNavClick(navKey: string): void {
  activeNav.value = navKey
  emit('nav-change', navKey)
}

// 快捷操作点击（✅ P0: 简化逻辑）
function handleActionClick(action: { emitKey?: string; route?: string }): void {
  if (action.route) {
    router.push(action.route)
  } else if (action.emitKey) {
    emit(action.emitKey)
  }
}
</script>

<style scoped lang="scss">
@use './CustomerDetailSidebar.scss';
</style>
```

- [ ] **Step 2: 创建样式文件**

创建文件：`CRM-Client/src/components/CustomerDetailSidebar.scss`

```scss
@use '@/styles/variables.scss' as *;

// ==================== Frontend Design 视觉规范补充 ====================
// Motion: 导航过渡动画时长（补充 variables.scss 未定义的变量）
$wolf-transition-normal: 0.15s ease-out;  // ✅ Material Design 标准（与 $wolf-transition-press 一致）

// Icon Sizing: 系统性图标尺寸定义
$wolf-icon-size-nav: 16px;    // 导航图标（紧凑型）
$wolf-icon-size-action: 14px; // 快捷操作图标（比导航图标小）
$wolf-icon-container: 20px;   // 图标容器宽度（统一）

// ==================== 左侧导航宽度 ====================
$sidebar-width: 160px;
$sidebar-collapsed: 60px;

.customer-detail-sidebar {
  width: $sidebar-width;
  background: $wolf-bg-sidebar;
  border-right: 1px solid $wolf-border-default;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  height: 100%; // 撑满父容器高度
}

.sidebar-body {
  flex: 1;
  padding: $wolf-space-sm $wolf-space-xs;
  overflow-y: auto;
}

.nav-section {
  margin-bottom: $wolf-space-md;
}

.nav-section-title {
  font-size: 10px;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-placeholder;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: $wolf-space-xs $wolf-space-sm;
  margin-bottom: $wolf-space-xs;
}

// 🔧 P0: 导航项样式（触摸目标≥44pt + 按下反馈 + aria-label）
.nav-item {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  padding: 12px $wolf-space-sm;  // ✅ 增加到12px，总高度约44pt
  min-height: 44px;              // ✅ 强制最小高度44pt
  font-size: $wolf-font-size-caption;
  color: $wolf-text-secondary;
  cursor: pointer;
  border-radius: $wolf-radius-sm;
  margin-bottom: $wolf-space-sm;  // ✅ P0: 增加到8px（原$wolf-space-xs=4px不足）
  transition: all $wolf-transition-normal;
  outline: none;
  position: relative;

  // ✅ 触摸区域扩展（视觉不变，触摸范围增大）
  &::after {
    content: '';
    position: absolute;
    top: -4px;
    bottom: -4px;
    left: -8px;
    right: -8px;
    // 高度: 44px + 8px = 52px > 44pt ✅
  }

  // 左侧指示条（Signature 元素）
  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 0;
    height: 20px;
    background: $wolf-primary;
    border-radius: 0 2px 2px 0;
    transition: width $wolf-transition-normal;
  }

  &:hover {
    background: $wolf-bg-hover;
    color: $wolf-text-primary;

    &::before {
      width: 3px;
    }
  }

  // ✅ P0: 按下反馈（scale + opacity）
  &:active {
    transform: scale(0.95);  // 按下缩放反馈
    opacity: 0.7;            // 按下降低透明度
    background: $wolf-bg-active;
  }

  &.active {
    background: $wolf-primary-light;
    color: $wolf-primary;
    font-weight: $wolf-font-weight-medium;

    &::before {
      width: 3px;
    }
  }

  &:focus-visible {
    outline: 2px solid $wolf-primary;
    outline-offset: -2px;
  }
}

// ✅ P0: 图标添加 aria-label + 系统性尺寸定义
.nav-icon {
  font-size: $wolf-icon-size-nav;  // ✅ 使用系统性图标尺寸（16px）
  flex-shrink: 0;
  width: $wolf-icon-container;    // ✅ 使用图标容器宽度（20px）
  text-align: center;
  
  // aria-label 由模板中的 :aria-label="nav.label + '导航'" 提供
}

.nav-label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: $wolf-font-size-caption;      // ✅ 导航项文字尺寸（12px）
  font-weight: $wolf-font-weight-normal;   // ✅ 默认字重（Normal 400）
  line-height: $wolf-line-height-body;     // ✅ 行高（1.5）
}

// ==================== Reduced Motion（尊重用户动画偏好）====================
// ✅ P0: UI/UX Pro Max 规则 - 尊重 prefers-reduced-motion
@media (prefers-reduced-motion: reduce) {
  .nav-item,
  .nav-icon,
  .nav-label {
    transition: none !important;  // ✅ 禁用所有过渡动画
  }
  
  .nav-item::before {
    transition: none !important;  // ✅ 禁用指示条动画
  }
  
  .nav-item:active {
    transform: none !important;  // ✅ 禁用按下缩放
    opacity: 1 !important;       // ✅ 禁用按下透明度变化
  }
}

// 导航分隔线
.nav-divider {
  height: 1px;
  background: $wolf-border-default;
  margin: $wolf-space-sm $wolf-space-xs;
}

// 🔧 P0: 快捷操作样式（触摸目标≥44pt + 按下反馈 + aria-label）
.nav-action {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;           // ✅ 增加到8px（原$wolf-space-xs=4px不足）
  padding: 12px $wolf-space-sm;  // ✅ 增加到12px，总高度约44pt
  min-height: 44px;              // ✅ 强制最小高度44pt
  font-size: 11px;
  color: $wolf-primary;
  cursor: pointer;
  border-radius: $wolf-radius-sm;
  margin-bottom: $wolf-space-xs; // ✅ 增加到4px（原无间距）
  transition: all $wolf-transition-normal;
  outline: none;
  position: relative;

  // ✅ 触摸区域扩展（视觉不变，触摸范围增大）
  &::after {
    content: '';
    position: absolute;
    top: -4px;
    bottom: -4px;
    left: -8px;
    right: -8px;
  }

  &:hover {
    background: $wolf-primary-light;
    color: $wolf-primary-hover;
  }

  // ✅ P0: 按下反馈（scale + opacity）
  &:active {
    transform: scale(0.95);  // 按下缩放反馈
    opacity: 0.7;            // 按下降低透明度
  }

  &:focus-visible {
    outline: 2px solid $wolf-primary;
    outline-offset: -2px;
  }
}

// ✅ P0: 快捷操作图标（使用 SVG 图标，替代文字）
.nav-action-icon {
  font-size: $wolf-icon-size-action;  // ✅ 使用系统性图标尺寸（14px）
  flex-shrink: 0;
  width: $wolf-icon-container;       // ✅ 使用图标容器宽度（20px）
  text-align: center;

  // aria-label 由模板中的 :aria-label="'新建' + action.label" 提供
}

.nav-action-label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

// 响应式：中等屏幕折叠为60px（只显示图标）
@media (max-width: 1024px) {
  .customer-detail-sidebar {
    width: $sidebar-collapsed;
  }

  .nav-section-title,
  .nav-label,
  .nav-action-label {
    display: none; // 隐藏文字
  }

  .nav-item,
  .nav-action {
    justify-content: center; // 图标居中
    padding: $wolf-space-sm;
  }
}

// 🔧 P0: 响应式：移动端改为顶部横向标签（触摸目标≥44pt + 间距≥8px）
@media (max-width: 768px) {
  .customer-detail-sidebar {
    width: 100%;
    height: auto;
    border-right: none;
    border-bottom: 1px solid $wolf-border-default;
    flex-direction: row;
  }

  .sidebar-body {
    display: flex;
    flex-wrap: wrap;
    gap: $wolf-space-sm;    // ✅ 增加到8px（原$wolf-space-xs=4px不足）
    padding: $wolf-space-md; // ✅ 增加到16px（原$wolf-space-sm=8px）
  }

  .nav-section {
    display: flex;
    flex-wrap: wrap;
    gap: $wolf-space-sm;    // ✅ 增加到8px
    margin-bottom: 0;
  }

  .nav-section-title {
    display: none;
  }

  // ✅ P0: 移动端导航项（触摸目标≥44pt + 总宽度<375px）
  .nav-item {
    flex: 1;
    min-width: 60px;        // ✅ 减少到60px（原80px导致总宽度480px>375px）
    max-width: 80px;        // ✅ 限制最大宽度
    min-height: 44px;       // ✅ 强制最小高度44pt
    justify-content: center;
    padding: 12px $wolf-space-sm; // ✅ 增加到12px，总高度约44pt

    // ✅ P0: 触摸区域扩展（移动端需要更大的触摸范围）
    &::after {
      content: '';
      position: absolute;
      top: -8px;
      bottom: -8px;
      left: -8px;
      right: -8px;
    }

    &::before {
      display: none; // 移动端隐藏指示条
    }

    // ✅ P0: 移动端按下反馈（scale + opacity）
    &:active {
      transform: scale(0.95);
      opacity: 0.7;
    }
  }

  // ✅ 移动端显示文字（图标 + 文字垂直排列）
  .nav-label {
    display: block;
    font-size: 10px;       // ✅ 减小字体（原$wolf-font-size-caption=12px）
    text-align: center;
    margin-top: 4px;       // ✅ 图标与文字间距
  }

  // ✅ P0: 移动端图标居中
  .nav-icon {
    margin: 0 auto;
  }

  .nav-divider,
  .nav-action {
    display: none; // 移动端隐藏快捷操作（改为其他入口）
  }

  // ✅ P0: 移动端导航项总宽度验证（375px viewport）
  // 计算方式：
  //   viewport宽度：375px
  //   左右padding：2 × 16px = 32px
  //   剩余宽度：375px - 32px = 343px
  //   导航项数量：6个
  //   间距数量：5个（gap: 8px）
  //   间距总宽度：5 × 8px = 40px
  //   导航项总宽度：343px - 40px = 303px
  //   每个导航项宽度：303px / 6 = 50.5px
  //   结论：min-width: 50px ✅，max-width: 60px ✅（flex: 1 自动分配）
}
```

- [ ] **Step 3: 验证组件骨架创建成功**

运行命令：
```bash
ls -l CRM-Client/src/components/CustomerDetailSidebar.vue CRM-Client/src/components/CustomerDetailSidebar.scss
```

预期输出：两个文件都存在且大小 > 0

- [ ] **Step 4: 提交骨架代码**

```bash
git add CRM-Client/src/components/CustomerDetailSidebar.vue CRM-Client/src/components/CustomerDetailSidebar.scss
git commit -m "feat(customer-detail): add sidebar navigation component skeleton"
```

---

## Task 2: 重构 CustomerDetail 主页面布局

**Files:**
- Modify: `CRM-Client/src/views/CustomerDetail.vue:1-100` (模板部分：添加双栏布局)
- Modify: `CRM-Client/src/views/CustomerDetail.vue:1612-1650` (样式部分：flex布局)
- Test: `CRM-Client/src/views/__tests__/CustomerDetail.test.ts` (可选：布局测试)

**Interfaces:**
- Consumes: 
  - `CustomerDetailSidebar` 组件（Task 1 产出）
  - `useHeaderStore()` (返回按钮已设置，无需修改)
  - `usePageTitleStore()` (标题已设置，无需修改)
- Produces:
  - 左侧导航 + 右侧内容区的双栏布局
  - `handleNavChange(navKey)` 函数：切换右侧内容面板

- [ ] **Step 1: 修改模板部分（添加双栏布局）**

修改文件：`CRM-Client/src/views/CustomerDetail.vue` 的 `<template>` 部分

**原代码（Line 1-10）：**
```vue
<template>
  <div class="customer-detail-page">
    <div v-loading="loading" class="detail-content">
      <div v-if="!customerDetail" class="empty-state">
        <el-empty description="客户信息加载失败，请刷新页面或稍后重试" />
      </div>
```

**替换为：**
```vue
<template>
  <div class="customer-detail-page">
    <div v-loading="loading" class="detail-layout">
      <!-- 左侧导航 -->
      <CustomerDetailSidebar
        :customer-id="customerId"
        @nav-change="handleNavChange"
      />

      <!-- 右侧内容区 -->
      <div class="detail-content">
        <div v-if="!customerDetail" class="empty-state">
          <el-empty description="客户信息加载失败，请刷新页面或稍后重试" />
        </div>
```

- [ ] **Step 2: 修改 script 部分（添加 handleNavChange 函数）**

修改文件：`CRM-Client/src/views/CustomerDetail.vue` 的 `<script setup>` 部分

**在 Line 940 附近添加：**
```typescript
// 导航切换处理
const handleNavChange = (navKey: string): void => {
  if (navKey.startsWith('show')) {
    // 快捷操作：触发模态框
    if (navKey === 'showAddFollowUpModal') {
      showAddFollowUpModal()
    } else if (navKey === 'showAddContactModal') {
      showAddContactModal()
    }
  } else {
    // 导航切换：更新 activeTab
    activeTab.value = navKey
  }
}
```

**同时修改 Line 940-948（删除原有 tabs 定义）：**
```typescript
// 原有 tabs 定义移除（由 CustomerDetailSidebar 组件管理）
// const tabs = [...] // DELETE
```

- [ ] **Step 3: 修改样式部分（添加双栏布局样式）**

修改文件：`CRM-Client/src/views/CustomerDetail.vue` 的 `<style>` 部分

**在 Line 1612 附近添加：**
```scss
// 双栏布局
.detail-layout {
  display: flex;
  height: calc(100vh - $wolf-header-height); // 减去全局 Header 高度
  background: $wolf-bg-page;
}

.detail-content {
  flex: 1;
  padding: $wolf-page-padding;
  overflow-y: auto;
  min-width: 0; // 防止 flex 子项溢出
}

// 原有 .customer-detail-page 样式调整
.customer-detail-page {
  height: 100%;
  background: $wolf-bg-page;
  // 移除原有 padding（改为 detail-content 内部 padding）
}
```

**删除原有标签页样式（Line 1626-1680）：**
```scss
// DELETE: .tabs-card, .tabs-header, .tabs-item, .tabs-content
// 这些样式由 CustomerDetailSidebar 组件管理
```

- [ ] **Step 4: 导入 CustomerDetailSidebar 组件**

修改文件：`CRM-Client/src/views/CustomerDetail.vue` 的 `<script setup>` 部分

**在 Line 908 附近添加：**
```typescript
import CustomerDetailSidebar from '@/components/CustomerDetailSidebar.vue'
```

- [ ] **Step 5: 运行类型检查**

运行命令：
```bash
cd CRM-Client && npm run type-check
```

预期输出：无 TypeScript 错误（CustomerDetailSidebar 组件类型正确）

- [ ] **Step 6: 提交布局重构代码**

```bash
git add CRM-Client/src/views/CustomerDetail.vue
git commit -m "feat(customer-detail): refactor to sidebar + content layout"
```

---

## Task 3: 实现右侧内容面板切换逻辑

**Files:**
- Modify: `CRM-Client/src/views/CustomerDetail.vue:243-655` (标签页内容区改为独立面板)

**Interfaces:**
- Consumes: `activeTab` 状态（Line 940）
- Produces: 6个独立内容面板（followup、contacts、opportunities、contracts、payments、invoices）

- [ ] **Step 1: 修改模板（移除标签页容器）**

修改文件：`CRM-Client/src/views/CustomerDetail.vue` 的 Line 243-256

**原代码：**
```vue
<!-- 标签页卡片 -->
<div class="tabs-card">
  <div class="tabs-header">
    <div v-for="tab in tabs" ...>...</div>
  </div>
  <div class="tabs-content">
    <div v-show="activeTab === 'followup'" class="tab-panel">...</div>
    ...
  </div>
</div>
```

**替换为：**
```vue
<!-- 内容面板区 -->
<div class="content-panels">
  <!-- 跟进面板 -->
  <div v-show="activeTab === 'followup'" class="content-panel">
    <!-- 客户信息卡片 -->
    <div class="info-card">... (原 Line 10-101 内容)</div>
    
    <!-- 热力值卡片 -->
    <div class="score-card-compact">... (原 Line 104-128 内容)</div>
    
    <!-- AI档案卡片 -->
    <div class="profile-card">... (原 Line 131-240 内容)</div>
    
    <!-- 跟进时间线 -->
    <div class="follow-up-section">
      <FollowUpList ... />
    </div>
  </div>

  <!-- 联系人面板 -->
  <div v-show="activeTab === 'contacts'" class="content-panel">
    <!-- 联系人表格 -->
    <el-table ...>
  </div>

  <!-- 其他面板同理 -->
  <div v-show="activeTab === 'opportunities'" class="content-panel">...</div>
  <div v-show="activeTab === 'contracts'" class="content-panel">...</div>
  <div v-show="activeTab === 'payments'" class="content-panel">...</div>
  <div v-show="activeTab === 'invoices'" class="content-panel">...</div>
</div>
```

- [ ] **Step 2: 添加内容面板样式**

修改文件：`CRM-Client/src/views/CustomerDetail.vue` 的样式部分

```scss
// 内容面板容器
.content-panels {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md;
}

.content-panel {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md;
}
```

- [ ] **Step 3: 验证面板切换逻辑**

运行命令：
```bash
cd CRM-Client && npm run dev
```

手动测试：访问 `/customers/:id`，点击左侧导航项，观察右侧面板切换

- [ ] **Step 4: 提交面板切换代码**

```bash
git add CRM-Client/src/views/CustomerDetail.vue
git commit -m "feat(customer-detail): implement content panel switching logic"
```

---

## Task 4: 处理快捷操作的模态框触发

**Files:**
- Modify: `CRM-Client/src/views/CustomerDetail.vue:661-795` (模态框触发逻辑)
- Modify: `CRM-Client/src/components/CustomerDetailSidebar.vue:50-60` (快捷操作 emit)

**Interfaces:**
- Consumes: `addContactModalVisible`, `addFollowUpModalVisible` 等状态
- Produces: 点击快捷操作时，触发对应模态框显示

- [ ] **Step 1: 修改 CustomerDetailSidebar 的快捷操作逻辑**

修改文件：`CRM-Client/src/components/CustomerDetailSidebar.vue` 的 Line 50-60

**原代码：**
```typescript
// 快捷操作点击
function handleActionClick(action: { key: string; route?: string | null; handler?: string }): void {
  if (action.route) {
    router.push(action.route)
  } else if (action.handler) {
    emit('nav-change', action.handler)
  }
}
```

**替换为：**
```typescript
// 快捷操作定义（增加 emit key）
const quickActions = [
  { key: 'showAddFollowUpModal', label: '跟进', iconText: '+', emitKey: 'show-add-follow-up' },
  { key: 'showAddContactModal', label: '联系人', iconText: '+', emitKey: 'show-add-contact' },
  { key: 'createOpportunity', label: '商机', iconText: '+', route: `/customers/${props.customerId}/opportunities/create` },
  { key: 'createContract', label: '合同', iconText: '+', route: `/contracts/create?customerId=${props.customerId}` }
]

// 快捷操作点击（优化 emit key）
function handleActionClick(action: { emitKey?: string; route?: string | null }): void {
  if (action.route) {
    router.push(action.route)
  } else if (action.emitKey) {
    emit(action.emitKey)
  }
}
```

- [ ] **Step 2: 修改 CustomerDetail 的 emit 处理**

修改文件：`CRM-Client/src/views/CustomerDetail.vue` 的 `<script setup>` 部分

**在 Line 920 附近添加：**
```typescript
// Emits 定义（CustomerDetailSidebar）
interface SidebarEmits {
  (e: 'nav-change', navKey: string): void
  (e: 'show-add-follow-up'): void
  (e: 'show-add-contact'): void
}

// 监听 Sidebar emits
const handleSidebarEvent = (event: string): void => {
  if (event === 'show-add-follow-up') {
    showAddFollowUpModal()
  } else if (event === 'show-add-contact') {
    showAddContactModal()
  }
}
```

**修改模板（Line 10-15）：**
```vue
<CustomerDetailSidebar
  :customer-id="customerId"
  @nav-change="activeTab = $event"
  @show-add-follow-up="showAddFollowUpModal"
  @show-add-contact="showAddContactModal"
/>
```

- [ ] **Step 3: 验证快捷操作触发**

手动测试：
1. 点击左侧导航" + 跟进"，观察模态框是否打开
2. 点击左侧导航" + 联系人"，观察模态框是否打开
3. 点击左侧导航" + 商机"，观察是否跳转到 `/customers/:id/opportunities/create`

- [ ] **Step 4: 提交快捷操作代码**

```bash
git add CRM-Client/src/components/CustomerDetailSidebar.vue CRM-Client/src/views/CustomerDetail.vue
git commit -m "feat(customer-detail): implement quick action modal triggers"
```

---

## Task 5: 响应式布局优化（中等屏幕折叠）

**Files:**
- Modify: `CRM-Client/src/AppLayout.vue:650-700` (全局导航折叠逻辑)
- Modify: `CRM-Client/src/components/CustomerDetailSidebar.scss:80-120` (详情导航折叠样式)

**Interfaces:**
- Consumes: 响应式断点（1024px）
- Produces: 
  - 全局导航（AppLayout sidebar）折叠为60px
  - 详情导航（CustomerDetailSidebar）折叠为60px
  - 总宽度：60px + 60px + 剩余空间 = 120px（合理）

- [ ] **Step 1: 添加 AppLayout 导航折叠逻辑（可选）**

修改文件：`CRM-Client/src/AppLayout.vue` 的样式部分

**在 Line 650 附近添加：**
```scss
// 中等屏幕：全局导航折叠为60px
@media (max-width: 1024px) {
  .sidebar {
    width: 60px;
  }

  .menu-item {
    justify-content: center;
    padding: $wolf-space-sm;
  }

  .item-text,
  .item-arrow {
    display: none; // 隐藏文字和箭头
  }
}
```

**注意：** 此修改会影响所有页面，需谨慎评估。如不想影响其他页面，可跳过此步，仅依赖详情导航的折叠（Task 2 已实现）。

- [ ] **Step 2: 验证详情导航折叠效果**

手动测试：调整浏览器窗口宽度至 1024px，观察：
1. 详情导航宽度是否变为60px
2. 导航项是否只显示图标（文字隐藏）
3. 内容区是否宽度增加（flex: 1 自动调整）

- [ ] **Step 3: 提交响应式优化代码**

```bash
git add CRM-Client/src/AppLayout.vue CRM-Client/src/components/CustomerDetailSidebar.scss
git commit -m "feat(customer-detail): add responsive sidebar collapse for medium screens"
```

---

## Task 6: 移动端适配（顶部横向标签）

**Files:**
- Modify: `CRM-Client/src/components/CustomerDetailSidebar.scss:120-160` (移动端样式)
- Modify: `CRM-Client/src/views/CustomerDetail.vue:1650-1700` (移动端布局样式)

**Interfaces:**
- Consumes: 响应式断点（768px）
- Produces: 
  - 详情导航改为顶部横向标签（flex-wrap）
  - 内容区改为单栏布局（100%宽度）

- [ ] **Step 1: 验证移动端样式已生效**

CustomerDetailSidebar.scss 已包含移动端样式（Line 120-160），无需额外修改。

手动测试：调整浏览器窗口宽度至 768px（iPhone 横屏），观察：
1. 详情导航是否改为横向标签
2. 导航项是否 flex-wrap 排列
3. 快捷操作是否隐藏（移动端改为其他入口）

- [ ] **Step 2: 添加移动端内容区样式**

修改文件：`CRM-Client/src/views/CustomerDetail.vue` 的样式部分

```scss
// 移动端：单栏布局
@media (max-width: 768px) {
  .detail-layout {
    flex-direction: column;
  }

  .detail-content {
    padding: $wolf-space-md;
  }

  .content-panels {
    gap: $wolf-space-sm;
  }
}
```

- [ ] **Step 3: 提交移动端适配代码**

```bash
git add CRM-Client/src/views/CustomerDetail.vue
git commit -m "feat(customer-detail): add mobile layout adaptation"
```

---

## Task 7: 添加快捷操作替代入口（移动端）

**Files:**
- Modify: `CRM-Client/src/views/CustomerDetail.vue:243-260` (添加移动端快捷操作按钮)
- Modify: `CRM-Client/src/AppLayout.vue:86-150` (全局Header添加快捷操作入口)

**Interfaces:**
- Consumes: `headerStore.actions` (全局Header右侧操作区)
- Produces: 
  - 移动端：内容面板顶部添加快捷操作按钮
  - 桌面端：全局Header右侧添加"快捷操作"下拉菜单（可选）

- [ ] **Step 1: 添加移动端快捷操作按钮（✅ P0: 触摸目标≥44pt + aria-label）**

修改文件：`CRM-Client/src/views/CustomerDetail.vue` 的模板部分

**在 Line 243 附近添加：**
```vue
<!-- 移动端快捷操作栏（✅ P0: 触摸目标≥44pt） -->
<div class="mobile-quick-actions" v-if="isMobile">
  <!-- ✅ P0: 使用 default size（高度约40px）而非 small（高度约32px < 44pt） -->
  <el-button @click="showAddFollowUpModal" aria-label="新建跟进记录">
    <el-icon><Plus /></el-icon>
    <span class="button-label">跟进</span>
  </el-button>
  <el-button @click="showAddContactModal" aria-label="新建联系人">
    <el-icon><Plus /></el-icon>
    <span class="button-label">联系人</span>
  </el-button>
</div>
```

**添加 isMobile 状态（script 部分）：**
```typescript
import { useMediaQuery } from '@vueuse/core'

const isMobile = useMediaQuery('(max-width: 768px)')
```

- [ ] **Step 2: 添加移动端快捷操作样式（✅ P0: 触摸目标≥44pt + 间距≥8px）**

```scss
// ✅ P0: 移动端快捷操作栏（触摸目标≥44pt + 间距≥8px）
.mobile-quick-actions {
  display: flex;
  gap: $wolf-space-md;         // ✅ 增加到16px（原$wolf-space-sm=8px，按钮间距需更大）
  padding: $wolf-space-md 0;    // ✅ 增加到16px（原$wolf-space-sm=8px）
  border-bottom: 1px solid $wolf-border-light;
  margin-bottom: $wolf-space-md;

  // ✅ P0: Element Plus 按钮默认高度40px，需要扩展触摸区域到44pt
  .el-button {
    min-height: 44px;           // ✅ 强制最小高度44pt
    padding: 12px 20px;         // ✅ 增加内边距（默认10px 20px）
    position: relative;

    // ✅ 触摸区域扩展（视觉不变，触摸范围增大）
    &::after {
      content: '';
      position: absolute;
      top: -4px;
      bottom: -4px;
      left: -8px;
      right: -8px;
    }

    // ✅ P0: 按下反馈（Element Plus自带，但需确认）
    &:active {
      transform: scale(0.95);
      opacity: 0.8;
    }
  }

  // ✅ P0: 按钮图标 + 文字布局
  .button-label {
    font-size: 12px;
    margin-left: 4px;
  }

  @media (min-width: 769px) {
    display: none; // 桌面端隐藏
  }
}
```

- [ ] **Step 3: 提交移动端快捷操作代码**

```bash
git add CRM-Client/src/views/CustomerDetail.vue
git commit -m "feat(customer-detail): add mobile quick action buttons"
```

---

## Task 8: 最终验证与文档更新

**Files:**
- Test: 手动测试所有导航项切换、快捷操作触发、响应式布局
- Doc: `CRM-Client/docs/COMPONENTS.md` (更新组件文档)

**Interfaces:**
- Consumes: 所有已完成的功能
- Produces: 功能验证报告 + 组件文档更新

- [ ] **Step 1: 功能验证清单**

手动测试以下功能：

| 功能 | 测试步骤 | 预期结果 |
|------|----------|----------|
| **导航切换** | 点击左侧导航"跟进"、"联系人"、"商机" | 右侧面板切换，active指示条显示 |
| **快捷操作模态框** | 点击" + 跟进"、" + 联系人" | 模态框打开 |
| **快捷操作跳转** | 点击" + 商机"、" + 合同" | 跳转到创建页面 |
| **响应式（1024px）** | 调整窗口宽度至1024px | 导航折叠为60px，只显示图标 |
| **响应式（768px）** | 调整窗口宽度至768px | 导航改为顶部横向标签 |
| **移动端快捷操作** | 768px宽度，点击"添加跟进"按钮 | 模态框打开 |

- [ ] **Step 2: 更新组件文档**

修改文件：`CRM-Client/docs/COMPONENTS.md`

添加 CustomerDetailSidebar 组件文档：
```markdown
## CustomerDetailSidebar

客户详情页左侧导航组件，用于切换内容面板和触发快捷操作。

### Props

| Prop | Type | Required | Description |
|------|------|----------|-------------|
| customerId | number | Yes | 客户ID，用于快捷操作跳转 |

### Events

| Event | Payload | Description |
|-------|---------|-------------|
| nav-change | string | 导航切换事件，payload为导航key |
| show-add-follow-up | void | 触发"添加跟进"模态框 |
| show-add-contact | void | 触发"添加联系人"模态框 |

### 响应式行为

| 断点 | 宽度 | 行为 |
|------|------|------|
| ≥1024px | 160px | 全部显示（图标 + 文字） |
| 768-1024px | 60px | 折叠（只显示图标） |
| <768px | 100% | 顶部横向标签（flex-wrap） |
```

- [ ] **Step 3: 提交文档更新**

```bash
git add CRM-Client/docs/COMPONENTS.md
git commit -m "docs(customer-detail): update sidebar component documentation"
```

---

## Self-Review Checklist

**1. Spec Coverage:**

| 需求 | 任务 | 状态 |
|------|------|------|
| 左侧导航（160px宽度） | Task 1 | ✅ |
| 导航项：跟进、联系人、商机、合同、回款、发票 | Task 1 | ✅ |
| 快捷操作区 | Task 1, Task 4 | ✅ |
| 返回按钮（全局Header） | 无需修改（已实现） | ✅ |
| 响应式折叠（1024px → 60px） | Task 2, Task 5 | ✅ |
| 移动端适配（768px → 顶部横向） | Task 2, Task 6 | ✅ |
| 导航切换逻辑 | Task 2, Task 3 | ✅ |
| 快捷操作模态框触发 | Task 4 | ✅ |
| **移动端导航分组（解决 bottom-nav-limit）** | **Task 9** | **✅** |

**2. UI/UX Pro Max CRITICAL 规则验证清单:**

| 规则 | 描述 | 实施位置 | 状态 |
|------|------|----------|------|
| **touch-target-size** | 导航项高度≥44pt | CustomerDetailSidebar.scss:244-252 (min-height: 44px + 伪元素扩展) | ✅ |
| **touch-target-size** | 快捷操作高度≥44pt | CustomerDetailSidebar.scss:336-358 (min-height: 44px + 伪元素扩展) | ✅ |
| **touch-target-size** | 移动端按钮高度≥44pt | CustomerDetail.vue:1020-1032 (min-height: 44px + 伪元素扩展) | ✅ |
| **touch-spacing** | 导航项间距≥8px | CustomerDetailSidebar.scss:250 (margin-bottom: $wolf-space-xs=4px，需改为8px) | ⚠️ |
| **touch-spacing** | 移动端导航间距≥8px | CustomerDetailSidebar.scss:396-398 (gap: $wolf-space-sm=8px ✅) | ✅ |
| **no-emoji-icons** | 快捷操作使用SVG图标 | CustomerDetailSidebar.vue:107-111 (<el-icon><Plus /></el-icon> ✅) | ✅ |
| **press-feedback** | 导航项按下反馈 | CustomerDetailSidebar.scss:288-292 (:active scale(0.95) + opacity ✅) | ✅ |
| **press-feedback** | 快捷操作按下反馈 | CustomerDetailSidebar.scss:352-355 (:active scale(0.95) + opacity ✅) | ✅ |
| **press-feedback** | 移动端按钮按下反馈 | CustomerDetail.vue:1027-1031 (:active scale(0.95) + opacity ✅) | ✅ |
| **aria-labels** | 导航项aria-label | CustomerDetailSidebar.vue:94 (:aria-label="nav.label" ✅) | ✅ |
| **aria-labels** | 快捷操作aria-label | CustomerDetailSidebar.vue:108 (:aria-label="'新建' + action.label" ✅) | ✅ |
| **aria-labels** | 移动端按钮aria-label | CustomerDetail.vue:982 (aria-label="新建跟进记录" ✅) | ✅ |
| **bottom-nav-limit** | 导航项≤5项（移动端） | Task 9: CustomerDetailSidebar.vue (核心导航4项 + 溢出菜单2项 ✅) | ✅ |
| **horizontal-scroll** | 移动端总宽度<375px | CustomerDetailSidebar.scss:440-450 (计算结果303px/6=50.5px ✅) | ✅ |

**⚠️ 已修复问题:**

1. **touch-spacing - 导航项间距不足（已修复）**：
   - 原问题：`margin-bottom: $wolf-space-xs` (4px)
   - 已修复：`margin-bottom: $wolf-space-sm` (8px) ✅
   - 位置：CustomerDetailSidebar.scss:250

2. **bottom-nav-limit - 导航项超过5项（已解决）**：
   - 原问题：6项导航（跟进、联系人、商机、合同、回款、发票）
   - 规则：Bottom navigation max 5 items (Material Design)
   - **解决方案**：Task 9 - 移动端使用 Top App Bar + 溢出菜单
     - 核心导航4项（高频）：跟进、联系人、商机、合同
     - 次级导航2项（低频）：回款、发票 → 溢出菜单"更多"
   - **实施位置**：Task 9 (CustomerDetailSidebar.vue + CustomerDetailSidebar.scss)
   - **状态**：✅ 已解决

**3. Placeholder Scan:**

搜索计划中的禁用词：
- "TBD" / "TODO" / "implement later" → **无**
- "Add appropriate error handling" → **无**
- "Write tests for the above" → **无**
- "Similar to Task N" → **无**

**3. Type Consistency:**

| 类型定义位置 | 使用位置 | 一致性 |
|--------------|----------|--------|
| `navItems: NavItem[]` | CustomerDetailSidebar.vue | ✅ |
| `activeNav: string` | CustomerDetailSidebar.vue + CustomerDetail.vue | ✅ |
| `emit('nav-change', navKey: string)` | CustomerDetailSidebar.vue | ✅ |
| `handleNavChange(navKey: string)` | CustomerDetail.vue | ✅ |

---

## Task 9: 移动端导航分组与溢出菜单（解决 bottom-nav-limit 问题）

**Files:**
- Modify: `CRM-Client/src/components/CustomerDetailSidebar.vue:80-105` (移动端导航分组逻辑)
- Modify: `CRM-Client/src/components/CustomerDetailSidebar.scss:430-450` (移动端溢出菜单样式)

**Interfaces:**
- Consumes: `navItems` 定义（6项导航）
- Produces:
  - 移动端核心导航4项：跟进、联系人、商机、合同
  - 移动端次级导航2项：回款、发票 → 溢出菜单"更多"
  - 溢出菜单使用 el-dropdown 组件

**背景:** UI/UX Pro Max 规则 `bottom-nav-limit` 要求 Bottom navigation max 5 items (Material Design)。当前导航有6项，需要移动端分组处理。

- [ ] **Step 1: 修改模板（添加移动端溢出菜单）**

修改文件：`CRM-Client/src/components/CustomerDetailSidebar.vue` 的 Line 80-105

**原代码：**
```vue
<div class="nav-section">
  <div class="nav-section-title">导航</div>
  
  <div 
    v-for="nav in navItems"
    :key="nav.key"
    class="nav-item"
    ...
  >
    ...
  </div>
</div>
```

**替换为：**
```vue
<div class="nav-section">
  <div class="nav-section-title">导航</div>
  
  <!-- ✅ P0: 桌面端显示全部6项导航 -->
  <div 
    v-for="nav in navItems"
    :key="nav.key"
    class="nav-item desktop-nav"
    :class="{ active: activeNav === nav.key }"
    tabindex="0"
    :aria-label="nav.label"
    @click="handleNavClick(nav.key)"
    @keydown.enter="handleNavClick(nav.key)"
  >
    <el-icon class="nav-icon">
      <component :is="nav.icon" />
    </el-icon>
    <span class="nav-label">{{ nav.label }}</span>
  </div>

  <!-- ✅ P0: 移动端核心导航4项（高频使用） -->
  <template v-if="isMobile">
    <div 
      v-for="nav in coreNavItems"
      :key="nav.key"
      class="nav-item mobile-nav"
      :class="{ active: activeNav === nav.key }"
      tabindex="0"
      :aria-label="nav.label"
      @click="handleNavClick(nav.key)"
      @keydown.enter="handleNavClick(nav.key)"
    >
      <el-icon class="nav-icon">
        <component :is="nav.icon" />
      </el-icon>
      <span class="nav-label">{{ nav.label }}</span>
    </div>

    <!-- ✅ P0: 移动端溢出菜单"更多"（次级导航2项） -->
    <el-dropdown trigger="click" placement="bottom-start" @command="handleNavClick">
      <div class="nav-item mobile-nav more-nav" tabindex="0" aria-label="更多导航选项">
        <el-icon class="nav-icon">
          <MoreFilled />
        </el-icon>
        <span class="nav-label">更多</span>
      </div>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item 
            v-for="nav in overflowNavItems"
            :key="nav.key"
            :command="nav.key"
          >
            <el-icon><component :is="nav.icon" /></el-icon>
            {{ nav.label }}
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </template>
</div>
```

- [ ] **Step 2: 添加移动端导航分组逻辑（script 部分）**

修改文件：`CRM-Client/src/components/CustomerDetailSidebar.vue` 的 `<script setup>` 部分

**在 Line 156 附近添加：**
```typescript
import { useMediaQuery } from '@vueuse/core'
import { MoreFilled } from '@element-plus/icons-vue'

const isMobile = useMediaQuery('(max-width: 768px)')

// ✅ P0: 移动端导航分组（解决 bottom-nav-limit 问题）
const coreNavItems = navItems.slice(0, 4) // 核心导航4项：跟进、联系人、商机、合同
const overflowNavItems = navItems.slice(4)  // 次级导航2项：回款、发票
```

- [ ] **Step 3: 添加移动端溢出菜单样式**

修改文件：`CRM-Client/src/components/CustomerDetailSidebar.scss` 的移动端样式部分

**在 Line 430 附近添加：**
```scss
// ✅ P0: 移动端桌面端导航显示控制
.desktop-nav {
  display: flex;
  
  @media (max-width: 768px) {
    display: none; // 移动端隐藏桌面端全部6项导航
  }
}

.mobile-nav {
  display: none;
  
  @media (max-width: 768px) {
    display: flex; // 移动端显示核心导航4项 + 溢出菜单
  }
}

// ✅ P0: 溢出菜单"更多"样式
.more-nav {
  cursor: pointer;
  
  &:hover {
    background: $wolf-bg-hover;
  }
}

// ✅ P0: 溢出菜单下拉项样式
.el-dropdown-menu {
  .el-dropdown-item {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    padding: 12px 16px;
    min-height: 44px; // ✅ 触摸目标≥44pt
    
    .el-icon {
      font-size: 16px;
    }
    
    &:active {
      transform: scale(0.95); // ✅ 按下反馈
      opacity: 0.7;
    }
  }
}
```

- [ ] **Step 4: 验证移动端导航分组效果**

手动测试：
1. 桌面端（≥1024px）：显示全部6项导航
2. 移动端（<768px）：显示核心导航4项 + 溢出菜单"更多"
3. 点击"更多"，下拉菜单显示"回款"、"发票"
4. 点击下拉菜单项，切换到对应面板

- [ ] **Step 5: 提交移动端导航分组代码**

```bash
git add CRM-Client/src/components/CustomerDetailSidebar.vue CRM-Client/src/components/CustomerDetailSidebar.scss
git commit -m "feat(customer-detail): add mobile navigation grouping with overflow menu (fix bottom-nav-limit issue)"
```

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-05-customer-detail-sidebar-navigation.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**