import { z } from 'zod'

import {
  AgentChatRequestSchema,
  AgentTransportErrorEventSchema,
  AgentUIEnvelopeSchema,
  AgentUIStreamEventSchema,
  JsonObjectSchema,
  type AgentChatRequest,
  type AgentTransportErrorEvent,
  type AgentUIEnvelope,
  type AgentUIStreamEvent
} from '@/schemas/agent-contracts'
import type { PaginatedResponse } from '@/types/pagination'
import request from '@/utils/request'

const AgentSessionResponseSchema = z.object({
  id: z.number().int().positive(),
  session_key: z.string().min(1),
  team_id: z.number().int().positive(),
  user_id: z.number().int().positive(),
  title: z.string().nullable().optional(),
  status: z.string().min(1),
  summary: z.string().nullable().optional(),
  context_json: JsonObjectSchema.nullable().optional(),
  created_time: z.string().min(1),
  last_modified_time: z.string().min(1)
}).strict()

const AgentAsyncOperationStatusSchema = z.enum([
  'QUEUED',
  'RUNNING',
  'WAITING_USER',
  'RETRY_SCHEDULED',
  'SUCCEEDED',
  'DEGRADED',
  'FAILED',
  'CANCELLED'
])

const AgentAsyncOperationEventSchema = z.object({
  sequence: z.number().int(),
  event_type: z.string(),
  status: z.string(),
  event_key: z.string(),
  step: z.string().nullable().optional(),
  message: z.string().nullable().optional(),
  payload: JsonObjectSchema,
  occurred_at: z.string().min(1)
}).strict()

const AgentAsyncOperationSchema = z.object({
  public_id: z.string().min(1),
  request_id: z.string().min(1),
  team_id: z.number().int().positive(),
  user_id: z.number().int().positive(),
  session_id: z.number().int().positive().nullable().optional(),
  source_user_message_id: z.number().int().positive().nullable().optional(),
  source_assistant_message_id: z.number().int().positive().nullable().optional(),
  operation_type: z.string().min(1),
  resource_type: z.string().min(1),
  resource_id: z.number().int().nullable().optional(),
  resource_public_id: z.string().nullable().optional(),
  status: AgentAsyncOperationStatusSchema,
  summary: z.string().nullable().optional(),
  current_step: z.string().nullable().optional(),
  graph_thread_id: z.string().nullable().optional(),
  result: JsonObjectSchema,
  error_message: z.string().nullable().optional(),
  started_time: z.string().nullable().optional(),
  finished_time: z.string().nullable().optional(),
  next_retry_at: z.string().nullable().optional(),
  attempt_count: z.number().int().nonnegative(),
  created_time: z.string().min(1),
  updated_time: z.string().min(1),
  events: z.array(AgentAsyncOperationEventSchema)
}).strict()

const AgentSessionPageSchema = paginatedSchema(AgentSessionResponseSchema)
const AgentMessagePageSchema = paginatedSchema(AgentUIEnvelopeSchema)
const AgentAsyncOperationListSchema = z.array(AgentAsyncOperationSchema)

const AgentSessionStreamEventSchema = z.object({
  event: z.literal('session'),
  session_id: z.number().int().positive(),
  session_key: z.string().min(1).max(64)
}).strict()

const AgentDoneStreamEventSchema = z.object({
  event: z.literal('done'),
  session_id: z.number().int().positive()
}).strict()

const AgentStreamEventSchema = z.union([
  AgentSessionStreamEventSchema,
  AgentUIStreamEventSchema,
  AgentTransportErrorEventSchema,
  AgentDoneStreamEventSchema
])

export type AgentSessionResponse = z.infer<typeof AgentSessionResponseSchema>
export type AgentAsyncOperationStatus = z.infer<typeof AgentAsyncOperationStatusSchema>
export type AgentAsyncOperationEvent = z.infer<typeof AgentAsyncOperationEventSchema>
export type AgentAsyncOperation = z.infer<typeof AgentAsyncOperationSchema>
export type AgentSessionStreamEvent = z.infer<typeof AgentSessionStreamEventSchema>
export type AgentDoneStreamEvent = z.infer<typeof AgentDoneStreamEventSchema>
export type AgentStreamEvent = z.infer<typeof AgentStreamEventSchema>
export type {
  AgentChatRequest,
  AgentTransportErrorEvent,
  AgentUIEnvelope,
  AgentUIStreamEvent
}

