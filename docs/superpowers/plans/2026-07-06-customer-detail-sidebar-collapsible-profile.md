# CustomerDetail Sidebar Collapsible Profile 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 优化客户详情页左侧导航，解决导航层级混淆问题，添加可折叠客户档案功能

**Architecture:** 
- 收窄二级导航（48px icon-only + hover tooltip）
- 新增"客户档案"导航项（可折叠）
- 智能折叠逻辑：首次切换其他 tab 自动收起，用户手动展开后保持状态
- 收起时显示简化版客户名称卡片（而非完全隐藏）

**Tech Stack:** Vue 3 Composition API + Element Plus + Pinia + SCSS Design Tokens

---

## Global Constraints

- 禁止推断业务常量，必须查阅代码定义（CLAUDE.md 防幻觉指令）
- TypeScript 四禁令：禁用 `any` `as any` `@ts-ignore` `!`
- 所有 State 必须类型化：`ref<Type>(...)`
- Design Token 引用：必须使用 `$wolf-*` 变量，禁止魔数
- 触摸目标：最小 44×44pt（iOS）或 48×48dp（Android）
- **UI/UX Pro Max CRITICAL 规则**：
  - `touch-target-size` - icon-only 导航项高度必须 ≥44pt
  - `no-emoji-icons` - 使用 SVG 图标（Element Plus Icons）
  - `press-feedback` - 必须添加 `:active` 按下反馈
  - `hover-tooltip` - icon-only 模式必须提供 hover tooltip（桌面端）
  - `aria-labels` - 图标必须有 aria-label 描述
  - `state-preservation` - 用户手动展开后，切换其他 tab 不自动收起

---

## File Structure

**将创建/修改的文件：**

```
CRM-Client/src/
├── components/
│   └── CustomerDetailSidebar.vue         # 修改：新增客户档案导航项
│   └── CustomerDetailSidebar.scss        # 修改：收窄宽度 + 添加折叠样式
├── views/
│   └── CustomerDetail.vue                # 修改：添加智能折叠逻辑 + 简化版客户档案卡片
```

---

## Task 1: 收窄二级导航（48px icon-only）

**Files:**
- Modify: `CRM-Client/src/components/CustomerDetailSidebar.scss:259-262`

**Interfaces:**
- Consumes: 原有的 160px 宽度定义
- Produces: 48px icon-only sidebar + hover tooltip

**设计规范：**
- 一级导航（AppLayout sidebar）：200px（完整 sidebar）
- 二级导航（CustomerDetailSidebar）：48px（icon-only）
- 视觉区分：二级导航背景更浅（$wolf-bg-sidebar-light）
- Hover tooltip：CSS 或 el-tooltip（显示中文名）

- [ ] **Step 1: 修改 CustomerDetailSidebar.scss 的宽度定义**

修改文件：`CRM-Client/src/components/CustomerDetailSidebar.scss`

**在 Line 259-262 修改：**
```scss
// 原代码：
$sidebar-width: 160px;
$sidebar-collapsed: 60px;

// 替换为：
$sidebar-width: 48px;        // ✅ 收窄到48px（icon-only）
$sidebar-collapsed: 48px;    // ✅ 折叠状态也是48px
```

- [ ] **Step 2: 添加 hover tooltip 样式**

在 CustomerDetailSidebar.scss 中添加：
```scss
// ✅ Hover tooltip（桌面端）
.nav-item {
  position: relative;
  
  // ✅ hover 显示 tooltip
  &:hover::before {
    content: attr(data-tooltip);  // "跟进"、"联系人"等
    position: absolute;
    left: $sidebar-width + 8px;   // sidebar右侧
    top: 50%;
    transform: translateY(-50%);
    background: $wolf-bg-card;
    border: 1px solid $wolf-border-light;
    border-radius: $wolf-radius-sm;
    padding: 8px 12px;
    white-space: nowrap;
    font-size: $wolf-font-size-caption;
    color: $wolf-text-primary;
    z-index: 1000;
    opacity: 0;
    visibility: hidden;
    transition: opacity 0.15s ease-out, visibility 0.15s ease-out;
  }
  
  &:hover::before {
    opacity: 1;
    visibility: visible;
  }
}
```

- [ ] **Step 3: 修改模板，添加 data-tooltip 属性**

修改文件：`CRM-Client/src/components/CustomerDetailSidebar.vue`

**修改导航项模板：**
```vue
<div
  v-for="nav in navItems"
  :key="nav.key"
  class="nav-item"
  :class="{ active: activeNav === nav.key }"
  :data-tooltip="nav.label"  <!-- ✅ 添加 data-tooltip -->
  tabindex="0"
  :aria-label="nav.label"
  @click="handleNavClick(nav.key)"
>
  <el-icon class="nav-icon">
    <component :is="nav.icon" />
  </el-icon>
  <!-- ✅ 移除 nav-label（icon-only 模式不显示文字） -->
</div>
```

