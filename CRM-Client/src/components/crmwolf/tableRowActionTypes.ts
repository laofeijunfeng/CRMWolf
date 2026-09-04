import type { Component } from 'vue'

/**
 * Stable business semantics for row actions.
 *
 * Labels remain user-facing copy and are intentionally not used as the
 * canonical identity once a page has migrated to an id.
 */
export type TableRowActionId =
  | 'detail'
  | 'preview'
  | 'edit'
  | 'create-opportunity'
  | 'claim'
  | 'assign'
  | 'transfer'
  | 'return-to-public-pool'
  | 'advance-stage'
  | 'convert-to-customer'
  | 'submit'
  | 'submit-approval'
  | 'withdraw'
  | 'approve'
  | 'reject'
  | 'remind'
  | 'resubmit'
  | 'complete'
  | 'complete-confirmation'
  | 'defer'
  | 'keep-open'
  | 'cancel'
  | 'close-tracking'
  | 'win'
  | 'lose'
  | 'invalidate'
  | 'mark-invalid'
  | 'download'
  | 'confirm-payment'
  | 'issue-invoice'
  | 'delete'
  | 'add-follow-up'

export type TableRowActionRisk = 'normal' | 'state-transition' | 'destructive' | 'approval'

export type TableRowActionResultType =
  | 'none'
  | 'entity-updated'
  | 'status-changed'
  | 'entity-created'
  | 'entity-deleted'

export interface ActionConfig {
  label: string
  handler: (row: Record<string, unknown>) => void
  /** 稳定业务语义 ID；迁移期可缺省，缺省时回退到 label。 */
  id?: TableRowActionId
  visible?: boolean
  disabled?: boolean
  icon?: Component
  destructive?: boolean
  separator?: boolean
  /** 桌面列表中优先显示的主操作；最多展示两个，其余进入更多菜单 */
  desktopPrimary?: boolean
  /** 详情语义的动作由 DataTable 的详情入口承载，不重复投影到桌面操作区 */
  kind?: 'detail' | 'standard'
  /** 禁用时向用户解释原因，同时供按钮、菜单和读屏使用 */
  disabledReason?: string | undefined
  /** 用于主次投影和分组的业务风险；destructive 字段继续兼容旧页面。 */
  risk?: TableRowActionRisk
  /** 该动作完成后页面需要同步的读模型类型。 */
  resultType?: TableRowActionResultType
}
