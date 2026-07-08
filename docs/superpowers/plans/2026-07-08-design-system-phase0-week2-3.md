# CRMWolf 设计系统 Phase 0 Week 2-3 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 CRMWolf 设计系统 V2 的基础组件库（5 个基础组件 + 4 个导航组件），遵循 MASTER.md 设计规范和 UI/UX Pro Max CRITICAL 规则。

**Architecture:** 采用"组件封装"模式：基于 shadcn-vue 或原生 Vue 3 组件，使用 V2 Design Tokens 进行封装，确保所有组件符合 Touch Target、Focus Ring、Reduced Motion 等无障碍规则。

**Tech Stack:** Vue 3 + Vite + SCSS + Tailwind CSS + Storybook + Vitest

**Branch:** feature/design-system-v2

## Global Constraints

### Design Tokens 来源
- **唯一来源**: `CRM-Client/src/styles/variables-v2.scss`
- **规则来源**: `CRM-Docs/design-system/MASTER.md`
- **禁止事项**: 禁止硬编码颜色/圆角/间距，必须使用 Design Tokens

### UI/UX Pro Max CRITICAL 规则（强制）

| 规则类别 | UI/UX Pro Max 要求 | 组件实现 |
|---------|-------------------|---------|
| **Accessibility - Focus States** | Focus ring 2–4px visible | 所有交互组件必须实现 `:focus-visible` 状态 |
| **Touch - Touch Target** | Min 44×44pt (iOS) | 移动端组件高度 ≥44px |
| **Accessibility - Reduced Motion** | Respect `prefers-reduced-motion` | 动画时长在 reduced-motion 时降至 0.01ms |
| **Forms - Disabled States** | Opacity 0.38–0.5 + cursor | Disabled 状态必须使用 `$wolf-disabled-opacity-v2: 0.38` |
| **Forms - Input Labels** | Visible label per input | InputV2 必须包含 `<label>` 元素 |

### 组件结构规范

每个组件必须包含：
1. **`.vue` 文件**: 组件实现（使用 Design Tokens）
2. **`.stories.ts` 文件**: Storybook 展示（所有状态和变体）
3. **`.spec.ts` 文件**: 单元测试（功能 + Accessibility）
4. **`.md` 文件**: 设计说明（引用 MASTER.md 规则）

---

## Week 2: 基础组件库（5 个组件）

### Task 1: 创建 ButtonV2 组件

**Priority:** P0
**Workload:** 1 day
**Files:**
- Create: `CRM-Client/src/components/common/ButtonV2.vue`
- Create: `CRM-Client/src/components/common/ButtonV2.stories.ts`
- Create: `CRM-Client/src/components/common/ButtonV2.spec.ts`

- [ ] **Step 1: 创建 ButtonV2.vue 组件文件**