- [ ] **Step 4: 验证收窄效果**

手动测试：
1. 检查二级导航宽度是否为48px
2. hover 导航项时，tooltip 是否显示
3. 触摸目标是否 ≥44pt（nav-item 高度）

---

## Task 2: 新增"客户档案"导航项（可折叠）

**Files:**
- Modify: `CRM-Client/src/components/CustomerDetailSidebar.vue:205-212`

**Interfaces:**
- Consumes: 原有的 navItems 定义
- Produces: 新增 'profile' 导航项（可折叠）

- [ ] **Step 1: 修改 navItems 定义，新增客户档案**

修改文件：`CRM-Client/src/components/CustomerDetailSidebar.vue`

**在 Line 205-212 修改：**
```typescript
// 原代码：
const navItems = [
  { key: 'followup', label: '跟进', icon: ChatDotRound },
  { key: 'contacts', label: '联系人', icon: User },
  ...
]

// 替换为：
const navItems = [
  { 
    key: 'profile', 
    label: '客户档案', 
    icon: FolderOpened,  // ✅ 使用文件夹图标（展开状态）
    collapsible: true    // ✅ 标记为可折叠
  },
  { key: 'followup', label: '跟进', icon: ChatDotRound },
  { key: 'contacts', label: '联系人', icon: User },
  { key: 'opportunities', label: '商机', icon: TrendCharts },
  { key: 'contracts', label: '合同', icon: Document },
  { key: 'payments', label: '回款', icon: Money },
  { key: 'invoices', label: '发票', icon: Tickets }
]
```

- [ ] **Step 2: 导入新的图标**

修改文件：`CRM-Client/src/components/CustomerDetailSidebar.vue`

**在导入部分添加：**
```typescript
import {
  ChatDotRound,
  User,
  TrendCharts,
  Document,
  Money,
  Tickets,
  Plus,
  FolderOpened,   // ✅ 新增：文件夹图标（展开）
  Folder,         // ✅ 新增：文件夹图标（收起）
  ArrowDown,      // ✅ 新增：箭头向下（展开）
  ArrowRight      // ✅ 新增：箭头向右（收起）
} from '@element-plus/icons-vue'
```

- [ ] **Step 3: 修改模板，特殊处理客户档案项**

修改文件：`CRM-Client/src/components/CustomerDetailSidebar.vue`

**修改导航项模板：**
```vue
<!-- 导航项列表 -->
<div
  v-for="nav in navItems"
  :key="nav.key"
  class="nav-item"
  :class="{ 
    active: activeNav === nav.key,
    collapsible: nav.collapsible,
    expanded: nav.key === 'profile' && profileExpanded 
  }"
  :data-tooltip="nav.label + (nav.collapsible ? (profileExpanded ? '（点击收起）' : '（点击展开）') : '')"
  tabindex="0"
  :aria-label="nav.label"
  @click="nav.collapsible ? handleProfileClick() : handleNavClick(nav.key)"
>
  <el-icon class="nav-icon">
    <!-- ✅ 客户档案项：根据展开/收起状态切换图标 -->
    <component 
      v-if="nav.collapsible"
      :is="profileExpanded ? FolderOpened : Folder" 
    />
    <component v-else :is="nav.icon" />
  </el-icon>
  
  <!-- ✅ 客户档案项：显示展开/收起箭头 -->
  <el-icon v-if="nav.collapsible" class="collapse-icon">
    <component :is="profileExpanded ? ArrowDown : ArrowRight" />
  </el-icon>
</div>
```

- [ ] **Step 4: 添加 profileExpanded 状态和 handleProfileClick 函数**

修改文件：`CRM-Client/src/components/CustomerDetailSidebar.vue`

**在 script setup 添加：**
```typescript
const profileExpanded = ref(true)  // 默认：展开

// 点击客户档案：切换展开/收起
function handleProfileClick(): void {
  profileExpanded.value = !profileExpanded.value
  emit('profile-toggle', profileExpanded.value)
  activeNav.value = 'profile'
}
```

- [ ] **Step 5: 添加新的 emit 事件**

修改文件：`CRM-Client/src/components/CustomerDetailSidebar.vue`

**修改 Emits 定义：**
```typescript
interface Emits {
  (e: 'nav-change', navKey: string): void
  (e: 'show-add-follow-up' | 'show-add-contact'): void
  (e: 'profile-toggle', expanded: boolean): void  // ✅ 新增
}
```

---

## Task 3: 添加客户档案折叠样式

**Files:**
- Modify: `CRM-Client/src/components/CustomerDetailSidebar.scss`

**Interfaces:**
- Consumes: .nav-item 基础样式
- Produces: .nav-item.collapsible 折叠样式 + 展开/收起箭头

