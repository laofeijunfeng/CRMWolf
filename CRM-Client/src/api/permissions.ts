import request from '@/utils/request'
import {
  PermissionResponseSchema,
  RoleMutationResponseSchema,
  type PermissionResponse
} from '@/schemas/role'
import {
  UserPermissionsResponseSchema,
  type UserPermissionsResponse
} from '@/schemas/auth'
import { omitUndefined } from '@/lib/utils'
import { z } from 'zod'

export type { PermissionResponse } from '@/schemas/role'

export interface PermissionQueryParams {
  skip?: number
  limit?: number
  resource?: string
  action?: string
}

export interface GetUserPermissionsParams {
  use_cache?: boolean
}

const permissionApi = {
  async getUserPermissions(params?: GetUserPermissionsParams): Promise<UserPermissionsResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.get<UserPermissionsResponse>('/v1/auth/me/permissions', {
      params: params ?? {}
    })
    return omitUndefined(UserPermissionsResponseSchema.parse(response))
  },

  async getAllPermissions(params?: PermissionQueryParams): Promise<PermissionResponse[]> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.get('/v1/permissions', { params })
    return PermissionResponseSchema.array().parse(response)
  },

  async assignPermissionToRole(permissionId: number, roleId: number): Promise<z.infer<typeof RoleMutationResponseSchema>> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.post(`/v1/permissions/${permissionId}/roles`, { role_id: roleId })
    return RoleMutationResponseSchema.parse(response)
  },

  async removePermissionFromRole(permissionId: number, roleId: number): Promise<z.infer<typeof RoleMutationResponseSchema>> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.delete(`/v1/permissions/${permissionId}/roles/${roleId}`)
    return RoleMutationResponseSchema.parse(response)
  }
}

export default permissionApi