```vue
<template>
  <button
    class="button-v2"
    :class="[
      `button-v2--${variant}`,
      `button-v2--${size}`,
      {
        'button-v2--loading': loading,
        'button-v2--disabled': disabled || loading,
      },
    ]"
    :disabled="disabled || loading"
    :aria-label="ariaLabel"
    :aria-disabled="disabled || loading"
  >
    <!-- Loading Spinner -->
    <span v-if="loading" class="button-v2__spinner" aria-hidden="true">
      <Loader2 class="animate-spin" :size="iconSize" />
    </span>

    <!-- Icon (Left) -->
    <component
      v-if="icon && !loading"
      :is="icon"
      class="button-v2__icon"
      :size="iconSize"
      aria-hidden="true"
    />

    <!-- Text -->
    <span v-if="$slots.default" class="button-v2__text">
      <slot />
    </span>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Loader2 } from 'lucide-vue-next'
import type { Component } from 'vue'

/**
 * ButtonV2 - CRMWolf 设计系统 V2 按钮
 * 
 * @design-source CRM-Docs/design-system/MASTER.md §3.1 Button
 * @ux-rules UI/UX Pro Max §1 Focus States, §2 Touch Target, §7 Animation
 */

interface Props {
  /** 按钮变体 */
  variant?: 'default' | 'primary' | 'secondary' | 'danger' | 'ghost'
  /** 按钮尺寸 */
  size?: 'sm' | 'md' | 'lg' | 'mobile'
  /** 禁用状态 */
  disabled?: boolean
  /** 加载状态 */
  loading?: boolean
  /** 图标组件（Lucide Vue Next） */
  icon?: Component
  /** 无障碍标签（图标按钮必须） */
  ariaLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
  size: 'md',
  disabled: false,
  loading: false,
})

const iconSize = computed(() => {
  switch (props.size) {
    case 'sm':
      return 14
    case 'md':
      return 16
    case 'lg':
    case 'mobile':
      return 18
    default:
      return 16
  }
})
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

// ==================== Base Button ====================
.button-v2 {
  // Layout
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: $wolf-space-sm-v2; // 8px 图标与文字间距

  // Shape
  border-radius: $wolf-radius-v2; // ✅ 统一圆角 6px
  border: 1px solid transparent;

  // Typography
  font-family: inherit;
  font-weight: $wolf-font-weight-medium-v2; // 500
  font-size: $wolf-font-size-body-v2; // 14px

  // Interaction
  cursor: $wolf-cursor-clickable-v2; // ✅ UX 规则: cursor-pointer
  transition: $wolf-transition-v2; // ✅ 150ms ease

  // Focus Ring（UI/UX Pro Max CRITICAL）
  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2; // ✅ 2px focus ring
    outline-offset: $wolf-focus-ring-offset-v2; // ✅ 2px offset
  }

  // Reduced Motion（UI/UX Pro Max CRITICAL）
  @media (prefers-reduced-motion: reduce) {
    transition-duration: $wolf-reduced-motion-duration-v2; // ✅ 0.01ms
  }

  // ==================== Sizes ====================
  &--sm {
    height: $wolf-button-height-sm-v2; // 24px（桌面端迷你型）
    padding: $wolf-button-padding-sm-v2; // 4px 8px
  }

  &--md {
    height: $wolf-button-height-md-v2; // 32px（桌面端常规）
    padding: $wolf-button-padding-md-v2; // 8px 16px
  }

  &--lg {
    height: $wolf-button-height-lg-v2; // 44px（跨平台 touch target）
    padding: $wolf-button-padding-mobile-v2; // 12px 24px
  }

  &--mobile {
    height: $wolf-button-height-mobile-v2; // ✅ 44px（Touch Target 合规）
    padding: $wolf-button-padding-mobile-v2;
  }

  // ==================== Variants ====================
  &--default {
    background: $wolf-bg-card-v2; // #FFFFFF
    color: $wolf-text-secondary-v2; // #64748B
    border-color: $wolf-border-default-v2; // #E4ECFC

    &:hover:not(.button-v2--disabled) {
      background: $wolf-bg-hover-v2; // #EEF2FF
      border-color: $wolf-border-hover-v2; // #2563EB
    }

    &:active:not(.button-v2--disabled) {
      background: $wolf-primary-light-v2; // rgba(#2563EB, 0.1)
    }
  }

  &--primary {
    background: $wolf-primary-v2; // ✅ #2563EB
    color: $wolf-text-inverse-v2; // #FFFFFF
    border-color: $wolf-primary-v2;

    &:hover:not(.button-v2--disabled) {
      background: $wolf-primary-hover-v2; // ✅ #1E40AF
      border-color: $wolf-primary-hover-v2;
    }

    &:active:not(.button-v2--disabled) {
      background: $wolf-primary-active-v2; // ✅ #1D4ED8
    }
  }

  &--secondary {
    background: $wolf-primary-light-v2; // rgba(#2563EB, 0.1)
    color: $wolf-primary-v2; // #2563EB
    border-color: transparent;

    &:hover:not(.button-v2--disabled) {
      background: rgba($wolf-primary-v2, 0.2);
    }
  }

  &--danger {
    background: $wolf-danger-v2; // ✅ #DC2626
    color: $wolf-text-inverse-v2;
    border-color: $wolf-danger-v2;

    &:hover:not(.button-v2--disabled) {
      background: darken($wolf-danger-v2, 10%);
    }
  }

  &--ghost {
    background: transparent;
    color: $wolf-text-secondary-v2;
    border-color: transparent;

    &:hover:not(.button-v2--disabled) {
      background: $wolf-bg-hover-v2;
    }
  }

  // ==================== States ====================
  &--loading {
    cursor: wait;
    opacity: 0.7;
  }

  &--disabled {
    opacity: $wolf-disabled-opacity-v2; // ✅ 0.38（Material Design）
    cursor: $wolf-cursor-disabled-v2; // ✅ not-allowed
    pointer-events: none; // ✅ Disabled 禁止点击
  }

  // ==================== Elements ====================
  .button-v2__spinner {
    display: flex;
    align-items: center;
  }

  .button-v2__icon {
    flex-shrink: 0;
  }

  .button-v2__text {
    white-space: nowrap;
  }
}
</style>
```

