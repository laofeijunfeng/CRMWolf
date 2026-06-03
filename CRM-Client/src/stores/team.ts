import { defineStore } from 'pinia'
import { ref } from 'vue'
import { teamApi, type TeamResponse } from '@/api/team'
import { usePermissionStore } from './permissions'

export const useTeamStore = defineStore('team', () => {
  const teams = ref<TeamResponse[]>([])
  const currentTeam = ref<TeamResponse | null>(null)
  const loading = ref(false)

  const fetchUserTeams = async () => {
    loading.value = true
    try {
      const res = await teamApi.getUserTeams()
      teams.value = res.teams

      if (res.teams.length === 1) {
        currentTeam.value = res.teams[0]
      } else if (res.teams.length > 1 && res.current_team_id) {
        currentTeam.value = res.teams.find(t => t.id === res.current_team_id) || res.teams[0]
      }

      return res.teams
    } catch (error) {
      console.error('获取用户团队失败', error)
      teams.value = []
      currentTeam.value = null
      throw error
    } finally {
      loading.value = false
    }
  }

  const switchTeam = async (teamId: number) => {
    loading.value = true
    try {
      await teamApi.switchTeam(teamId)
      currentTeam.value = teams.value.find(t => t.id === teamId) || null
      // 切换团队后刷新权限
      const permissionStore = usePermissionStore()
      await permissionStore.refreshPermissions()
    } catch (error) {
      console.error('切换团队失败', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  const createTeam = async (name: string) => {
    loading.value = true
    try {
      const team = await teamApi.createTeam({ name })
      teams.value.push(team)
      currentTeam.value = team
      // 创建团队后刷新权限（获得 TEAM_ADMIN 角色）
      const permissionStore = usePermissionStore()
      await permissionStore.refreshPermissions()
      return team
    } catch (error) {
      console.error('创建团队失败', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  const joinTeam = async (code: string) => {
    loading.value = true
    try {
      const team = await teamApi.joinTeam({ code })
      teams.value.push(team)
      currentTeam.value = team
      // 加入团队后刷新权限（获得 SALES_MEMBER 角色）
      const permissionStore = usePermissionStore()
      await permissionStore.refreshPermissions()
      return team
    } catch (error) {
      console.error('加入团队失败', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  const hasTeam = () => {
    return !!currentTeam.value
  }

  const hasAnyTeam = () => {
    return teams.value.length > 0
  }

  const clearTeam = () => {
    teams.value = []
    currentTeam.value = null
  }

  return {
    teams,
    currentTeam,
    loading,
    fetchUserTeams,
    switchTeam,
    createTeam,
    joinTeam,
    hasTeam,
    hasAnyTeam,
    clearTeam
  }
})