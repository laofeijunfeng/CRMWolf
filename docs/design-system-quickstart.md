# CRMWolf 设计系统迁移 - 快速启动指南

## 🚀 立即开始（第一步）

### 步骤 1：创建新的 Design Tokens 文件

基于 `navigation-redesign-v3.html` 和 UI/UX Pro Max 生成的设计系统，创建新文件：

**文件位置**：`CRM-Client/src/styles/variables-v2.scss`

```scss
// ==================== CRMWolf 设计系统 V2 ====================
// 来源：navigation-redesign-v3.html + UI/UX Pro Max
// 生成：python3 skills/ui-ux-pro-max/scripts/search.py --design-system --persist

// ==================== 颜色系统（基于 v3 方案）====================

// 主色调（现代蓝色，更清晰）
$wolf-primary-v2: #2563EB;
$wolf-primary-hover-v2: #1E40AF;
$wolf-primary-active-v2: #1D4ED8;
$wolf-primary-light-v2: rgba(#2563EB, 0.1);

// 次要色
$wolf-secondary-v2: #3B82F6;

// 强调色（成功/成交）
$wolf-accent-v2: #059669;

// 背景
$wolf-bg-page-v2: #F8FAFC;
$wolf-bg-card-v2: #FFFFFF;
$wolf-bg-sidebar-v2: #FFFFFF;
$wolf-bg-hover-v2: #EEF2FF;
$wolf-bg-muted-v2: #F1F5FD;

// 文字
$wolf-text-primary-v2: #0F172A;
$wolf-text-secondary-v2: #64748B;
$wolf-text-tertiary-v2: #94A3B8;

// 边框
$wolf-border-default-v2: #E4ECFC;

// 功能色
$wolf-success-v2: #10B981;
$wolf-warning-v2: #F59E0B;
$wolf-danger-v2: #DC2626;

// ==================== 圆角系统（统一为 6px）====================

$wolf-radius-v2: 6px;        // 主要圆角（按钮、卡片、输入框）
$wolf-radius-sm-v2: 4px;     // 小圆角（标签、小型元素）
$wolf-radius-lg-v2: 8px;     // 大圆角（弹窗、对话框）
$wolf-radius-full-v2: 9999px; // 完全圆角（头像、徽章）

// ==================== 间距系统（保留 8dp grid）====================

$wolf-space-xs-v2: 4px;
$wolf-space-sm-v2: 8px;
$wolf-space-md-v2: 12px;
$wolf-space-lg-v2: 16px;
$wolf-space-xl-v2: 24px;

// ==================== 阴影系统（中等强度）====================

$wolf-shadow-card-v2: 0 1px 3px rgba(0, 0, 0, 0.1);
$wolf-shadow-hover-v2: 0 2px 8px rgba(0, 0, 0, 0.15);
$wolf-shadow-dropdown-v2: 0 -4px 12px rgba(0, 0, 0, 0.15);

// ==================== 过渡动画 ====================

$wolf-transition-v2: all 0.15s ease;  // 标准：150ms
$wolf-transition-hover-v2: all 0.2s ease; // hover：200ms

// ==================== 字体系统（保留现有）====================
// 建议：保留 IBM Plex Sans（技术感），不改为 Inter

$wolf-font-family-v2: $wolf-font-family;  // 继承现有系统字体栈
$wolf-font-display-v2: $wolf-font-display; // 继承 IBM Plex Sans

// ==================== 向后兼容（保留旧变量别名）====================

$wolf-primary: $wolf-primary-v2;
$wolf-primary-hover: $wolf-primary-hover-v2;
$wolf-radius-sm: $wolf-radius-v2;
```

---

### 步骤 2：创建第一个新组件 - Sidebar

基于 `navigation-redesign-v3.html` 的左侧菜单设计。

**文件位置**：`CRM-Client/src/components/navigation/SidebarV2.vue`

