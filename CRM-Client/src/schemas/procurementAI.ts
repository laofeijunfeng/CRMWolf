import { z } from 'zod'

const ParsedStageSchema = z.object({
  stage_name: z.string(),
  template_code: z.string(),
  win_probability: z.number().int().min(10).max(100),
  sort_order: z.number().int().positive(),
  is_default_start: z.boolean(),
  can_skip: z.boolean(),
  description: z.string().nullish()
})

export const ProcurementAIParseSSEEventSchema = z.object({
  event: z.enum(['status', 'content', 'parsed', 'error']),
  message: z.string().nullish(),
  content: z.string().nullish(),
  method: z.object({
    name: z.string(),
    code: z.string(),
    description: z.string().nullish(),
    stages: z.array(ParsedStageSchema)
  }).nullish(),
  thinking_process: z.string().nullish()
})

export const ProcurementAICreateResultSchema = z.object({
  success: z.boolean(),
  message: z.string(),
  data: z.object({
    method: z.object({
      id: z.number().int().positive(),
      name: z.string(),
      code: z.string(),
      description: z.string().optional().nullable()
    }),
    stages: z.array(z.object({
      id: z.number().int().positive(),
      stage_name: z.string(),
      template_code: z.string(),
      win_probability: z.number().int().min(0).max(100),
      sort_order: z.number().int().positive(),
      is_default_start: z.number().int().min(0).max(1)
    }))
  })
})

export type ProcurementAICreateResult = z.infer<typeof ProcurementAICreateResultSchema>
