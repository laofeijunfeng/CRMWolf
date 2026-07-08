// CRM-Client/src/components/common/TabV2.stories.ts
import type { Meta, StoryObj } from '@storybook/vue3'
import TabV2 from './TabV2.vue'
import type { TabItem } from './TabV2.vue'
import { User, Building2, FileText, Settings } from 'lucide-vue-next'

/**
 * TabV2 - CRMWolf 设计系统 V2 标签页组件
 *
 * @design-source CRM-Docs/design-system/MASTER.md §3.4 Tab
 * @ux-rules UI/UX Pro Max §1 Focus States, §9 Navigation Patterns
 */

interface TabV2Args {
  modelValue: string
  tabs: TabItem[]
  ariaLabel?: string
  panelIdPrefix?: string
}

interface RenderResult {
  components: Record<string, unknown>
  setup(): { args: TabV2Args }
  template: string
}

const meta: Meta<typeof TabV2> = {
  title: 'Common/TabV2',
  component: TabV2,
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/file/xxx', // 设计稿链接
    },
    docs: {
      description: {
        component: `
# TabV2 设计说明

**引用规则**: CRM-Docs/design-system/MASTER.md §3.4 (Tab)

## 视觉规范
- 激活指示条: 左侧 4px 宽度 ($wolf-primary-v2)
- 圆角: 6px ($wolf-radius-v2)
- 过渡动画: 150ms ($wolf-transition-v2)
- 容器背景: $wolf-bg-muted-v2 (#F1F5FD)
- 激活背景: $wolf-bg-card-v2 (#FFFFFF)

## 交互规范
- Hover: 显示 3px 指示条提示
- Active: 显示 4px 指示条
- Focus: 2px focus ring 可见
- 过渡: 150ms ease

## UI/UX Pro Max CRITICAL 规则
- ✅ Focus ring 2px visible (§1 Accessibility)
- ✅ Keyboard navigation (§9 Navigation)
- ✅ Reduced motion support (§7 Animation)
- ✅ ARIA attributes for screen readers

## 禁止事项
- ❌ 禁止硬编码颜色
- ❌ 禁止超过 500ms 的动画
- ❌ 禁止禁用 focus-visible
        `,
      },
    },
  },
  argTypes: {
    modelValue: {
      control: 'text',
      description: '当前激活的 Tab 值',
    },
    tabs: {
      control: 'object',
      description: 'Tab 列表配置',
    },
    ariaLabel: {
      control: 'text',
      description: '无障碍标签',
    },
  },
}

export default meta
type Story = StoryObj<typeof TabV2>

// ========== Default ==========
export const Default: Story = {
  args: {
    modelValue: 'info',
    tabs: [
      { value: 'info', label: '基本信息' },
      { value: 'contacts', label: '联系人' },
      { value: 'deals', label: '商机' },
      { value: 'files', label: '附件' },
    ],
  },
  render: (args: TabV2Args): RenderResult => ({
    components: { TabV2 },
    setup(): { args: TabV2Args } {
      return { args }
    },
    template: '<TabV2 v-bind="args" />',
  }),
}

// ========== With Icons ==========
export const WithIcons: Story = {
  args: {
    modelValue: 'info',
    tabs: [
      { value: 'info', label: '基本信息', icon: User },
      { value: 'company', label: '公司', icon: Building2 },
      { value: 'documents', label: '文档', icon: FileText },
      { value: 'settings', label: '设置', icon: Settings },
    ],
  },
  render: (args: TabV2Args): RenderResult => ({
    components: { TabV2 },
    setup(): { args: TabV2Args } {
      return { args }
    },
    template: '<TabV2 v-bind="args" />',
  }),
}

