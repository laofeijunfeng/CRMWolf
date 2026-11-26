import { z } from 'zod'

import { JsonObjectSchema } from '@/schemas/agent-contracts/common'
import { AgentUIEnvelopeSchema } from '@/schemas/agent-contracts/ui-envelope'
import { InteractionFieldSchema } from '@/schemas/agent-contracts/ui-interactions'

export const DraftFieldStatusSchema = z.enum(['MISSING', 'CANDIDATE', 'ACCEPTED', 'EXPLICITLY_NONE'])
export type DraftFieldStatus = z.infer<typeof DraftFieldStatusSchema>

export const DraftFieldSchema = z.object({
  status: DraftFieldStatusSchema,
  value: z.string().nullable().optional()
}).strict()
export type DraftField = z.infer<typeof DraftFieldSchema>

export const EntityKindSchema = z.enum([
  'contact_create', 'invoice_title_create', 'deployment_create', 'customer_create', 'opportunity_create'
])
export type EntityKind = z.infer<typeof EntityKindSchema>
export const TaskKindSchema = z.enum(['customer_activity', ...EntityKindSchema.options])

const EntityFieldValueSchema = z.object({
  value: z.union([z.string().max(2000), z.number(), z.array(z.string().max(64))]).nullable().optional(),
  source: z.enum(['ORIGINAL', 'DERIVED', 'DEFAULT', 'USER_CHOICE', 'SUPPLEMENT', 'NORMALIZED', 'AUTO_NAME', 'CUSTOMER_DEFAULT']),
  phrase: z.string().max(200).nullable().optional(),
  choices: z.array(z.string()).max(8).optional(),
  warning: z.string().max(200).nullable().optional()
}).strict()

