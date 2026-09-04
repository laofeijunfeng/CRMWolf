/**
 * 页面动作收尾契约。
 *
 * 这是前端 UI 层的结果模型，不等同于后端 API 响应。列表页、详情 Sheet
 * 和表单通过它传递“做了什么、作用于谁、结果是否确定以及是否需要同步”。
 */
export type ActionOutcomeStatus = 'success' | 'unknown'

export type ActionEntityType =
  | 'customer'
  | 'follow-up-task'
  | 'opportunity'
  | 'contract'
  | 'payment-plan'
  | 'payment-record'
  | 'invoice'
  | 'approval-task'

export type NextActionKind =
  | 'view-detail'
  | 'continue'
  | 'submit-approval'
  | 'create-follow-up'
  | 'open-related'

export interface NextAction {
  id: string
  label: string
  kind: NextActionKind
  priority?: 'primary' | 'secondary'
  run: () => void | Promise<void>
}

export interface ActionOutcome {
  status: ActionOutcomeStatus
  entityType: ActionEntityType
  entityId: string | number
  action: string
  message: string
  nextActions?: NextAction[]
  recoveryAction?: 'query' | 'retry' | 'manual-confirm'
  stateSync?: 'synced' | 'pending-refresh' | 'refresh-failed'
  stateLabel?: string
}

/** 表单保存成功后传给父页面的最小结果。 */
export interface FormSuccessPayload {
  entityType: ActionEntityType
  entityId: string | number
  operation: 'create' | 'update'
  outcome: 'success'
  stateSyncRequested: boolean
}
