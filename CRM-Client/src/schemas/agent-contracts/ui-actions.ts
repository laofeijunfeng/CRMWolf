import { z } from 'zod'

export const AgentErrorCodeSchema = z.enum([
  'ROUTE_AMBIGUOUS',
  'ENTITY_AMBIGUOUS',
  'QUERY_INVALID',
  'QUERY_UNSUPPORTED',
  'QUERY_EMPTY',
  'PERMISSION_DENIED',
  'QUERY_LIMIT_EXCEEDED',
  'UPSTREAM_TIMEOUT',
  'CHECKPOINT_UNAVAILABLE',
  'MODEL_OUTPUT_INVALID',
  'RESULT_SET_EXPIRED',
  'ACTION_ALREADY_CONSUMED',
  'ACTION_EXPIRED',
  'ACTION_INVALID',
  'TURN_IN_PROGRESS',
  'IDEMPOTENCY_KEY_REUSED',
  'INTERNAL_ERROR'
])

const RawAgentUIValueSchema = z.object({
  kind: z.enum(['text', 'number', 'money', 'date', 'datetime', 'boolean', 'status', 'link']),
  value: z.union([z.string(), z.number(), z.boolean(), z.null()]),
  display: z.string().max(10000).nullable().optional(),
  currency: z.string().length(3).nullable().optional()
}).strict()

export const AgentUIValueSchema = RawAgentUIValueSchema.superRefine((item, context) => {
  const value = item.value
  if ((item.kind === 'number' || item.kind === 'money') && value !== null && typeof value !== 'number') {
    context.addIssue({ code: z.ZodIssueCode.custom, message: `${item.kind} value must be numeric`, path: ['value'] })
  } else if (item.kind === 'boolean' && value !== null && typeof value !== 'boolean') {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'boolean value must be boolean', path: ['value'] })
  } else if (!['number', 'money', 'boolean'].includes(item.kind) && value !== null && typeof value !== 'string') {
    context.addIssue({ code: z.ZodIssueCode.custom, message: `${item.kind} value must be a string`, path: ['value'] })
  }
  if (item.currency != null && item.kind !== 'money') {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'currency is only valid for money values', path: ['currency'] })
  }
})

const ActionBaseShape = {
  action_id: z.string().min(1).max(128),
  label: z.string().min(1).max(200)
}

export const OpenEntityActionSchema = z.object({ ...ActionBaseShape, type: z.literal('open_entity') }).strict()
export const QueryRefinementActionSchema = z.object({ ...ActionBaseShape, type: z.literal('query_refinement') }).strict()
export const StartWorkflowActionSchema = z.object({ ...ActionBaseShape, type: z.literal('start_workflow') }).strict()
export const SubmitInteractionActionSchema = z.object({ ...ActionBaseShape, type: z.literal('submit_interaction') }).strict()
export const RetryActionSchema = z.object({ ...ActionBaseShape, type: z.literal('retry') }).strict()

export const AgentUIActionSchema = z.discriminatedUnion('type', [
  OpenEntityActionSchema,
  QueryRefinementActionSchema,
  StartWorkflowActionSchema,
  SubmitInteractionActionSchema,
  RetryActionSchema
])

export type AgentUIValue = z.infer<typeof AgentUIValueSchema>
export type AgentUIAction = z.infer<typeof AgentUIActionSchema>
