import { z } from 'zod'

const NullableStringSchema = z.string().nullable()

export const PermissionResponseSchema = z.object({
  id: z.number(),
  code: z.string(),
  name: z.string(),
  resource: z.string(),
  action: z.string(),
  scope: NullableStringSchema,
  description: NullableStringSchema,
  created_at: z.string(),
  updated_at: z.string(),
}).passthrough()

export const RoleResponseSchema = z.object({
  id: z.number(),
  code: z.string(),
  name: z.string(),
  description: NullableStringSchema,
  created_at: z.string(),
  updated_at: z.string(),
}).passthrough()

export const RoleWithPermissionsSchema = RoleResponseSchema.extend({
  permissions: z.array(PermissionResponseSchema),
})

export const RoleUserResponseSchema = z.object({
  id: z.number(),
  name: z.string(),
  email: z.string(),
  avatar_url: z.string().nullable().optional(),
  status: z.string(),
}).passthrough()

export const RoleMutationResponseSchema = z.object({
  message: z.string(),
}).passthrough()

export type PermissionResponse = z.infer<typeof PermissionResponseSchema>
export type RoleResponse = z.infer<typeof RoleResponseSchema>
export type RoleWithPermissions = z.infer<typeof RoleWithPermissionsSchema>
export type RoleUserResponse = z.infer<typeof RoleUserResponseSchema>
export type RoleMutationResponse = z.infer<typeof RoleMutationResponseSchema>