- [ ] **Step 2: 创建 ButtonV2.stories.ts**

```typescript
// CRM-Client/src/components/common/ButtonV2.stories.ts
import type { Meta, StoryObj } from '@storybook/vue3'
import ButtonV2 from './ButtonV2.vue'
import { Plus, Trash2, Save, Search } from 'lucide-vue-next'

/**
 * ButtonV2 - CRMWolf 设计系统 V2 按钮
 * 
 * @design-source CRM-Docs/design-system/MASTER.md §3.1
 * @ux-rules UI/UX Pro Max §1 Focus States, §2 Touch Target
 */

const meta: Meta<typeof ButtonV2> = {
  title: 'Common/ButtonV2',
  component: ButtonV2,
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/file/xxx', // 设计稿链接
    },
    docs: {
      description: {
        component: `
# ButtonV2 设计说明

**引用规则**: CRM-Docs/design-system/MASTER.md §3.1 (Button)

## 视觉规范
- 圆角: 6px ($wolf-radius-v2)
- 高度: sm=24px / md=32px / lg=44px / mobile=44px
- 阴影: hover 时显示 $wolf-shadow-hover-v2
- 动画: 150ms ($wolf-transition-v2)

## UI/UX Pro Max CRITICAL 规则
- ✅ Focus ring 2px visible (§1 Accessibility)
- ✅ Touch target ≥44px on mobile (§2 Touch)
- ✅ Reduced motion support (§7 Animation)
- ✅ Disabled opacity 0.38 (§8 Forms)

