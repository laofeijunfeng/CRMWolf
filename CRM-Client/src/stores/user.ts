import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authApi, type LoginParams, type LoginResponse, type UserInfoResponse } from '@/api/auth'
import { usePermissionStore } from './permissions'

export const useUserStore = defineStore('user', () => {
  const token = ref<string>(localStorage.getItem('token') || '')
  const userInfo = ref<UserInfoResponse | null>(null)
  const loading = ref(false)

  const setToken = (newToken: string) => {
    token.value = newToken
    localStorage.setItem('token', newToken)
  }

  const setUserInfo = (info: UserInfoResponse) => {
    userInfo.value = info
  }

  const login = async (params: LoginParams) => {
    loading.value = true
    try {
      const res = await authApi.login(params) as unknown as LoginResponse
      setToken(res.access_token)
      
      const user = res.user as any
      
      try {
        const roles = await authApi.getUserRoles()
        user.roles = roles
      } catch (roleError) {
        console.warn('获取用户角色失败', roleError)
        user.roles = []
      }
      
      setUserInfo(user as unknown as UserInfoResponse)
      
      console.log('========== 用户登录信息 ==========')
      console.log('用户信息:', user)
      console.log('用户ID:', user.id)
      console.log('用户名:', user.name)
      console.log('飞书ID:', user.feishu_open_id)
      console.log('角色信息:', user.roles)
      if (user.roles && user.roles.length > 0) {
        console.log('角色列表:', user.roles.map((r: any) => `${r.name}(${r.code})`))
      }
      console.log('====================================')
      
      const permissionStore = usePermissionStore()
      await permissionStore.fetchPermissions()
      
      return res
    } catch (error) {
      console.error('登录失败', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  const fetchUserInfo = async () => {
    loading.value = true
    try {
      const res = await authApi.getUserInfo() as any
      
      try {
        const roles = await authApi.getUserRoles()
        res.roles = roles
      } catch (roleError) {
        console.warn('获取用户角色失败', roleError)
        res.roles = []
      }
      
      setUserInfo(res)
      
      console.log('========== 获取用户信息 ==========')
      console.log('用户信息:', res)
      console.log('用户ID:', res.id)
      console.log('用户名:', res.name)
      console.log('飞书ID:', res.feishu_open_id)
      console.log('角色信息:', res.roles)
      if (res.roles && res.roles.length > 0) {
        console.log('角色列表:', res.roles.map((r: any) => `${r.name}(${r.code})`))
      }
      console.log('====================================')
      
      return res
    } catch (error) {
      console.error('获取用户信息失败', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  const logout = () => {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('token')
  }

  const isLoggedIn = () => {
    return !!token.value
  }

  return {
    token,
    userInfo,
    loading,
    setToken,
    setUserInfo,
    login,
    fetchUserInfo,
    logout,
    isLoggedIn
  }
})
