# AppLayout 导航系统改造实施计划

**基于设计规范 + UI/UX Pro Max + navigation-redesign-v3.html**

---

## 一、改造目标

### 1.1 设计规范合规

| 规范来源 | 目标 |
|---------|------|
| **MASTER.md 六、导航组件规范** | Sidebar/TopBar/UserInfoDropdown 100% 合规 |
| **UI/UX Pro Max §9 Navigation Patterns** | nav-hierarchy, bottom-nav-limit, overflow-menu |
| **UI/UX Pro Max §2 Touch & Interaction** | touch-target-size 44×44px |
| **UI/UX Pro Max §1 Accessibility** | aria-labels, keyboard-nav, focus-states |
| **§1.5 shadcn-vue 优先原则** | Element Plus → shadcn-vue + Lucide icons |

### 1.2 效果稿核心变更

| 变更 | 规范依据 | 收益 |
|------|---------|------|
| **移除独立团队选择器** | §9 nav-hierarchy（团队切换为 secondary nav） | 节省约 80px sidebar 高度 |
| **用户信息显示当前团队** | MASTER.md 6.4 UserInfoDropdown | 用户随时知道自己在哪个团队 |
| **Hover 下拉菜单包含团队切换** | §9 overflow-menu（低频操作隐藏） | 符合 UX 最佳实践 |
| **分组导航菜单** | MASTER.md 6.1 Sidebar 分组规范 | 清晰的业务流程层级 |
| **左侧指示条 Signature 元素** | MASTER.md 6.1 左侧指示条设计 | 核心视觉特征 |

---

## 二、改造范围

### 2.1 文件清单

| 文件 | 改造内容 | 优先级 |
|------|---------|--------|
| `AppLayout.vue` | Sidebar 导航、TopBar Header、UserInfoDropdown | **P0 CRITICAL** |
| `src/styles/variables-v2.scss` | 确保 Design Tokens 完整 | P1 |
| `src/components/crmwolf/BottomNav.vue` | 已符合规范，无需改造 | - |

### 2.2 技术栈变更

| 当前技术 | 目标技术 | 规范依据 |
|---------|---------|---------|
| `@element-plus/icons-vue` | `lucide-vue-next` | §4 no-emoji-icons, icon-style-consistent |
| `el-button` | `shadcn-vue Button` | §1.5 shadcn-vue 优先原则 |
| `el-dialog` | `shadcn-vue Dialog/DropdownMenu` | §1.5 shadcn-vue 优先原则 |
| `variables.scss` | `variables-v2.scss` | MASTER.md 二、Design Token 强制规范 |

---

## 三、详细实施步骤

### Phase 1：Sidebar 导航菜单改造（MASTER.md 6.1）

#### Step 1.1：替换 Element Plus icons → Lucide

**规范依据**：§4 Style Selection - `icon-style-consistent`, `no-emoji-icons`

```typescript
// 当前（AppLayout.vue Line 160）
import { Flag, OfficeBuilding, TrendCharts, Document, Money, Tickets, ... } from '@element-plus/icons-vue'

// 目标（Lucide icons）
import {
  Calendar,      // 日历 - MASTER.md 6.5 日历
  Flag,          // 线索 - 效果稿
  Building2,     // 客户 - Lucide
  TrendingUp,    // 商机 - Lucide
  FileText,      // 合同 - Lucide
  Wallet,        // 回款 - Lucide
  Receipt,       // 发票 - Lucide
  Settings,      // 设置 - Lucide
  LogOut,        // 退出 - Lucide
  User,          // 个人资料 - Lucide
  ChevronDown,   // 下拉箭头 - 效果稿
  Check,         // 确认 - Lucide
  ArrowLeft,     // 返回 - Lucide
} from 'lucide-vue-next'
```

#### Step 1.2：分组导航菜单（MASTER.md 6.1 分组规范）

**效果稿结构**：

