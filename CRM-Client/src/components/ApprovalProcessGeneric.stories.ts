/**
 * ApprovalProcessGeneric Stories（C-DSG-5 通用审批操作组件）
 *
 * 4 态对照：无审批单（草稿态 + 提交 CTA）/ 审批中（PENDING + 同意/驳回 或 撤回）/
 * 已驳回（REJECTED 终态）/ 已通过（APPROVED 终态）。状态徽章统一引用
 * ApprovalStatusBadge，颜色取 $wolf-approval-* token。
 *
 * 注：项目当前未安装 Storybook 运行时；本文件遵循 COMPONENTS.md「共享组件必须
 * 配 .stories.ts」约定，作为 props 文档与未来接入 Storybook 时的入口。组件
 * 内部通过 useApprovalStore() 调 actions，运行 Storybook 时需配 Pinia decorator
 * 与 mock API（此处仅给 args，运行时配置见 Storybook setup）。
 */
import ApprovalProcessGeneric from './ApprovalProcessGeneric.vue'
import type { EntityType } from '@/schemas/approvalGeneric'

interface StoryArgs {
  entityType: EntityType
  entityId: number
  canApprove: boolean
  isSubmitter: boolean
}

interface StoryMeta {
  title: string
  component: typeof ApprovalProcessGeneric
  tags: string[]
}

const meta: StoryMeta = {
  title: 'Approval/ApprovalProcessGeneric',
  component: ApprovalProcessGeneric,
  tags: ['autodocs']
}

export default meta

interface Story {
  args: StoryArgs
}

const makeStory = (args: StoryArgs): Story => ({ args })

// 草稿态：无审批单，提交人可见「提交审批」CTA
export const NoApproval = makeStory({
  entityType: 'INVOICE',
  entityId: 1,
  canApprove: false,
  isSubmitter: true
})

// 审批中：审批人侧，可见「同意 / 驳回」
export const PendingApprover = makeStory({
  entityType: 'PAYMENT',
  entityId: 5,
  canApprove: true,
  isSubmitter: false
})

// 审批中：提交人侧，可见「撤回审批」
export const PendingSubmitter = makeStory({
  entityType: 'INVOICE',
  entityId: 7,
  canApprove: false,
  isSubmitter: true
})

// 已驳回：终态，无操作按钮
export const Rejected = makeStory({
  entityType: 'CONTRACT',
  entityId: 12,
  canApprove: false,
  isSubmitter: true
})

// 已通过：终态，无操作按钮
export const Approved = makeStory({
  entityType: 'INVOICE',
  entityId: 20,
  canApprove: false,
  isSubmitter: false
})
