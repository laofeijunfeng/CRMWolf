import { z } from 'zod'

import { AgentErrorCodeSchema } from './ui-actions'
import { AgentUIBlockSchema } from './ui-blocks'
import { AgentUIEnvelopeSchema } from './ui-envelope'

export const AppendTextOperationSchema = z.object({
  op: z.literal('append_text'),
  block_id: z.string().min(1).max(128),
  delta: z.string().min(1).max(10000)
}).strict()

export const UpsertBlockOperationSchema = z.object({
  op: z.literal('upsert_block'),
  block: AgentUIBlockSchema
}).strict()

export const AgentUIStreamOperationSchema = z.discriminatedUnion('op', [
  AppendTextOperationSchema,
  UpsertBlockOperationSchema
])

export const AgentUIDeltaStreamEventSchema = z.object({
  event: z.literal('agent_ui'),
  phase: z.literal('delta'),
  message_id: z.number().int().positive().nullable().optional().default(null),
  turn_id: z.string().min(1).max(128),
  sequence: z.number().int().min(1),
  operations: z.array(AgentUIStreamOperationSchema).min(1).max(100)
}).strict()

export const AgentUIFinalStreamEventSchema = z.object({
  event: z.literal('agent_ui'),
  phase: z.literal('final'),
  message_id: z.number().int().positive(),
  turn_id: z.string().min(1).max(128),
  sequence: z.number().int().min(1),
  message: AgentUIEnvelopeSchema
}).strict()

export const AgentUIStreamEventSchema = z.discriminatedUnion('phase', [
  AgentUIDeltaStreamEventSchema,
  AgentUIFinalStreamEventSchema
]).superRefine((event, context) => {
  if (event.phase !== 'final') return
  if (event.message.state !== 'final') {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'final stream message must have final state',
      path: ['message', 'state']
    })
  }
  if (event.message.message_id !== event.message_id || event.message.turn_id !== event.turn_id) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'final stream identity must match message envelope',
      path: ['message']
    })
  }
})

export const AgentTransportErrorEventSchema = z.object({
  event: z.literal('transport_error'),
  code: AgentErrorCodeSchema,
  message: z.string().min(1).max(10000),
  retryable: z.boolean(),
  session_id: z.number().int().positive().nullable().optional(),
  status_code: z.number().int().min(400).max(599).nullable().optional()
}).strict()

export type AppendTextOperation = z.infer<typeof AppendTextOperationSchema>
export type UpsertBlockOperation = z.infer<typeof UpsertBlockOperationSchema>
export type AgentUIStreamOperation = z.infer<typeof AgentUIStreamOperationSchema>
export type AgentUIDeltaStreamEvent = z.infer<typeof AgentUIDeltaStreamEventSchema>
export type AgentUIFinalStreamEvent = z.infer<typeof AgentUIFinalStreamEventSchema>
export type AgentUIStreamEvent = z.infer<typeof AgentUIStreamEventSchema>
export type AgentTransportErrorEvent = z.infer<typeof AgentTransportErrorEventSchema>