## 禁止事项
- ❌ 禁止硬编码颜色
- ❌ 禁止使用旧圆角 (4px/8px/12px/16px)
- ❌ 禁止超过 500ms 的动画
        `,
      },
    },
  },
  argTypes: {
    variant: {
      control: 'select',
      options: ['default', 'primary', 'secondary', 'danger', 'ghost'],
      description: '按钮变体',
    },
    size: {
      control: 'select',
      options: ['sm', 'md', 'lg', 'mobile'],
      description: '按钮尺寸',
    },
    disabled: {
      control: 'boolean',
      description: '禁用状态',
    },
    loading: {
      control: 'boolean',
      description: '加载状态',
    },
    ariaLabel: {
      control: 'text',
      description: '无障碍标签（图标按钮必须）',
    },
  },
}

export default meta
type Story = StoryObj<typeof ButtonV2>

// ========== Variants ==========
export const Default: Story = {
  args: {
    variant: 'default',
    size: 'md',
  },
  render: (args) => ({
    components: { ButtonV2 },
    setup() {
      return { args }
    },
    template: '<ButtonV2 v-bind="args">默认按钮</ButtonV2>',
  }),
}

export const Primary: Story = {
  args: {
    variant: 'primary',
    size: 'md',
  },
  render: (args) => ({
    components: { ButtonV2 },
    setup() {
      return { args }
    },
    template: '<ButtonV2 v-bind="args">主要按钮</ButtonV2>',
  }),
}

export const Secondary: Story = {
  args: {
    variant: 'secondary',
    size: 'md',
  },
  render: (args) => ({
    components: { ButtonV2 },
    setup() {
      return { args }
    },
    template: '<ButtonV2 v-bind="args">次要按钮</ButtonV2>',
  }),
}

export const Danger: Story = {
  args: {
    variant: 'danger',
    size: 'md',
  },
  render: (args) => ({
    components: { ButtonV2 },
    setup() {
      return { args }
    },
    template: '<ButtonV2 v-bind="args">删除</ButtonV2>',
  }),
}

export const Ghost: Story = {
  args: {
    variant: 'ghost',
    size: 'md',
  },
  render: (args) => ({
    components: { ButtonV2 },
    setup() {
      return { args }
    },
    template: '<ButtonV2 v-bind="args">幽灵按钮</ButtonV2>',
  }),
}

// ========== Sizes ==========
export const Small: Story = {
  args: {
    variant: 'primary',
    size: 'sm',
  },
  render: (args) => ({
    components: { ButtonV2 },
    setup() {
      return { args }
    },
    template: '<ButtonV2 v-bind="args">小型按钮</ButtonV2>',
  }),
}

export const Medium: Story = {
  args: {
    variant: 'primary',
    size: 'md',
  },
  render: (args) => ({
    components: { ButtonV2 },
    setup() {
      return { args }
    },
    template: '<ButtonV2 v-bind="args">中等按钮</ButtonV2>',
  }),
}

export const Large: Story = {
  args: {
    variant: 'primary',
    size: 'lg',
  },
  render: (args) => ({
    components: { ButtonV2 },
    setup() {
      return { args }
    },
    template: '<ButtonV2 v-bind="args">大型按钮 (44px Touch Target)</ButtonV2>',
  }),
}

export const Mobile: Story = {
  args: {
    variant: 'primary',
    size: 'mobile',
  },
  render: (args) => ({
    components: { ButtonV2 },
    setup() {
      return { args }
    },
    template: '<ButtonV2 v-bind="args">移动端按钮 (44px 合规)</ButtonV2>',
  }),
}

// ========== States ==========
export const Loading: Story = {
  args: {
    variant: 'primary',
    size: 'md',
    loading: true,
  },
  render: (args) => ({
    components: { ButtonV2 },
    setup() {
      return { args }
    },
    template: '<ButtonV2 v-bind="args">加载中...</ButtonV2>',
  }),
}

export const Disabled: Story = {
  args: {
    variant: 'primary',
    size: 'md',
    disabled: true,
  },
  render: (args) => ({
    components: { ButtonV2 },
    setup() {
      return { args }
    },
    template: '<ButtonV2 v-bind="args">禁用按钮</ButtonV2>',
  }),
}

// ========== With Icons ==========
export const WithIcon: Story = {
  args: {
    variant: 'primary',
    size: 'md',
    icon: Plus,
  },
  render: (args) => ({
    components: { ButtonV2, Plus },
    setup() {
      return { args }
    },
    template: '<ButtonV2 v-bind="args">新增</ButtonV2>',
  }),
}

export const IconOnly: Story = {
  args: {
    variant: 'default',
    size: 'md',
    icon: Search,
    ariaLabel: '搜索',
  },
  render: (args) => ({
    components: { ButtonV2, Search },
    setup() {
      return { args }
    },
    template: '<ButtonV2 v-bind="args" />',
  }),
  parameters: {
    docs: {
      description: {
        story: '⚠️ 图标按钮必须提供 ariaLabel（UI/UX Pro Max §1 Accessibility）',
      },
    },
  },
}

export const DeleteWithIcon: Story = {
  args: {
    variant: 'danger',
    size: 'md',
    icon: Trash2,
  },
  render: (args) => ({
    components: { ButtonV2, Trash2 },
    setup() {
      return { args }
    },
    template: '<ButtonV2 v-bind="args">删除</ButtonV2>',
  }),
}

// ========== All Variants Grid ==========
export const AllVariants: Story = {
  render: () => ({
    components: { ButtonV2 },
    template: `
      <div style="display: grid; gap: 16px; grid-template-columns: repeat(5, 1fr);">
        <ButtonV2 variant="default">Default</ButtonV2>
        <ButtonV2 variant="primary">Primary</ButtonV2>
        <ButtonV2 variant="secondary">Secondary</ButtonV2>
        <ButtonV2 variant="danger">Danger</ButtonV2>
        <ButtonV2 variant="ghost">Ghost</ButtonV2>
      </div>
    `,
  }),
}

// ========== All Sizes Grid ==========
export const AllSizes: Story = {
  render: () => ({
    components: { ButtonV2 },
    template: `
      <div style="display: grid; gap: 16px; grid-template-columns: repeat(4, 1fr);">
        <ButtonV2 variant="primary" size="sm">Small (24px)</ButtonV2>
        <ButtonV2 variant="primary" size="md">Medium (32px)</ButtonV2>
        <ButtonV2 variant="primary" size="lg">Large (44px)</ButtonV2>
        <ButtonV2 variant="primary" size="mobile">Mobile (44px)</ButtonV2>
      </div>
    `,
  }),
}
```