export class AgentProtocolError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'AgentProtocolError'
  }
}

function paginatedSchema<T extends z.ZodTypeAny>(itemSchema: T): z.ZodObject<{
  items: z.ZodArray<T>
  total: z.ZodNumber
  page: z.ZodNumber
  page_size: z.ZodNumber
  total_pages: z.ZodNumber
}> {
  return z.object({
    items: z.array(itemSchema),
    total: z.number().int().nonnegative(),
    page: z.number().int().positive(),
    page_size: z.number().int().positive(),
    total_pages: z.number().int().nonnegative()
  }).strict()
}

function parseAgentStreamEvent(payload: string): AgentStreamEvent {
  let decoded: unknown
  try {
    decoded = JSON.parse(payload)
  } catch (error) {
    throw new AgentProtocolError(`Agent stream contains invalid JSON: ${error instanceof Error ? error.message : String(error)}`)
  }

  const parsed = AgentStreamEventSchema.safeParse(decoded)
  if (!parsed.success) {
    throw new AgentProtocolError(`Agent stream event does not match crm.agent.ui.v1: ${parsed.error.message}`)
  }
  return parsed.data
}

function eventData(frame: string): string | null {
  const dataLines = frame
    .split(/\r?\n/)
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice(5).trimStart())
  return dataLines.length > 0 ? dataLines.join('\n') : null
}

export const agentApi = {
  listSessions: async (): Promise<PaginatedResponse<AgentSessionResponse>> => {
    return AgentSessionPageSchema.parse(await request.get<unknown>('/v1/agent/sessions'))
  },

  listMessages: async (
    sessionId: number,
    params?: { page?: number, page_size?: number }
  ): Promise<PaginatedResponse<AgentUIEnvelope>> => {
    return AgentMessagePageSchema.parse(
      await request.get<unknown>(`/v1/agent/sessions/${sessionId}/messages`, { params })
    )
  },

  listSessionOperations: async (
    sessionId: number,
    params?: { limit?: number }
  ): Promise<AgentAsyncOperation[]> => {
    return AgentAsyncOperationListSchema.parse(
      await request.get<unknown>(`/v1/agent/sessions/${sessionId}/operations`, { params })
    )
  },

  getOperation: async (operationPublicId: string): Promise<AgentAsyncOperation> => {
    return AgentAsyncOperationSchema.parse(
      await request.get<unknown>(`/v1/agent/operations/${operationPublicId}`)
    )
  },

  chatStream: async (
    data: AgentChatRequest,
    onEvent: (event: AgentStreamEvent) => void,
    token: string
  ): Promise<void> => {
    const validatedRequest = AgentChatRequestSchema.parse(data)
    const response = await fetch('/api/v1/agent/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(validatedRequest)
    })

    if (!response.ok) {
      throw new Error(`Agent request failed with HTTP ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (reader === undefined) {
      throw new AgentProtocolError('Agent stream response has no body')
    }

    const decoder = new TextDecoder()
    let buffer = ''
    let completed = false
    let transportErrorSeen = false

    const processFrame = (frame: string): boolean => {
      const payload = eventData(frame)
      if (payload === null) return false
      const event = parseAgentStreamEvent(payload)
      onEvent(event)
      if (event.event === 'transport_error') transportErrorSeen = true
      if (event.event === 'done') {
        completed = true
        return true
      }
      return false
    }

    while (!completed) {
      const chunk = await reader.read()
      if (chunk.done) break
      buffer += decoder.decode(chunk.value, { stream: true })
      const frames = buffer.split(/\r?\n\r?\n/)
      buffer = frames.pop() ?? ''
      if (frames.some(processFrame)) break
    }

    buffer += decoder.decode()
    if (!completed && buffer.trim().length > 0) {
      processFrame(buffer)
    }
    if (!completed && !transportErrorSeen) {
      throw new AgentProtocolError('Agent stream ended before done')
    }
  }
}