```vue
<nav class="sidebar-nav">
  <!-- 销售流程 -->
  <div class="nav-section">
    <div class="nav-section-title">销售流程</div>
    <a class="nav-item" :class="{ active: ... }">...</a>
  </div>

  <!-- 财务流程 -->
  <div class="nav-section">
    <div class="nav-section-title">财务流程</div>
    <a class="nav-item">...</a>
  </div>

  <!-- 管理工具 -->
  <div class="nav-section">
    <div class="nav-section-title">管理工具</div>
    <a class="nav-item">...</a>
  </div>
</nav>
```

**分组规范**：

| 分组 | 标题 | 菜单项 |
|------|------|--------|
| **销售流程** | `销售流程` | 我的日历、线索管理、客户管理、商机管理 |
| **财务流程** | `财务流程` | 合同管理、回款管理、发票管理 |
| **管理工具** | `管理工具` | 采购管理、团队管理、系统配置 |

#### Step 1.3：左侧指示条 Signature 元素（MASTER.md 6.1）

**视觉规范**：

```scss
.nav-item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 0;  // default
  height: 16px;
  background: $wolf-primary-v2;  // #2563EB
  border-radius: 0 2px 2px 0;
  transition: width 0.15s ease;  // MASTER.md 四、动画系统
}

.nav-item:hover::before { width: 3px; }   // hover 3px
.nav-item.active::before { width: 4px; }  // active 4px
```

#### Step 1.4：Design Token 切换（MASTER.md 二）

**变量映射表**：

| 旧变量（variables.scss） | 新变量（variables-v2.scss） | 值 |
|-------------------------|----------------------------|-----|
| `$wolf-bg-page` | `$wolf-bg-page-v2` | `#F8FAFC` |
| `$wolf-bg-sidebar` | `$wolf-bg-card-v2` | `#FFFFFF` |
| `$wolf-bg-hover` | `$wolf-bg-hover-v2` | `#EEF2FF` |
| `$wolf-bg-active` | `$wolf-primary-light-v2` | `#F1F5FD` |
| `$wolf-border-default` | `$wolf-border-default-v2` | `#E4ECFC` |
| `$wolf-primary` | `$wolf-primary-v2` | `#2563EB` |
| `$wolf-text-primary` | `$wolf-text-primary-v2` | `#0F172A` |
| `$wolf-text-secondary` | `$wolf-text-secondary-v2` | `#64748B` |
| `$wolf-text-tertiary` | `$wolf-text-tertiary-v2` | `#94A3B8` |
| `$wolf-space-sm` | `$wolf-space-sm-v2` | `8px` |
| `$wolf-space-md` | `$wolf-space-md-v2` | `16px` |
| `$wolf-radius-sm` | `$wolf-radius-sm-v2` | `6px` |
| `$wolf-header-height` | `$wolf-header-height-v2` | `56px` |

#### Step 1.5：菜单项完整视觉规范（MASTER.md 6.1）

**视觉规范表**：

| 属性 | Token | 值 | 说明 |
|------|-------|-----|------|
| **视觉高度** | - | `40px` | MASTER.md 6.1 菜单项高度 |
| **Touch Target** | - | `44px` | §2 touch-target-size（通过 padding 扩展） |
| **圆角** | `$wolf-radius-sm-v2` | `6px` | MASTER.md 6.1 菜单项圆角 |
| **字号** | `$wolf-font-size-body-v2` | `14px` | 正文尺寸 |
| **字重 default** | `$wolf-font-weight-medium-v2` | `500` | 中等字重 |
| **字重 active** | `$wolf-font-weight-semibold-v2` | `600` | 半粗体 |
| **文字颜色 default** | `$wolf-text-tertiary-v2` | `#94A3B8` | 三级文字 |
| **文字颜色 hover** | `$wolf-text-secondary-v2` | `#64748B` | 二级文字 |
| **文字颜色 active** | `$wolf-primary-v2` | `#2563EB` | 主色 |

**实现代码**：

