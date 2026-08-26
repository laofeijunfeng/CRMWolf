import { z } from 'zod'

import { JsonObjectSchema } from './common'

export const TextAgentInputSchema = z.object({
  type: z.literal('text'),
  text: z.string().min(1).max(10000).refine(value => value.trim().length > 0, 'text cannot be blank')
}).strict()

export const InteractionSubmissionInputSchema = z.object({
  type: z.literal('interaction_submission'),
  action_id: z.string().min(1).max(128),
  values: JsonObjectSchema
}).strict()

export const EntityActionInputSchema = z.object({
  type: z.literal('entity_action'),
  action_id: z.string().min(1).max(128)
}).strict()

export const AgentChatInputSchema = z.discriminatedUnion('type', [
  TextAgentInputSchema,
  InteractionSubmissionInputSchema,
  EntityActionInputSchema
])

export const AgentChatRequestSchema = z.object({
  session_id: z.number().int().positive().nullable().optional(),
  session_key: z.string().min(1).max(64).nullable().optional(),
  client_request_id: z.string().uuid(),
  input: AgentChatInputSchema
}).strict()

export type AgentChatInput = z.infer<typeof AgentChatInputSchema>
export type AgentChatRequest = z.infer<typeof AgentChatRequestSchema>