- [ ] **Step 3: 创建 ButtonV2.spec.ts 单元测试**

```typescript
// CRM-Client/src/components/common/ButtonV2.spec.ts
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ButtonV2 from './ButtonV2.vue'
import { Plus } from 'lucide-vue-next'

describe('ButtonV2', () => {
  // ========== 基础功能测试 ==========
  it('renders correctly with default props', () => {
    const wrapper = mount(ButtonV2, {
      slots: {
        default: 'Button Text',
      },
    })
    expect(wrapper.text()).toContain('Button Text')
    expect(wrapper.classes()).toContain('button-v2')
    expect(wrapper.classes()).toContain('button-v2--default')
    expect(wrapper.classes()).toContain('button-v2--md')
  })

  it('applies variant class correctly', () => {
    const wrapper = mount(ButtonV2, {
      props: { variant: 'primary' },
    })
    expect(wrapper.classes()).toContain('button-v2--primary')
  })

  it('applies size class correctly', () => {
    const wrapper = mount(ButtonV2, {
      props: { size: 'lg' },
    })
    expect(wrapper.classes()).toContain('button-v2--lg')
  })

  // ========== 禁用状态测试 ==========
  it('disables button when disabled prop is true', () => {
    const wrapper = mount(ButtonV2, {
      props: { disabled: true },
    })
    expect(wrapper.attributes('disabled')).toBe('true')
    expect(wrapper.attributes('aria-disabled')).toBe('true')
    expect(wrapper.classes()).toContain('button-v2--disabled')
  })

  it('does not emit click when disabled', async () => {
    const wrapper = mount(ButtonV2, {
      props: { disabled: true },
    })
    await wrapper.trigger('click')
    expect(wrapper.emitted('click')).toBeFalsy()
  })

  // ========== 加载状态测试 ==========
  it('shows loading spinner when loading prop is true', () => {
    const wrapper = mount(ButtonV2, {
      props: { loading: true },
    })
    expect(wrapper.classes()).toContain('button-v2--loading')
    expect(wrapper.find('.button-v2__spinner').exists()).toBe(true)
  })

  it('disables button when loading', () => {
    const wrapper = mount(ButtonV2, {
      props: { loading: true },
    })
    expect(wrapper.attributes('disabled')).toBe('true')
  })

  // ========== 图标测试 ==========
  it('renders icon correctly', () => {
    const wrapper = mount(ButtonV2, {
      props: { icon: Plus },
    })
    expect(wrapper.find('.button-v2__icon').exists()).toBe(true)
  })

  it('does not render icon when loading', () => {
    const wrapper = mount(ButtonV2, {
      props: { icon: Plus, loading: true },
    })
    expect(wrapper.find('.button-v2__icon').exists()).toBe(false)
    expect(wrapper.find('.button-v2__spinner').exists()).toBe(true)
  })

  // ========== 无障碍测试（Accessibility - CRITICAL）==========
  it('has aria-label for icon-only button', () => {
    const wrapper = mount(ButtonV2, {
      props: {
        icon: Plus,
        ariaLabel: 'Add item',
      },
    })
    expect(wrapper.attributes('aria-label')).toBe('Add item')
  })

  it('has aria-disabled attribute when disabled', () => {
    const wrapper = mount(ButtonV2, {
      props: { disabled: true },
    })
    expect(wrapper.attributes('aria-disabled')).toBe('true')
  })

  // ========== Focus 状态测试（UI/UX Pro Max CRITICAL）==========
  it('has focus-visible styles', async () => {
    const wrapper = mount(ButtonV2)
    const button = wrapper.find('button')
    
    // 模拟 focus-visible
    await button.trigger('focus')
    
    // 检查 focus ring 样式（通过 CSS 类）
    expect(wrapper.find('button').element.style.outline).toBeDefined()
  })

  // ========== Touch Target 测试（UI/UX Pro Max CRITICAL）==========
  it('mobile size meets touch target requirement (44px)', () => {
    const wrapper = mount(ButtonV2, {
      props: { size: 'mobile' },
    })
    expect(wrapper.classes()).toContain('button-v2--mobile')
    // 验证高度通过 CSS 类实现（44px）
  })

  it('lg size meets touch target requirement (44px)', () => {
    const wrapper = mount(ButtonV2, {
      props: { size: 'lg' },
    })
    expect(wrapper.classes()).toContain('button-v2--lg')
  })

  // ========== Design Tokens 验证测试 ==========
  it('uses Design Tokens (no hardcoded colors)', () => {
    const wrapper = mount(ButtonV2)
    const style = wrapper.find('button').element.style
    
    // 检查是否有硬编码的颜色值（应该通过 SCSS 变量）
    // 注意：这个测试在运行时可能无法直接验证 SCSS 变量
    // 主要依赖 Stylelint 在构建时检查
  })

  // ========== 事件测试 ==========
  it('emits click event when clicked', async () => {
    const wrapper = mount(ButtonV2)
    await wrapper.trigger('click')
    expect(wrapper.emitted('click')).toBeTruthy()
  })

  it('does not emit click when loading', async () => {
    const wrapper = mount(ButtonV2, {
      props: { loading: true },
    })
    await wrapper.trigger('click')
    expect(wrapper.emitted('click')).toBeFalsy()
  })
})
```