```scss
.nav-item {
  // 视觉高度 + Touch Target 扩展
  height: 40px;  // 视觉高度（MASTER.md 6.1）
  min-height: 44px;  // Touch target（§2 touch-target-size）
  padding: 10px 12px;  // 扩展点击区域

  // 圆角
  border-radius: $wolf-radius-sm-v2;  // 6px

  // 字体
  font-size: $wolf-font-size-body-v2;  // 14px
  font-weight: $wolf-font-weight-medium-v2;  // 500

  // 文字颜色
  color: $wolf-text-tertiary-v2;  // default

  // 状态过渡
  transition: all $wolf-transition-v2;  // 150ms ease

  &:hover {
    background: $wolf-bg-hover-v2;
    color: $wolf-text-secondary-v2;
  }

  &.active {
    background: $wolf-primary-light-v2;
    color: $wolf-primary-v2;
    font-weight: $wolf-font-weight-semibold-v2;  // 600
  }
}
```

#### Step 1.6：分组标题样式（效果稿）

**视觉规范**：

| 属性 | 值 |
|------|-----|
| **字号** | `11px` |
| **字重** | `600` |
| **文字颜色** | `#94A3B8`（$wolf-text-tertiary-v2） |
| **大写** | `uppercase` |
| **字母间距** | `0.5px` |
| **内边距** | `0 12px` |
| **底部间距** | `8px` |

**实现代码**：

```scss
.nav-section-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: $wolf-text-tertiary-v2;
  padding: 0 12px;
  margin-bottom: 8px;
}
```

#### Step 1.7：导航项 Badge 设计（效果稿）

**视觉规范**：

| 属性 | 值 |
|------|-----|
| **位置** | 右侧对齐 |
| **背景 default** | `#DC2626`（danger） |
| **背景 warning** | `#F59E0B`（warning） |
| **背景 success** | `#10B981`（success） |
| **文字颜色** | `#FFFFFF` |
| **字号** | `10px` |
| **字重** | `600` |
| **内边距** | `2px 6px` |
| **圆角** | `10px` |
| **最小宽度** | `18px` |

**实现代码**：

```vue
<a class="nav-item">
  <component :is="item.icon" class="nav-item-icon" />
  <span class="nav-item-text">{{ item.label }}</span>
  <span
    v-if="item.badge"
    class="nav-item-badge"
    :class="item.badge.type"
  >
    {{ item.badge.count }}
  </span>
</a>
```

```scss
.nav-item-badge {
  margin-left: auto;
  background: #DC2626;  // default danger
  color: white;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 10px;
  font-weight: 600;
  min-width: 18px;
  text-align: center;

  &.warning { background: #F59E0B; }
  &.success { background: #10B981; }
}
```

---

### Phase 2：团队选择器优化（MASTER.md 6.4 UserInfoDropdown）

#### Step 2.1：移除独立团队选择器卡片

**当前代码**（AppLayout.vue Line 5-23）：

```vue
<div class="team-selector" @click="showTeamSwitcher = true">
  <el-icon class="team-icon"><OfficeBuilding /></el-icon>
  <span class="team-name">{{ teamStore.currentTeam?.name || '未选择团队' }}</span>
  <el-icon class="switch-icon"><ArrowDown /></el-icon>
</div>
<el-dialog v-model="showTeamSwitcher" title="切换团队" width="300px">
  ...
</el-dialog>
```

**改造**：删除这段代码，节省约 80px sidebar 高度。

#### Step 2.2：整合到用户信息区域

**效果稿结构**：

```vue
<div class="sidebar-footer">
  <div class="user-info" @click="showUserDropdown = !showUserDropdown">
    <!-- 用户头像 -->
    <div class="user-avatar">{{ userStore.userInfo?.name?.charAt(0) || 'U' }}</div>

    <!-- 用户详情 -->
    <div class="user-details">
      <div class="user-name">{{ userStore.userInfo?.name || '未登录' }}</div>
      <div class="user-team">{{ teamStore.currentTeam?.name || '未选择团队' }}</div>  <!-- 新增：显示当前团队 -->
    </div>

    <!-- 下拉箭头 -->
    <ChevronDown class="user-chevron" :class="{ 'rotate-180': showUserDropdown }" />

    <!-- 用户下拉菜单（向上展开） -->
    <div v-if="showUserDropdown" class="user-dropdown">
      <!-- 切换团队 section -->
      <div class="dropdown-header">
        <div class="dropdown-header-label">切换团队</div>
      </div>
      <div
        v-for="team in teamStore.teams"
        :key="team.id"
        class="dropdown-item"
        :class="{ active: team.id === teamStore.currentTeam?.id }"
        @click="handleSwitchTeam(team.id)"
      >
        <Building2 class="dropdown-icon" />
        <div class="dropdown-label">{{ team.name }}</div>
        <Check v-if="team.id === teamStore.currentTeam?.id" class="dropdown-active-indicator" />
      </div>

      <!-- 分隔线 -->
      <div class="dropdown-separator"></div>

      <!-- 个人设置 section -->
      <div class="dropdown-header">
        <div class="dropdown-header-label">个人设置</div>
      </div>
      <div class="dropdown-item" @click="handleUserProfile">
        <User class="dropdown-icon" />
        <div class="dropdown-label">个人资料</div>
      </div>
      <div class="dropdown-item" @click="handleAccountSettings">
        <Settings class="dropdown-icon" />
        <div class="dropdown-label">账户设置</div>
      </div>
      <div class="dropdown-item" @click="handleLogout">
        <LogOut class="dropdown-icon" />
        <div class="dropdown-label">退出登录</div>
      </div>
    </div>
  </div>
</div>
```

