# CRMWolf 设计系统 - MASTER.md

**全局设计规则唯一来源**

---

## 一、设计原则（核心价值观）

### 1.1 四大核心原则

| 原则 | 说明 | 反模式 |
|------|------|---------|
| **极致克制** | 所有设计元素必须有明确用途，装饰性元素不超过5% | 过度装饰、无意义动画 |
| **柔和低噪** | 避免高饱和色彩，使用中性暖灰为主色调 | 高饱和蓝、荧光色 |
| **统一有序** | 所有组件使用统一的 Design Tokens | 硬编码颜色、圆角、间距 |
| **服务内容** | UI 不抢夺用户注意力，内容为王 | UI 元素比内容更显眼 |

### 1.2 设计优先级

```
功能完整性 > 可用性 > 性能 > 视觉一致性 > 装饰性
```

**决策标准**：
- 如果影响功能，必须优化
- 如果影响可用性，必须优化
- 如果仅影响视觉，可以权衡

### 1.3 移动端设计原则（UI/UX Pro Max）

| 原则 | 说明 | UI/UX Pro Max 规则 |
|------|------|-------------------|
| **Mobile-First** | 先设计移动端，再扩展到桌面端 | §5: `mobile-first` |
| **No Horizontal Scroll** | 移动端禁止横向滚动（页面主体） | §5: `horizontal-scroll` |
| **Touch Target ≥44px** | 所有可点击元素最小 44×44pt | §2: `touch-target-size` |
| **16px Body Text** | 移动端正文最小 16px（避免 iOS auto-zoom） | §5: `readable-font-size` |
| **Safe Areas** | 避开 notch、Dynamic Island、手势区域 | §2: `safe-area-awareness` |
| **Adaptive Navigation** | 大屏用 Sidebar，小屏用 Bottom Nav | §9: `adaptive-navigation` |
| **Dynamic Viewport** | 使用 `min(100vh, 100dvh)` 替代 `100vh` | §5: `viewport-units` |

**移动端禁止事项**：
- ❌ 固定 px 容器宽度（导致横向滚动）
- ❌ `user-scalable=no`（禁止缩放，违反 Accessibility）
- ❌ `100vh`（iOS Safari 地址栏展开时超出可视区域）
- ❌ Bottom Nav 超过 5 个项目
- ❌ Touch targets 放在 notch/Dynamic Island 下方

---

## 二、设计系统强制规范（CRITICAL）

> ⚠️ **违反以下规则将导致构建失败或设计系统混乱**

### 2.1 Design Token 强制规范

| 规则 | 强制要求 | 禁止行为 |
|------|----------|----------|
| **唯一来源** | 所有样式必须使用 `variables-v2.scss` 定义的变量 | 使用 `variables.scss`、硬编码颜色/间距/圆角 |
| **变量命名** | 必须使用 `-v2` 后缀的变量名 | 使用不带 `-v2` 后缀的变量名 |
| **导入规范** | `@use '@/styles/variables-v2.scss' as *;` | 导入其他 SCSS 变量文件 |

### 2.2 正确示例

```scss
// ✅ 正确：导入 V2 设计系统
@use '@/styles/variables-v2.scss' as *;

.card {
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-v2;
  padding: $wolf-space-md-v2;
  color: $wolf-text-primary-v2;
}
```

### 2.3 错误示例

```scss
// ❌ 错误：导入旧版 variables.scss
@use '@/styles/variables.scss' as *;

// ❌ 错误：使用不带 -v2 后缀的变量
.card {
  background: $wolf-bg-card;  // 缺少 -v2 后缀
  border-radius: 8px;          // 硬编码圆角
}
```

### 2.4 新建组件检查清单

创建新组件时，必须验证：

- [ ] 导入 `variables-v2.scss`（不是 `variables.scss`）
- [ ] 所有变量使用 `-v2` 后缀
- [ ] 无硬编码颜色（如 `#FFFFFF`、`rgb(0,0,0)`）
- [ ] 无硬编码间距（如 `8px`、`16px`）
- [ ] 无硬编码圆角（如 `6px`、`12px`）

### 2.5 违规后果

- **Sass 编译失败**：变量未定义错误
- **设计系统不一致**：违反"统一有序"原则
- **代码审查拒绝**：不符合强制规范

---

## 三、组件开发规范（CRITICAL）

> ⚠️ **强制规则：所有 UI 组件必须使用已安装的 shadcn-vue 组件，禁止自定义开发**

### 3.0 shadcn-vue 强制使用规则 ⚠️

> **铁律**：
> 1. **必须使用已安装的 shadcn-vue 组件**
> 2. **如果 shadcn-vue 没有所需组件，必须向用户确认后才能自定义**
> 3. **禁止任何形式的"自己写更好"、"临时方案"、"先自定义后优化"**

**强制流程**：
```
需要 UI 组件
    ↓
检查 shadcn-vue 是否已安装（src/components/ui/）
    ↓
    ├─ 有 → 直接使用
    │       ↓
    │   /shadcn-vue 查阅组件 API 和示例
    │       ↓
    │   在代码中使用
    │
    └─ 无 → 🛑 停止！必须向用户确认
            ↓
        "shadcn-vue 没有 [组件名] 组件，是否需要自定义开发？"
            ↓
        用户确认后才可继续
```

**禁止行为（零容忍）**：
- ❌ **自定义已存在于 shadcn-vue 的组件**（如 Button, Dialog, DropdownMenu 等）
- ❌ **"技术壁垒"、"特殊需求"、"临时方案"等借口**
- ❌ **凭记忆使用组件而不查阅文档**
- ❌ **复制网上代码而不遵循 shadcn-vue 规范**
- ❌ **"先自定义，后续再迁移到 shadcn-vue"**

### 3.1 shadcn-vue 唯一来源原则

| 规则 | 强制要求 | 零容忍行为 |
|------|----------|------------|
| **唯一来源** | 所有 UI 组件必须来自 `src/components/ui/` | 从其他库、网上复制、自定义开发 |
| **文档优先** | 使用前必须查阅 shadcn-vue 官方文档或使用 `/shadcn-vue` Skill | 凭记忆、猜测、推断使用 |
| **改造而非重写** | 基于 shadcn-vue 组件扩展功能、调整样式 | 完全重写、创建同名组件 |

**例外情况（必须用户确认）**：
- ✅ shadcn-vue 确实没有该组件（如业务特定组件）
- ✅ 用户明确批准自定义开发
- ⚠️ 未经用户确认的自定义开发 = 违反设计规范

### 3.2 正确示例

```vue
<!-- ✅ 正确：直接使用 shadcn-vue Button -->
<script setup>
import { Button } from '@/components/ui/button'
import { Plus } from 'lucide-vue-next'
</script>

<template>
  <Button size="lg">
    <Plus class="w-4 h-4 mr-2" />
    新建线索
  </Button>
</template>

<!-- ✅ 正确：基于 shadcn-vue Button 扩展（如需要 loading 状态） -->
<script setup>
import { Button } from '@/components/ui/button'
import { Loader2 } from 'lucide-vue-next'
</script>

<template>
  <Button :disabled="loading">
    <Loader2 v-if="loading" class="w-4 h-4 mr-2 animate-spin" />
    <slot v-else />
  </Button>
</template>
```

### 3.2 正确示例（续）

**基于 shadcn-vue 扩展 loading 状态**：
```vue
<script setup>
import { Button } from '@/components/ui/button'
import { Loader2 } from 'lucide-vue-next'
</script>

<template>
  <Button :disabled="loading">
    <Loader2 v-if="loading" class="w-4 h-4 mr-2 animate-spin" />
    <slot v-else />
  </Button>
</template>
```

### 3.3 违规后果

- **代码审查直接拒绝**：必须改为 shadcn-vue 方案
- **重复造轮子**：维护成本增加、无社区支持、无文档更新
- **组件库混乱**：多个同名组件并存（如 TouchButton vs Button）