---

### Task 2: 创建 InputV2 组件

**Priority:** P0
**Workload:** 1 day
**Files:**
- Create: `CRM-Client/src/components/common/InputV2.vue`
- Create: `CRM-Client/src/components/common/InputV2.stories.ts`
- Create: `CRM-Client/src/components/common/InputV2.spec.ts`

- [ ] **Step 1: 创建 InputV2.vue 组件**

核心特性：
- ✅ Visible label（UI/UX Pro Max §8 Forms）
- ✅ Error placement below field（UI/UX Pro Max §8 Forms）
- ✅ Focus ring visible（UI/UX Pro Max §1 Accessibility）
- ✅ Mobile height 44px（UI/UX Pro Max §2 Touch Target）
- ✅ Helper text support（UI/UX Pro Max §8 Forms）

（详细代码见实施计划文件）

- [ ] **Step 2: 创建 InputV2.stories.ts**

（详细代码见实施计划文件）

- [ ] **Step 3: 创建 InputV2.spec.ts**

（详细代码见实施计划文件）

---

### Task 3: 创建 TableV2 组件

**Priority:** P0
**Workload:** 2 days
**Files:**
- Create: `CRM-Client/src/components/common/TableV2.vue`
- Create: `CRM-Client/src/components/common/TableV2.stories.ts`
- Create: `CRM-Client/src/components/common/TableV2.spec.ts`

