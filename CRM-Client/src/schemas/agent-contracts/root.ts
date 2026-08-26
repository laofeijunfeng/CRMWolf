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

export const RootDecisionSchema = z.object({
  task_relation: z.enum(['NEW_TASK', 'CONTINUE_TASK', 'SWITCH_TASK']),
  route: z.enum(['QUERY', 'WORKFLOW', 'CLARIFY']),
  risk: z.enum(['READ_ONLY', 'WRITE']),
  context_policy: ContextPolicySchema,
  confidence: z.number().min(0).max(1),
  reason_code: z.string().min(1).max(128),
  evidence: z.array(z.string()).max(20).default([])
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
