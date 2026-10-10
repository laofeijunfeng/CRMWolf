import { z } from 'zod'

import {
  AssistantTaskViewSchema,
  AssistantTurnStatusSchema,
  parseAssistantTaskList,
  SubmitInputResponseSchema,
  type AssistantInputKind,
  type AssistantTaskView,
  type SubmitInputResponse
} from '@/schemas/assistant-contracts'
import { useUserStore } from '@/stores/user'
import request from '@/utils/request'

const AssistantTaskActionSchema = z.object({
  actor: z.string(),
  action: z.string(),
  input: z.record(z.unknown()),
  result: z.record(z.unknown()),
  event_type: z.string().nullable().optional(),
  event_key: z.string().nullable().optional(),
  correlation_id: z.string().nullable().optional(),
  created_time: z.string()
}).strict()

export type AssistantTaskAction = z.infer<typeof AssistantTaskActionSchema>

export const StageNameSchema = z.enum(['classify', 'structure', 'quality_gate', 'write'])
export type StageName = z.infer<typeof StageNameSchema>

export interface StageEvent {
  stage: StageName
  phase: 'start' | 'done'
  ms?: number | undefined
  score?: number | undefined
}

export interface SubmitStreamError {
  code: string
  retryable: boolean
  message: string
  seq?: number | undefined
}

export interface SubmitStreamHandlers {
  onAccepted(turnId: string, seq?: number | undefined): void
  onStage(event: StageEvent & { seq?: number | undefined }): void
  onWaiting(data: { task: AssistantTaskView; message: string; seq?: number | undefined }): void
  onError(event: SubmitStreamError): void
  onNetworkLost(): void
}

const TurnEventSchema = z.object({
  seq: z.number().int().nonnegative(),
  event: z.string(),
  data: z.record(z.unknown())
}).strict()

const AssistantTurnSchema = z.object({
  turn_id: z.string(),
  status: AssistantTurnStatusSchema,
  events: z.array(TurnEventSchema),
  task: AssistantTaskViewSchema
}).strict()

export type AssistantTurn = z.infer<typeof AssistantTurnSchema>

/** Parse one SSE frame block into [event, data-json]; returns null on noise. */
export function parseSseBlock(block: string): { event: string; data: string } | null {
  let event = ''
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) {
      event = line.slice('event: '.length).trim()
    } else if (line.startsWith('data: ')) {
      data += line.slice('data: '.length)
    }
  }
  if (event === '' && data === '') return null
  return { event, data }
}

/** Incremental splitter: feed chunks, yields complete blocks. */
export function createSseSplitter(): (chunk: string) => string[] {
  let buffer = ''
  return (chunk: string): string[] => {
    buffer += chunk
    const blocks: string[] = []
    let idx = buffer.indexOf('\n\n')
    while (idx !== -1) {
      blocks.push(buffer.slice(0, idx))
      buffer = buffer.slice(idx + 2)
      idx = buffer.indexOf('\n\n')
    }
    return blocks
  }
}

export async function submitInputStream(
  publicId: string,
  input: SubmitAssistantInput,
  handlers: SubmitStreamHandlers
): Promise<void> {
  const userStore = useUserStore()
  const base = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api'
  let settled = false

  const finish = (): void => {
    settled = true
  }

  try {
    const response = await fetch(`${base}/v1/assistant/tasks/${encodeURIComponent(publicId)}/submit`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        Authorization: `Bearer ${userStore.token}`
      },
      body: JSON.stringify({
        kind: input.kind, text: input.text ?? null, choice: input.choice ?? null,
        client_request_id: input.client_request_id,
        ...(input.action_id !== undefined ? { action_id: input.action_id } : {}),
        ...(input.expected_version !== undefined ? { expected_version: input.expected_version } : {})
      })
    })
    if (!response.ok || response.body === null) {
      handlers.onNetworkLost()
      finish()
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    const split = createSseSplitter()

    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      for (const block of split(decoder.decode(value, { stream: true }))) {
        const parsed = parseSseBlock(block)
        if (parsed === null) continue
        let payload: Record<string, unknown>
        try {
          payload = JSON.parse(parsed.data) as Record<string, unknown>
        } catch {
          continue
        }
        const sequence = typeof payload['seq'] === 'number' ? payload['seq'] : undefined
        if (parsed.event === 'accepted') {
          handlers.onAccepted(typeof payload['turn_id'] === 'string' ? payload['turn_id'] : '', sequence)
        } else if (parsed.event === 'stage') {
          const stage = StageNameSchema.safeParse(payload['stage'])
          const phase = payload['phase'] === 'done' ? 'done' : 'start'
          if (stage.success) {
            handlers.onStage({
              stage: stage.data,
              phase,
              ms: typeof payload['ms'] === 'number' ? payload['ms'] : undefined,
              score: typeof payload['score'] === 'number' ? payload['score'] : undefined,
              seq: sequence
            })
          }
        } else if (parsed.event === 'waiting') {
          const task = AssistantTaskViewSchema.safeParse(payload['task'])
          const message = typeof payload['message'] === 'string' ? payload['message'] : ''
          if (task.success) {
            handlers.onWaiting({ task: task.data, message, seq: sequence })
            finish()
            return
          }
        } else if (parsed.event === 'error') {
          handlers.onError({
            code: typeof payload['code'] === 'string' ? payload['code'] : 'UNKNOWN',
            retryable: payload['retryable'] === true,
            message: typeof payload['message'] === 'string' ? payload['message'] : '处理失败',
            seq: sequence
          })
          finish()
          return
        }
      }
    }
    if (!settled) {
      handlers.onNetworkLost()
    }
  } catch {
    if (!settled) {
      handlers.onNetworkLost()
    }
  }
}

