import request from '@/utils/request'
import type { PaginatedResponse } from '@/types/pagination'
import {
  UserListResponseSchema,
  UserResponseSchema,
  UserSearchResultsSchema,
  UserWithRolesResponseSchema,
  UserStatus,
  type UserMutationResponse
} from '@/schemas/user'

export { UserStatus } from '@/schemas/user'

export interface RoleInfo {
  id?: number
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
  getUsers: async (params?: UserQueryParams): Promise<UserResponse[] | PaginatedResponse<UserResponse>> =>
    UserListResponseSchema.parse(await request.get('/v1/users/', { params })),

  getUser: async (userId: number): Promise<UserResponse> =>
    UserWithRolesResponseSchema.parse(await request.get(`/v1/users/${userId}`)),

  createUser: async (data: UserCreate): Promise<UserMutationResponse> =>
    UserResponseSchema.parse(await request.post('/v1/users/', data)),

  updateUser: async (userId: number, data: UserUpdate): Promise<UserMutationResponse> =>
    UserResponseSchema.parse(await request.put(`/v1/users/${userId}`, data)),

  deleteUser: async (userId: number): Promise<UserMutationResponse> =>
    UserResponseSchema.parse(await request.delete(`/v1/users/${userId}`)),

  searchUsers: async (email: string, excludeTeamId?: number): Promise<UserSearchResult[]> => {
    const params: Record<string, unknown> = { email, limit: 10 }
    if (excludeTeamId !== undefined) {
      params['exclude_team_id'] = excludeTeamId
    }
    return UserSearchResultsSchema.parse(await request.get('/v1/users/search', { params }))
  }
}

export default userApi