#### Step 2.3：UserInfoDropdown 视觉规范（MASTER.md 6.4）

**视觉规范表**：

| 属性 | Token | 值 | 说明 |
|------|-------|-----|------|
| **展开方向** | - | 向上 | 从底部展开 |
| **圆角** | `$wolf-radius-lg-v2` | `8px` | MASTER.md 6.4 |
| **阴影** | - | `0 -4px 12px rgba(0, 0, 0, 0.15)` | 向上阴影 |
| **过渡** | `$wolf-transition-v2` | `0.2s ease` | MASTER.md 四、动画系统 |

#### Step 2.4：用户头像规范（MASTER.md 6.4）

**视觉规范**：

| 属性 | Token | 值 | 说明 |
|------|-------|-----|------|
| **尺寸** | - | `32px` | 效果稿标准 |
| **圆角** | `$wolf-radius-full-v2` | `50%` | 完整圆形 |
| **背景** | `$wolf-primary-v2` | `#2563EB` | 主色背景 |
| **文字颜色** | `$wolf-text-inverse-v2` | `#FFFFFF` | 白色文字 |
| **字号** | `$wolf-font-size-caption-v2` | `14px` | 辅助文字尺寸 |
| **字重** | `$wolf-font-weight-semibold-v2` | `600` | 半粗体 |

**实现代码**：

```scss
.user-avatar {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border-radius: $wolf-radius-full-v2;  // 50%
  overflow: hidden;
  background: $wolf-primary-v2;  // #2563EB
  display: flex;
  align-items: center;
  justify-content: center;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .avatar-placeholder {
    font-size: $wolf-font-size-caption-v2;  // 14px
    font-weight: $wolf-font-weight-semibold-v2;  // 600
    color: $wolf-text-inverse-v2;  // #FFFFFF
  }
}
```

#### Step 2.5：Dropdown Item 规范（效果稿）

**视觉规范**：

| 属性 | 值 |
|------|-----|
| **高度** | `44px`（Touch target） |
| **内边距** | `12px 16px` |
| **字号** | `14px` |
| **字重** | `500` |
| **图标尺寸** | `16px` |
| **图标右边距** | `12px` |
| **Hover 背景** | `#EEF2FF` |

**实现代码**：

```scss
.dropdown-item {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  min-height: 44px;  // Touch target
  cursor: pointer;
  transition: all $wolf-transition-v2;
  border-bottom: 1px solid $wolf-border-default-v2;

  &:last-child {
    border-bottom: none;
  }

  &:hover {
    background: $wolf-bg-hover-v2;  // #EEF2FF
  }

  &.active {
    background: $wolf-primary-light-v2;  // #F1F5FD
  }
}

.dropdown-icon {
  width: 16px;
  height: 16px;
  margin-right: 12px;
  color: $wolf-text-secondary-v2;
  flex-shrink: 0;
}

.dropdown-label {
  font-size: $wolf-font-size-body-v2;  // 14px
  font-weight: $wolf-font-weight-medium-v2;  // 500
  color: $wolf-text-primary-v2;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dropdown-active-indicator {
  width: 16px;
  height: 16px;
  color: $wolf-primary-v2;
  margin-left: 8px;
}
```

