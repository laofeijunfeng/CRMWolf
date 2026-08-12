/* eslint-disable crmwolf/require-zod-schema */
import { z } from 'zod'
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


const NullableDateTimeSchema = z.string().datetime({ offset: true }).nullable().or(z.string().datetime().nullable())

export const FollowUpConfirmationCustomerSchema = z.object({
  id: z.string(),
  public_id: z.string(),
  name: z.string(),
  account_name: z.string()
})

export const FollowUpConfirmationTaskSchema = z.object({
  id: z.string(),
  public_id: z.string(),
  title: z.string(),
  description: z.string().nullable().optional(),
  status: z.string(),
  due_at: NullableDateTimeSchema,
  due_at_text: z.string().nullable().optional(),
  source_type: z.string().nullable().optional(),
  source_public_id: z.string().nullable().optional()
})

export const FollowUpConfirmationCaseSchema = z.object({
  id: z.string(),
  public_id: z.string(),
  status: z.string(),
  question_text: z.string(),
  suggested_action: z.string(),
  owner_id: z.string(),
  creator_id: z.string(),
  customer: FollowUpConfirmationCustomerSchema.nullable(),
  task: FollowUpConfirmationTaskSchema.nullable(),
  expires_at: NullableDateTimeSchema,
  prompt_count: z.number().int().nonnegative(),
  last_prompted_at: NullableDateTimeSchema,
  unresolved_reply_count: z.number().int().nonnegative(),
  last_unresolved_reply_text: z.string().nullable(),
  last_unresolved_reply_at: NullableDateTimeSchema,
  resolved_action: z.string().nullable(),
  resolved_due_at: NullableDateTimeSchema,
  resolved_due_at_text: z.string().nullable(),
  expired_at: NullableDateTimeSchema,
  application_status: z.string().nullable(),
  application_skip_reason: z.string().nullable(),
  applied_at: NullableDateTimeSchema,
  created_time: NullableDateTimeSchema
})

export const FollowUpConfirmationCaseListResponseSchema = z.object({
  items: z.array(FollowUpConfirmationCaseSchema),
  total: z.number().int().nonnegative(),
  skip: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  filters: z.object({
    status: z.string(),
    owner_scope: z.string()
  }),
  usage_policy: z.object({
    case_state_source: z.string().nullable().optional(),
    task_state_source: z.string().nullable().optional(),
    mutation_gate: z.string().nullable().optional(),
    rule: z.string()
  })
})

export const FollowUpConfirmationPendingCountResponseSchema = z.object({
  count: z.number().int().nonnegative()
})

const FollowUpConfirmationDecisionSchema = z.object({
  action: z.string(),
  confidence: z.number(),
  reason: z.string(),
  resolved: z.boolean(),
  proposed_due_at: NullableDateTimeSchema,
  proposed_due_at_text: z.string().nullable()
})

const FollowUpConfirmationApplicationSchema = z.object({
  status: z.string(),
  case_public_id: z.string().nullable(),
  task_public_id: z.string().nullable(),
  action: z.string().nullable(),
  skip_reason: z.string().nullable(),
  execution_results: z.array(z.object({
    status: z.string(),
    action: z.string(),
    task_public_id: z.string().nullable(),
    previous_status: z.string().nullable(),
    new_status: z.string().nullable(),
    skip_reason: z.string().nullable(),
    event_type: z.string().nullable(),
    payload_json: z.record(z.unknown()).nullable()
  }))
})

export const FollowUpConfirmationResolveResponseSchema = z.object({
  case: FollowUpConfirmationCaseSchema.nullable(),
  decision: FollowUpConfirmationDecisionSchema,
  application: FollowUpConfirmationApplicationSchema,
  assistant_follow_up_prompt: z.string().nullable(),
  usage_policy: z.object({
    case_state_source: z.string().nullable().optional(),
    task_state_source: z.string().nullable().optional(),
    mutation_gate: z.string().nullable().optional(),
    rule: z.string()
  })
})

export type FollowUpConfirmationCase = z.infer<typeof FollowUpConfirmationCaseSchema>
export type FollowUpConfirmationCaseListResponse = z.infer<typeof FollowUpConfirmationCaseListResponseSchema>
export type FollowUpConfirmationResolveResponse = z.infer<typeof FollowUpConfirmationResolveResponseSchema>

export interface FollowUpConfirmationCaseListParams {
  skip?: number
  limit?: number
}

export interface FollowUpConfirmationResolvePayload {
  reply_text: string
}

export const followUpConfirmationApi = {
  async list(params: FollowUpConfirmationCaseListParams = {}): Promise<FollowUpConfirmationCaseListResponse> {
    const raw = await request.get<unknown>('/v1/follow-up-tasks/confirmation-cases', { params })
    return FollowUpConfirmationCaseListResponseSchema.parse(raw)
  },

  async getPendingCount(): Promise<number> {
    const raw = await request.get<unknown>('/v1/follow-up-tasks/confirmation-cases/pending-count')
    return FollowUpConfirmationPendingCountResponseSchema.parse(raw).count
  },

  async resolve(
    caseId: string,
    payload: FollowUpConfirmationResolvePayload
  ): Promise<FollowUpConfirmationResolveResponse> {
    const raw = await request.post<unknown>(
      `/v1/follow-up-tasks/confirmation-cases/${caseId}/resolve`,
      payload
    )
    return FollowUpConfirmationResolveResponseSchema.parse(raw)
  }
}
