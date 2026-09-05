/* eslint-disable crmwolf/require-zod-schema */
import axios, { type AxiosError } from 'axios'
import { z } from 'zod'
import request, { type RequestConfig } from '@/utils/request'

export const CommandStatusSchema = z.enum([
  'PENDING',
  'SUCCEEDED',
  'FAILED',
  'UNKNOWN',
  'CONFLICT',
  'PARTIAL',
])

export type CommandStatus = z.infer<typeof CommandStatusSchema>

const CommandErrorSchema = z.object({
  code: z.string(),
  message: z.string(),
  field_path: z.string().nullable().optional(),
})

export const CommandExecutionResponseSchema = z.object({
  operation_id: z.string(),
  status: CommandStatusSchema,
  command_type: z.string(),
  resource: z.record(z.unknown()).nullable().optional(),
  data: z.unknown().nullable().optional(),
  effects: z.array(z.record(z.unknown())).default([]),
  next_actions: z.array(z.record(z.unknown())).default([]),
  retryable: z.boolean().default(false),
  queryable: z.boolean().default(true),
  error: CommandErrorSchema.nullable().optional(),
  correlation_id: z.string().nullable().optional(),
  created_time: z.string(),
  updated_time: z.string(),
  completed_time: z.string().nullable().optional(),
})

export type CommandExecutionResponse = z.infer<typeof CommandExecutionResponseSchema>

export type CommandRequestOptions = Pick<
  RequestConfig,
  'operationId' | 'idempotencyKey' | 'expectedVersion' | 'correlationId'
>

function createUuid(): string {
  return typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `fallback-${Date.now()}-${Math.random()}`
}

/**
 * Create the three identifiers that must remain stable for the lifetime of a
 * write command and any subsequent result query.
 */
export function createCommandRequestOptions(
  options: Partial<CommandRequestOptions> = {},
): CommandRequestOptions {
  const operationId = options.operationId ?? `op_${createUuid().replace(/-/g, '')}`
  const idempotencyKey = options.idempotencyKey ?? createUuid()
  return {
    operationId,
    idempotencyKey,
    correlationId: options.correlationId ?? createUuid(),
    ...(options.expectedVersion === undefined ? {} : { expectedVersion: options.expectedVersion }),
  }
}

/** Alias kept close to the HTTP terminology used by the TRD. */
export const createCommandHeaders = createCommandRequestOptions

export function getCommandStatus(operationId: string): Promise<CommandExecutionResponse> {
  return request
    .get<unknown>(`/v1/operations/${encodeURIComponent(operationId)}`)
    .then((payload) => CommandExecutionResponseSchema.parse(payload))
}

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds))
}

/**
 * Query an existing operation only. This intentionally never replays the
 * original mutation and gives the UI a bounded recovery window.
 */
export async function pollCommandStatus(
  operationId: string,
  options: { attempts?: number; intervalMs?: number } = {},
): Promise<CommandExecutionResponse> {
  const attempts = options.attempts ?? 8
  const intervalMs = options.intervalMs ?? 500
  let lastError: unknown = null

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const result = await getCommandStatus(operationId)
      if (result.status !== 'PENDING' || attempt === attempts - 1) return result
    } catch (error) {
      lastError = error
      // A command record can become visible a few milliseconds after the
      // mutation response. Only retry 404; permissions and server errors must
      // remain visible to the caller.
      if (!isNotFoundError(error) || attempt === attempts - 1) throw error
    }
    await wait(intervalMs)
  }

  throw lastError instanceof Error ? lastError : new Error('操作结果暂未确认')
}

export function operationIdFromError(error: unknown): string | null {
  if (!axios.isAxiosError<unknown>(error)) return null
  const responseData = error.response?.data
  if (typeof responseData !== 'object' || responseData === null || !('detail' in responseData)) return null
  const detail = (responseData as { detail?: unknown }).detail
  if (typeof detail === 'object' && detail !== null && 'operation_id' in detail) {
    const operationId = (detail as { operation_id?: unknown }).operation_id
    return typeof operationId === 'string' && operationId.length > 0 ? operationId : null
  }
  return null
}

export function isPendingCommandResponse(payload: unknown): payload is {
  detail: { operation_id: string; message?: string }
} {
  if (typeof payload !== 'object' || payload === null || !('detail' in payload)) return false
  const detail = (payload as { detail?: unknown }).detail
  if (typeof detail !== 'object' || detail === null || !('operation_id' in detail)) return false
  const operationId = (detail as { operation_id?: unknown }).operation_id
  return typeof operationId === 'string' && operationId.length > 0
}

function isNotFoundError(error: unknown): boolean {
  if (!axios.isAxiosError(error)) return false
  return error.response?.status === 404
}

export function isNetworkOrTimeoutError(error: unknown): boolean {
  if (!axios.isAxiosError(error)) return false
  const candidate = error as AxiosError & { code?: string }
  const message = candidate.message?.toLowerCase() ?? ''
  return (
    candidate.code === 'ECONNABORTED' ||
    candidate.code === 'ERR_NETWORK' ||
    message.includes('timeout') ||
    message.includes('network error')
  )
}