---

### Phase 3：TopBar Header 改造（MASTER.md 6.2）

#### Step 3.1：替换 el-button → shadcn-vue Button

**规范依据**：§1.5 shadcn-vue 优先原则

```vue
<!-- 当前（AppLayout.vue Line 84-103） -->
<el-button circle ...>
  <el-icon><component :is="headerStore.leftAction.icon" /></el-icon>
</el-button>

<!-- 目标 -->
<Button variant="ghost" size="icon" :aria-label="headerStore.leftAction.ariaLabel || '操作'" @click="headerStore.leftAction.handler">
  <component :is="headerStore.leftAction.icon" class="w-5 h-5" />
</Button>
```

#### Step 3.2：操作按钮使用 Button + Lucide

```vue
<template v-for="action in headerStore.actions" :key="action.id">
  <Button
    v-if="action.visible !== false"
    :variant="action.variant || 'outline'"
    :disabled="action.disabled"
    @click="action.handler"
  >
    <component v-if="action.icon" :is="action.icon" class="w-4 h-4 mr-2" />
    {{ action.label }}
  </Button>
</template>
```

#### Step 3.3：TopBar 三段式布局（MASTER.md 6.2）

**视觉规范表**：

| 属性 | Token | 值 |
|------|-------|-----|
| **高度** | `$wolf-header-height-v2` | `56px` |
| **背景** | `$wolf-bg-card-v2` | `#FFFFFF` |
| **标题字号** | `$wolf-font-size-title-v2` | `20px` |
| **标题字重** | `$wolf-font-weight-semibold-v2` | `600` |

**三段式布局**：

| 区域 | 内容 | 宽度 |
|------|------|------|
| **左侧** | 返回按钮 | `48px`（Touch target minimum） |
| **中间** | 页面标题 | 自适应居中 |
| **右侧** | 操作按钮 + 审批铃铛 | 自适应 |

---

### Phase 3.5：ContextTabs（上下文标签栏）（MASTER.md 6.3）

> ⚠️ **缺失项补充**：ContextTabs 在原计划中未覆盖

#### Step 3.5.1：视觉规范（MASTER.md 6.3）

| 属性 | Token | 值 | 说明 |
|------|-------|-----|------|
| **高度** | - | `48px` | MASTER.md 6.3 |
| **背景** | `$wolf-bg-card-v2` | `#FFFFFF` | 白色背景 |
| **字号** | `$wolf-font-size-body-v2` | `14px` | 正文尺寸 |
| **字重 default** | `$wolf-font-weight-medium-v2` | `500` | 中等字重 |
| **字重 active** | `$wolf-font-weight-semibold-v2` | `600` | 半粗体 |

#### Step 3.5.2：状态定义（MASTER.md 5.5 Tab）

| 状态 | 背景 | 文字 | Badge |
|------|------|------|-------|
| **Default** | 透明 | `#64748B` | 无 |
| **Hover** | `#EEF2FF` | `#2563EB` | 无 |
| **Active** | `#F1F5FD` | `#2563EB` | 主色 Badge |

#### Step 3.5.3：动态切换规则（MASTER.md 6.3）

| 页面类型 | 标签内容 |
|---------|---------|
| **客户详情页** | 基本信息 / 跟进记录 / 联系人 / 商机 / 合同 / 回款 / 发票 / License |
| **合同详情页** | 基本信息 / 回款计划 |
| **回款管理页** | 回款计划 / 回款记录 |

#### Step 3.5.4：实现代码