export interface SubmitAssistantInput {
  kind: AssistantInputKind
  text?: string | undefined
  choice?: string | undefined
  client_request_id?: string | undefined
  action_id?: string | undefined
  expected_version?: number | undefined
}

export const assistantApi = {
  async createTask(goal: string, clientRequestId: string = crypto.randomUUID()): Promise<AssistantTaskView> {
    // eslint-disable-next-line crmwolf/require-zod-schema -- payload is parsed below
    const payload: unknown = await request.post('/v1/assistant/tasks', { goal, client_request_id: clientRequestId })
    return AssistantTaskViewSchema.parse(payload)
  },

  async getTask(publicId: string): Promise<AssistantTaskView> {
    // eslint-disable-next-line crmwolf/require-zod-schema -- payload is parsed below
    const payload: unknown = await request.get(`/v1/assistant/tasks/${encodeURIComponent(publicId)}`)
    return AssistantTaskViewSchema.parse(payload)
  },
  async getTurn(publicId: string, turnId: string, afterSeq = 0): Promise<AssistantTurn> {
    // eslint-disable-next-line crmwolf/require-zod-schema -- payload is parsed below
    const payload: unknown = await request.get(
      `/v1/assistant/tasks/${encodeURIComponent(publicId)}/turns/${encodeURIComponent(turnId)}`,
      { params: { after_seq: afterSeq } }
    )
    return AssistantTurnSchema.parse(payload)
  },
  async listTasks(statusFilter?: string): Promise<{ tasks: AssistantTaskView[]; skipped: number[] }> {
    const params = statusFilter !== undefined ? { status_filter: statusFilter } : undefined
    // eslint-disable-next-line crmwolf/require-zod-schema -- payload is parsed below
    const payload: unknown = await request.get('/v1/assistant/tasks', { params })
    return parseAssistantTaskList(payload)
  },

  async latestActiveTask(): Promise<AssistantTaskView | null> {
    // eslint-disable-next-line crmwolf/require-zod-schema -- 204/None path returns null
    const payload: unknown = await request.get('/v1/assistant/tasks/latest/active')
    if (payload === null || payload === undefined) return null
    return AssistantTaskViewSchema.parse(payload)
  },

  async changeKind(publicId: string, kind: 'FOLLOW_UP' | 'ONLINE_MEETING' | 'OFFLINE_MEETING'): Promise<AssistantTaskView> {
    // eslint-disable-next-line crmwolf/require-zod-schema -- payload is parsed below
    const payload: unknown = await request.post(
      `/v1/assistant/tasks/${encodeURIComponent(publicId)}/change-kind`,
      { kind }
    )
    return AssistantTaskViewSchema.parse(payload)
  },

  async listTaskActions(publicId: string): Promise<AssistantTaskAction[]> {
    // eslint-disable-next-line crmwolf/require-zod-schema -- payload is parsed below
    const payload: unknown = await request.get(`/v1/assistant/tasks/${encodeURIComponent(publicId)}/actions`)
    return z.array(AssistantTaskActionSchema).parse(payload)
  },

  async submitInput(publicId: string, input: SubmitAssistantInput): Promise<SubmitInputResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema -- payload is parsed below
    const payload: unknown = await request.post(`/v1/assistant/tasks/${encodeURIComponent(publicId)}/submit`, {
      kind: input.kind,
      text: input.text ?? null,
      choice: input.choice ?? null,
      client_request_id: input.client_request_id,
      ...(input.action_id !== undefined ? { action_id: input.action_id } : {}),
      ...(input.expected_version !== undefined ? { expected_version: input.expected_version } : {})
    })
    return SubmitInputResponseSchema.parse(payload)
  }
}