### 3.4 已安装的 shadcn-vue 组件清单（2026-07-10）

| 类别 | 组件 |
|------|------|
| **核心组件** | Button, Input, Textarea, Label |
| **布局容器** | Card, Separator, ScrollArea, AspectRatio |
| **导航组件** | Tabs, Breadcrumb, NavigationMenu, DropdownMenu, Select |
| **数据录入** | Checkbox, Switch, RadioGroup, Select, Combobox, Slider |
| **反馈状态** | Badge, Progress, Skeleton, Avatar, Alert, Toast |
| **弹窗模态** | Dialog, AlertDialog, DropdownMenu, Popover, Sheet, Drawer, Tooltip, HoverCard |
| **命令菜单** | Command, ContextMenu, Menubar |
| **数据展示** | Table, Pagination |
| **折叠展开** | Accordion, Collapsible |
| **日历日期** | Calendar |
| **轮播** | Carousel |

> **总计**：41 个组件目录，136+ 个组件文件
> **导入方式**：统一从 `@/components/crmwolf` 导入

### 3.5 组件封装原则（CRITICAL）

> ⚠️ **最高优先级原则**：如有冲突，以此原则为准

**核心规则**：

| 规则 | 说明 |
|------|------|
| **严格按规范封装** | 所有使用 shadcn-vue 的组件，必须严格按照设计规范进行封装 |
| **样式改造** | 封装过程中，仅根据设计规范调整样式（颜色、圆角、间距等） |
| **保留原生动态效果** | 所有动态效果（动画、过渡、交互反馈）使用组件本身的动态效果，不做任何调整 |
| **冲突处理** | 当其他规则与本原则冲突时，以本原则为准 |

**实施要点**：

```vue
<!-- ✅ 正确：仅封装样式 -->
<script setup>
import { Button } from '@/components/ui/button'
</script>

<template>
  <!-- 仅样式改造，使用组件原生的 hover/active/focus 效果 -->
  <Button class="bg-primary text-white rounded-md">
    <slot />
  </Button>
</template>

<!-- ❌ 错误：修改动态效果 -->
<script setup>
import { Button } from '@/components/ui/button'
</script>

<template>
  <!-- ❌ 禁止修改过渡时长、动画曲线 -->
  <Button
    class="bg-primary"
    style="transition: all 0.3s ease"
  >
    <slot />
  </Button>
</template>
```

**为什么这样做**：

1. **一致性保证**：shadcn-vue 的动画经过精心设计和测试，保证跨浏览器一致性
2. **维护成本最低**：避免自定义动画带来的维护负担
3. **用户体验统一**：保持整个应用的交互体验一致性
4. **升级友好**：组件库升级时，不会因为自定义动画而产生冲突

**适用范围**：

- ✅ Button、Input、Table、Card 等所有 shadcn-vue 组件
- ✅ Dialog、DropdownMenu、Popover 等弹窗类组件
- ✅ Tabs、Breadcrumb 等导航类组件
- ✅ 所有未来新增的 shadcn-vue 组件

**设计规范冲突处理优先级**：

```
组件封装原则（本节） > 其他设计规则
```

示例：
- 如果某设计稿要求"按钮 hover 效果延迟 0.3s"，而 shadcn-vue Button 默认为 0.15s
- ❌ 禁止修改 Button 的 transition-duration
- ✅ 向设计师反馈：遵循 shadcn-vue 原生效果

### 3.6 AppLayout.vue 导航系统迁移示例（Phase 0 Week 3）

> **迁移完成日期**：2026-07-09

#### 迁移概览

| 组件 | Element Plus | shadcn-vue/V2 | 状态 |
|------|--------------|---------------|------|
| **Sidebar 菜单图标** | `@element-plus/icons-vue` | `lucide-vue-next` | ✅ 已替换 |
| **TopBar 按钮** | `el-button` | `Button` (shadcn-vue) | ✅ 已替换 |
| **团队切换对话框** | `el-dialog` | 自定义 Dropdown（向上展开） | ✅ 已移除并重构 |
| **Design Tokens** | `variables.scss` | `variables-v2.scss` | ✅ 已迁移 |

#### Lucide Icons 映射表

| Element Plus Icon | Lucide Icon | 用途 |
|-------------------|-------------|------|
| `Calendar` | `Calendar` | 我的日历 |
| `Flag` | `Flag` | 线索管理 |
| `OfficeBuilding` | `Building2` | 客户管理 |
| `TrendCharts` | `TrendingUp` | 商机管理 |
| `Document` | `FileText` | 合同管理 |
| `Money` | `Wallet` | 回款管理 |
| `Tickets` | `Receipt` | 发票管理 |
| `Settings` | `Settings` | 系统配置 |
| `ArrowLeft` | `ArrowLeft` | 返回按钮 |
| `ArrowDown` | `ChevronDown` | 下拉箭头 |
| `Check` | `Check` | 确认图标 |

#### Sidebar 导航菜单改造

**核心变更**：

1. **分组导航菜单**（销售流程/财务流程/管理工具）
2. **左侧指示条 Signature 元素**（hover 3px / active 4px）
3. **移除独立团队选择器**（节省 ~80px sidebar 高度）
4. **UserInfoDropdown 向上展开**（含团队切换）

**代码示例**：

```vue
<script setup lang="ts">
import { Calendar, Flag, Building2, TrendingUp, FileText, Wallet, Receipt, Settings } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
</script>

<template>
  <!-- 分组导航菜单 -->
  <nav class="sidebar-nav" role="navigation" aria-label="主导航">
    <div class="nav-section">
      <div class="nav-section-title">销售流程</div>
      <a class="nav-item" :class="{ active: currentPath === '/leads' }" role="menuitem">
        <component :is="Flag" class="nav-item-icon" aria-hidden="true" />
        <span class="nav-item-text">线索管理</span>
      </a>
    </div>
  </nav>

  <!-- 用户信息区域（含团队切换） -->
  <div class="sidebar-footer">
    <div class="user-info" role="button" aria-expanded="showUserDropdown">
      <div class="user-avatar">...</div>
      <div class="user-details">
        <div class="user-name">{{ userStore.userInfo?.name }}</div>
        <div class="user-team">{{ teamStore.currentTeam?.name }}</div>
      </div>
      <!-- Hover 下拉菜单 -->
      <Transition name="dropdown">
        <div v-if="showUserDropdown" class="user-dropdown">
          <div class="dropdown-header">切换团队</div>
          <a v-for="team in teamStore.teams" class="dropdown-item" @click="handleSwitchTeam(team.id)">
            <component :is="Building2" class="dropdown-icon" />
            <span>{{ team.name }}</span>
          </a>
        </div>
      </Transition>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

// 左侧指示条 Signature 元素
.nav-item::before {
  content: '';
  position: absolute;
  left: 0;
  width: 0;
  height: 16px;
  background: $wolf-primary-v2;
  border-radius: 0 2px 2px 0;
  transition: width 0.15s ease;
}

.nav-item:hover::before { width: 3px; }
.nav-item.active::before { width: 4px; }

// Touch targets 44×44px（UI/UX Pro Max §2）
.nav-item {
  height: 40px;  // 视觉高度
  min-height: 44px;  // Touch target
  border-radius: $wolf-radius-sm-v2;  // 6px
}
</style>
```

#### Accessibility 验收清单

| 检查项 | 规范来源 | 状态 |
|--------|---------|------|
| `role="navigation"` aria-label="主导航" | §1 aria-labels | ✅ |
| `role="menuitem"` aria-current="page" | §1 aria-labels | ✅ |
| `aria-expanded` on dropdown trigger | §1 aria-labels | ✅ |
| `focus-visible` outline 2px | §1 focus-states | ✅ |
| Touch targets ≥44px | §2 touch-target-size | ✅ |
| `prefers-reduced-motion` 支持 | §7 reduced-motion | ✅ |