```vue
<template>
  <!-- ContextTabs（二级导航） -->
  <div class="context-tabs">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      class="context-tab"
      :class="{ active: activeTab === tab.key }"
      @click="activeTab = tab.key"
    >
      {{ tab.label }}
      <span v-if="tab.badge" class="context-tab-badge">{{ tab.badge }}</span>
    </button>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.context-tabs {
  position: fixed;
  left: 220px;  // Sidebar 宽度
  top: 56px;    // TopBar 高度
  right: 0;
  height: 48px;  // MASTER.md 6.3
  background: $wolf-bg-card-v2;
  border-bottom: 1px solid $wolf-border-default-v2;
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 4px;
  z-index: 85;  // z-index 管理
}

.context-tab {
  padding: 8px 16px;
  border-radius: $wolf-radius-sm-v2;  // 6px
  font-size: $wolf-font-size-body-v2;  // 14px
  font-weight: $wolf-font-weight-medium-v2;  // 500
  color: $wolf-text-secondary-v2;  // #64748B
  cursor: pointer;
  transition: all $wolf-transition-v2;  // 150ms ease
  border: none;
  background: transparent;
  white-space: nowrap;

  &:hover {
    background: $wolf-bg-hover-v2;  // #EEF2FF
    color: $wolf-primary-v2;  // #2563EB
  }

  &.active {
    background: $wolf-primary-light-v2;  // #F1F5FD
    color: $wolf-primary-v2;  // #2563EB
    font-weight: $wolf-font-weight-semibold-v2;  // 600
  }
}

.context-tab-badge {
  margin-left: 4px;
  background: $wolf-primary-v2;
  color: white;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 10px;
  font-weight: 600;
}
</style>
```

---

### Phase 4：Accessibility & Touch Targets（UI/UX Pro Max §1 §2）

#### Step 4.1：Touch targets 44×44px（§2 touch-target-size）

**规范**：最小 44×44pt（Apple HIG） / 48×48dp（Material）

```scss
// Sidebar 菜单项
.nav-item {
  min-height: 44px;  // Touch target minimum
  padding: 10px 12px;
}

// TopBar 按钮
.header-back-btn,
.header-left-btn {
  width: 44px;   // 或使用 padding 扩展点击区域
  height: 44px;
}

// UserInfoDropdown
.user-info {
  min-height: 44px;
  padding: 10px;
}
```

#### Step 4.2：aria-labels（§1 aria-labels）

```vue
<!-- Sidebar -->
<nav role="navigation" aria-label="主导航">
  <a
    class="nav-item"
    :aria-current="isActive ? 'page' : undefined"
    :aria-label="item.label"
  >
    ...
  </a>
</nav>

<!-- TopBar -->
<Button :aria-label="headerStore.leftAction.ariaLabel || '操作'" ...>
  <component :is="headerStore.leftAction.icon" aria-hidden="true" />
</Button>

<!-- UserInfoDropdown -->
<div
  class="user-info"
  role="button"
  aria-label="用户设置"
  aria-expanded="showUserDropdown"
  @click="toggleUserDropdown"
>
  ...
</div>
```

#### Step 4.3：keyboard-nav + focus-states（§1 keyboard-nav, §8.2 Focus）

```scss
// Focus ring（MASTER.md 8.2）
.nav-item:focus-visible {
  outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;  // 2px rgba(#2563EB, 0.5)
  outline-offset: $wolf-focus-ring-offset-v2;  // 2px
}

.user-info:focus-visible {
  outline: 2px solid $wolf-primary-v2;
  outline-offset: 2px;
}

.dropdown-item:focus-visible {
  outline: 2px solid $wolf-primary-v2;
  outline-offset: 2px;
}
```

---

### Phase 5：Mobile Responsive（MASTER.md 十、响应式规范）

#### Step 5.1：Sidebar 响应式切换（MASTER.md 10.1）

```scss
.sidebar {
  width: 220px;  // MASTER.md 6.1

  // §9 adaptive-navigation: Hide on mobile
  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {  // <768px
    display: none;
  }
}
```

#### Step 5.2：UserInfoDropdown 移动端适配

**移动端**：点击触发（而非 hover）

```vue
<script setup>
// 移动端使用点击，桌面端使用 hover
const isMobile = computed(() => window.innerWidth < 768)
const showUserDropdown = ref(false)

function toggleUserDropdown() {
  if (isMobile.value) {
    showUserDropdown.value = !showUserDropdown.value
  }
}

function handleUserInfoHover() {
  if (!isMobile.value) {
    showUserDropdown.value = true
  }
}

function handleUserInfoLeave() {
  if (!isMobile.value) {
    showUserDropdown.value = false
  }
}
</script>

<template>
  <div
    class="user-info"
    @click="toggleUserDropdown"
    @mouseenter="handleUserInfoHover"
    @mouseleave="handleUserInfoLeave"
  >
    ...
  </div>
</template>
```

