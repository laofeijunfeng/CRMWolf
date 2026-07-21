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

const NullableStringSchema = z.string().nullable().optional()

export const RoleResponseSchema = z.object({
  id: z.number(),
  name: z.string(),
  code: z.string(),
  description: NullableStringSchema,
  created_at: z.string(),
  updated_at: z.string(),
}).passthrough()

export const UserResponseSchema = z.object({
  id: z.number(),
  name: z.string(),
  email: z.string(),
  mobile: NullableStringSchema,
  avatar_url: NullableStringSchema,
  employee_no: NullableStringSchema,
  region: NullableStringSchema,
  status: z.string(),
  created_at: z.string().nullable(),
  updated_at: z.string().nullable(),
  roles: z.array(RoleResponseSchema).nullable().optional(),
}).passthrough()

export const PermissionResponseSchema = z.object({
  id: z.number(),
  code: z.string(),
  name: z.string(),
  resource: z.string(),
  action: z.string(),
  scope: NullableStringSchema,
  description: NullableStringSchema,
}).passthrough()

export const LoginResponseSchema = z.object({
  access_token: z.string(),
  token_type: z.string(),
  user: UserResponseSchema,
})

export const MessageResponseSchema = z.object({
  message: z.string(),
})

export const UserPermissionsResponseSchema = z.object({
  permissions: z.array(PermissionResponseSchema),
  total: z.number(),
  cached: z.boolean(),
})

export type LoginResponse = z.infer<typeof LoginResponseSchema>
export type UserResponse = z.infer<typeof UserResponseSchema>
export type RoleResponse = z.infer<typeof RoleResponseSchema>
export type PermissionResponse = z.infer<typeof PermissionResponseSchema>
export type MessageResponse = z.infer<typeof MessageResponseSchema>
export type UserPermissionsResponse = z.infer<typeof UserPermissionsResponseSchema>