// ========== With Badges ==========
export const WithBadges: Story = {
  args: {
    modelValue: 'all',
    tabs: [
      { value: 'all', label: '全部' },
      { value: 'pending', label: '待处理', badge: 12 },
      { value: 'approved', label: '已通过', badge: 5, badgeVariant: 'success' },
      { value: 'rejected', label: '已驳回', badge: 2, badgeVariant: 'danger' },
    ],
  },
  render: (args: TabV2Args): RenderResult => ({
    components: { TabV2 },
    setup(): { args: TabV2Args } {
      return { args }
    },
    template: '<TabV2 v-bind="args" />',
  }),
}

// ========== With Icons And Badges ==========
export const WithIconsAndBadges: Story = {
  args: {
    modelValue: 'all',
    tabs: [
      { value: 'all', label: '全部', icon: FileText },
      { value: 'pending', label: '待处理', icon: User, badge: 12, badgeVariant: 'warning' },
      { value: 'approved', label: '已通过', icon: Building2, badge: 5, badgeVariant: 'success' },
    ],
  },
  render: (args: TabV2Args): RenderResult => ({
    components: { TabV2 },
    setup(): { args: TabV2Args } {
      return { args }
    },
    template: '<TabV2 v-bind="args" />',
  }),
}

// ========== Large Number Badge ==========
export const LargeNumberBadge: Story = {
  args: {
    modelValue: 'notifications',
    tabs: [
      { value: 'home', label: '首页' },
      { value: 'messages', label: '消息', badge: 99 },
      { value: 'notifications', label: '通知', badge: 150, badgeVariant: 'danger' },
    ],
  },
  render: (args: TabV2Args): RenderResult => ({
    components: { TabV2 },
    setup(): { args: TabV2Args } {
      return { args }
    },
    template: '<TabV2 v-bind="args" />',
  }),
}

// ========== Single Tab ==========
export const SingleTab: Story = {
  args: {
    modelValue: 'only',
    tabs: [{ value: 'only', label: '唯一选项' }],
  },
  render: (args: TabV2Args): RenderResult => ({
    components: { TabV2 },
    setup(): { args: TabV2Args } {
      return { args }
    },
    template: '<TabV2 v-bind="args" />',
  }),
}

// ========== Many Tabs ==========
export const ManyTabs: Story = {
  args: {
    modelValue: 'tab1',
    tabs: [
      { value: 'tab1', label: '选项一' },
      { value: 'tab2', label: '选项二' },
      { value: 'tab3', label: '选项三' },
      { value: 'tab4', label: '选项四' },
      { value: 'tab5', label: '选项五' },
      { value: 'tab6', label: '选项六' },
    ],
  },
  render: (args: TabV2Args): RenderResult => ({
    components: { TabV2 },
    setup(): { args: TabV2Args } {
      return { args }
    },
    template: '<TabV2 v-bind="args" />',
  }),
}

interface InteractiveDemoResult {
  components: Record<string, unknown>
  data(): { activeTab: string; tabs: TabItem[] }
  template: string
}

// ========== Interactive Demo ==========
export const InteractiveDemo: Story = {
  render: (): InteractiveDemoResult => ({
    components: { TabV2, User, Building2, FileText, Settings },
    data(): { activeTab: string; tabs: TabItem[] } {
      return {
        activeTab: 'info',
        tabs: [
          { value: 'info', label: '基本信息', icon: User },
          { value: 'company', label: '公司', icon: Building2, badge: 3 },
          { value: 'documents', label: '文档', icon: FileText },
          { value: 'settings', label: '设置', icon: Settings },
        ],
      }
    },
    template: `
      <div style="display: flex; flex-direction: column; gap: 16px;">
        <TabV2 v-model="activeTab" :tabs="tabs" />
        <div style="padding: 16px; background: #FFFFFF; border-radius: 6px; border: 1px solid #E4ECFC;">
          <p style="color: #64748B; font-size: 14px;">当前激活: {{ activeTab }}</p>
        </div>
      </div>
    `,
  }),
  parameters: {
    docs: {
      description: {
        story: '交互式演示：点击 Tab 可以切换激活状态',
      },
    },
  },
}