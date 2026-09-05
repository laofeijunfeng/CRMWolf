import { defineStore } from 'pinia'
import { ref } from 'vue'
import { teamApi, type TeamResponse } from '@/api/team'
import { logger } from '@/utils/logger'
import { usePermissionStore } from './permissions'

export type PermissionSyncState = 'idle' | 'loading' | 'ready' | 'error'

export const useTeamStore = defineStore('team', () => {
  const teams = ref<TeamResponse[]>([])
  const currentTeam = ref<TeamResponse | null>(null)
  const loading = ref(false)
  const loadState = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const loadError = ref<unknown | null>(null)
  const switchRevision = ref(0)
  const permissionSyncState = ref<PermissionSyncState>('idle')
  const permissionSyncError = ref<unknown | null>(null)

  const fetchUserTeams = async (): Promise<TeamResponse[]> => {
    loading.value = true
    loadState.value = 'loading'
    loadError.value = null
    try {
      const res = await teamApi.getUserTeams()
      teams.value = res.teams

      loadState.value = 'ready'

      currentTeam.value = res.teams.find(t => t.id === res.current_team_id) ?? res.teams[0] ?? null

      return res.teams
    } catch (error) {
      loadState.value = 'error'
      loadError.value = error
      logger.error('[TeamStore]', 'fetchUserTeams:failed', { error })
      // Keep the last known team context. A transient list request failure is
      // not evidence that the user has no team.
      throw error
    } finally {
      loading.value = false
    }
  }

  const syncTeamPermissions = async (): Promise<boolean> => {
    permissionSyncState.value = 'loading'
    permissionSyncError.value = null
    try {
      const permissionStore = usePermissionStore()
      await permissionStore.refreshPermissions()
      permissionSyncState.value = 'ready'
      return true
    } catch (error) {
      permissionSyncState.value = 'error'
      permissionSyncError.value = error
      logger.warn('[TeamStore]', 'syncTeamPermissions:failed', { error })
      return false
    }
  }

  const retryPermissionSync = async (): Promise<boolean> => syncTeamPermissions()

  const switchTeam = async (teamId: number): Promise<void> => {
    loading.value = true
    try {
      await teamApi.switchTeam(teamId)
      currentTeam.value = teams.value.find(t => t.id === teamId) ?? null
      switchRevision.value += 1
      // 团队切换已成功；权限刷新失败不能把已完成的切换误报成失败。
      await syncTeamPermissions()
    } catch (error) {
      logger.error('[TeamStore]', 'switchTeam:failed', { teamId, error })
      throw error
    } finally {
      loading.value = false
    }
  }

  const createTeam = async (name: string): Promise<TeamResponse> => {
    loading.value = true
    try {
      const team = await teamApi.createTeam({ name })
      teams.value.push(team)
      currentTeam.value = team
      // 创建团队已成功；权限同步失败不应让用户误以为团队没有创建。
      await syncTeamPermissions()
      return team
    } catch (error) {
      logger.error('[TeamStore]', 'createTeam:failed', { error })
      throw error
    } finally {
      loading.value = false
    }
  }

  const joinTeam = async (code: string): Promise<TeamResponse> => {
    loading.value = true
    try {
      const team = await teamApi.joinTeam({ code })
      teams.value.push(team)
      currentTeam.value = team
      // 加入团队已成功；权限同步失败不应让用户误以为加入没有生效。
      await syncTeamPermissions()
      return team
    } catch (error) {
      logger.error('[TeamStore]', 'joinTeam:failed', { error })
      throw error
    } finally {
      loading.value = false
    }
  }

  const hasTeam = (): boolean => {
    return currentTeam.value !== null
  }

  const hasAnyTeam = (): boolean => {
    return teams.value.length > 0
  }

  const clearTeam = (): void => {
    teams.value = []
    currentTeam.value = null
    loadState.value = 'idle'
    loadError.value = null
    permissionSyncState.value = 'idle'
    permissionSyncError.value = null
  }

  return {
    teams,
    currentTeam,
    loading,
    loadState,
    loadError,
    switchRevision,
    permissionSyncState,
    permissionSyncError,
    fetchUserTeams,
    switchTeam,
    retryPermissionSync,
    createTeam,
    joinTeam,
    hasTeam,
    hasAnyTeam,
    clearTeam
  }
})
