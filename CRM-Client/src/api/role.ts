import request from '@/utils/request'

export interface PermissionResponse {
  id: number
  code: string
  name: string
  resource: string
  action: string
  scope: string | null
  description: string | null
  created_at: string
  updated_at: string
}

export interface RoleResponse {
  id: number
  code: string
  name: string
  description: string | null
  created_at: string
  updated_at: string
}

export interface RoleWithPermissions {
  id: number
  code: string
  name: string
  description: string | null
  permissions: PermissionResponse[]
  created_at: string
  updated_at: string
}

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
  getRoles: async (params?: RoleQueryParams) => {
    const response = await request.get<RoleResponse[]>('/roles/', { params }) as any
    return response.data || response
  },

  getRole: async (roleId: number) => {
    const response = await request.get<RoleWithPermissions>(`/roles/${roleId}`)
    return response
  },

  createRole: async (data: RoleCreate) => {
    const response = await request.post<RoleResponse>('/roles/', data)
    return response
  },

  updateRole: async (roleId: number, data: RoleUpdate) => {
    const response = await request.put<RoleResponse>(`/roles/${roleId}`, data)
    return response
  },

  deleteRole: async (roleId: number) => {
    const response = await request.delete<RoleResponse>(`/roles/${roleId}`)
    return response
  },

  assignRoleToUser: (roleId: number, userId: number, teamId: number) => {
    return request.post(`/roles/${roleId}/users`, { user_id: userId, role_id: roleId, team_id: teamId })
  },

  removeRoleFromUser: (roleId: number, userId: number, teamId: number) => {
    return request.delete(`/roles/${roleId}/users/${userId}`, { params: { team_id: teamId } })
  },

  updateRolePermissions: async (roleId: number, permissionIds: number[]): Promise<PermissionResponse[]> => {
    const response = await request.put<PermissionResponse[]>(`/roles/${roleId}/permissions`, {
      permission_ids: permissionIds
    })
    return response
  }
}

export default roleApi
