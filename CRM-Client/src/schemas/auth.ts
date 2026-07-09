/**
 * Auth Validation Schemas
 * UI/UX Pro Max §8 Forms: validation with clear error messages
 */
import { z } from 'zod'

/**
 * Email schema with Chinese error messages
 */
export const emailSchema = z
  .string()
  .min(1, '请输入邮箱')
  .email('请输入正确的邮箱格式')

/**
 * Login form schema
 */
export const loginFormSchema = z.object({
  email: emailSchema,
  password: z
    .string()
    .min(1, '请输入密码'),
})

export type LoginForm = z.infer<typeof loginFormSchema>

/**
 * Register form schema
 */
export const registerFormSchema = z.object({
  email: emailSchema,
  name: z
    .string()
    .min(1, '请输入姓名')
    .max(100, '姓名长度不能超过100个字符'),
  password: z
    .string()
    .min(6, '密码长度至少为6个字符')
    .max(50, '密码长度不能超过50个字符'),
})

export type RegisterForm = z.infer<typeof registerFormSchema>