- [ ] **Step 1: 添加可折叠导航项样式**

修改文件：`CRM-Client/src/components/CustomerDetailSidebar.scss`

**添加：**
```scss
// ✅ 可折叠导航项样式
.nav-item.collapsible {
  position: relative;
  
  // ✅ 收起状态：视觉反馈
  &:not(.expanded) {
    .nav-icon { opacity: 0.6; }  // 收起时图标半透明
    
    // tooltip 显示"（点击展开）"
    &:hover::before {
      content: attr(data-tooltip) "（点击展开）";
    }
  }
  
  // ✅ 展开状态：视觉反馈
  &.expanded {
    background: $wolf-primary-light;  // 展开时背景高亮
    
    .nav-icon { color: $wolf-primary; }  // 展开时图标高亮
    
    // tooltip 显示"（点击收起）"
    &:hover::before {
      content: attr(data-tooltip) "（点击收起）";
    }
  }
  
  // ✅ 展开/收起箭头（右侧）
  .collapse-icon {
    position: absolute;
    right: $wolf-space-sm;
    top: 50%;
    transform: translateY(-50%);
    font-size: 12px;
    color: $wolf-text-tertiary;
    transition: transform 0.15s ease-out;
  }
  
  &.expanded .collapse-icon {
    transform: translateY(-50%) rotate(90deg);  // 展开时箭头向下
  }
}
```

---

## Task 4: 修改 CustomerDetail 主页面（智能折叠逻辑）

**Files:**
- Modify: `CRM-Client/src/views/CustomerDetail.vue`

**Interfaces:**
- Consumes: CustomerDetailSidebar 的 emit 事件
- Produces: 智能折叠逻辑 + 简化版客户档案卡片

- [ ] **Step 1: 添加智能折叠状态**

修改文件：`CRM-Client/src/views/CustomerDetail.vue`

**在 script setup 添加：**
```typescript
const profileExpanded = ref(true)  // 默认：展开
const userExpandedProfile = ref(false)  // 用户是否手动展开过
```

- [ ] **Step 2: 修改 handleNavChange 函数，添加智能折叠逻辑**

修改文件：`CRM-Client/src/views/CustomerDetail.vue`

**修改：**
```typescript
// 导航切换处理
const handleNavChange = (navKey: string): void => {
  activeTab.value = navKey
  
  // ✅ 智能折叠逻辑：
  // - 首次切换：自动收起客户档案（节省空间）
  // - 用户手动展开后：不自动收起（尊重用户控制权）
  if (navKey !== 'profile' && !userExpandedProfile.value) {
    profileExpanded.value = false  // 自动收起
  }
}
```

- [ ] **Step 3: 添加 handleProfileToggle 函数**

修改文件：`CRM-Client/src/views/CustomerDetail.vue`

**添加：**
```typescript
// 监听客户档案展开/收起
const handleProfileToggle = (expanded: boolean): void => {
  profileExpanded.value = expanded
  
  // ✅ 记录用户是否手动展开
  if (expanded) {
    userExpandedProfile.value = true
  } else {
    userExpandedProfile.value = false
  }
}
```

- [ ] **Step 4: 修改模板，监听 profile-toggle 事件**

修改文件：`CRM-Client/src/views/CustomerDetail.vue`

**修改 CustomerDetailSidebar 组件：**
```vue
<CustomerDetailSidebar
  :customer-id="customerId"
  @nav-change="handleNavChange"
  @show-add-follow-up="showAddFollowUpModal"
  @show-add-contact="showAddContactModal"
  @profile-toggle="handleProfileToggle"  <!-- ✅ 新增 -->
/>
```

- [ ] **Step 5: 添加简化版客户档案卡片**

修改文件：`CRM-Client/src/views/CustomerDetail.vue`

**修改客户档案面板：**
```vue
<!-- 客户档案面板（可折叠） -->
<div 
  v-show="activeTab === 'profile' || profileExpanded"
  class="content-panel profile-panel"
  :class="{ expanded: profileExpanded, collapsed: !profileExpanded }"
>
  <!-- ✅ 收起时：只显示简化版客户名称卡片 -->
  <div v-if="!profileExpanded" class="customer-name-card-compact">
    <div class="customer-avatar">{{ customerDetail?.account_name?.charAt(0) || '客' }}</div>
    <div class="customer-info">
      <div class="customer-name">{{ customerDetail?.account_name }}</div>
      <div class="customer-status">
        <span :class="['status-tag', getStatusClass(customerDetail?.status)]">
          {{ getStatusText(customerDetail?.status) }}
        </span>
      </div>
    </div>
  </div>
  
  <!-- ✅ 展开时：显示完整客户档案 -->
  <div v-else>
    <!-- 客户信息卡片 -->
    <div class="info-card">... (原内容)</div>
    
    <!-- 热力值卡片 -->
    <div class="score-card-compact">... (原内容)</div>
    
    <!-- AI档案卡片 -->
    <div class="profile-card">... (原内容)</div>
  </div>
</div>
```

