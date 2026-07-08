// CRM-Client/src/components/common/ButtonV2.stories.ts
import type { Meta, StoryObj } from '@storybook/vue3'
import ButtonV2 from './ButtonV2.vue'
import { Plus, Trash2, Search } from 'lucide-vue-next'

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