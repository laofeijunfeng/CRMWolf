import request from '@/utils/request'

export enum UserStatus {
  ACTIVE = 'active',
  INACTIVE = 'inactive'
}

export interface RoleInfo {
  code: string
  name: string
}

export interface UserResponse {
  id: number
  name: string
  email: string
  mobile: string | null
  avatar_url: string | null
  employee_no: string | null
  region: string | null
  status: UserStatus
  roles: RoleInfo[]
  created_at: string
  updated_at: string
}

export interface UserCreate {
  name: string
  email: string
  mobile?: string | null
  avatar_url?: string | null
  region?: string | null
  status?: UserStatus
}

export interface UserUpdate {
  name?: string | null
  email?: string | null
  mobile?: string | null
  avatar_url?: string | null
  region?: string | null
  status?: UserStatus
}

export interface UserQueryParams {
  skip?: number
  limit?: number
  status?: UserStatus | null
  region?: string | null
}

export interface UserSearchResult {
  id: number
  name: string
  email: string
  mobile: string | null
  avatar_url: string | null
  region: string | null
  status: string
}

const userApi = {
  getUsers: async (params?: UserQueryParams) => {
    const response = await request.get<UserResponse[]>('/users/', { params })
    return response
  },

  getUser: async (userId: number) => {
    const response = await request.get<UserResponse>(`/users/${userId}`)
    return response
  },

  createUser: async (data: UserCreate) => {
    const response = await request.post<UserResponse>('/users/', data)
    return response
  },

  updateUser: async (userId: number, data: UserUpdate) => {
    const response = await request.put<UserResponse>(`/users/${userId}`, data)
    return response
  },

  deleteUser: async (userId: number) => {
    const response = await request.delete<UserResponse>(`/users/${userId}`)
    return response
  },

  searchUsers: async (email: string, excludeTeamId?: number) => {
    const params: Record<string, unknown> = { email, limit: 10 }
    if (excludeTeamId) {
      params.exclude_team_id = excludeTeamId
    }
    const response = await request.get<UserSearchResult[]>('/users/search', { params })
    return response
  }
}

export default userApi
