import { z } from 'zod'

export const changePasswordSchema = z.object({
  oldPassword: z.string().min(1, '请输入当前密码'),
  newPassword: z.string().min(6, '新密码长度为 6–50 个字符').max(50, '新密码长度为 6–50 个字符'),
  confirmPassword: z.string().min(1, '请确认新密码'),
}).refine((values) => values.newPassword === values.confirmPassword, {
  message: '两次输入的密码不一致',
  path: ['confirmPassword'],
})

export type ChangePasswordFormValues = z.infer<typeof changePasswordSchema>