### 3.7 API 错误处理规范（CRITICAL）

> ⚠️ **所有 API 错误处理必须使用统一的工具函数**

#### 消息提示规范

| 场景 | 工具函数 | 禁止行为 |
|------|---------|----------|
| **成功提示** | `toast.success()` | `ElMessage.success()` |
| **错误提示** | `handleApiError()` | 直接 `toast.error()`、`ElMessage.error()` |
| **确认对话框** | `confirmDialog()` | `ElMessageBox.confirm()` |

#### 工具函数位置

| 函数 | 路径 | 用途 |
|------|------|------|
| `handleApiError` | `@/utils/errorHandler.ts` | API 错误统一处理 |
| `confirmDialog` | `@/utils/confirmDialog.ts` | 确认对话框 |
| `confirmDelete` | `@/utils/confirmDialog.ts` | 删除确认快捷方法 |
| `confirmLogout` | `@/utils/confirmDialog.ts` | 退出登录确认 |
| `confirmSubmit` | `@/utils/confirmDialog.ts` | 提交确认快捷方法 |
| `toast` | `vue-sonner` | 轻量消息提示 |

#### handleApiError 使用示例

```typescript
import { handleApiError } from '@/utils/errorHandler'

// 基本用法
try {
  await api.deleteCustomer(id)
} catch (error) {
  handleApiError(error, '删除客户')
}

// 自定义错误消息
try {
  await authApi.login(email, password)
} catch (error) {
  handleApiError(error, '登录', {
    password: {
      title: '密码错误',
      description: '密码不正确，请检查输入或尝试重置密码',
    },
    email: {
      title: '邮箱未注册',
      description: '该邮箱尚未注册，请检查邮箱地址',
    },
  })
}
```

#### confirmDialog 使用示例

```typescript
import { confirmDialog, confirmDelete, confirmLogout } from '@/utils/confirmDialog'

// 基本用法
const confirmed = await confirmDialog('确定提交该表单？', '提交确认')
if (confirmed) {
  await submitForm()
}

// 删除确认快捷方法
const confirmed = await confirmDelete('客户张三')
if (confirmed) {
  await deleteCustomer(id)
}

// 退出登录确认
const confirmed = await confirmLogout()
if (confirmed) {
  await logout()
}
```

#### 迁移对照表

| Element Plus | V2 工具函数 | 说明 |
|--------------|-------------|------|
| `ElMessage.success()` | `toast.success()` | 成功提示 |
| `ElMessage.error()` | `handleApiError()` | 错误提示 |
| `ElMessage.warning()` | `toast.warning()` | 警告提示 |
| `ElMessage.info()` | `toast.info()` | 信息提示 |
| `ElMessageBox.confirm()` | `confirmDialog()` | 确认对话框 |
| `ElMessageBox.alert()` | `AlertDialog` (shadcn-vue) | 警告对话框 |

#### 设计依据

- **UI/UX Pro Max §8**: error-clarity + error-recovery
- **错误消息必须包含**: 原因 + 修复建议
- **确认对话框必须包含**: 清晰的标题 + 描述 + 确认/取消按钮

---

## 四、视觉风格规范

### 4.1 色彩系统（V2）

#### 主色调（现代蓝色）

| 角色 | Hex | CSS Variable | 使用场景 |
|------|-----|--------------|---------|
| **Primary** | `#2563EB` | `$wolf-primary-v2` | 主按钮、导航激活态、链接 |
| **Primary Hover** | `#1E40AF` | `$wolf-primary-hover-v2` | 主按钮 hover |
| **Primary Light** | `rgba(#2563EB, 0.1)` | `$wolf-primary-light-v2` | 浅底色、选中背景 |

#### 中性色（暖灰梯度）

| 角色 | Hex | 用途 |
|------|-----|------|
| **Background** | `#F8FAFC` | 页面画布底色 |
| **Card** | `#FFFFFF` | 卡片、表格背景 |
| **Sidebar** | `#FFFFFF` | 侧边栏背景 |
| **Hover** | `#EEF2FF` | hover 态背景、斑马纹 |
| **Muted** | `#F1F5FD` | 辅助背景、禁用态 |

#### 文字色

| 角色 | Hex | Contrast Ratio | 用途 |
|------|-----|----------------|------|
| **Primary Text** | `#0F172A` | 15:1 | 页面主标题、一级信息 |
| **Secondary Text** | `#64748B` | 4.5:1 | 正文、按钮文字 |
| **Tertiary Text** | `#94A3B8` | 3:1 | 辅助信息、未选中导航 |

#### 功能色（状态）

| 角色 | Hex | 使用场景 |
|------|-----|---------|
| **Success** | `#10B981` | 成功状态、成交标记 |
| **Warning** | `#F59E0B` | 警告状态、待审批 |
| **Danger** | `#DC2626` | 危险操作、驳回状态 |

#### 暗色模式（Dark Mode）

**UI/UX Pro Max 规则**：Dark mode uses desaturated / lighter tonal variants, not inverted colors

| 角色 | Token | Hex | 对比度 | 说明 |
|------|-------|-----|--------|------|
| **页面背景** | `$wolf-bg-page-dark-v2` | `#0F172A` | - | Slate-900 |
| **卡片背景** | `$wolf-bg-card-dark-v2` | `#1E293B` | - | Slate-800 |
| **Sidebar 背景** | `$wolf-bg-sidebar-dark-v2` | `#1E293B` | - | Slate-800 |
| **Hover 背景** | `$wolf-bg-hover-dark-v2` | `#334155` | - | Slate-700 |
| **主文字** | `$wolf-text-primary-dark-v2` | `#F8FAFC` | 15:1 | Slate-50 |
| **次文字** | `$wolf-text-secondary-dark-v2` | `#CBD5E1` | 4.5:1 | Slate-300 |
| **辅助文字** | `$wolf-text-tertiary-dark-v2` | `#94A3B8` | 3:1 | Slate-400 |

**暗色功能色（更亮）**：

| 角色 | Token | Hex | 说明 |
|------|-------|-----|------|
| **成功色** | `$wolf-success-dark-v2` | `#34D399` | 暗色模式更亮 |
| **警告色** | `$wolf-warning-dark-v2` | `#FBBF24` | 暗色模式更亮 |
| **危险色** | `$wolf-danger-dark-v2` | `#F87171` | 暗色模式更亮 |

**关键规则**：
- ✅ 暗色对比度必须独立验证（不假设亮色值可用）
- ✅ 使用 desaturated tonal variants（不直接反转颜色）
- ❌ 禁止黑→白直接反转

---

### 4.2 圆角系统（统一 6px）

| 场景 | Token | 值 |
|------|-------|-----|
| **主要圆角** | `$wolf-radius-v2` | `6px` |
| **小圆角** | `$wolf-radius-sm-v2` | `4px` |
| **大圆角** | `$wolf-radius-lg-v2` | `8px` |
| **完全圆角** | `$wolf-radius-full-v2` | `9999px` |

**应用规则**：
- ✅ 所有按钮：`6px`
- ✅ 所有卡片：`6px`
- ✅ 所有输入框：`6px`
- ✅ 所有下拉框：`6px`
- ❌ 禁止使用 `4px / 8px / 12px / 16px`（旧圆角）

---

### 4.3 间距系统（保留 8dp grid）

| 场景 | Token | 值 |
|------|-------|-----|
| **元素内间距** | `$wolf-space-xs-v2` | `4px` |
| **关联元素间距** | `$wolf-space-sm-v2` | `8px` |
| **模块内间距** | `$wolf-space-md-v2` | `12px` |
| **模块间间距** | `$wolf-space-lg-v2` | `16px` |

