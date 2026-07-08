/**
 * CardV2 Stories（CRMWolf Design System V2）
 *
 * 展示 CardV2 组件的所有状态和变体：
 * - 基础卡片
 * - 可点击卡片
 * - 禁用状态
 * - 边框变体
 * - 内边距变体（none/sm/md/lg）
 * - 阴影变体（none/sm/md/lg）
 * - 暗色模式
 *
 * 设计规范：UI/UX Pro Max
 * - §3.5 Card: Unified shadow, unified radius 6px
 * - §1 Accessibility: Focus states for interactive cards
 * - §2 Touch Target: Mobile-friendly padding
 * - §6 Typography & Color: Dark mode support
 * - §7 Animation: Reduced motion support
 *
 * 注：项目当前未安装 Storybook 运行时；本文件遵循 COMPONENTS.md
 * 「共享组件必须配 .stories.ts」约定，作为 props 文档与未来接入
 * Storybook 时的入口。
 */
import CardV2 from './CardV2.vue'

interface StoryArgs {
  title: string
  subtitle: string
  clickable: boolean
  disabled: boolean
  bordered: boolean
  padding: 'none' | 'sm' | 'md' | 'lg'
  shadow: 'none' | 'sm' | 'md' | 'lg'
  customClass: string
  ariaLabel: string
}

interface StoryMeta {
  title: string
  component: typeof CardV2
  tags: string[]
  argTypes: Record<string, unknown>
}

const meta: StoryMeta = {
  title: 'Layout/CardV2',
  component: CardV2,
  tags: ['autodocs'],
  argTypes: {
    title: {
      control: 'text',
      description: '卡片标题'
    },
    subtitle: {
      control: 'text',
      description: '卡片副标题'
    },
    clickable: {
      control: 'boolean',
      description: '是否可点击（显示 hover 效果）'
    },
    disabled: {
      control: 'boolean',
      description: '是否禁用（仅对可点击卡片生效）'
    },
    bordered: {
      control: 'boolean',
      description: '是否显示边框'
    },
    padding: {
      control: 'select',
      options: ['none', 'sm', 'md', 'lg'],
      description: '内边距大小（none: 0, sm: 12px, md: 16px, lg: 24px）'
    },
    shadow: {
      control: 'select',
      options: ['none', 'sm', 'md', 'lg'],
      description: '阴影变体'
    },
    customClass: {
      control: 'text',
      description: '自定义类名'
    },
    ariaLabel: {
      control: 'text',
      description: 'aria-label（用于可访问性）'
    }
  }
}

export default meta

interface Story {
  args: StoryArgs
}

const makeStory = (
  title: string,
  overrides: Partial<StoryArgs> = {}
): Story => ({
  args: {
    title,
    ...overrides
  } satisfies StoryArgs
})

// ========== 基础状态 ==========

export const Default: Story = makeStory('客户信息', {
  subtitle: '客户基本信息卡片'
})

export const WithoutSubtitle: Story = makeStory('简单卡片')

export const WithoutTitle: Story = makeStory('', {
  subtitle: '仅副标题卡片'
})

// ========== 内边距变体 ==========

export const PaddingNone: Story = makeStory('无内边距卡片', {
  padding: 'none',
  subtitle: 'padding: none'
})

export const PaddingSmall: Story = makeStory('小内边距卡片', {
  padding: 'sm',
  subtitle: 'padding: sm (12px)'
})

export const PaddingMedium: Story = makeStory('中等内边距卡片（默认）', {
  padding: 'md',
  subtitle: 'padding: md (16px)'
})

export const PaddingLarge: Story = makeStory('大内边距卡片', {
  padding: 'lg',
  subtitle: 'padding: lg (24px)'
})

// ========== 阴影变体 ==========

export const ShadowNone: Story = makeStory('无阴影卡片', {
  shadow: 'none',
  bordered: true,
  subtitle: 'shadow: none'
})

export const ShadowSmall: Story = makeStory('小阴影卡片（默认）', {
  shadow: 'sm',
  subtitle: 'shadow: sm'
})

export const ShadowMedium: Story = makeStory('中等阴影卡片', {
  shadow: 'md',
  subtitle: 'shadow: md'
})

export const ShadowLarge: Story = makeStory('大阴影卡片', {
  shadow: 'lg',
  subtitle: 'shadow: lg（弹窗级别）'
})

// ========== 边框变体 ==========

export const WithBorder: Story = makeStory('带边框卡片', {
  bordered: true,
  subtitle: 'bordered: true'
})

export const WithBorderNoShadow: Story = makeStory('边框卡片无阴影', {
  bordered: true,
  shadow: 'none',
  subtitle: 'bordered: true, shadow: none'
})

// ========== 可点击卡片 ==========

export const Clickable: Story = makeStory('可点击卡片', {
  clickable: true,
  subtitle: '点击查看详情'
})

export const ClickableWithCustomAction: Story = makeStory('点击触发操作', {
  clickable: true,
  subtitle: '点击执行操作'
})

// ========== 禁用状态 ==========

export const Disabled: Story = makeStory('禁用卡片', {
  clickable: true,
  disabled: true,
  subtitle: '此卡片已禁用'
})

export const DisabledClickable: Story = makeStory('禁用可点击卡片', {
  clickable: true,
  disabled: true,
  subtitle: '无法点击此卡片'
})

// ========== 组合场景 ==========

export const ClickableWithBorder: Story = makeStory('可点击边框卡片', {
  clickable: true,
  bordered: true,
  subtitle: '点击查看详情'
})

export const ClickableWithLargeShadow: Story = makeStory('可点击大阴影卡片', {
  clickable: true,
  shadow: 'lg',
  subtitle: '强调卡片'
})

// ========== 内容丰富示例 ==========

export const RichContent: Story = {
  args: {
    title: '客户详情',
    subtitle: '张三 - 销售经理'
  }
}

export const WithFooter: Story = {
  args: {
    title: '操作卡片',
    subtitle: '包含底部操作按钮'
  }
}

export const WithHeaderSlot: Story = {
  args: {
    title: '',
    subtitle: ''
  }
}

// ========== 暗色模式演示 ==========
// 注：暗色模式通过 prefers-color-scheme 自动切换

export const DarkModeDemo: Story = makeStory('暗色模式卡片', {
  subtitle: '切换系统暗色模式查看效果'
})

export const DarkModeClickable: Story = makeStory('暗色模式可点击卡片', {
  clickable: true,
  subtitle: '点击查看详情'
})

// ========== 响应式演示 ==========

export const ResponsivePadding: Story = makeStory('响应式内边距', {
  padding: 'md',
  subtitle: '桌面端 16px，移动端 12px'
})

// ========== 可访问性演示 ==========

export const AccessibleClickable: Story = makeStory('可访问性卡片', {
  clickable: true,
  ariaLabel: '查看客户详情',
  subtitle: '支持键盘导航（Tab + Enter）'
})

// ========== 性能优化演示 ==========

export const NoAnimationsForReducedMotion: Story = makeStory('减少动画模式', {
  clickable: true,
  subtitle: '在 prefers-reduced-motion: reduce 下无动画'
})