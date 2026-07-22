import request from '@/utils/request'
import {
  PermissionResponseSchema,
  RoleMutationResponseSchema,
  RoleResponseSchema,
  RoleUserResponseSchema,
  RoleWithPermissionsSchema,
  type PermissionResponse,
  type RoleMutationResponse,
  type RoleResponse,
  type RoleUserResponse,
  type RoleWithPermissions,
} from '@/schemas/role'

export type {
  PermissionResponse,
  RoleResponse,
  RoleUserResponse,
  RoleWithPermissions,
} from '@/schemas/role'

export interface RoleCreate {
  code: string
  name: string
  description?: string | null
}

export interface RoleUpdate {
  role_name?: string | null
  description?: string | null
}

export interface UserRoleCreate {
  user_id: number
  role_id: number
  team_id: number
}

export interface RoleQueryParams {
  skip?: number
  limit?: number
}

export interface RolePermissionsUpdate {
  permission_ids: number[]
}

const roleApi = {
  getRoles: async (params?: RoleQueryParams): Promise<RoleResponse[]> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.get('/v1/roles', { params })
    return RoleResponseSchema.array().parse(response)
  },

  getRole: async (roleId: number): Promise<RoleWithPermissions> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.get(`/v1/roles/${roleId}`)
    return RoleWithPermissionsSchema.parse(response)
  },

  createRole: async (data: RoleCreate): Promise<RoleResponse> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.post('/v1/roles', data)
    return RoleResponseSchema.parse(response)
  },

  updateRole: async (roleId: number, data: RoleUpdate): Promise<RoleResponse> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.put(`/v1/roles/${roleId}`, data)
    return RoleResponseSchema.parse(response)
  },

  deleteRole: async (roleId: number): Promise<RoleResponse> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.delete(`/v1/roles/${roleId}`)
    return RoleResponseSchema.parse(response)
  },

  assignRoleToUser: async (roleId: number, userId: number, teamId: number): Promise<RoleMutationResponse> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.post(`/v1/roles/${roleId}/users`, { user_id: userId, role_id: roleId, team_id: teamId })
    return RoleMutationResponseSchema.parse(response)
  },

  removeRoleFromUser: async (roleId: number, userId: number, teamId: number): Promise<RoleMutationResponse> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.delete(`/v1/roles/${roleId}/users/${userId}`, { params: { team_id: teamId } })
    return RoleMutationResponseSchema.parse(response)
  },

  getRoleUsers: async (roleId: number): Promise<RoleUserResponse[]> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.get(`/v1/roles/${roleId}/users`)
    return RoleUserResponseSchema.array().parse(response)
  },

  updateRolePermissions: async (roleId: number, permissionIds: number[]): Promise<PermissionResponse[]> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.put(`/v1/roles/${roleId}/permissions`, {
      permission_ids: permissionIds
    })
    return PermissionResponseSchema.array().parse(response)
  }
}

export default roleApi
