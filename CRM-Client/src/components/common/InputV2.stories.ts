/**
 * InputV2 Stories（CRMWolf Design System V2）
 *
 * 展示 InputV2 组件的所有状态和变体：
 * - 基础输入框
 * - 必填字段
 * - 错误状态
 * - 禁用状态
 * - 辅助说明
 * - 尺寸变体（桌面/移动端）
 * - 类型变体（text/password/email/number）
 *
 * 设计规范：UI/UX Pro Max
 * - §8 Forms: Visible label, error placement, helper text
 * - §1 Accessibility: Focus ring visible
 * - §2 Touch Target: Mobile height 44px
 *
 * 注：项目当前未安装 Storybook 运行时；本文件遵循 COMPONENTS.md
 * 「共享组件必须配 .stories.ts」约定，作为 props 文档与未来接入
 * Storybook 时的入口。
 */
import InputV2 from './InputV2.vue'

interface StoryArgs {
  modelValue: string | number
  label: string
  type?: 'text' | 'password' | 'email' | 'number' | 'tel' | 'url' | 'search'
  placeholder?: string
  helperText?: string
  error?: string
  disabled?: boolean
  readonly?: boolean
  required?: boolean
  maxlength?: number
  minlength?: number
  min?: number
  max?: number
  step?: number
  autofocus?: boolean
  autocomplete?: string
  inputId?: string
  size?: 'default' | 'large'
}

interface StoryMeta {
  title: string
  component: typeof InputV2
  tags: string[]
  argTypes: Record<string, unknown>
}

const meta: StoryMeta = {
  title: 'Form/InputV2',
  component: InputV2,
  tags: ['autodocs'],
  argTypes: {
    modelValue: {
      control: 'text',
      description: 'v-model 绑定值'
    },
    label: {
      control: 'text',
      description: '标签文本（必须可见）'
    },
    type: {
      control: 'select',
      options: ['text', 'password', 'email', 'number', 'tel', 'url', 'search'],
      description: '输入类型'
    },
    placeholder: {
      control: 'text',
      description: '占位符文本'
    },
    helperText: {
      control: 'text',
      description: '辅助说明文本'
    },
    error: {
      control: 'text',
      description: '错误信息'
    },
    disabled: {
      control: 'boolean',
      description: '是否禁用'
    },
    readonly: {
      control: 'boolean',
      description: '是否只读'
    },
    required: {
      control: 'boolean',
      description: '是否必填'
    },
    size: {
      control: 'select',
      options: ['default', 'large'],
      description: '尺寸变体（large 用于移动端 44px touch target）'
    }
  }
}

export default meta

interface Story {
  args: StoryArgs
}

const makeStory = (
  label: string,
  overrides: Partial<StoryArgs> = {}
): Story => ({
  args: {
    label,
    modelValue: '',
    ...overrides
  } satisfies StoryArgs
})

// ========== 基础状态 ==========

export const Default: Story = makeStory('用户名')

export const WithPlaceholder: Story = makeStory('用户名', {
  placeholder: '请输入用户名'
})

export const WithValue: Story = makeStory('用户名', {
  modelValue: 'zhang_san'
})

// ========== 必填字段 ==========

export const Required: Story = makeStory('用户名 *', {
  required: true,
  placeholder: '请输入用户名'
})

export const RequiredWithValue: Story = makeStory('用户名 *', {
  required: true,
  modelValue: 'zhang_san'
})

// ========== 错误状态 ==========

export const WithError: Story = makeStory('用户名', {
  error: '用户名不能为空',
  placeholder: '请输入用户名'
})

export const WithErrorAndHelper: Story = makeStory('邮箱', {
  helperText: '请输入有效的邮箱地址',
  error: '邮箱格式不正确',
  placeholder: 'example@email.com'
})

// ========== 辅助说明 ==========

export const WithHelperText: Story = makeStory('密码', {
  type: 'password',
  helperText: '密码长度至少 8 位，包含字母和数字',
  placeholder: '请输入密码'
})

export const WithHelperTextAndRequired: Story = makeStory('密码 *', {
  type: 'password',
  required: true,
  helperText: '密码长度至少 8 位，包含字母和数字',
  placeholder: '请输入密码'
})

// ========== 禁用/只读状态 ==========

export const Disabled: Story = makeStory('用户名', {
  disabled: true,
  modelValue: 'zhang_san'
})

export const DisabledWithPlaceholder: Story = makeStory('用户名', {
  disabled: true,
  placeholder: '此字段已禁用'
})

export const Readonly: Story = makeStory('用户名', {
  readonly: true,
  modelValue: 'zhang_san'
})

// ========== 尺寸变体 ==========

export const LargeSize: Story = makeStory('用户名', {
  size: 'large',
  placeholder: '移动端 44px touch target'
})

export const LargeSizeWithError: Story = makeStory('用户名', {
  size: 'large',
  error: '用户名不能为空'
})

// ========== 类型变体 ==========

export const Password: Story = makeStory('密码', {
  type: 'password',
  placeholder: '请输入密码'
})

export const Email: Story = makeStory('邮箱', {
  type: 'email',
  placeholder: 'example@email.com',
  helperText: '用于接收系统通知'
})

export const NumberInput: Story = makeStory('数量', {
  type: 'number',
  modelValue: 10,
  min: 1,
  max: 100,
  step: 1
})

export const Tel: Story = makeStory('电话', {
  type: 'tel',
  placeholder: '13800138000'
})

export const Search: Story = makeStory('搜索', {
  type: 'search',
  placeholder: '搜索客户、商机...'
})

// ========== 长度限制 ==========

export const WithMaxLength: Story = makeStory('备注', {
  placeholder: '最多输入 100 个字符',
  maxlength: 100
})

export const WithMinLength: Story = makeStory('密码', {
  type: 'password',
  placeholder: '至少输入 8 个字符',
  minlength: 8
})

// ========== 组合场景 ==========

export const CompleteForm: Story = makeStory('邮箱地址 *', {
  type: 'email',
  required: true,
  placeholder: 'your@email.com',
  helperText: '用于接收重要通知和密码重置',
  modelValue: ''
})

export const CompleteFormWithError: Story = makeStory('邮箱地址 *', {
  type: 'email',
  required: true,
  placeholder: 'your@email.com',
  helperText: '用于接收重要通知和密码重置',
  error: '请输入有效的邮箱地址',
  modelValue: 'invalid-email'
})

// ========== 暗色模式演示 ==========
// 注：暗色模式通过 prefers-color-scheme 自动切换

export const DarkModeDemo: Story = makeStory('用户名', {
  placeholder: '切换系统暗色模式查看效果',
  helperText: '组件支持自动暗色模式适配'
})