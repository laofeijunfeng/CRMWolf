import { z } from 'zod'

import { AgentUIActionSchema } from './ui-actions'
import { AgentUIBlockSchema } from './ui-blocks'

export const AgentUIMetadataSchema = z.object({
  display: z.enum(['MESSAGE', 'STATE_UPDATE']).default('MESSAGE'),
  route: z.enum(['QUERY', 'WORKFLOW', 'CLARIFY', 'CHITCHAT']).nullable().optional(),
  result_set_id: z.string().min(1).max(128).nullable().optional(),
  accessibility_label: z.string().max(10000).nullable().optional()
}).strict()

export const AgentUIEnvelopeSchema = z.object({
  schema_version: z.literal('crm.agent.ui.v1'),
  message_id: z.number().int().positive(),
  turn_id: z.string().min(1).max(128),
  role: z.enum(['user', 'assistant', 'system']),
  state: z.enum(['streaming', 'final', 'failed']),
  blocks: z.array(AgentUIBlockSchema).max(30),
  suggested_actions: z.array(AgentUIActionSchema).max(10).default([]),
  metadata: AgentUIMetadataSchema
}).strict().superRefine((envelope, context) => {
  const blockIds = envelope.blocks.map(block => block.id)
  if (new Set(blockIds).size !== blockIds.length) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'block ids must be unique within an envelope', path: ['blocks'] })
  }
  const actionIds = envelope.suggested_actions.map(action => action.action_id)
  if (new Set(actionIds).size !== actionIds.length) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'suggested action ids must be unique within an envelope', path: ['suggested_actions'] })
  }
})

export type AgentUIEnvelope = z.infer<typeof AgentUIEnvelopeSchema>
