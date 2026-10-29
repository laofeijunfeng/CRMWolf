import { z } from 'zod'

import {
  AssistantTaskViewSchema,
  ConversationViewSchema, ConversationReplySchema,
  AssistantTurnStatusSchema,
  parseAssistantTaskList,
  SubmitInputResponseSchema,
  type ConversationView, type ConversationReply,
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
  onTerminalInvalid?(detail: { event: string; turnId: string; seq?: number | undefined; issues: string[] }): void
}

const TurnEventSchema = z.object({
  seq: z.number().int().nonnegative(),
  event: z.string(),
  data: z.record(z.unknown())
}).strict()

const AssistantTurnSchema = z.object({
  turn_id: z.string(),
  status: AssistantTurnStatusSchema,
  lease_version: z.number().int().nonnegative(),
  reprocess_allowed: z.boolean().optional().default(false),
  events: z.array(TurnEventSchema),
  task: AssistantTaskViewSchema
}).strict()

export type AssistantTurn = z.infer<typeof AssistantTurnSchema>

export type SseSplitter = ((chunk: string) => string[]) & { flush(): string[] }

/** Empty build args must follow the axios rule and stay on the `/api` proxy. */
export function resolveAssistantApiBase(raw: string | null | undefined): string {
  if (raw === undefined || raw === null || raw.trim() === '') return '/api'
  return raw
}

function schemaIssuePaths(error: z.ZodError): string[] {
  return error.issues.map((issue) => issue.path.map((part) => String(part)).join('.') || '$')
}

function logAssistantClient(level: 'info' | 'warn' | 'error', action: string, data: Record<string, unknown>): void {
  void import('@/utils/logger').then(({ logger }) => {
    logger[level]('[SalesAssistant]', action, data)
  }).catch(() => undefined)
}

/** Parse one SSE frame block into [event, data-json]; returns null on noise. */
export function parseSseBlock(block: string): { event: string; data: string } | null {
  let event = ''
  let data = ''
  const normalized = block.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  for (const line of normalized.split('\n')) {
    if (line.startsWith('event: ')) {
      event = line.slice('event: '.length).trim()
    } else if (line.startsWith('data: ')) {
      data += line.slice('data: '.length)
    }
  }
  if (event === '' && data === '') return null
  return { event, data }
}

/** Incremental splitter: LF and CRLF frames, plus a legal tail frame on flush. */
export function createSseSplitter(): SseSplitter {
  let buffer = ''
  const take = (final: boolean): string[] => {
    const holdCarriage = !final && buffer.endsWith('\r')
    const body = holdCarriage ? buffer.slice(0, -1) : buffer
    buffer = body.replace(/\r\n/g, '\n')
    const blocks: string[] = []
    let idx = buffer.indexOf('\n\n')
    while (idx !== -1) {
      blocks.push(buffer.slice(0, idx))
      buffer = buffer.slice(idx + 2)
      idx = buffer.indexOf('\n\n')
    }
    if (holdCarriage) buffer += '\r'
    if (final && buffer.trim() !== '') {
      blocks.push(buffer.replace(/\s+$/g, ''))
      buffer = ''
    }
    return blocks
  }
  const push = ((chunk: string): string[] => {
    buffer += chunk
    return take(false)
  }) as SseSplitter
  push.flush = (): string[] => take(true)
  return push
}