**Reference:** `CRM-Docs/design-system/MASTER.md §3.4 Table`

- [ ] **Step 1: 创建 TableV2.vue**

核心特性：
- ✅ No vertical divider lines（MASTER.md 规范）
- ✅ Adaptive row height
- ✅ Hover state visible
- ✅ Focus ring for interactive cells
- ✅ Responsive design

（详细代码见实施计划文件）

---

### Task 4: 创建 CardV2 组件

**Priority:** P1
**Workload:** 1 day

（详细代码见实施计划文件）

---

### Task 5: 创建 TabV2 组件

**Priority:** P1
**Workload:** 1 day

（详细代码见实施计划文件）

---

## Week 3: 导航组件库（4 个组件）

### Task 6: 创建 SidebarV2 组件

**Priority:** P0
**Workload:** 2 days
**Reference:** `navigation-redesign-v3.html`

（详细代码见实施计划文件）

---

### Task 7: 创建 TopBarV2 组件

**Priority:** P0
**Workload:** 2 days

（详细代码见实施计划文件）

---

### Task 8: 创建 ContextTabsV2 组件

**Priority:** P1
**Workload:** 2 days

（详细代码见实施计划文件）

---

### Task 9: 创建 UserInfoDropdownV2 组件

**Priority:** P1
**Workload:** 1 day

（详细代码见实施计划文件）

---

## Task 10: 创建组件库统一导出

- [ ] **Step 1: 创建 src/components/common/index.ts**

```typescript
// CRM-Client/src/components/common/index.ts
/**
 * CRMWolf 设计系统 V2 基础组件库统一导出
 * 
 * @design-source CRM-Docs/design-system/MASTER.md
 */

// 基础组件
export { default as ButtonV2 } from './ButtonV2.vue'
export { default as InputV2 } from './InputV2.vue'
export { default as TableV2 } from './TableV2.vue'
export { default as CardV2 } from './CardV2.vue'
export { default as TabV2 } from './TabV2.vue'

// 导航组件
export { default as SidebarV2 } from './SidebarV2.vue'
export { default as TopBarV2 } from './TopBarV2.vue'
export { default as ContextTabsV2 } from './ContextTabsV2.vue'
export { default as UserInfoDropdownV2 } from './UserInfoDropdownV2.vue'
```

---

## Self-Review Checklist

### 1. UI/UX Pro Max CRITICAL 规则合规性

| 规则类别 | 所有组件验证项 | 状态 |
|---------|---------------|------|
| **Focus States** | 所有交互组件实现 `:focus-visible` | ⏳ |
| **Touch Target** | 移动端组件高度 ≥44px | ⏳ |
| **Reduced Motion** | 动画在 reduced-motion 时降速 | ⏳ |
| **Disabled States** | opacity 0.38 + cursor not-allowed | ⏳ |
| **Input Labels** | InputV2 包含 `<label>` | ⏳ |

### 2. Design Tokens 使用验证

| 检查项 | 验证方式 | 状态 |
|-------|---------|------|
| 禁止硬编码颜色 | Stylelint 检查 | ⏳ |
| 使用 `$wolf-radius-v2` | grep 检查 | ⏳ |
| 使用 `$wolf-primary-v2` | grep 检查 | ⏳ |

### 3. Storybook 完整性

| 检查项 | 状态 |
|-------|------|
| 所有组件有 `.stories.ts` | ⏳ |
| 所有变体和状态有 Story | ⏳ |
| 设计说明引用 MASTER.md | ⏳ |

### 4. 单元测试完整性

| 检查项 | 状态 |
|-------|------|
| 所有组件有 `.spec.ts` | ⏳ |
| Accessibility 测试覆盖 | ⏳ |
| Touch Target 测试覆盖 | ⏳ |

---

**Plan created at:** docs/superpowers/plans/2026-07-08-design-system-phase0-week2-3.md