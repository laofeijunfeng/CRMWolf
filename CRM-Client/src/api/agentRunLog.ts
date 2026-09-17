import { z } from 'zod'
import type { PaginatedResponse } from '@/types/pagination'
import request from '@/utils/request'

const TurnOutcomeSchema = z.enum([
  'answered',
  'blocked_unwritten',
  'waiting_confirmation',
  'waiting_input',
  'written',
  'failed',
  'clarified',
])

const StepKindSchema = z.enum(['model', 'code', 'interaction', 'api', 'background'])
const StepToneSchema = z.enum(['done', 'blocked', 'skipped'])

const AgentRunLogStepSchema = z.object({
  kind: StepKindSchema,
  title: z.string().min(1),
  detail: z.string().min(1),
  tone: StepToneSchema,
}).strict()

const AgentRunLogTurnListItemSchema = z.object({
  turn_id: z.string().min(1),
  user_id: z.number().int().positive(),
  user_name: z.string().min(1).nullable().optional(),
  user_text: z.string().min(1),
  outcome: TurnOutcomeSchema,
  summary: z.string().min(1),
  quality_score: z.number().int().min(0).max(100).nullable().optional(),
  customer_name: z.string().min(1).nullable().optional(),
  model: z.string().min(1).nullable().optional(),
  created_time: z.string().min(1),
}).strict()

const AgentRunLogTurnDetailSchema = AgentRunLogTurnListItemSchema.extend({
  steps: z.array(AgentRunLogStepSchema).length(6),
}).strict()

const AgentRunLogTurnPageSchema = z.object({
  items: z.array(AgentRunLogTurnListItemSchema),
  total: z.number().int().nonnegative(),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total_pages: z.number().int().nonnegative(),
}).strict()

export type TurnOutcome = z.infer<typeof TurnOutcomeSchema>
export type AgentRunLogStep = z.infer<typeof AgentRunLogStepSchema>
export type AgentRunLogTurnListItem = z.infer<typeof AgentRunLogTurnListItemSchema>
export type AgentRunLogTurnDetail = z.infer<typeof AgentRunLogTurnDetailSchema>

export const agentRunLogApi = {
  listTurns: async (params?: {
    page?: number
    page_size?: number
    user_id?: number
    outcome?: TurnOutcome
    q?: string
  }): Promise<PaginatedResponse<AgentRunLogTurnListItem>> => {
    return AgentRunLogTurnPageSchema.parse(
      await request.get<unknown>('/v1/agent/run-log/turns', { params }),
    )
  },

  getTurn: async (turnId: string): Promise<AgentRunLogTurnDetail> => {
    return AgentRunLogTurnDetailSchema.parse(
      await request.get<unknown>(`/v1/agent/run-log/turns/${turnId}`),
    )
  },
}