export const EntityDraftSchema = z.object({
  kind: EntityKindSchema,
  customer_public_id: z.string().max(64).nullable().optional(),
  customer_name: z.string().max(200).nullable().optional(),
  fields: z.record(EntityFieldValueSchema).optional(),
  customer_fields: z.record(EntityFieldValueSchema).optional(),
  extracted: z.array(z.object({ key: z.string(), value: z.string(), quote: z.string() }).strict()).max(40).optional(),
  submitted: z.record(JsonObjectSchema).optional(),
  source_text: z.string().max(20000).optional(),
  credentials_mentioned: z.boolean().optional()
}).strict()
export type EntityDraft = z.infer<typeof EntityDraftSchema>

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
  quality_score: DraftFieldSchema.optional(),
  channel_status: z.enum(['recognized', 'required', 'selected', 'revised']).nullable().optional(),
  channel_kind: z.string().nullable().optional(),
  channel_source: z.enum(['model', 'keyword', 'user']).nullable().optional(),
  channel_quote: z.string().nullable().optional(),
  channel_reason: z.string().nullable().optional(),
  channel_confidence: z.number().nullable().optional(),
  channel_status_label: z.string().nullable().optional(),
  channel_source_text: z.string().nullable().optional(),
  channel_options: z.array(z.string()).optional(),
  channel_origin_label: z.string().nullable().optional(),
  input_noise: z.array(z.object({
    segment_id: z.string(),
    kind: z.enum(['SPEAKER_TIMESTAMP', 'CHANNEL_MENTION']),
    start: z.number().int(),
    end: z.number().int(),
    raw_text: z.string()
  }).strict()).optional(),
  entity: EntityDraftSchema.nullable().optional()
}).strict()
export type TaskDraft = z.infer<typeof TaskDraftSchema>
export const ActivityPreviewSchema = z.object({
  customer_name: z.string(),
  activity_kind: z.enum(['PHONE_FOLLOW_UP', 'WECHAT_FOLLOW_UP', 'EMAIL_FOLLOW_UP', 'VISIT_FOLLOW_UP', 'OTHER_FOLLOW_UP', 'ONLINE_MEETING', 'OFFLINE_MEETING']).nullable().optional(),
  channel_status: z.enum(['recognized', 'required', 'selected', 'revised']).optional(),
  channel_status_label: z.string().nullable().optional(),
  channel_source_text: z.string().nullable().optional(),
  channel_options: z.array(z.string()).optional(),
  title: z.string().nullable().optional(),
  summary: z.string().nullable().optional(),
  content_json: z.record(z.unknown()),
  source_content: z.string(),
  score: z.number().int(),
  score_reason: z.string(),
  next_action: z.string().nullable().optional(),
  next_follow_time: z.string().nullable().optional(),
  next_follow_time_text: z.string().nullable().optional(),
  next_follow_time_granularity: z.enum(['DATE', 'DATETIME', 'UNKNOWN']).optional(),
  comparison: z.object({
    kind: z.enum(['CUSTOMER_COMMITMENT', 'RESCHEDULE']),
    subject: z.string().min(1).max(80),
    action_id: z.string().min(1).max(100),
    summary: z.string().min(1).max(300),
    current: z.object({
      segment_id: z.string().min(1).max(100), quote_start: z.number().int().nonnegative(),
      quote_end: z.number().int().nonnegative(), quote: z.string().min(1).max(500)
    }).strict(),
    previous: z.object({
      ref: z.string().min(1).max(16), source_type: z.string().min(1).max(40), occurred_at: z.string().nullable().optional(),
      quote_start: z.number().int().nonnegative(), quote_end: z.number().int().nonnegative(), quote: z.string().min(1).max(120)
    }).strict(),
    previous_date: z.string().nullable().optional(),
    current_date: z.string().nullable().optional()
  }).strict().nullable().optional(),
  context_status: z.string().max(120).nullable().optional(),
  change_signal: z.enum(['推进', '持平', '放缓', '待确认']).nullable().optional(),
  change_summary: z.string().nullable().optional(),
  opportunity_name: z.string().nullable().optional(),
  opportunity_stage: z.string().nullable().optional(),
  context_as_of: z.string().nullable().optional(),
  context_notices: z.array(z.string()).optional(),
  context_evidence: z.array(z.object({
    source_type: z.string(),
    occurred_at: z.string().nullable().optional(),
    summary: z.string(),
    relation: z.string(),
    key: z.boolean().optional()
  }).strict()).optional(),
  ignored_noise_summary: z.string().nullable().optional()
}).strict()

export const ProposalKindSchema = z.enum(['follow_up_task_create', 'opportunity_stage', 'opportunity_create'])
export type ProposalKind = z.infer<typeof ProposalKindSchema>
// Waits frozen before CRM-154 may still carry retired kinds; they stay loadable and the server settles
// them as no-effect. `follow_up_task` receipts are still written by the follow-up disposition.
export const StoredProposalKindSchema = z.enum([...ProposalKindSchema.options, 'customer_fact', 'follow_up_task'])

export const ProposalCandidateSchema = z.object({
  kind: StoredProposalKindSchema,
  key: z.string().min(1),
  payload: z.record(z.unknown()),
  action_id: z.string().nullable().optional(),
  evidence_quote: z.string().min(1),
  activity_id: z.number().int(),
  customer_id: z.number().int(),
  source_revision: z.number().int(),
  segment_id: z.string().nullable().optional(),
  due_date_granularity: z.enum(['DATE', 'DATETIME', 'UNKNOWN']).nullable().optional(),
  target_public_id: z.string().nullable().optional(),
  prior_status: z.string().nullable().optional(),
  task_owner_id: z.string().nullable().optional(),
  prior_stage_snapshot_id: z.number().int().nullable().optional(),
  prior_version: z.number().int().nullable().optional(),
  prior_fact_version: z.number().int().nullable().optional(),
  task_hash: z.string().nullable().optional()
}).strict().superRefine((candidate, ctx) => {
  if (candidate.kind === 'opportunity_stage'
    && (candidate.target_public_id === undefined || candidate.target_public_id === null || candidate.target_public_id === '')) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['target_public_id'], message: '现有对象提议缺少目标' })
  }
})