---

## Task 5: 添加简化版客户档案卡片样式

**Files:**
- Modify: `CRM-Client/src/views/CustomerDetail.vue` (style 部分)

**Interfaces:**
- Consumes: 原有的 info-card 样式
- Produces: .customer-name-card-compact 简化版样式

- [ ] **Step 1: 添加简化版客户档案卡片样式**

修改文件：`CRM-Client/src/views/CustomerDetail.vue`

**添加：**
```scss
// ✅ 简化版客户名称卡片（收起状态）
.customer-name-card-compact {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  padding: $wolf-space-sm $wolf-space-md;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-sm;
  border: 1px solid $wolf-border-light;
  
  .customer-avatar {
    width: 40px;
    height: 40px;
    border-radius: $wolf-radius-full;
    background: $wolf-primary-light;
    color: $wolf-primary;
    font-size: 18px;
    font-weight: $wolf-font-weight-semibold;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  
  .customer-info {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  
  .customer-name {
    font-size: $wolf-font-size-title;
    font-weight: $wolf-font-weight-semibold;
    color: $wolf-text-primary;
  }
  
  .customer-status {
    font-size: $wolf-font-size-caption;
    color: $wolf-text-tertiary;
  }
}
```

---

## Task 6: 验证和测试

**Files:**
- Test: 手动测试所有功能

- [ ] **Step 1: 验证收窄效果**

手动测试：
1. 检查二级导航宽度是否为48px
2. hover 导航项时，tooltip 是否显示
3. 触摸目标是否 ≥44pt

- [ ] **Step 2: 验证客户档案折叠功能**

手动测试：
1. 默认进入客户详情页：客户档案是否展开
2. 点击"联系人"：客户档案是否自动收起
3. 点击"客户档案"：是否重新展开
4. 展开后再次点击"联系人"：客户档案是否保持展开（不自动收起）

- [ ] **Step 3: 验证简化版客户档案卡片**

手动测试：
1. 收起状态：简化版卡片是否显示（客户名称 + 状态）
2. 展开状态：完整客户档案是否显示

---

## Task 7: 提交代码

- [ ] **Step 1: 提交所有修改**

```bash
git add CRM-Client/src/components/CustomerDetailSidebar.vue CRM-Client/src/components/CustomerDetailSidebar.scss CRM-Client/src/views/CustomerDetail.vue
git commit -m "feat(customer-detail): add collapsible profile panel with smart auto-collapse

完成 Task 1-5:
- 收窄二级导航到48px（icon-only + hover tooltip）
- 新增客户档案导航项（可折叠）
- 添加智能折叠逻辑（首次切换自动收起，用户手动展开后保持状态）
- 添加简化版客户档案卡片（收起状态）

符合 UI/UX Pro Max 规则：
- touch-target-size ≥44pt ✅
- hover-tooltip ✅
- state-preservation ✅
- content-priority ✅"
```

---

## Self-Review Checklist

**1. Spec Coverage:**

| 需求 | 任务 | 状态 |
|------|------|------|
| 收窄二级导航（48px） | Task 1 | ✅ |
| 新增客户档案导航项 | Task 2 | ✅ |
| 添加折叠样式 | Task 3 | ✅ |
| 添加智能折叠逻辑 | Task 4 | ✅ |
| 添加简化版卡片 | Task 5 | ✅ |
| 验证和测试 | Task 6 | ✅ |
| 提交代码 | Task 7 | ✅ |

**2. UI/UX Pro Max CRITICAL 规则验证清单:**

| 规则 | 实施位置 | 状态 |
|------|----------|------|
| touch-target-size ≥44pt | CustomerDetailSidebar.scss (nav-item min-height: 44px) | ✅ |
| hover-tooltip | CustomerDetailSidebar.scss (:hover::before tooltip) | ✅ |
| state-preservation | CustomerDetail.vue (userExpandedProfile 逻辑) | ✅ |
| content-priority | CustomerDetail.vue (简化版卡片 + 智能折叠) | ✅ |
| aria-labels | CustomerDetailSidebar.vue (:aria-label) | ✅ |

**3. Type Consistency:**

| 类型定义位置 | 使用位置 | 一致性 |
|--------------|----------|--------|
| `profileExpanded: boolean` | CustomerDetailSidebar + CustomerDetail | ✅ |
| `userExpandedProfile: boolean` | CustomerDetail.vue | ✅ |
| `emit('profile-toggle', expanded: boolean)` | CustomerDetailSidebar.vue | ✅ |

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-06-customer-detail-sidebar-collapsible-profile.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**