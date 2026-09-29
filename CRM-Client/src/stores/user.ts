import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authApi, type UserResponse } from '@/api/auth'
import { logger } from '@/utils/logger'
import { usePermissionStore } from './permissions'
import { useTeamStore } from './team'

const TOKEN_STORAGE_KEY = 'token'

const isTokenExpired = (value: string): boolean => {
  const payloadPart = value.split('.')[1]
  if (payloadPart === undefined || payloadPart === '') return true
  try {
    const decoded = JSON.parse(atob(payloadPart.replace(/-/g, '+').replace(/_/g, '/'))) as { exp?: unknown }
    if (typeof decoded.exp !== 'number') return false
    return decoded.exp * 1000 <= Date.now()
  } catch {
    return false
  }
}

/** Drops a leftover token that is expired so the router treats the session as logged out. */
const readStoredToken = (): string => {
  const stored = localStorage.getItem(TOKEN_STORAGE_KEY) ?? ''
  if (stored !== '' && isTokenExpired(stored)) {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
    return ''
  }
  return stored
}
export const useUserStore = defineStore('user', () => {

  const token = ref<string>(readStoredToken())
  const userInfo = ref<UserResponse | null>(null)
  const loading = ref(false)

  const setToken = (newToken: string): void => {
    token.value = newToken
    localStorage.setItem(TOKEN_STORAGE_KEY, newToken)
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
    localStorage.removeItem(TOKEN_STORAGE_KEY)
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