export const ConfirmationPayloadSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('activity_write'), preview: ActivityPreviewSchema }).strict(),
  z.object({ kind: z.literal('proposal'), proposal_kind: StoredProposalKindSchema, candidate: ProposalCandidateSchema }).strict()
]).superRefine((payload, ctx) => {
  if (payload.kind === 'proposal' && payload.proposal_kind !== payload.candidate.kind) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['candidate', 'kind'], message: '提议类型不一致' })
  }
})
export type ConfirmationPayload = z.infer<typeof ConfirmationPayloadSchema>
export type ProposalConfirmation = Extract<ConfirmationPayload, { kind: 'proposal' }>


export const TaskWaitingSchema = z.object({
  type: z.enum([
    'FIELD', 'CONFIRMATION', 'ACTIVITY_KIND', 'OBJECT_SELECTION', 'FOLLOW_UP_DISPOSITION', 'PROPOSAL_FORM',
    'CONFIRMATION_EDIT', 'ENTITY_FORM', 'ENTITY_DEFERRED', 'PROFILE_PROPOSALS'
  ]),
  field: z.string().nullable().optional(),
  question_id: z.string().min(1),
  prompt: z.string().min(1),
  action_id: z.string().min(1).nullable().optional(),
  expected_version: z.number().int().nonnegative().nullable().optional(),
  fingerprint: z.string().nullable().optional(),
  candidates: z.array(z.union([
    z.object({ id: z.string().min(1), account_name: z.string().min(1) }).strict(),
    z.object({ id: z.string().min(1), label: z.string().min(1) }).strict(),
    z.object({
      id: z.string().min(1),
      label: z.string().min(1),
      description: z.string().nullable().optional(),
      group: z.string().nullable().optional()
    }).strict()
  ])).optional(),
  hint: z.string().max(400).nullable().optional(),
  confirmation_payload: ConfirmationPayloadSchema.nullable().optional(),
  form_revision: z.number().int().nonnegative().nullable().optional(),
  form_fields: z.array(InteractionFieldSchema).max(20).nullable().optional()
}).strict().superRefine((waiting, ctx) => {
  const isForm = waiting.type === 'PROPOSAL_FORM' || waiting.type === 'CONFIRMATION_EDIT' || waiting.type === 'ENTITY_FORM'
  if (isForm !== (waiting.form_revision != null)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['form_revision'], message: '仅表单等待需要表单版本' })
  }
  if (!isForm && waiting.form_fields != null) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['form_fields'], message: '仅表单等待可携带表单字段' })
  }
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
  customer_id: z.number().int().nullable().optional(),
  customer_public_id: z.string().min(1).nullable().optional()
}).strict()

export const AssistantTurnStatusSchema = z.enum(['PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED'])

const AcceptedProposalReceiptSchema = z.object({
  kind: StoredProposalKindSchema,
  public_id: z.string().min(1),
  proposal_key: z.string().min(1),
  customer_id: z.number().int().nullable().optional(),
  customer_public_id: z.string().min(1).nullable().optional(),
  approval_id: z.number().int().nullable().optional(),
  approval_phase: z.literal('pending_review').nullable().optional(),
  detail: z.string().nullable().optional(),
  name: z.string().min(1).max(200).nullable().optional()
}).strict()

const RefusedProposalReceiptSchema = z.object({
  kind: z.enum([
    'refused:customer_fact', 'refused:follow_up_task_create', 'refused:follow_up_task',
    'refused:opportunity_stage', 'refused:opportunity_create', 'refused:opportunity',
    'refused:contact_create', 'refused:invoice_title_create', 'refused:deployment_create', 'refused:customer_create'
  ]),
  proposal_key: z.string().min(1).optional()
}).strict()

export const EntityCreateReceiptSchema = z.object({
  kind: EntityKindSchema,
  public_id: z.string().min(1).max(64),
  outcome: z.enum(['created', 'existing']),
  customer_public_id: z.string().nullable().optional(),
  name: z.string().min(1).max(200).nullable().optional(),
  approval_phase: z.literal('pending_review').nullable().optional()
}).strict()
export type EntityCreateReceipt = z.infer<typeof EntityCreateReceiptSchema>

