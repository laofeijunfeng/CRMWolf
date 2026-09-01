import { computed, type ComputedRef } from 'vue'
import { usePermissionStore } from '@/stores/permissions'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'
import type { SettingsNavigationItem } from '@/settingsNavigation'

export const isTeamOwner = (userId: number | string | null | undefined, ownerId: number | string | null | undefined): boolean => {
  if (userId === null || userId === undefined || ownerId === null || ownerId === undefined) return false
  return String(userId) === String(ownerId)
}

export const useSettingsAccess = (): {
  isOwner: ComputedRef<boolean>
  canAccess: (item: SettingsNavigationItem) => boolean
} => {
  const permissionStore = usePermissionStore()
  const teamStore = useTeamStore()
  const userStore = useUserStore()

  const isOwner = computed(() => isTeamOwner(
    userStore.userInfo?.id,
    teamStore.currentTeam?.owner_id,
  ))

  const canAccess = (item: SettingsNavigationItem): boolean => {
    if (item.scope === 'personal') return true
    if (item.requiresTeam === true && teamStore.currentTeam === null) return false
    if (isOwner.value) return true
    if (!permissionStore.initialized) return false
    return permissionStore.hasAnyPermission([...item.requiredAnyPermissions])
  }

  return { isOwner, canAccess }
}
