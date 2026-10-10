import { z } from 'zod'

export const DraftFieldStatusSchema = z.enum(['MISSING', 'CANDIDATE', 'ACCEPTED', 'EXPLICITLY_NONE'])
export type DraftFieldStatus = z.infer<typeof DraftFieldStatusSchema>

export const DraftFieldSchema = z.object({
  status: DraftFieldStatusSchema,
  value: z.string().nullable().optional()
}).strict()
export type DraftField = z.infer<typeof DraftFieldSchema>

export const TaskDraftSchema = z.object({
  customer: DraftFieldSchema,
  content: DraftFieldSchema,
  next_action: DraftFieldSchema,
  next_follow_time: DraftFieldSchema,
  meeting_subject: DraftFieldSchema.optional(),
  participants: DraftFieldSchema.optional(),
  content_json: z.record(z.unknown()).optional(),
  source_segments: z.array(z.string()).optional(),
  source_records: z.array(z.object({
    segment_id: z.string(), turn_id: z.string().nullable(), recorded_at: z.string(),
    timezone: z.literal('Asia/Shanghai'), text: z.string()
  }).strict()).optional(),
  score_reason: z.string().nullable().optional(),
  score_detail: z.record(z.unknown()).optional(),
  quality_score: DraftFieldSchema.optional()
}).strict()
export type TaskDraft = z.infer<typeof TaskDraftSchema>
export const ActivityPreviewSchema = z.object({
  customer_name: z.string(),
  activity_kind: z.enum(['PHONE_FOLLOW_UP', 'WECHAT_FOLLOW_UP', 'EMAIL_FOLLOW_UP', 'VISIT_FOLLOW_UP', 'OTHER_FOLLOW_UP', 'ONLINE_MEETING', 'OFFLINE_MEETING']),
  title: z.string().nullable().optional(),
  summary: z.string().nullable().optional(),
  content_json: z.record(z.unknown()),
  source_content: z.string(),
  score: z.number().int(),
  score_reason: z.string(),
  next_action: z.string().nullable().optional(),
  next_follow_time: z.string().nullable().optional(),
  next_follow_time_text: z.string().nullable().optional(),
  next_follow_time_granularity: z.enum(['DATE', 'DATETIME', 'UNKNOWN']).optional()
}).strict()

export const ProposalKindSchema = z.enum([
  'customer_fact', 'follow_up_task_create', 'follow_up_task', 'opportunity_stage', 'opportunity_create'
])
export type ProposalKind = z.infer<typeof ProposalKindSchema>

export const ProposalCandidateSchema = z.object({
  kind: ProposalKindSchema,
  key: z.string().min(1),
  payload: z.record(z.unknown()),
  action_id: z.string().nullable().optional(),
  evidence_quote: z.string().min(1),
  activity_id: z.number().int(),
  customer_id: z.number().int(),
  source_revision: z.number().int(),
  due_date_granularity: z.enum(['DATE', 'DATETIME', 'UNKNOWN']).nullable().optional(),
  target_public_id: z.string().nullable().optional(),
  prior_status: z.string().nullable().optional(),
  task_owner_id: z.string().nullable().optional(),
  prior_stage_snapshot_id: z.number().int().nullable().optional(),
  prior_version: z.number().int().nullable().optional(),
  prior_fact_version: z.number().int().nullable().optional(),
  task_hash: z.string().nullable().optional()
}).strict().superRefine((candidate, ctx) => {
  if ((candidate.kind === 'follow_up_task' || candidate.kind === 'opportunity_stage')
    && (candidate.target_public_id === undefined || candidate.target_public_id === null || candidate.target_public_id === '')) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['target_public_id'], message: '现有对象提议缺少目标' })
  }
})

export const ConfirmationPayloadSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('activity_write'), preview: ActivityPreviewSchema }).strict(),
  z.object({ kind: z.literal('proposal'), proposal_kind: ProposalKindSchema, candidate: ProposalCandidateSchema }).strict()
]).superRefine((payload, ctx) => {
  if (payload.kind === 'proposal' && payload.proposal_kind !== payload.candidate.kind) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['candidate', 'kind'], message: '提议类型不一致' })
  }
})
export type ConfirmationPayload = z.infer<typeof ConfirmationPayloadSchema>
export type ProposalConfirmation = Extract<ConfirmationPayload, { kind: 'proposal' }>


