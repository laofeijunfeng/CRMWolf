import { z } from 'zod'

export const FrontendLogEntrySchema = z.object({
  level: z.enum(['debug', 'info', 'warn', 'error']),
  context: z.string(),
  action: z.string(),
  data: z.unknown(),
  timestamp: z.number(),
  traceId: z.string().optional(),
  userId: z.number().optional(),
  teamId: z.number().optional(),
}).passthrough()

export const FrontendLogBatchResponseSchema = z.object({
  received: z.number(),
  error: z.string().optional(),
}).passthrough()

export type FrontendLogEntry = z.infer<typeof FrontendLogEntrySchema>
