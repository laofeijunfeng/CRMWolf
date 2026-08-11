import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authApi, type UserResponse } from '@/api/auth'
import { logger } from '@/utils/logger'
import { usePermissionStore } from './permissions'
import { useTeamStore } from './team'

export const useUserStore = defineStore('user', () => {
  const token = ref<string>(localStorage.getItem('token') ?? '')
  const userInfo = ref<UserResponse | null>(null)

  const loading = ref(false)

  const setToken = (newToken: string): void => {
    token.value = newToken
    localStorage.setItem('token', newToken)
  }

  const setUserInfo = (info: UserResponse): void => {
    userInfo.value = info
  }

  const login = async (): Promise<void> => {
    loading.value = true
    try {
      const permissionStore = usePermissionStore()
      await permissionStore.fetchPermissions()
    } catch (error) {
      logger.error('[UserStore]', 'loginPermissions:failed', { error })
    } finally {
      loading.value = false
    }
  }

  const fetchUserInfo = async (): Promise<UserResponse> => {
    loading.value = true
    try {
      const res = await authApi.getUserInfo()

      try {
        const roles = await authApi.getUserRoles()
        setUserInfo({ ...res, roles })
      } catch (roleError) {
        logger.warn('[UserStore]', 'fetchUserRoles:failed', { error: roleError })
        setUserInfo(res)
      }

      logger.debug('[UserStore]', 'fetchUserInfo:success', {
        userId: res.id,
        name: res.name,
        email: res.email,
      })

      return res
    } catch (error) {
      logger.error('[UserStore]', 'fetchUserInfo:failed', { error })
      throw error
    } finally {
      loading.value = false
    }
  }

  const logout = (): void => {
    const permissionStore = usePermissionStore()
    const teamStore = useTeamStore()

    token.value = ''
    userInfo.value = null
    localStorage.removeItem('token')
    permissionStore.clearPermissions()
    teamStore.clearTeam()
  }

  const isLoggedIn = (): boolean => {
    return token.value.length > 0
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
