/* eslint-disable crmwolf/require-zod-schema */
import request from '@/utils/request'

export type FollowUpTaskStatus = 'OPEN' | 'COMPLETED' | 'CANCELLED' | string
export type FollowUpTaskStatusFilter = 'all' | 'open' | 'completed' | 'cancelled'
export type FollowUpTaskTransitionAction = 'complete' | 'cancel' | 'delay'

export interface FollowUpTaskCustomer {
  id: string
  public_id: string
  name: string
  account_name: string
}

export interface FollowUpTaskSourceActivity {
  customer?: FollowUpTaskCustomer | null
  activity_kind?: string | null
  title?: string | null
  summary?: string | null
  next_action?: string | null
  next_follow_time?: string | null
  occurred_at?: string | null
  owner_id?: string | null
  owner_info?: FollowUpTaskUser | null
}

export interface FollowUpTaskUser {
  id: string
  name: string
  avatar_url?: string | null
}

export interface FollowUpTaskItem {
  id: string
  public_id: string
  customer: FollowUpTaskCustomer | null
  owner_id: string
  owner_info?: FollowUpTaskUser | null
  creator_id: string
  creator_info?: FollowUpTaskUser | null
  title: string
  description?: string | null
  status: FollowUpTaskStatus
  due_at: string | null
  due_at_text?: string | null
  due_at_granularity?: string | null
  due_at_timezone?: string | null
  overdue_days?: number
  source_type?: string | null
  source_public_id?: string | null
  confidence?: number | null
  completed_at?: string | null
  cancelled_at?: string | null
  created_time?: string | null
  updated_time?: string | null
  semantic_evidence?: Record<string, unknown>[]
  source_activity?: FollowUpTaskSourceActivity | null
}

export interface FollowUpTaskListResponse {
  items: FollowUpTaskItem[]
  total: number
  filters?: Record<string, unknown>
  customer_summary?: Record<string, unknown>[]
}

export interface FollowUpTaskTransitionResponse {
  executed: boolean
  result: Record<string, unknown>
  task: FollowUpTaskItem
}

export interface FollowUpTaskListParams {
  status?: FollowUpTaskStatusFilter
  due_window?: string
  customer_id?: string
  owner_scope?: 'mine' | 'customer'
  limit?: number
}

export interface FollowUpTaskTransitionPayload {
  action: FollowUpTaskTransitionAction
  proposed_due_at?: string | null
  reason?: string | null
}

export const followUpTaskApi = {
  list(params: FollowUpTaskListParams = {}): Promise<FollowUpTaskListResponse> {
    return request.get<FollowUpTaskListResponse>('/v1/follow-up-tasks', { params })
  },

  getDetail(taskId: string): Promise<FollowUpTaskItem> {
    return request.get<FollowUpTaskItem>(`/v1/follow-up-tasks/${taskId}`)
  },

  transition(taskId: string, payload: FollowUpTaskTransitionPayload): Promise<FollowUpTaskTransitionResponse> {
    return request.post<FollowUpTaskTransitionResponse>(`/v1/follow-up-tasks/${taskId}/transition`, payload)
  },
}