**应用规则**：
- ✅ 图标与文字间距：`8px`
- ✅ 按钮左右 padding：`16px`
- ✅ 卡片内边距：`16px`
- ✅ 页面安全边距：`24px`

---

### 4.4 阴影系统（中等强度）

| 场景 | Token | 值 |
|------|-------|-----|
| **卡片阴影** | `$wolf-shadow-card-v2` | `0 1px 3px rgba(0, 0, 0, 0.1)` |
| **Hover 阴影** | `$wolf-shadow-hover-v2` | `0 2px 8px rgba(0, 0, 0, 0.15)` |
| **下拉面板阴影** | `$wolf-shadow-dropdown-v2` | `0 -4px 12px rgba(0, 0, 0, 0.15)` |

---

### 4.5 过渡动画系统

| 场景 | Token | 值 |
|------|-------|-----|
| **标准过渡** | `$wolf-transition-v2` | `all 0.15s ease` |
| **Hover 过渡** | `$wolf-transition-hover-v2` | `all 0.2s ease` |

**应用规则**：
- ✅ 所有交互元素 hover：`150ms`
- ✅ 状态切换动画：`150-300ms`
- ❌ 禁止超过 `500ms` 的动画

---

## 五、组件设计规范

### 5.1 Button（按钮）

#### 视觉规范（桌面端）

| 属性 | Token | 值 | 说明 |
|------|-------|-----|------|
| **圆角** | `$wolf-radius-v2` | `6px` | 统一圆角 |
| **高度 sm** | `$wolf-button-height-sm-v2` | `24px` | 迷你型（文本按钮，仅桌面） |
| **高度 md** | `$wolf-button-height-md-v2` | `32px` | 常规型（桌面端） |
| **padding sm** | `$wolf-button-padding-sm-v2` | `4px 8px` | 上下 4px，左右 8px |
| **padding md** | `$wolf-button-padding-md-v2` | `8px 16px` | 上下 8px，左右 16px |

#### 视觉规范（移动端 - Touch Target 合规）

| 属性 | Token | 值 | UI/UX Pro Max 规则 |
|------|-------|-----|-------------------|
| **高度 mobile** | `$wolf-button-height-mobile-v2` | `44px` | §2: Touch Target ≥44pt |
| **高度 lg** | `$wolf-button-height-lg-v2` | `44px` | 跨平台 touch target |
| **padding mobile** | `$wolf-button-padding-mobile-v2` | `12px 24px` | 移动端更大 padding |

**关键规则**：
- ✅ 桌面端使用 `32px`（鼠标点击精度高）
- ✅ 移动端使用 `44px`（Touch Target 合规）
- ✅ 小于 44px 的图标使用 `hitSlop` 扩展点击区域

#### 状态定义

| 状态 | 背景 | 文字 | 边框 |
|------|------|------|------|
| **Default** | `#FFFFFF` | `#64748B` | `1px #E4ECFC` |
| **Primary** | `#2563EB` | `#FFFFFF` | 无 |
| **Danger** | `#DC2626` | `#FFFFFF` | 无 |
| **Hover** | `#EEF2FF` | `#2563EB` | `1px #2563EB` |
| **Disabled** | `#F1F5FD` | `#94A3B8` | 无 |

#### UX 规则

- ✅ **cursor: pointer**（所有可点击元素）
- ✅ **hover 状态可见**（150ms 过渡）
- ✅ **disabled 状态明确**（opacity: 0.5）
- ✅ **加载反馈**（禁用 + spinner）

---

### 5.2 Input（输入框）

#### 视觉规范（桌面端）

| 属性 | Token | 值 |
|------|-------|-----|
| **高度** | `$wolf-input-height-v2` | `32px` |
| **圆角** | `$wolf-radius-v2` | `6px` |
| **背景 default** | - | `#FFFFFF` |
| **背景 hover** | - | `#EEF2FF` |
| **背景 focus** | - | `#FFFFFF` |

#### 视觉规范（移动端 - Touch Target 合规）

| 属性 | Token | 值 | UI/UX Pro Max 规则 |
|------|-------|-----|-------------------|
| **高度 mobile** | `$wolf-input-height-mobile-v2` | `44px` | §8: `touch-friendly-input` |
| **padding mobile** | `$wolf-input-padding-mobile-v2` | `16px` | 更大 padding |
| **字号 mobile** | `$wolf-font-size-body-mobile-v2` | `16px` | §5: 避免 iOS auto-zoom |

**关键规则**：
- ✅ 移动端 input 高度 ≥ 44px
- ✅ 移动端 input 字号 = 16px（iOS Safari 不会 auto-zoom）
- ❌ 禁止移动端 input 字号 < 16px

#### 状态定义

| 状态 | 边框 | 阴影 |
|------|------|------|
| **Default** | `1px #E4ECFC` | 无 |
| **Hover** | `1px #2563EB` | 无 |
| **Focus** | `2px #2563EB` | `0 0 0 3px rgba(#2563EB, 0.1)` |
| **Error** | `2px #DC2626` | 无 |

#### UX 规则

- ✅ **Visible label**（必须有可见标签）
- ✅ **Error near field**（错误提示在输入框下方）
- ✅ **Focus ring**（2px 轮廓 + 外发光）
- ✅ **Helper text**（复杂输入框提供帮助文本）

---

### 5.3 Table（表格）

#### 视觉规范

| 属性 | 值 |
|------|-----|
| **行高** | `44px`（自适应，内容多时撑高） |
| **表头背景** | `#F1F5FD` |
| **表头文字** | `#64748B` |
| **表头字号** | `13px` |
| **表头字重** | `600` |
| **行分割线** | `#E4ECFC`（极淡） |
| **Hover 背景** | `#EEF2FF` |

#### 设计原则

- ✅ **无竖分割线**（极简风格）
- ✅ **自适应行高**（内容换行时撑高）
- ✅ **Hover 状态明显**（背景色变化）
- ❌ **禁止固定行高**（导致内容截断）

---

### 5.4 Card（卡片）

#### 视觉规范

| 属性 | 值 |
|------|-----|
| **圆角** | `6px` |
| **阴影** | `0 1px 3px rgba(0, 0, 0, 0.1)` |
| **边框** | `1px #E4ECFC` |
| **内边距** | `16px` |

#### 状态定义

| 状态 | 阴影 |
|------|------|
| **Default** | `0 1px 3px rgba(0, 0, 0, 0.1)` |
| **Hover** | `0 2px 8px rgba(0, 0, 0, 0.15)` |

---

### 5.5 Tab（标签栏）

#### 视觉规范

| 属性 | 值 |
|------|-----|
| **高度** | `48px` |
| **圆角** | `6px` |
| **字号** | `14px` |
| **字重 default** | `500` |
| **字重 active** | `600` |

#### 状态定义

| 状态 | 背景 | 文字 |
|------|------|------|
| **Default** | 透明 | `#64748B` |
| **Hover** | `#EEF2FF` | `#2563EB` |
| **Active** | `#F1F5FD` | `#2563EB` |

#### Active 指示条设计

- ✅ **左侧指示条**（`4px` 高亮条）
- ✅ **hover 时显示 3px**
- ✅ **active 时显示 4px**
- ✅ **过渡动画 150ms**

#### 常见 Tab 设计模式

| 模式 | 特点 | 适用场景 | 实现方式 |
|------|------|---------|---------|
| **Segmented Control** | 灰色容器 + 白色激活态 | 登录/注册、筛选器、切换视图 | 见下方规范 |
| **Underline Tabs** | 下划线指示器 | 内容页面导航、设置页面 | `border-bottom: 2px` |
| **Pill Tabs** | 胶囊形激活态 | 现代风格、强调活跃项 | `border-radius: 9999px` |