```vue
<template>
  <aside class="sidebar">
    <div class="sidebar-logo">
      <svg viewBox="0 0 32 32" fill="none">
        <rect width="32" height="32" rx="6" fill="#2563EB"/>
        <path d="M8 12L16 8L24 12V20L16 24L8 20V12Z" 
              stroke="white" stroke-width="2" fill="none"/>
      </svg>
      <span>CRMWolf</span>
    </div>

    <nav class="sidebar-nav">
      <div class="nav-section">
        <div class="nav-section-title">销售流程</div>
        
        <a 
          v-for="item in navItems"
          :key="item.key"
          class="nav-item"
          :class="{ active: activeNav === item.key }"
          @click="handleNavClick(item.key)"
        >
          <svg class="nav-icon">
            <component :is="item.icon" />
          </svg>
          <span class="nav-text">{{ item.label }}</span>
          <span v-if="item.badge" class="nav-badge">{{ item.badge }}</span>
        </a>
      </div>
    </nav>

    <div class="sidebar-footer">
      <div class="user-info" @click="showDropdown = true">
        <div class="user-avatar">张</div>
        <div class="user-details">
          <div class="user-name">张三</div>
          <div class="user-team">广东智通人才...</div>
        </div>
        
        <!-- 用户下拉菜单 -->
        <div v-if="showDropdown" class="user-dropdown">
          <!-- 团队切换 -->
          <div class="dropdown-section">切换团队</div>
          <div class="dropdown-item">广东智通人才连锁股份有限公司 ✓</div>
          <div class="dropdown-item">北京科技有限公司</div>
          
          <!-- 个人设置 -->
          <div class="dropdown-section">个人设置</div>
          <div class="dropdown-item">个人资料</div>
          <div class="dropdown-item">退出登录</div>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const activeNav = ref<string>('customers')
const showDropdown = ref<boolean>(false)

const navItems = [
  { key: 'calendar', label: '我的日历', badge: '3' },
  { key: 'leads', label: '线索管理' },
  { key: 'customers', label: '客户管理' },
  { key: 'opportunities', label: '商机管理' },
  { key: 'contracts', label: '合同管理', badge: '12' },
  { key: 'payments', label: '回款管理', badge: '5' },
  { key: 'invoices', label: '发票管理' }
]

function handleNavClick(key: string) {
  activeNav.value = key
  // TODO: 路由跳转
}
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.sidebar {
  width: 220px;
  background: $wolf-bg-sidebar-v2;
  border-right: 1px solid $wolf-border-default-v2;
  
  // ✅ 左侧指示条设计（核心视觉特征）
  .nav-item {
    position: relative;
    transition: $wolf-transition-v2;
    
    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 50%;
      transform: translateY(-50%);
      width: 0;
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
  
  // ✅ 统一圆角 6px
  .nav-item {
    border-radius: $wolf-radius-v2;
  }
  
  // ✅ 统一过渡动画 150ms
  .nav-item:hover {
    background: $wolf-bg-hover-v2;
    transition: $wolf-transition-v2;
  }
}
</style>
```

---

### 步骤 3：创建 Storybook 展示

**文件位置**：`CRM-Client/src/components/navigation/SidebarV2.stories.ts`

```typescript
import type { Meta, StoryObj } from '@storybook/vue3'
import SidebarV2 from './SidebarV2.vue'

const meta: Meta<typeof SidebarV2> = {
  title: 'Navigation/SidebarV2',
  component: SidebarV2,
  tags: ['autodocs'],
  parameters: {
    layout: 'fullscreen',
    docs: {
      description: {
        component: `
# SidebarV2 设计说明

**引用规则**：CRM-Docs/design-system/README.md

**核心视觉特征**：
- 左侧指示条设计（hover 3px，active 4px）
- 统一圆角 6px
- 过渡动画 150ms
- 颜色：Primary #2563EB

**交互规则**：
- 所有可点击元素 cursor: pointer
- Hover 状态：背景 #EEF2FF
- Active 状态：背景 #F1F5FD，指示条 4px

