import { z } from 'zod'

export const teamJoinSchema = z.object({
  code: z
    .string()
    .min(4, { message: '邀请码长度为4-20个字符' })
    .max(20, { message: '邀请码长度为4-20个字符' }),
})

export type TeamJoinFormValues = z.infer<typeof teamJoinSchema>