import { z } from 'zod'
import { BusinessDateTimeStringSchema } from './common'

export enum UserStatus {
  ACTIVE = 'active',
  INACTIVE = 'inactive',
  SUSPENDED = 'suspended'
}

const NullableString = z.string().nullable()

export const UserRoleInfoSchema = z.object({
  id: z.number().int().positive(),
  name: z.string(),
  code: z.string()
})

export const UserResponseSchema = z.object({
  id: z.number().int().positive(),
  name: z.string(),
  email: z.string(),
  mobile: NullableString,
  avatar_url: NullableString,
  employee_no: NullableString,
  region: NullableString,
  status: z.nativeEnum(UserStatus),
  created_at: BusinessDateTimeStringSchema,
  updated_at: BusinessDateTimeStringSchema
})

export const UserWithRolesResponseSchema = UserResponseSchema.extend({
  roles: z.array(UserRoleInfoSchema)
})

export const UserListResponseSchema = z.union([
  z.array(UserWithRolesResponseSchema),
  z.object({
    items: z.array(UserWithRolesResponseSchema),
    total: z.number().int().nonnegative(),
    page: z.number().int().positive(),
    page_size: z.number().int().positive(),
    total_pages: z.number().int().nonnegative()
  })
])

export const UserSearchResultSchema = UserResponseSchema
export const UserSearchResultsSchema = z.array(UserSearchResultSchema)

export type RoleInfo = z.infer<typeof UserRoleInfoSchema>
export type UserResponse = z.infer<typeof UserWithRolesResponseSchema>
export type UserMutationResponse = z.infer<typeof UserResponseSchema>
export type UserListResponse = z.infer<typeof UserListResponseSchema>
export type UserSearchResult = z.infer<typeof UserSearchResultSchema>