export const TaskWaitingSchema = z.object({
  type: z.enum(['FIELD', 'CONFIRMATION', 'ACTIVITY_KIND', 'OBJECT_SELECTION']),
  field: z.string().nullable().optional(),
  question_id: z.string().min(1),
  prompt: z.string().min(1),
  action_id: z.string().min(1).nullable().optional(),
  expected_version: z.number().int().nonnegative().nullable().optional(),
  fingerprint: z.string().nullable().optional(),
  candidates: z.array(z.object({ id: z.string().min(1), account_name: z.string().min(1) }).strict()).optional(),
  confirmation_payload: ConfirmationPayloadSchema.nullable().optional()
}).strict().superRefine((waiting, ctx) => {
  const payload = waiting.confirmation_payload
  if (waiting.type !== 'CONFIRMATION') {
    if (payload != null) ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['confirmation_payload'], message: '非确认等待不能携带命令' })
    return
  }
  const field = payload?.kind === 'activity_write' ? 'activity_write' : payload?.kind === 'proposal' ? `proposal:${payload.proposal_kind}` : null
  if (field === null || waiting.field !== field) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['confirmation_payload'], message: '确认命令与等待字段不一致' })
  }
})
export type TaskWaiting = z.infer<typeof TaskWaitingSchema>

export const AssistantTaskStatusSchema = z.enum(['ACTIVE', 'COMPLETED', 'CANCELLED', 'FAILED'])
export type AssistantTaskStatus = z.infer<typeof AssistantTaskStatusSchema>

const CustomerActivityReceiptSchema = z.object({
  kind: z.literal('customer_activity'),
  public_id: z.string().min(1),
  customer_id: z.number().int().nullable().optional()
}).strict()

export const AssistantTurnStatusSchema = z.enum(['PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED'])

const AcceptedProposalReceiptSchema = z.object({
  kind: ProposalKindSchema,
  public_id: z.string().min(1),
  proposal_key: z.string().min(1)
}).strict()

const RefusedProposalReceiptSchema = z.object({
  kind: z.enum([
    'refused:customer_fact', 'refused:follow_up_task_create', 'refused:follow_up_task',
    'refused:opportunity_stage', 'refused:opportunity_create',
    'refused:opportunity'
  ]),
  proposal_key: z.string().min(1).optional()
}).strict()

export const CommittedReceiptSchema = z.union([
  CustomerActivityReceiptSchema, AcceptedProposalReceiptSchema, RefusedProposalReceiptSchema
])
export type CommittedReceipt = z.infer<typeof CommittedReceiptSchema>

export const AssistantTaskViewSchema = z.object({
  public_id: z.string().min(1),
  status: AssistantTaskStatusSchema,
  goal: z.string().min(1),
  activity_kind: z.string().nullable().optional(),
  draft: TaskDraftSchema,
  waiting: TaskWaitingSchema.nullable().optional(),
  committed: z.array(CommittedReceiptSchema),
  budget_steps: z.number().int().nonnegative(),
  budget_max_steps: z.number().int().positive(),
  version: z.number().int().nonnegative(),
  last_modified_time: z.string().nullable().optional(),
  processing_turn_id: z.string().min(1).nullable().optional(),
  processing_turn_status: AssistantTurnStatusSchema.nullable().optional(),
}).strict().superRefine((task, ctx) => {
  if ((task.processing_turn_id == null) !== (task.processing_turn_status == null)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['processing_turn_id'], message: '处理轮次 ID 和状态必须同时提供' })
  }
})
export type AssistantTaskView = z.infer<typeof AssistantTaskViewSchema>

export function parseAssistantTaskList(payload: unknown): { tasks: AssistantTaskView[]; skipped: number[] } {
  if (!Array.isArray(payload)) throw new Error('任务列表格式不正确')
  const tasks: AssistantTaskView[] = []
  const skipped: number[] = []
  payload.forEach((item, index) => {
    const parsed = AssistantTaskViewSchema.safeParse(item)
    if (parsed.success) tasks.push(parsed.data)
    else skipped.push(index)
  })
  return { tasks, skipped }
}

export const AssistantInputKindSchema = z.enum(['text', 'submit_field', 'confirm', 'cancel'])
export type AssistantInputKind = z.infer<typeof AssistantInputKindSchema>

export const SubmitInputResponseSchema = z.object({
  task: AssistantTaskViewSchema,
  message: z.string().min(1)
}).strict()
export type SubmitInputResponse = z.infer<typeof SubmitInputResponseSchema>
