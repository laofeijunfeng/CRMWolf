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

export interface UserPermissionsResponse {
  permissions: PermissionResponse[]
  total: number
  cached?: boolean
}

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
  getUserPermissions: async (params?: GetUserPermissionsParams) => {
    const response = await request.get<UserPermissionsResponse>('/auth/me/permissions', { 
      params: params || {} 
    })
    return response
  },

  getAllPermissions: async (params?: PermissionQueryParams) => {
    const response = await request.get<PermissionResponse[]>('/permissions', { params })
    return response
  },

  assignPermissionToRole: (permissionId: number, roleId: number) => {
    return request.post(`/permissions/${permissionId}/roles`, { role_id: roleId })
  },

  removePermissionFromRole: (permissionId: number, roleId: number) => {
    return request.delete(`/permissions/${permissionId}/roles/${roleId}`)
  }
}

export default permissionApi
