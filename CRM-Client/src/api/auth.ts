import request from '@/utils/request'

export interface SendCodeParams {
  email: string
  purpose: 'register' | 'login' | 'reset_password'
}

export interface RegisterRequest {
  email: string
  code: string
  name: string
  password?: string
}

export interface RegisterPasswordRequest {
  email: string
  name: string
  password: string
}

export interface LoginCodeRequest {
  email: string
  code: string
}

export interface LoginPasswordRequest {
  email: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: UserResponse
}

export interface UserResponse {
  id: number
  name: string
  email: string
  mobile?: string
  avatar_url?: string
  employee_no?: string
  region?: string
  status: string
  created_at: string
  updated_at: string
}

export interface RoleResponse {
  id: number
  name: string
  code: string
  description?: string
  created_at: string
  updated_at: string
}

export interface PermissionResponse {
  id: number
  code: string
  name: string
  resource: string
  action: string
  scope?: string
  description?: string
}

export const authApi = {
  // 发送验证码
  sendCode: (params: SendCodeParams) => {
    return request.post<{ message: string }>('/auth/send-code', params)
  },

  // 邮箱注册
  register: (data: RegisterRequest) => {
    return request.post<LoginResponse>('/auth/register', data)
  },

  // 验证码登录
  loginWithCode: (data: LoginCodeRequest) => {
    return request.post<LoginResponse>('/auth/login', data)
  },

  // 密码登录
  loginWithPassword: (data: LoginPasswordRequest) => {
    return request.post<LoginResponse>('/auth/login-password', data)
  },

  // 密码注册
  registerWithPassword: (data: RegisterPasswordRequest) => {
    return request.post<LoginResponse>('/auth/register-password', data)
  },

  // 获取当前用户信息
  getUserInfo: () => {
    return request.get<UserResponse>('/auth/me')
  },

  // 获取当前用户角色
  getUserRoles: () => {
    return request.get<RoleResponse[]>('/auth/me/roles')
  },

  // 获取当前用户权限
  getUserPermissions: (useCache = true) => {
    return request.get<{ permissions: PermissionResponse[], total: number, cached: boolean }>('/auth/me/permissions', { params: { use_cache: useCache } })
  }
}