export const CommittedReceiptSchema = z.union([
  CustomerActivityReceiptSchema, AcceptedProposalReceiptSchema, RefusedProposalReceiptSchema, EntityCreateReceiptSchema
])
export type CommittedReceipt = z.infer<typeof CommittedReceiptSchema>

export const AssistantTaskViewSchema = z.object({
  public_id: z.string().min(1),
  status: AssistantTaskStatusSchema,
  goal: z.string().min(1),
  task_kind: TaskKindSchema.optional(),
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
  reprocess_turn_id: z.string().min(1).nullable().optional(),
  proposal_outcome: z.enum(['proposal_failed', 'proposal_rejected']).nullable().optional(),
  reconciliation_required: z.boolean().optional(),
  follow_up_disposition: z.object({
    batch_id: z.string().min(1).nullable().optional(),
    activity_public_id: z.string().min(1).nullable().optional(),
    status: z.enum(['ACTIVE', 'DONE', 'OVERFLOW', 'QUERY_FAILED']),
    customer_name: z.string(),
    customer_public_id: z.string().min(1).max(64).nullable().optional(),
    activity_kind_label: z.string(),
    total: z.number().int().nonnegative(),
    current_index: z.number().int().positive().nullable(),
    settling: z.boolean().optional(),
    visible_count: z.number().int().nonnegative().optional(),
    suppression_status: z.enum(['applied', 'stale']).nullable().optional(),
    items: z.array(z.object({
      item_id: z.string().min(1),
      task_public_id: z.string().min(1).nullable().optional(),
      title: z.string().min(1),
      owner_line: z.string().nullable().optional(),
      related: z.boolean(),
      evidence_quote: z.string().nullable().optional(),
      evidence_reason: z.string().nullable().optional(),
      state: z.enum(['current', 'waiting', 'complete', 'hold', 'skip', 'failed', 'unknown']),
      result_title: z.string().nullable().optional(),
      result_message: z.string().nullable().optional(),
      failure_code: z.string().nullable().optional()
    }).strict()).max(100)
  }).strict().nullable().optional(),
  profile_proposals: z.array(z.object({
    index: z.number().int().nonnegative(),
    kind: z.enum(['contact_create', 'invoice_title_create', 'deployment_create']),
    label: z.string(),
    summary: z.string(),
    quote: z.string(),
    decision: z.enum(['pending', 'go', 'skip', 'failed']),
    child_task_public_id: z.string().nullable().optional(),
    child_status: AssistantTaskStatusSchema.nullable().optional(),
    child_waiting_type: z.string().nullable().optional(),
    child_receipt: EntityCreateReceiptSchema.nullable().optional()
  }).strict()).nullable().optional(),
}).strict().superRefine((task, ctx) => {
  if ((task.processing_turn_id == null) !== (task.processing_turn_status == null)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['processing_turn_id'], message: '处理轮次 ID 和状态必须同时提供' })
  }
})
export type AssistantTaskView = z.infer<typeof AssistantTaskViewSchema>

/** One unfinished direct-create draft listed in 「待补充」. */
export const PendingEntityDraftSchema = z.object({
  public_id: z.string().min(1),
  task_kind: TaskKindSchema,
  label: z.string().min(1),
  customer_name: z.string().nullable(),
  waiting_type: z.string().nullable(),
  prompt: z.string().nullable(),
  last_modified_time: z.string()
}).strict()
export type PendingEntityDraft = z.infer<typeof PendingEntityDraftSchema>

export const AssistantInputKindSchema = z.enum(['text', 'submit_field', 'confirm', 'cancel', 'revise_activity_kind', 'submit_form', 'request_edit'])
export type AssistantInputKind = z.infer<typeof AssistantInputKindSchema>

