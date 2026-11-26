import { z } from 'zod'

import { EntityRefSchema } from './common'
import { CRMQuerySpecSchema } from './query'

export const ContextPolicySchema = z.object({
  selected_entity: z.enum(['USE', 'IGNORE']),
  previous_query: z.enum(['USE', 'IGNORE']),
  result_set: z.enum(['USE', 'IGNORE']),
  active_workflow: z.enum(['RESUME', 'SUSPEND', 'NONE'])
}).strict()

export const WorkflowRefSchema = z.object({
  workflow_id: z.string().min(1).max(128),
  interrupt_id: z.string().min(1).max(128).nullable().optional()
}).strict()

export const ResultSetContextSchema = z.object({
  result_set_id: z.string().min(1).max(128),
  ordered_entity_refs: z.array(EntityRefSchema).max(100).default([])
}).strict()

const AgentQueryTemporalPlanSchema = z.object({
  kind: z.enum([
    'today', 'tomorrow', 'this_week', 'next_week', 'last_week', 'this_month', 'overdue', 'custom', 'unspecified'
  ]).default('unspecified'),
  start_at: z.string().max(64).nullable().optional(),
  end_at: z.string().max(64).nullable().optional(),
  timezone: z.string().max(128).nullable().optional()
}).strict()

const AgentQueryPlanSchema = z.object({
  scope: z.enum(['global_work', 'customer_scoped', 'customer_list', 'unknown']),
  resource: z.enum([
    'follow_up_tasks', 'completed_work', 'customer_context', 'customer_activities',
    'customer_contacts', 'deployment_info', 'customers'
  ]).nullable().optional(),
  query_goal: z.enum(['list', 'search', 'get_detail', 'get_status', 'summarize']).default('list'),
  customer_text: z.string().max(255).nullable().optional(),
  task_text: z.string().max(1000).nullable().optional(),
  temporal: AgentQueryTemporalPlanSchema.default({})
}).strict()

const AgentSemanticPlanSchema = z.object({
  speech_act: z.enum([
    'ASSERT_EVENT', 'ASK_FACT', 'REQUEST_ACTION', 'CONFIRM_ACTION', 'PROVIDE_SUPPLEMENT', 'CANCEL', 'UNKNOWN'
  ]).default('UNKNOWN'),
  business_object: z.enum([
    'CUSTOMER_ACTIVITY', 'FOLLOW_UP_TASK', 'CUSTOMER', 'OPPORTUNITY', 'PAYMENT_RECORD',
    'CONTRACT', 'LEAD', 'CONTACT', 'INVOICE_TITLE', 'DEPLOYMENT_INFO', 'CUSTOMER_MEMBER', 'UNKNOWN'
  ]).default('UNKNOWN'),
  operation: z.enum(['CREATE', 'READ', 'TRANSITION', 'DELETE', 'NONE', 'UNKNOWN']).default('UNKNOWN'),
  user_goal: z.string().max(2000).nullable().optional(),
  customer_reference: z.string().max(255).nullable().optional(),
  activity_content: z.string().max(100_000).nullable().optional(),
  query_target: z.string().max(2000).nullable().optional(),
  query_plan: AgentQueryPlanSchema.nullable().optional(),
  confidence: z.number().min(0).max(1).default(0),
  evidence: z.array(z.string()).max(20).default([])
}).strict()

export const RootDecisionSchema = z.object({
  task_relation: z.enum(['NEW_TASK', 'CONTINUE_TASK', 'SWITCH_TASK']),
  route: z.enum(['QUERY', 'WORKFLOW', 'CLARIFY']),
  risk: z.enum(['READ_ONLY', 'WRITE']),
  context_policy: ContextPolicySchema,
  confidence: z.number().min(0).max(1),
  reason_code: z.string().min(1).max(128),
  evidence: z.array(z.string()).max(20).default([]),
  semantic_plan: AgentSemanticPlanSchema
}).strict().superRefine((decision, context) => {
  if (decision.route === 'QUERY' && decision.risk !== 'READ_ONLY') {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'QUERY route requires READ_ONLY risk',
      path: ['risk']
    })
  }
  if (decision.route === 'WORKFLOW' && decision.risk !== 'WRITE') {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'WORKFLOW route requires WRITE risk',
      path: ['risk']
    })
  }
})

export const RootContextSnapshotSchema = z.object({
  previous_query: CRMQuerySpecSchema.nullable().optional(),
  result_set: ResultSetContextSchema.nullable().optional(),
  active_workflow: WorkflowRefSchema.nullable().optional(),
  resumable_workflows: z.array(WorkflowRefSchema).max(20).default([])
}).strict()

export type ContextPolicy = z.infer<typeof ContextPolicySchema>
export type WorkflowRef = z.infer<typeof WorkflowRefSchema>
export type ResultSetContext = z.infer<typeof ResultSetContextSchema>
export type RootDecision = z.infer<typeof RootDecisionSchema>
export type RootContextSnapshot = z.infer<typeof RootContextSnapshotSchema>
