/**
 * ApprovalStatusBadge Stories（C-DSG-1 唯一状态徽章）
 *
 * 展示 4 态：PENDING（待审批/审批中 琥珀）/ APPROVED（已通过 绿）/ REJECTED
 * （已驳回 红）/ CANCELLED（已撤回 灰）。颜色取 $wolf-approval-* token，图标
 * + 文字 + aria-label 三重指示，颜色非唯一信号（WCAG AA）。
 *
 * 注：项目当前未安装 Storybook 运行时；本文件遵循 COMPONENTS.md「共享组件必须
 * 配 .stories.ts」约定，作为 props 文档与未来接入 Storybook 时的入口。
 */
import ApprovalStatusBadge from './ApprovalStatusBadge.vue'
import type { ApprovalStatus } from '@/schemas/approvalGeneric'

interface StoryArgs {
  status: ApprovalStatus
  size?: 'default' | 'small'
}

interface StoryMeta {
  title: string
  component: typeof ApprovalStatusBadge
  tags: string[]
}

const meta: StoryMeta = {
  title: 'Approval/ApprovalStatusBadge',
  component: ApprovalStatusBadge,
  tags: ['autodocs']
}

export default meta

interface Story {
  args: StoryArgs
}

const makeStory = (
  status: ApprovalStatus,
  size: 'default' | 'small' = 'default'
): Story => ({
  args: { status, size } satisfies StoryArgs
})

export const Pending = makeStory('PENDING')
export const Approved = makeStory('APPROVED')
export const Rejected = makeStory('REJECTED')
export const Cancelled = makeStory('CANCELLED')
export const PendingSmall = makeStory('PENDING', 'small')
