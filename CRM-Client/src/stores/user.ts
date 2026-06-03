import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authApi, type UserResponse } from '@/api/auth'
import { usePermissionStore } from './permissions'

export const useUserStore = defineStore('user', () => {
  const token = ref<string>(localStorage.getItem('token') || '')
  const userInfo = ref<UserResponse | null>(null)
  const loading = ref(false)

  const setToken = (newToken: string) => {
    token.value = newToken
    localStorage.setItem('token', newToken)
  }

  const setUserInfo = (info: UserResponse & { roles?: { id: number; name: string; code: string }[] }) => {
    userInfo.value = info
  }

  const login = async () => {
    loading.value = true
    try {
      const permissionStore = usePermissionStore()
      await permissionStore.fetchPermissions()
    } catch (error) {
      console.error('获取权限失败', error)
    } finally {
      loading.value = false
    }
  }

  const fetchUserInfo = async () => {
    loading.value = true
    try {
      const res = await authApi.getUserInfo()

      try {
        const roles = await authApi.getUserRoles()
        setUserInfo({ ...res, roles })
      } catch (roleError) {
        console.warn('获取用户角色失败', roleError)
        setUserInfo(res)
      }

      console.log('========== 获取用户信息 ==========')
      console.log('用户信息:', res)
      console.log('用户ID:', res.id)
      console.log('用户名:', res.name)
      console.log('邮箱:', res.email)
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