#### Step 5.3：Safe Areas（MASTER.md 10.4）

```scss
.sidebar-footer {
  padding-bottom: env(safe-area-inset-bottom, 0px);  // iOS notch / Android gesture bar
}
```

---

### Phase 6.5：z-index 管理（MASTER.md 5.5）

> ⚠️ **缺失项补充**：z-index 层级管理规范

**z-index 层级规范**（MASTER.md 5.5 + UI/UX Pro Max §5）：

| 元素 | z-index | 说明 |
|------|---------|------|
| **Sidebar** | `100` | 左侧菜单固定 |
| **TopBar** | `90` | 顶部栏固定 |
| **ContextTabs** | `85` | 二级导航固定 |
| **UserDropdown** | `1000` | 下拉菜单最高层级 |
| **Modal/Dialog** | `1000` | 模态框最高层级 |
| **BottomNav（Mobile）** | `100` | 底部导航固定 |

**实现代码**：

```scss
// z-index 变量定义
$z-index-sidebar: 100;
$z-index-topbar: 90;
$z-index-context-tabs: 85;
$z-index-dropdown: 1000;
$z-index-modal: 1000;
$z-index-bottom-nav: 100;

.sidebar {
  z-index: $z-index-sidebar;
}

.topbar {
  z-index: $z-index-topbar;
}

.context-tabs {
  z-index: $z-index-context-tabs;
}

.user-dropdown {
  z-index: $z-index-dropdown;
}

.bottom-nav {
  z-index: $z-index-bottom-nav;
}
```

---

### Phase 6：Reduced Motion（MASTER.md 8.3）

```scss
// §7 reduced-motion
@media (prefers-reduced-motion: reduce) {
  .nav-item::before {
    transition: none;  // 或使用 MASTER.md 8.3 的 0.01ms
  }

  .nav-item,
  .user-dropdown,
  .dropdown-item {
    transition: opacity $wolf-reduced-motion-duration-v2 ease-out;  // 0.01ms
  }
}
```

---

## 四、改造优先级（按 UI/UX Pro Max Priority）

| Priority | Phase | 规范依据 | 预估时间 |
|----------|-------|---------|---------|
| **1 CRITICAL** | Phase 4 | §1 Accessibility, §2 Touch Targets | 15min |
| **9 HIGH** | Phase 1 | MASTER.md 6.1 Sidebar, §9 Navigation Patterns | 30min |
| **9 HIGH** | Phase 2 | MASTER.md 6.4 UserInfoDropdown, §9 overflow-menu | 20min |
| **9 HIGH** | Phase 3 | MASTER.md 6.2 TopBar, §1.5 shadcn-vue | 15min |
| **5 HIGH** | Phase 5 | MASTER.md 10 响应式规范, §5 Layout | 10min |
| **7 MEDIUM** | Phase 6 | MASTER.md 8.3 Reduced Motion | 5min |
| **总计** | - | - | **95min** |

---

## 五、验收标准

### 5.1 设计规范验收