**选择标准**：
- ✅ **登录/注册页面** → Segmented Control（清晰层级）
- ✅ **内容页面** → Underline Tabs（简洁）
- ✅ **筛选器/切换器** → Segmented Control（紧凑）
- ❌ **禁止混用**（同一页面只能用一种模式）

---

### 5.6 Segmented Control（分段控制器）

#### 视觉规范

| 属性 | Token | 值 | 说明 |
|------|-------|-----|------|
| **容器高度** | - | `48px` | 包含 padding |
| **容器背景** | `$wolf-bg-muted-v2` | `#F1F5FD` | 灰色背景 |
| **容器 padding** | - | `4px` | 为内部元素留出呼吸空间 |
| **容器圆角** | `$wolf-radius-lg-v2` | `8px` | 外层容器圆角 |
| **Item 高度** | - | `40px` | 比容器小 8px |
| **Item 背景（active）** | `$wolf-bg-card-v2` | `#FFFFFF` | 白色背景 |
| **Item 圆角** | `$wolf-radius-v2` | `6px` | 内层元素圆角 |

#### 状态定义

| 状态 | 背景 | 文字 | 阴影 |
|------|------|------|------|
| **Default** | 透明 | `#64748B` | 无 |
| **Hover** | 透明 | `#2563EB` | 无 |
| **Active** | `#FFFFFF` | `#2563EB` | `0 1px 2px rgba(0,0,0,0.05)` |

#### 切换动画（UI/UX Pro Max §7）

| 属性 | 值 | 说明 |
|------|-----|------|
| **内容切换** | `150ms fade` | TabsContent 使用 opacity transition |
| **背景变化** | `150ms ease-out` | TabsTrigger 背景 transition |
| **文字颜色** | `150ms ease-out` | color transition |
| **Reduced motion** | CSS fallback | 支持 `prefers-reduced-motion` |

**实现代码**：

```vue
<!-- TabsList（容器） -->
<div class="p-1 bg-wolf-bg-muted rounded-wolf-lg">
  <button class="data-[state=active]:bg-wolf-bg-card data-[state=active]:shadow-sm transition-all duration-wolf-fast">
    标签
  </button>
</div>

<!-- TabsContent（内容） -->
<div class="data-[state=inactive]:opacity-0 data-[state=active]:opacity-100 transition-opacity duration-wolf-fast ease-out">
  内容
</div>
```

**关键规则**：
- ✅ 容器必须有 padding（`4px`），为 Item 留出呼吸空间
- ✅ Item 的 active 态必须有阴影（`shadow-sm`），增强层级
- ✅ 内容切换必须有 fade 动画（150ms）
- ✅ 必须支持 `prefers-reduced-motion`
- ❌ 禁止 Item 有边框（与容器背景冲突）

---

## 六、导航组件规范

### 6.1 Sidebar（左侧菜单）

#### 视觉规范

| 属性 | 值 |
|------|-----|
| **宽度** | `220px` |
| **背景** | `#FFFFFF` |
| **菜单项高度** | `40px` |
| **菜单项圆角** | `6px` |

#### 左侧指示条设计（核心视觉特征）

```scss
.nav-item {
  position: relative;
  
  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 0;  // default
    height: 16px;
    background: $wolf-primary-v2;
    border-radius: 0 2px 2px 0;
    transition: width 0.15s ease;
  }
  
  &:hover::before {
    width: 3px;  // hover 时显示 3px
  }
  
  &.active::before {
    width: 4px;  // active 时显示 4px
  }
}
```

#### 分组规范

| 分组 | 标题 | 示例 |
|------|------|------|
| **销售流程** | `销售流程` | 我的日历、线索、客户、商机 |
| **财务流程** | `财务流程` | 合同、回款、发票 |
| **管理工具** | `管理工具` | 采购、团队、系统 |

---

### 6.2 TopBar（顶部栏）

#### 视觉规范

| 属性 | 值 |
|------|-----|
| **高度** | `56px` |
| **背景** | `#FFFFFF` |
| **标题字号** | `20px` |
| **标题字重** | `600` |

#### 三段式布局

| 区域 | 内容 | 宽度 |
|------|------|------|
| **左侧** | 返回按钮 | `48px` |
| **中间** | 页面标题 | 自适应居中 |
| **右侧** | 操作按钮 + 审批铃铛 | 自适应 |

---

### 6.3 ContextTabs（上下文标签栏）

#### 视觉规范

| 属性 | 值 |
|------|-----|
| **高度** | `48px` |
| **背景** | `#FFFFFF` |

#### 动态切换规则

| 页面类型 | 标签内容 |
|---------|---------|
| **客户详情页** | 基本信息 / 跟进 / 联系人 / 商机 / 合同 / 回款 / 发票 / License |
| **回款管理页** | 回款计划 / 回款记录 |
| **合同详情页** | 基本信息 / 回款计划 |

---

### 6.4 UserInfoDropdown（用户下拉菜单）

#### 视觉规范

| 属性 | 值 |
|------|-----|
| **展开方向** | 向上（从底部展开） |
| **圆角** | `8px` |
| **阴影** | `0 -4px 12px rgba(0, 0, 0, 0.15)` |
| **过渡** | `0.2s ease` |

#### 内容分组

| 分组 | 内容 |
|------|------|
| **切换团队** | 所有团队列表（当前团队有 ✓ 标记） |
| **个人设置** | 个人资料、账户设置、退出登录 |

---

### 6.6 布局架构实现（AppLayout）

#### 架构设计

CRMWolf 采用 **"内部 Sticky TopBar"** 布局架构，与设计规范 HTML（navigation-redesign-v3.html）略有不同。

**设计规范架构（参考 HTML）：**
```
Sidebar (fixed, left: 0)
├── TopBar (fixed, top: 0, left: 220px)
└── MainContent (margin-top: 120px)  ← 通过 margin 推开
```

**CRMWolf 实际架构（AppLayout.vue）：**
```
AppLayout (flex)
├── Sidebar (fixed, left: 0, 220px)
└── MainContent (flex: 1)
    ├── TopBar (sticky, top: 0, height: 56px)  ← 在内部
    └── router-view (页面内容)
```

#### 核心差异说明

| 维度 | 设计规范 HTML | CRMWolf 实现 | 原因 |
|------|--------------|--------------|------|
| **TopBar 定位** | `fixed` 在外部 | `sticky` 在内部 | 更好的路由集成，TopBar 随页面滚动 |
| **间距处理** | `margin-top` 推开 | `padding-top` 创建间距 | 适配 sticky 定位模式 |
| **ContextTabs** | 有（48px） | 暂无 | 简化初始设计，后续可扩展 |

#### AppLayout 实现规范

```scss
// AppLayout.vue
.app-layout {
  display: flex;
  min-height: 100dvh;  // Dynamic viewport height
  background: $wolf-bg-page-v2;
}

.main-content {
  flex: 1;
  margin-left: $wolf-sidebar-width-v2;  // 220px
  overflow: auto;
  // 无 padding-top，让 TopBar 紧贴顶部
}

.top-bar {
  height: $wolf-topbar-height-v2;  // 56px
  position: sticky;
  top: 0;  // 紧贴顶部
  z-index: 90;
}
```

#### 页面级布局规范

所有页面组件应遵循以下布局模式：

```scss
// 例如：Leads.vue
.leads-page {
  padding: $wolf-page-padding-v2;  // 24px（顶部、左右、底部）
  background: $wolf-bg-page-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-section-gap-v2;  // 24px - 组件间距
  min-height: 0;  // 让 flexbox 控制高度
  flex: 1;  // 继承父容器高度
}
```

#### 间距层次

```
AppLayout.main-content (无 padding-top)
├── TopBar (56px, sticky, top: 0)  ← 紧贴顶部
└── 页面组件（如 Leads.vue）
    ├── padding-top: 24px  ← 与 TopBar 的间距
    ├── 左右 padding: 24px
    ├── 底部 padding: 24px
    ├── 组件 gap: 24px
    └── 内容区域
```