export const AssistantRejectReasonSchema = z.enum(['wrong_customer', 'wrong_content', 'should_not_record', 'other'])
export type AssistantRejectReason = z.infer<typeof AssistantRejectReasonSchema>

export const ConversationBoundarySchema = z.object({ entry_id: z.string().min(1), prompt: z.string().min(1) }).strict()
export type ConversationBoundary = z.infer<typeof ConversationBoundarySchema>
export const ConversationDispositionProjectionSchema = z.object({
  task_public_id: z.string().min(1),
  batch_id: z.string().min(1),
  item_ids: z.array(z.string().min(1)).max(100),
  card_role: z.enum(['NONE', 'CURRENT', 'FINAL']),
  version: z.number().int().nonnegative()
}).strict()
export type ConversationDispositionProjection = z.infer<typeof ConversationDispositionProjectionSchema>
export const ConversationProjectionSchema = z.object({
  visibility: z.enum(['VISIBLE', 'FALLBACK_RECEIPT', 'COVERED']),
  covered_by: z.string().min(1).nullable().optional(),
  activity_public_id: z.string().min(1).nullable().optional(),
  disposition: ConversationDispositionProjectionSchema.nullable().optional()
}).strict()
export type ConversationProjection = z.infer<typeof ConversationProjectionSchema>
export const ConversationLinkSchema = z.object({
  page: z.enum(['leads', 'payments', 'invoices', 'contracts', 'customers', 'follow_up_tasks']),
  label: z.string().min(1).max(40),
  customer_public_id: z.string().min(1).max(64).nullable().optional()
}).strict()
export type ConversationLink = z.infer<typeof ConversationLinkSchema>
export const ConversationMessageSchema = z.object({
  id: z.string().min(1), role: z.enum(['user', 'assistant']), text: z.string(), at: z.string(),
  task: AssistantTaskViewSchema.nullable(), boundary: ConversationBoundarySchema.nullable(),
  outcome: z.enum(['activity_written', 'failure', 'follow_up_disposition', 'task_completed', 'proposal_unavailable']).nullable(),
  ui: AgentUIEnvelopeSchema.nullable(), links: z.array(ConversationLinkSchema).max(4).optional(),
  projection: ConversationProjectionSchema.nullable().optional()
}).strict()
export const ConversationViewSchema = z.object({
  public_id: z.string().min(1), version: z.number().int().nonnegative(),
  focused_task: AssistantTaskViewSchema.nullable(), pending_choice: ConversationBoundarySchema.nullable(),
  has_pending_request: z.boolean().default(false),
  messages: z.array(ConversationMessageSchema), older_cursor: z.number().int().positive().nullable()
}).strict()
export type ConversationView = z.infer<typeof ConversationViewSchema>
/** What the server knows about one send whose response was lost; never asks the client to resend blindly. */
export const ConversationRequestStatusSchema = z.object({
  state: z.enum(['none', 'running', 'not_saved', 'saved']),
  conversation: ConversationViewSchema
}).strict()
export type ConversationRequestStatus = z.infer<typeof ConversationRequestStatusSchema>
export const ConversationReplySchema = z.object({
  conversation: ConversationViewSchema,
  submission: z.object({
    task_public_id: z.string().min(1), turn_id: z.string().min(1),
    input: z.object({
      kind: AssistantInputKindSchema, text: z.string().nullable().optional(), choice: z.string().nullable().optional(),
      client_request_id: z.string().min(8), action_id: z.string().nullable().optional(),
      expected_version: z.number().int().nonnegative().nullable().optional(),
      values: JsonObjectSchema.nullable().optional(),
      form_revision: z.number().int().nonnegative().nullable().optional(),
      choices: z.array(z.string().min(1).max(64)).max(100).nullable().optional(),
      suppress_week: z.boolean().optional(),
      reason: AssistantRejectReasonSchema.nullable().optional()
    }).strict()
  }).strict().nullable()
}).strict()
export type ConversationReply = z.infer<typeof ConversationReplySchema>