export async function submitInputStream(
  publicId: string,
  input: SubmitAssistantInput,
  handlers: SubmitStreamHandlers
): Promise<void> {
  const userStore = useUserStore()
  const base = resolveAssistantApiBase(import.meta.env.VITE_API_BASE_URL as string | undefined)
  let settled = false
  let streamTurnId = ''

  const finish = (): void => {
    settled = true
  }
  const deliver = (block: string): boolean => {
    const parsed = parseSseBlock(block)
    if (parsed === null) return false
    let payload: Record<string, unknown>
    try {
      payload = JSON.parse(parsed.data) as Record<string, unknown>
    } catch {
      logAssistantClient('warn', 'sse_frame_invalid', {
        event_name: parsed.event, turn_id: streamTurnId, task: publicId, client_request_id: input.client_request_id ?? ''
      })
      return false
    }
    const sequence = typeof payload['seq'] === 'number' ? payload['seq'] : undefined
    if (parsed.event === 'accepted') {
      streamTurnId = typeof payload['turn_id'] === 'string' ? payload['turn_id'] : streamTurnId
      handlers.onAccepted(streamTurnId, sequence)
      return false
    }
    if (parsed.event === 'stage') {
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
      return false
    }
    if (parsed.event === 'waiting') {
      const task = AssistantTaskViewSchema.safeParse(payload['task'])
      const message = typeof payload['message'] === 'string' ? payload['message'] : ''
      if (task.success && message !== '') {
        handlers.onWaiting({ task: task.data, message, seq: sequence })
        finish()
        return true
      }
      const issues = task.success ? ['message'] : schemaIssuePaths(task.error)
      logAssistantClient('error', 'terminal_schema_invalid', {
        event_name: 'waiting', turn_id: streamTurnId, task: publicId, seq: sequence ?? null,
        client_request_id: input.client_request_id ?? '', issues
      })
      handlers.onTerminalInvalid?.({ event: 'waiting', turnId: streamTurnId, seq: sequence, issues })
      return false
    }
    if (parsed.event === 'error') {
      const code = typeof payload['code'] === 'string' ? payload['code'] : ''
      const message = typeof payload['message'] === 'string' ? payload['message'] : ''
      if (code === '' || message === '') {
        logAssistantClient('error', 'terminal_schema_invalid', {
          event_name: 'error', turn_id: streamTurnId, task: publicId, seq: sequence ?? null,
          client_request_id: input.client_request_id ?? '', issues: [code === '' ? 'code' : 'message']
        })
        handlers.onTerminalInvalid?.({ event: 'error', turnId: streamTurnId, seq: sequence, issues: [code === '' ? 'code' : 'message'] })
        return false
      }
      handlers.onError({ code, retryable: payload['retryable'] === true, message, seq: sequence })
      finish()
      return true
    }
    logAssistantClient('info', 'sse_event_ignored', {
      event_name: parsed.event, turn_id: streamTurnId, task: publicId, seq: sequence ?? null
    })
    return false
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
      logAssistantClient('warn', 'sse_disconnect', {
        task: publicId, turn_id: streamTurnId, client_request_id: input.client_request_id ?? '',
        http_status: response.status, event_name: 'submit'
      })
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
        if (deliver(block)) return
      }
    }
    for (const block of split.flush()) {
      if (deliver(block)) return
    }
    if (!settled) handlers.onNetworkLost()
  } catch {
    if (!settled) {
      logAssistantClient('warn', 'sse_disconnect', {
        task: publicId, turn_id: streamTurnId, client_request_id: input.client_request_id ?? '',
        http_status: null, event_name: 'submit'
      })
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
  async openConversation(): Promise<ConversationView> {
    // eslint-disable-next-line crmwolf/require-zod-schema -- parsed at this boundary
    const payload: unknown = await request.post('/v1/assistant/conversation/open')
    return ConversationViewSchema.parse(payload)
  },
  async getConversation(before?: number): Promise<ConversationView> {
    // eslint-disable-next-line crmwolf/require-zod-schema -- parsed at this boundary
    const payload: unknown = await request.get('/v1/assistant/conversation', { params: { before } })
    return ConversationViewSchema.parse(payload)
  },
  async conversationText(input: { text: string; client_request_id: string; expected_version: number }): Promise<ConversationReply> {
    // eslint-disable-next-line crmwolf/require-zod-schema -- parsed at this boundary
    const payload: unknown = await request.post('/v1/assistant/conversation/messages', input, { timeout: 150_000 })
    return ConversationReplySchema.parse(payload)
  },
  async retryConversationEntry(entryId: string, expectedVersion: number): Promise<ConversationReply> {
    // eslint-disable-next-line crmwolf/require-zod-schema -- parsed at this boundary
    const payload: unknown = await request.post(
      `/v1/assistant/conversation/entries/${encodeURIComponent(entryId)}/retry`,
      { expected_version: expectedVersion },
      { timeout: 150_000 }
    )
    return ConversationReplySchema.parse(payload)
  },
  async conversationChoice(input: { entry_id: string; choice: 'CONTINUE' | 'NEW' | 'CANCEL'; client_request_id: string; expected_version: number }): Promise<ConversationReply> {
    // eslint-disable-next-line crmwolf/require-zod-schema -- parsed at this boundary
    const payload: unknown = await request.post('/v1/assistant/conversation/choices', input)
    return ConversationReplySchema.parse(payload)
  },
  async conversationCommand(input: { task_public_id: string; input: SubmitAssistantInput; expected_version: number }): Promise<ConversationReply> {
    // eslint-disable-next-line crmwolf/require-zod-schema -- parsed at this boundary
    const payload: unknown = await request.post('/v1/assistant/conversation/commands', input)
    return ConversationReplySchema.parse(payload)
  },
  async resumeConversation(): Promise<ConversationReply> {
    // eslint-disable-next-line crmwolf/require-zod-schema -- parsed at this boundary
    const payload: unknown = await request.post('/v1/assistant/conversation/resume', undefined, { timeout: 150_000 })
    return ConversationReplySchema.parse(payload)
  },
  async conversationKind(input: { task_public_id: string; kind: 'FOLLOW_UP' | 'ONLINE_MEETING' | 'OFFLINE_MEETING';
    task_version: number; expected_version: number; client_request_id: string }): Promise<ConversationReply> {
    // eslint-disable-next-line crmwolf/require-zod-schema -- parsed at this boundary
    const payload: unknown = await request.post('/v1/assistant/conversation/change-kind', input)
    return ConversationReplySchema.parse(payload)
  },
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
  async retryTurn(publicId: string, turnId: string, expectedLeaseVersion: number, afterSeq = 0): Promise<AssistantTurn> {
    // eslint-disable-next-line crmwolf/require-zod-schema -- payload is parsed below
    const payload: unknown = await request.post(
      `/v1/assistant/tasks/${encodeURIComponent(publicId)}/turns/${encodeURIComponent(turnId)}/retry`,
      { expected_lease_version: expectedLeaseVersion, after_seq: afterSeq }
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