**总间距计算：**
- TopBar → 页面内容：**24px**（由页面 padding-top 提供）
- 页面内组件间距：**24px**（gap）

#### 实现注意事项

1. **禁止硬编码高度计算**
   ```scss
   // ❌ 错误：固定计算
   min-height: calc(100vh - 56px);

   // ✅ 正确：使用 flexbox
   min-height: 0;
   flex: 1;
   ```

2. **页面组件不需要处理 TopBar 间距**
   - AppLayout 已经提供系统级的 `padding-top: 16px`
   - 页面只需要自己的 `padding: 24px`

3. **高度管理原则**
   - AppLayout: 使用 `100dvh` (dynamic viewport height)
   - 页面组件: 使用 `min-height: 0` + `flex: 1`
   - DataTable: 使用固定高度 `calc(100vh - 200px)` 或自定义

#### ContextTabs 扩展预留

如果未来需要添加 ContextTabs（详情页二级导航）：

```scss
// 预留方案：在 TopBar 下方添加
.context-tabs {
  height: 48px;
  position: sticky;
  top: 56px;  // TopBar 下方
  z-index: 85;
}
```

**影响评估：**
- AppLayout 需调整 `padding-top`：`16px + 48px = 64px`
- 页面总间距：`64px + 24px = 88px`
- 需要更新所有页面组件

---

### 6.7 Bottom Navigation（移动端底部导航）

#### 视觉规范

| 属性 | Token | 值 | 说明 |
|------|-------|-----|------|
| **高度** | `$wolf-bottom-nav-height-v2` | `56px` | 固定底部栏高度 |
| **项目高度** | `$wolf-bottom-nav-item-height-v2` | `44px` | Touch Target 合规 |
| **最多项目** | `$wolf-bottom-nav-max-items-v2` | `5` | UI/UX Pro Max 规则 |
| **padding** | `$wolf-bottom-nav-padding-v2` | `8px` | 内边距 |

#### 设计原则（UI/UX Pro Max §9）

- ✅ **必须有 Icon + Text Label**（§9: `nav-label-icon`）
- ✅ **最多 5 个项目**（§9: `bottom-nav-limit`）
- ✅ **当前项高亮显示**（§9: `nav-state-active`）
- ❌ **禁止 Icon-only Bottom Nav**（损害可发现性）
- ❌ **禁止嵌套子导航**（§9: `bottom-nav-top-level`）

#### Bottom Nav 项目示例

| 序号 | Icon | Label | 说明 |
|------|------|-------|------|
| 1 | `calendar` | 日历 | 我的日历 |
| 2 | `users` | 客户 | 客户管理 |
| 3 | `opportunities` | 商机 | 商机管理 |
| 4 | `file-text` | 合同 | 合同管理 |
| 5 | `more-horizontal` | 更多 | Overflow Menu（线索/回款/发票/审批/设置） |

#### 响应式切换

```scss
.bottom-nav {
  display: none;  // 桌面端隐藏
  
  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    display: flex;  // <1024px 显示
    position: fixed;
    bottom: 0;
    padding-bottom: $wolf-safe-area-bottom-v2;  // Safe Area
  }
}
```

---

## 七、交互规范

### 7.1 Hover 状态

| 元素 | Hover 效果 | 过渡时间 |
|------|----------|---------|
| **按钮** | 背景 + 边框变化 | `150ms` |
| **菜单项** | 背景 + 左侧指示条 | `150ms` |
| **卡片** | 阴影增强 | `150ms` |
| **表格行** | 背景变色 | `150ms` |

### 7.2 Active 状态

| 元素 | Active 效果 |
|------|------------|
| **按钮** | 背景 + 边框 + 阴影 |
| **菜单项** | 背景 + 左侧指示条（4px） |
| **Tab** | 背景 + 文字 + 左侧指示条 |

### 7.3 Disabled 状态

| 属性 | 值 |
|------|-----|
| **opacity** | `0.5` |
| **cursor** | `not-allowed` |
| **交互** | 禁止点击 |

### 7.4 Loading 状态

| 场景 | 反馈 |
|------|------|
| **按钮** | 禁用 + spinner |
| **表格** | skeleton shimmer |
| **页面** | skeleton 屏幕 |

---

## 八、无障碍规范

### 8.1 对比度要求

| 类型 | 最小对比度 | Token |
|------|-----------|-------|
| **正常文字** | `4.5:1`（WCAG AA） | `$wolf-text-secondary-v2: #64748B` |
| **大文字** | `3:1` | `$wolf-text-tertiary-v2: #94A3B8` |
| **图标** | `3:1` | 所有 Icon 颜色 |

**暗色模式对比度（独立验证）**：

| 类型 | Token | 对比度 |
|------|-------|--------|
| **主文字** | `$wolf-text-primary-dark-v2: #F8FAFC` | 15:1 on `#0F172A` ✅ |
| **次文字** | `$wolf-text-secondary-dark-v2: #CBD5E1` | 4.5:1 on `#1E293B` ✅ |

### 8.2 Focus 状态（详细规范）

| Token | 值 | 说明 |
|-------|-----|------|
| `$wolf-focus-ring-width-v2` | `2px` | Focus ring 宽度（WCAG 2.4.7 合规） |
| `$wolf-focus-ring-color-v2` | `rgba(#2563EB, 0.5)` | 主色半透明 |
| `$wolf-focus-ring-offset-v2` | `2px` | 偏移（不覆盖元素边界） |

**Focus Ring 变体**：

| 类型 | Token | 值 | 应用场景 |
|------|-------|-----|---------|
| **强 focus** | `$wolf-focus-ring-width-strong-v2` | `3px` | 主要按钮、关键输入 |
| **弱 focus** | `$wolf-focus-ring-width-subtle-v2` | `1px` | 次要链接 |
| **Focus Shadow** | `$wolf-focus-shadow-v2` | `0 0 0 2px rgba(#2563EB, 0.3)` | Material Design 风格替代 |

**Focus 状态 CSS 示例**：

```scss
.button:focus-visible {
  outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
  outline-offset: $wolf-focus-ring-offset-v2;
}

// Material Design 风格（替代 outline）
.button:focus-visible {
  outline: none;
  box-shadow: $wolf-focus-shadow-v2;
}
```

**关键规则**：
- ✅ Focus ring 必须可见（WCAG 2.4.7 Focus Visible）
- ✅ Focus ring 与背景对比度 ≥ 3:1
- ❌ 禁止 `outline: none`（无替代方案）

### 8.3 Reduced Motion 支持

| Token | 值 | 说明 |
|-------|-----|------|
| `$wolf-reduced-motion-duration-v2` | `0.01ms` | `prefers-reduced-motion` 时的动画时长 |
| `$wolf-reduced-motion-delay-v2` | `0ms` | Reduced motion 延迟 |

**CSS 示例**：

```scss
.button {
  transition: all 150ms ease;
  
  @media (prefers-reduced-motion: reduce) {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
```

**关键规则**：
- ✅ 所有动画必须支持 `prefers-reduced-motion`
- ✅ Reduced motion 时保留 `0.01ms` 微动画（非完全禁用）
- ❌ 禁止忽略 `prefers-reduced-motion`

### 8.4 Screen Reader

- ✅ **aria-label**（图标按钮）
- ✅ **aria-live**（动态内容）
- ✅ **语义化标签**（button、label、nav）
- ✅ **Focus 管理**（错误后自动 focus 第一个错误字段）
- ✅ **Tab 顺序正确**（匹配视觉顺序）

### 8.5 Disabled 状态规范（Material Design）

