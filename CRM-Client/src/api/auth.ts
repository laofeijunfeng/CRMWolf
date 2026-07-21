import request from '@/utils/request'
import {
  LoginResponseSchema,
  MessageResponseSchema,
  RoleResponseSchema,
  UserPermissionsResponseSchema,
  UserResponseSchema,
  type LoginResponse,
  type MessageResponse,
  type RoleResponse,
  type UserPermissionsResponse,
  type UserResponse,
} from '@/schemas/auth'

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

export type {
  LoginResponse,
  PermissionResponse,
  RoleResponse,
  UserPermissionsResponse,
  UserResponse,
} from '@/schemas/auth'

export interface ChangePasswordRequest {
  old_password: string
  new_password: string
}

export const authApi = {
  // 发送验证码
  async sendCode(params: SendCodeParams): Promise<MessageResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.post('/v1/auth/send-code', params)
    return MessageResponseSchema.parse(raw)
  },

  // 邮箱注册
  async register(data: RegisterRequest): Promise<LoginResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.post('/v1/auth/register', data)
    return LoginResponseSchema.parse(raw)
  },

  // 验证码登录
  async loginWithCode(data: LoginCodeRequest): Promise<LoginResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.post('/v1/auth/login', data)
    return LoginResponseSchema.parse(raw)
  },

  // 密码登录
  async loginWithPassword(data: LoginPasswordRequest): Promise<LoginResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.post('/v1/auth/login-password', data)
    return LoginResponseSchema.parse(raw)
  },

  // 密码注册
  async registerWithPassword(data: RegisterPasswordRequest): Promise<LoginResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.post('/v1/auth/register-password', data)
    return LoginResponseSchema.parse(raw)
  },

  // 获取当前用户信息
  async getUserInfo(): Promise<UserResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get('/v1/auth/me')
    return UserResponseSchema.parse(raw)
  },

  // 获取当前用户角色
  async getUserRoles(): Promise<RoleResponse[]> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get('/v1/auth/me/roles')
    return RoleResponseSchema.array().parse(raw)
  },

  // 获取当前用户权限
  async getUserPermissions(useCache = true): Promise<UserPermissionsResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get('/v1/auth/me/permissions', { params: { use_cache: useCache } })
    return UserPermissionsResponseSchema.parse(raw)
  },

  // 修改密码
  async changePassword(data: ChangePasswordRequest): Promise<MessageResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.post('/v1/auth/me/change-password', data)
    return MessageResponseSchema.parse(raw)
  }
}
