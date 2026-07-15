import { z } from 'zod'

export const teamCreateSchema = z.object({
  name: z
    .string()
    .min(2, { message: '团队名称长度为2-50个字符' })
    .max(50, { message: '团队名称长度为2-50个字符' }),
})

export type TeamCreateFormValues = z.infer<typeof teamCreateSchema>