| Token | 值 | 说明 |
|-------|-----|------|
| `$wolf-disabled-opacity-v2` | `0.38` | Material Design disabled opacity |
| `$wolf-disabled-opacity-light-v2` | `0.5` | 亮色模式（更柔和） |
| `$wolf-disabled-opacity-dark-v2` | `0.38` | 暗色模式 |
| `$wolf-cursor-disabled-v2` | `not-allowed` | Disabled cursor |

**关键规则**：
- ✅ Disabled 元素必须有语义属性（`disabled` 或 `aria-disabled="true"`）
- ✅ Disabled 元素必须有视觉区分（opacity + cursor）
- ❌ 禁止 Disabled 元素可点击（pointer-events: none 或 disabled 属性）

---

## 九、性能规范

### 9.1 动画性能

- ✅ **仅使用 transform/opacity**（避免 animating width/height/top/left）
- ✅ **避免 layout reflow**
- ✅ **requestAnimationFrame**（复杂动画）

### 9.2 响应时间

| 操作 | 最大延迟 |
|------|---------|
| **Tap 反馈** | `100ms` |
| **Hover 反馈** | `150ms` |
| **Loading 显示** | `300ms` |

---

## 十、响应式规范

### 10.1 断点系统

| 断点 | Token | 值 | 设备 | 导航模式 |
|------|-------|-----|------|---------|
| **xs** | `$wolf-breakpoint-xs-v2` | `375px` | 小手机（iPhone SE） | Bottom Nav |
| **sm** | `$wolf-breakpoint-sm-v2` | `768px` | 平板竖屏（iPad Mini） | Sidebar 可折叠 |
| **md** | `$wolf-breakpoint-md-v2` | `1024px` | 平板横屏 / 小桌面 | Sidebar 显示 |
| **lg** | `$wolf-breakpoint-lg-v2` | `1440px` | 大桌面 | Sidebar 固定 |

**断点切换规则**：
- **xs → sm**：Sidebar 从隐藏变为可折叠
- **sm → md**：Sidebar 从折叠变为固定显示，Bottom Nav 消失
- **md → lg**：容器宽度扩展，内容区最大 1200px

### 10.2 间距适配（Mobile-First）

| 断点 | Token | 页面边距 | 卡片间距 | 说明 |
|------|-------|---------|---------|------|
| **xs** | `$wolf-page-padding-mobile-v2` | `16px` | `12px` | 移动端更紧凑 |
| **sm** | - | `24px` | `16px` | 平板适中 |
| **md+** | `$wolf-page-padding-v2` | `24px` | `20px` | 桌面端舒适 |

### 10.3 移动端字体尺寸（iOS Auto-Zoom 防护）

| 场景 | Token | 值 | 说明 |
|------|-------|-----|------|
| **移动端正文** | `$wolf-font-size-body-mobile-v2` | `16px` | UI/UX Pro Max: 避免 iOS Safari auto-zoom |
| **移动端标题** | `$wolf-font-size-title-mobile-v2` | `18px` | 更醒目 |
| **移动端辅助** | `$wolf-font-size-caption-mobile-v2` | `14px` | 辅助信息 |

**关键规则**：
- ✅ 移动端 input/textarea 必须使用 `16px` 字号
- ❌ 禁止移动端使用 `< 16px` 字号（iOS Safari 会自动放大页面）

### 10.4 安全区域（Safe Areas）

| Token | 值 | 用途 |
|-------|-----|------|
| `$wolf-safe-area-top-v2` | `env(safe-area-inset-top, 0px)` | iOS notch / Dynamic Island |
| `$wolf-safe-area-bottom-v2` | `env(safe-area-inset-bottom, 0px)` | iOS Home Indicator / Android 手势区域 |
| `$wolf-safe-area-left-v2` | `env(safe-area-inset-left, 0px)` | 横屏左侧安全区域 |
| `$wolf-safe-area-right-v2` | `env(safe-area-inset-right, 0px)` | 横屏右侧安全区域 |

**应用场景**：
- ✅ TopBar padding-top: `$wolf-safe-area-top-v2`
- ✅ Bottom Nav padding-bottom: `$wolf-safe-area-bottom-v2`
- ❌ 禁止将 Touch Targets 放在安全区域下方

### 10.5 Viewport 单位（iOS Safari 适配）

| 场景 | Token | 值 | 说明 |
|------|-------|-----|------|
| **移动端高度** | `$wolf-viewport-height-mobile-v2` | `min(100vh, 100dvh)` | UI/UX Pro Max: 解决 iOS Safari 地址栏问题 |
| **桌面端高度** | `$wolf-viewport-height-desktop-v2` | `100vh` | 桌面端固定高度 |

**关键规则**：
- ❌ 禁止移动端使用 `100vh`（地址栏展开时超出可视区域）
- ✅ 使用 `min(100vh, 100dvh)` 或 `100svh`

### 10.6 响应式导航切换

| 断点 | 导航模式 | Sidebar | TopBar | Bottom Nav |
|------|---------|---------|--------|-----------|
| **≥1024px（桌面）** | Sidebar + TopBar | 220px 固定 | 56px，显示标题 | 隐藏 |
| **<1024px（移动）** | TopBar + Bottom Nav | 隐藏 | 56px，显示 hamburger + 标题 | 56px，最多 5 项目 |

**导航切换 CSS 示例**：

```scss
// Sidebar: 桌面端显示，移动端隐藏
.sidebar {
  display: block;  // 默认桌面端显示
  
  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    display: none;  // <1024px 隐藏
  }
}

// Bottom Nav: 移动端显示，桌面端隐藏
.bottom-nav {
  display: none;  // 默认桌面端隐藏
  
  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    display: flex;  // <1024px 显示
  }
}
```

### 10.7 Bottom Navigation 规范

| 属性 | Token | 值 | UI/UX Pro Max 规则 |
|------|-------|-----|-------------------|
| **高度** | `$wolf-bottom-nav-height-v2` | `56px` | 固定底部栏高度 |
| **最多项目** | `$wolf-bottom-nav-max-items-v2` | `5` | §9: `bottom-nav-limit` |
| **必须有** | - | Icon + Text Label | §9: `nav-label-icon` |
| **项目高度** | `$wolf-bottom-nav-item-height-v2` | `44px` | Touch Target 合规 |

**Bottom Nav 项目示例（销售流程）**：

| 项目 | Icon | Label | 说明 |
|------|------|-------|------|
| 1 | calendar | 日历 | 我的日历 |
| 2 | users | 客户 | 客户管理 |
| 3 | opportunities | 商机 | 商机管理 |
| 4 | file-text | 合同 | 合同管理 |
| 5 | more-horizontal | 更多 | 线索/回款/发票/审批/设置 |

**关键规则**：
- ✅ 必须同时显示 Icon 和 Text Label（§9: `nav-label-icon`）
- ✅ 最多 5 个项目，超出放入 "更多" Overflow Menu
- ❌ 禁止 Icon-only Bottom Nav（损害可发现性）

### 10.8 移动端表格适配

| 属性 | Token | 值 | 说明 |
|------|-------|-----|------|
| **最小宽度** | `$wolf-table-min-width-mobile-v2` | `100%` | 允许横向滚动 |
| **单元格 padding** | `$wolf-table-cell-padding-mobile-v2` | `8px 4px` | 更紧凑 |

**移动端表格策略**：
- ✅ 简化列数（仅显示核心信息）
- ✅ 允许表格横向滚动（页面主体禁止）
- ❌ 禁止固定 px 宽表格容器

### 10.9 移动端 Modal/Sheet

| 属性 | Token | 值 | UI/UX Pro Max 规则 |
|------|-------|-----|-------------------|
| **最大高度** | `$wolf-modal-height-mobile-v2` | `90vh` | 不占满屏幕 |
| **顶部圆角** | `$wolf-modal-radius-mobile-v2` | `8px` | 仅顶部圆角 |
| **展开方向** | - | 从底部向上 | §7: `modal-motion` |