| 检查项 | 规范来源 | 验收方法 |
|--------|---------|---------|
| **Sidebar 宽度 220px** | MASTER.md 6.1 | DevTools 测量 |
| **Sidebar 左侧指示条** | MASTER.md 6.1 | hover 3px / active 4px |
| **菜单项视觉高度 40px** | MASTER.md 6.1 | DevTools 测量 |
| **菜单项圆角 6px** | MASTER.md 6.1 | DevTools 测量 |
| **分组导航菜单** | MASTER.md 6.1 分组规范 | 销售流程/财务流程/管理工具 |
| **分组标题样式** | 效果稿 | 11px uppercase |
| **导航项 Badge** | 效果稿 | 右侧对齐 + 颜色区分 |
| **TopBar 高度 56px** | MASTER.md 6.2 | DevTools 测量 |
| **TopBar 三段式布局** | MASTER.md 6.2 | 视觉检查 |
| **ContextTabs 高度 48px** | MASTER.md 6.3 | DevTools 测量 |
| **ContextTabs 动态切换** | MASTER.md 6.3 | 页面类型匹配标签内容 |
| **UserInfoDropdown 向上展开** | MASTER.md 6.4 | 视觉检查 |
| **UserInfoDropdown 内容分组** | MASTER.md 6.4 | 切换团队 / 个人设置 |
| **用户头像 32px + 主色背景** | MASTER.md 6.4 | DevTools 测量 |
| **Dropdown Item 高度 44px** | 效果稿 | Touch target |
| **z-index 层级** | MASTER.md 5.5 | Sidebar 100 / TopBar 90 / Dropdown 1000 |
| **Touch targets 44×44px** | §2 touch-target-size | axe-core / DevTools |
| **aria-labels** | §1 aria-labels | axe-core |
| **keyboard-nav** | §1 keyboard-nav | Tab 键测试 |
| **Focus ring 2px** | MASTER.md 8.2 | Focus Visible 测试 |
| **reduced-motion** | MASTER.md 8.3 | prefers-reduced-motion 测试 |

### 5.2 技术栈验收

| 检查项 | 验收方法 |
|--------|---------|
| **无 Element Plus icons** | `grep "@element-plus/icons-vue" src/AppLayout.vue` → 无匹配 |
| **无 el-button** | `grep "el-button" src/AppLayout.vue` → 无匹配 |
| **无 el-dialog** | `grep "el-dialog" src/AppLayout.vue` → 无匹配 |
| **使用 variables-v2.scss** | `grep "variables-v2" src/AppLayout.vue` → 有匹配 |
| **使用 Lucide icons** | `grep "lucide-vue-next" src/AppLayout.vue` → 有匹配 |

---

## 六、风险与替代方案

### 6.1 技术风险

| 风险 | 影响 | 替代方案 |
|------|------|---------|
| **shadcn-vue 无 DropdownMenu** | UserInfoDropdown 实现受阻 | 自定义 Vue Dropdown + Lucide icons |
| **Lucide icons 缺少某些图标** | 图标替换受阻 | 使用 Lucide 最接近的图标或自定义 SVG |
| **移动端 Hover 不触发** | UserInfoDropdown 交互受阻 | 移动端使用点击触发 |

### 6.2 向后兼容（MASTER.md 十二）

| 旧变量 | 新变量 | 迁移时间 |
|--------|--------|---------|
| `variables.scss` | `variables-v2.scss` | 2026-07-15 前 |

---

## 七、文档更新

### 7.1 需要更新的文档

| 文档 | 更新内容 |
|------|---------|
| **MASTER.md** | §1.5 补充 Sidebar/TopBar/UserInfoDropdown 迁移示例 |
| **README.md** | Phase 0 Week 3 状态更新为 ✅ 已完成 |
| **ELEMENT-PLUS-MIGRATION.md** | AppLayout.vue 迁移记录 |

---

## 八、执行确认

- **是否开始执行改造**：[待用户确认]
- **改造范围**：Phase 1-6 全量改造
- **预估完成时间**：95min

---

**文档版本**：V1.1（补充完整规范） | **创建日期**：2026-07-09 | **依据规范**：MASTER.md V2.1 + UI/UX Pro Max

---

## 附录：补充内容汇总

| 补充项 | 原因 | 补充位置 |
|--------|------|---------|
| **菜单项完整视觉规范** | MASTER.md 6.1 高度 40px + 圆角 6px 未明确 | Step 1.5 |
| **分组标题样式** | 效果稿有但规范未覆盖 | Step 1.6 |
| **导航项 Badge 设计** | 效果稿有但规范未覆盖 | Step 1.7 |
| **ContextTabs（二级导航）** | MASTER.md 6.3 完全缺失 | Phase 3.5 |
| **用户头像规范** | MASTER.md 6.4 尺寸 32px 未明确 | Step 2.4 |
| **Dropdown Item 规范** | 效果稿高度 44px 未覆盖 | Step 2.5 |
| **z-index 管理** | MASTER.md 5.5 未覆盖 | Phase 6.5 |
| **验收标准补充** | 新增检查项 | 5.1 |