**无障碍**：
- 键盘导航支持（Tab 顺序）
- Focus ring 可见（2px outline）
        `
      }
    }
  }
}

export default meta
type Story = StoryObj<typeof SidebarV2>

export const Default: Story = {
  args: {
    // 默认参数
  }
}

export const WithActiveCalendar: Story = {
  args: {
    activeNav: 'calendar'
  }
}

export const WithTeamDropdown: Story = {
  args: {
    showDropdown: true
  }
}
```

---

### 步骤 4：配置 ESLint 强制使用新变量

**文件位置**：`CRM-Client/.eslintrc.design-system.js`

```javascript
module.exports = {
  rules: {
    // ✅ 禁止使用旧变量（强制使用新变量）
    'no-restricted-syntax': [
      'error',
      {
        // 禁止旧颜色变量
        selector: 'Identifier[name=/^wolf-primary$/]',
        message: '请使用 $wolf-primary-v2 (#2563EB) 替代旧变量'
      },
      {
        // 禁止旧圆角变量
        selector: 'Identifier[name=/^wolf-radius-/]',
        message: '请使用 $wolf-radius-v2 (统一 6px) 替代'
      }
    ]
  }
}
```

---

### 步骤 5：配置 Stylelint 禁止硬编码样式

**文件位置**：`CRM-Client/.stylelintrc.design-system.js`

```javascript
module.exports = {
  rules: {
    // ✅ 禁止直接写颜色 hex 值（强制使用 Design Tokens）
    'declaration-property-value-disallowed-list': {
      'color': [
        '/#[0-9a-fA-F]{3,6}/'  // 禁止：color: #2563EB
      ],
      '/.*/': [
        '/#2563EB/',  // 禁止硬编码主色
        '/#4A6FA5/',  // 禁止旧主色
        '/border-radius: (4|8|12|16)px/'  // 禁止旧圆角值
      ]
    },
    
    // ✅ 强制使用 Design Tokens
    'declaration-property-value-allowed-list': {
      'border-radius': [
        '$wolf-radius-v2',
        '$wolf-radius-sm-v2',
        '$wolf-radius-lg-v2'
      ]
    }
  }
}
```

---

## 📋 立即检查清单

完成上述 5 个步骤后，检查：

- ✅ `variables-v2.scss` 文件已创建
- ✅ `SidebarV2.vue` 组件已创建
- ✅ `SidebarV2.stories.ts` Storybook 已创建
- ✅ ESLint 配置已添加（强制使用新变量）
- ✅ Stylelint 配置已添加（禁止硬编码）

---

## 🎯 下一步（Phase 1）

完成上述步骤后，继续：

1. **创建 TopBarV2 组件**（顶部栏 + 审批铃铛）
2. **创建 ContextTabsV2 组件**（上下文标签栏）
3. **创建 UserInfoDropdownV2 组件**（用户下拉菜单）
4. **创建 ButtonV2 组件**（统一按钮样式）
5. **创建完整的设计系统文档**（design-system/crmwolf/MASTER.md）

---

## 💡 核心原则

**记住**：所有新组件必须遵守：

| 规则 | 说明 | 验证方式 |
|------|------|---------|
| **统一圆角** | 6px（`$wolf-radius-v2`） | Stylelint 检查 |
| **统一颜色** | Primary #2563EB（`$wolf-primary-v2`） | ESLint 检查 |
| **统一过渡** | 150ms（`$wolf-transition-v2`） | 代码审查 |
| **禁止硬编码** | 所有样式必须用 Design Tokens | Stylelint 检查 |
| **必须有 Storybook** | 每个组件有 `.stories.ts` | CI 检查 |

---

**开始时间**：现在！  
**预计完成 Phase 1**：2-3 周  
**总工期**：8-15 周  

---

## 📚 参考资料

- **设计系统文档**：`docs/design-system-migration-roadmap.md`
- **实施路线图**：`docs/design-system/crmwolf/MASTER.md`
- **UI/UX Pro Max**：`python3 skills/ui-ux-pro-max/scripts/search.py --design-system`
- **原型效果图**：`navigation-redesign-v3.html`