**关键规则**：
- ✅ Modal 从底部滑入（§7: `modal-motion`）
- ✅ Sheet 可 swipe-down 关闭（§9: `modal-escape`）
- ✅ 有 unsaved changes 时确认关闭（§8: `sheet-dismiss-confirm`）

### 10.10 横向滚动约束

| Token | 值 | 应用场景 |
|-------|-----|---------|
| `$wolf-overflow-x-mobile-v2` | `hidden` | 页面主体禁止横向滚动 |
| `$wolf-overflow-x-allowed-v2` | `auto` | 表格、图片画廊允许横向滚动 |

**关键规则**：
- ✅ 页面主体 `overflow-x: hidden`
- ✅ 特定组件（表格、图片画廊）`overflow-x: auto`
- ❌ 禁止主要内容区域横向滚动

---

## 十一、禁止事项（Anti-Patterns）

### 11.1 通用禁止项

| 禁止项 | 原因 |
|--------|------|
| ❌ Emoji 作为图标 | 跨平台不一致、无法控制 |
| ❌ 硬编码颜色 | 违反 Design Tokens 原则 |
| ❌ 硬编码圆角 | 统一 6px 标准 |
| ❌ 超过 500ms 动画 | 用户感知慢 |
| ❌ 无 Focus 状态 | 无障碍不合规 |
| ❌ 旧圆角值 | 4px / 8px / 12px / 16px |
| ❌ **未定义的 Tailwind 类名** | Tailwind 不会编译，样式失效 |
| ❌ **未定义的 Design Token** | 违反设计系统统一原则 |

**开发原则（CRITICAL）**：

```typescript
// ❌ 错误：使用了未定义的类名
<div class="p-wolf-8 mb-wolf-8">
<img class="w-wolf-icon-sm h-wolf-icon-sm">

// ✅ 正确：使用已定义的 Token
<div class="p-wolf-lg pt-wolf-xl mb-wolf-xl">
<img class="w-wolf-icon-sm h-wolf-icon-sm">  // 必须在 tailwind.config.ts 中定义

// ✅ 正确：在 tailwind.config.ts 中定义
spacing: {
  'wolf-lg': '16px',
  'wolf-xl': '24px',
},
height: {
  'wolf-icon-sm': '20px',
}
```

**检查方法**：
- ✅ 使用 `npm run dev` 后检查浏览器开发工具，确认样式是否生效
- ✅ 使用 `grep -r "wolf-" src/ | grep -v "wolf-lg\|wolf-md\|wolf-xl"` 查找未定义的类名
- ✅ 参考 `tailwind.config.ts` 中的完整 Token 列表

### 11.2 移动端禁止项（UI/UX Pro Max）

| 禁止项 | 原因 | UI/UX Pro Max 规则 |
|--------|------|-------------------|
| ❌ 固定 px 容器宽度（如 `width: 1200px`） | 导致横向滚动 | §5: `horizontal-scroll` |
| ❌ `user-scalable=no`（禁止缩放） | 违反 Accessibility | §5: `viewport-meta` |
| ❌ `100vh`（移动端） | iOS Safari 地址栏展开时超出可视区域 | §5: `viewport-units` |
| ❌ Touch targets 在 notch/Dynamic Island 下方 | 无法点击 | §2: `safe-area-awareness` |
| ❌ Bottom Nav 超过 5 个项目 | 损害可发现性 | §9: `bottom-nav-limit` |
| ❌ Icon-only Bottom Nav | 损害可发现性 | §9: `nav-label-icon` |
| ❌ 移动端 input 字号 < 16px | iOS Safari auto-zoom | §5: `readable-font-size` |
| ❌ 移动端正文字号 < 16px | iOS Safari auto-zoom | §5: `readable-font-size` |
| ❌ 页面主体横向滚动 | 用户体验差 | §5: `horizontal-scroll` |

### 11.3 Stylelint 强制规则

```javascript
{
  'declaration-property-value-disallowed-list': {
    'color': ['/#[0-9a-fA-F]{3,6}/'],  // 禁止硬编码颜色
    'border-radius': ['/(4|8|12|16)px/']  // 禁止旧圆角
  }
}
```

---

## 十二、向后兼容

### 12.1 变量别名（过渡期）

```scss
// 保留旧变量名，指向新变量（向后兼容）
$wolf-primary: $wolf-primary-v2;
$wolf-radius-sm: $wolf-radius-v2;
```

### 12.2 迁移时间表

| 阶段 | 时间 | 操作 |
|------|------|------|
| **Phase 0** | 2-3周 | 建立新组件库 |
| **Phase 1** | 4-6周 | 渐进式迁移 |
| **Phase 2** | 1-2周 | 删除旧变量别名 |

---

## 十三、文档检索规则

### 13.1 层级检索

```
页面特定规则 > MASTER.md 规则
```

**检索流程**：
1. 查看特定页面文档（如 `pages/customer-detail.md`）
2. 如果存在，覆盖 MASTER.md 规则
3. 如果不存在，使用 MASTER.md 规则

### 13.2 页面文档命名

| 页面 | 文档路径 |
|------|---------|
| **客户详情** | `pages/customer-detail.md` |
| **合同详情** | `pages/contract-detail.md` |
| **审批中心** | `pages/approval-center.md` |

---

**版本：V2.2（强化 shadcn-vue 强制使用） | 最后更新：2026-07-10**

> **本次更新**：删除技术壁垒等妥协性描述，明确"用户确认"流程，零容忍自定义组件

---

## 附录：移动端设计 Token 快速索引

| 类别 | Token | 值 | 说明 |
|------|-------|-----|------|
| **断点 xs** | `$wolf-breakpoint-xs-v2` | `375px` | 小手机 |
| **断点 sm** | `$wolf-breakpoint-sm-v2` | `768px` | 平板竖屏 |
| **断点 md** | `$wolf-breakpoint-md-v2` | `1024px` | 平板横屏/小桌面 |
| **断点 lg** | `$wolf-breakpoint-lg-v2` | `1440px` | 大桌面 |
| **移动端正文** | `$wolf-font-size-body-mobile-v2` | `16px` | 避免 iOS auto-zoom |
| **安全区域 top** | `$wolf-safe-area-top-v2` | `env(safe-area-inset-top)` | notch/Dynamic Island |
| **安全区域 bottom** | `$wolf-safe-area-bottom-v2` | `env(safe-area-inset-bottom)` | 手势区域 |
| **Viewport 高度** | `$wolf-viewport-height-mobile-v2` | `min(100vh, 100dvh)` | iOS Safari 适配 |
| **Bottom Nav 高度** | `$wolf-bottom-nav-height-v2` | `56px` | 底部导航高度 |
| **Bottom Nav 最多项目** | `$wolf-bottom-nav-max-items-v2` | `5` | UI/UX Pro Max |
| **移动端按钮高度** | `$wolf-button-height-mobile-v2` | `44px` | Touch Target 合规 |
| **移动端输入框高度** | `$wolf-input-height-mobile-v2` | `44px` | Touch Target 合规 |
| **移动端页面边距** | `$wolf-page-padding-mobile-v2` | `16px` | 更紧凑 |
| **移动端卡片边距** | `$wolf-card-padding-mobile-v2` | `12px` | 更紧凑 |
| **Disabled opacity** | `$wolf-disabled-opacity-v2` | `0.38` | Material Design |
| **Focus ring width** | `$wolf-focus-ring-width-v2` | `2px` | WCAG 合规 |
| **Reduced motion** | `$wolf-reduced-motion-duration-v2` | `0.01ms` | Accessibility |
| **暗色页面背景** | `$wolf-bg-page-dark-v2` | `#0F172A` | Slate-900 |
| **暗色主文字** | `$wolf-text-primary-dark-v2` | `#F8FAFC` | 15:1 contrast |