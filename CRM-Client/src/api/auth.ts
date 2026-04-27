import request from '@/utils/request'

export interface LoginParams {
  code: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: {
    id: string
    name: string
    email?: string
    avatar_url?: string
  }
}

export interface UserInfoResponse {
  id: string
  feishu_open_id: string
  name: string
  email?: string
  avatar_url?: string
  status: string
  created_time: string
  roles?: RoleResponse[]
}

export interface MockLoginRequest {
  name: string
  email: string
  mobile: string
  region: string
}

export interface CreateAdminRequest {
  name: string
  email: string
}

export interface CreateSalesDirectorRequest {
  name: string
  email: string
  region: string
}

export interface CreateSalesMemberRequest {
  name: string
  email: string
  region: string
}

export interface RoleResponse {
  id: number
  name: string
  code: string
  description?: string
  created_at: string
  updated_at: string
}

export const authApi = {
  login: (params: LoginParams) => {
    return request.post<LoginResponse>('/auth/login', null, { params })
  },

  getUserInfo: () => {
    return request.get<UserInfoResponse>('/auth/me')
  },

  getUserRoles: () => {
    return request.get<RoleResponse[]>('/auth/me/roles')
  },

  mockLogin: (data: MockLoginRequest) => {
    return request.post<LoginResponse>('/dev/mock-login', data)
  },

  createAdmin: (data: CreateAdminRequest) => {
    return request.post<LoginResponse>('/dev/create-admin', data)
  },

  createSalesDirector: (data: CreateSalesDirectorRequest) => {
    return request.post<LoginResponse>('/dev/create-sales-director', data)
  },

  createSalesMember: (data: CreateSalesMemberRequest) => {
    return request.post<LoginResponse>('/dev/create-sales-member', data)
  }
}
