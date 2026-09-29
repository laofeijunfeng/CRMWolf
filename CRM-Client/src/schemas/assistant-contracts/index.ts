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
  score_reason: z.string().nullable().optional(),
  score_detail: z.record(z.unknown()).optional(),
  quality_score: DraftFieldSchema.optional()
}).strict()
export type TaskDraft = z.infer<typeof TaskDraftSchema>
export const ConfirmationPayloadSchema = z.object({
  customer_name: z.string(),
  activity_kind: z.string(),
  title: z.string().nullable().optional(),
  summary: z.string().nullable().optional(),
  content_json: z.unknown(),
  source_content: z.string(),
  score: z.number(),
  score_reason: z.string(),
  next_action: z.string().nullable().optional(),
  next_follow_time: z.string().nullable().optional()
}).passthrough()
export type ConfirmationPayload = z.infer<typeof ConfirmationPayloadSchema>


export const TaskWaitingSchema = z.object({
  type: z.enum(['FIELD', 'CONFIRMATION', 'ACTIVITY_KIND', 'OBJECT_SELECTION']),
  field: z.string().nullable().optional(),
  question_id: z.string().min(1),
  prompt: z.string().min(1),
  action_id: z.string().min(1).optional(),
  expected_version: z.number().int().nonnegative().optional(),
  fingerprint: z.string().nullable().optional(),
  candidates: z.array(z.object({ id: z.string().min(1), account_name: z.string().min(1) }).strict()).optional(),
  confirmation_payload: ConfirmationPayloadSchema.nullable().optional()
}).strict()
export type TaskWaiting = z.infer<typeof TaskWaitingSchema>

export const AssistantTaskStatusSchema = z.enum(['ACTIVE', 'COMPLETED', 'CANCELLED', 'FAILED'])
export type AssistantTaskStatus = z.infer<typeof AssistantTaskStatusSchema>

const CustomerActivityReceiptSchema = z.object({
  kind: z.literal('customer_activity'),
  public_id: z.string().min(1),
  customer_id: z.number().int()
}).strict()

const ProposalKindSchema = z.enum([
  'customer_fact', 'follow_up_task_create', 'follow_up_task', 'opportunity_stage', 'opportunity_create'
])

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
  last_modified_time: z.string().nullable().optional()
}).strict()
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
