import { z } from 'zod'

const NullableStringSchema = z.string().nullable().optional()
const NullableNumberSchema = z.number().nullable().optional()

const RoleResponseSchema = z.object({
  id: z.number(),
  name: z.string(),
  code: z.string(),
  description: NullableStringSchema,
  created_at: z.string(),
  updated_at: z.string(),
}).passthrough()

const UserResponseSchema = z.object({
  id: z.number(),
  name: z.string(),
  email: z.string(),
  mobile: NullableStringSchema,
  avatar_url: NullableStringSchema,
  employee_no: NullableStringSchema,
  region: NullableStringSchema,
  status: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  roles: z.array(RoleResponseSchema).optional(),
}).passthrough()

export const OAuthProviderConfigResponseSchema = z.object({
  id: NullableNumberSchema,
  team_id: z.number(),
  provider: z.string(),
  app_id: NullableStringSchema,
  redirect_uri: NullableStringSchema,
  enabled: z.boolean(),
  app_secret_configured: z.boolean(),
  created_at: NullableStringSchema,
  updated_at: NullableStringSchema,
})

export const OAuthProviderConfigUpdateSchema = z.object({
  app_id: z.string(),
  app_secret: NullableStringSchema,
  redirect_uri: z.string(),
  enabled: z.boolean(),
})

export const InviteLoginOptionsResponseSchema = z.object({
  team_name: z.string(),
  code: z.string(),
  feishu_login_enabled: z.boolean(),
})

export const OAuthLoginUrlResponseSchema = z.object({
  auth_url: z.string(),
})

export const OAuthBindingStatusResponseSchema = z.object({
  provider: z.string(),
  enabled: z.boolean(),
  bound: z.boolean(),
  name: NullableStringSchema,
  email: NullableStringSchema,
  avatar_url: NullableStringSchema,
  updated_at: NullableStringSchema,
})

const LoginResponseSchema = z.object({
  access_token: z.string(),
  token_type: z.string(),
  user: UserResponseSchema,
})

export const FeishuCallbackResponseSchema = z.object({
  mode: z.enum(['invite', 'bind']),
  message: z.string(),
  login: LoginResponseSchema.nullable().optional(),
})

export const MessageResponseSchema = z.object({
  message: z.string(),
})

export type OAuthProviderConfigResponse = z.infer<typeof OAuthProviderConfigResponseSchema>
export type OAuthProviderConfigUpdate = z.infer<typeof OAuthProviderConfigUpdateSchema>
export type InviteLoginOptionsResponse = z.infer<typeof InviteLoginOptionsResponseSchema>
export type OAuthLoginUrlResponse = z.infer<typeof OAuthLoginUrlResponseSchema>
export type OAuthBindingStatusResponse = z.infer<typeof OAuthBindingStatusResponseSchema>
export type FeishuCallbackResponse = z.infer<typeof FeishuCallbackResponseSchema>
