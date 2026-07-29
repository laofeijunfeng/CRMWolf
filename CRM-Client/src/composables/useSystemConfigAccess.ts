import { computed, type ComputedRef } from 'vue'
import type { RoleResponse } from '@/api/auth'
import type { usePermissionStore } from '@/stores/permissions'

export const SYSTEM_CONFIG_PERMISSION_CODES = [
  'role:manage',
  'approval:flow:create',
  'approval:flow:edit',
  'procurement_method:view',
  'system:config',
  'ai:manage',
] as const

export const SYSTEM_CONFIG_TEAM_ADMIN_ROLE = 'TEAM_ADMIN'

type PermissionStore = ReturnType<typeof usePermissionStore>

export const hasTeamAdminRole = (roles: readonly Pick<RoleResponse, 'code'>[] | null | undefined): boolean => {
  return roles?.some(role => role.code === SYSTEM_CONFIG_TEAM_ADMIN_ROLE) ?? false
}

export const hasSystemConfigPermission = (permissionStore: PermissionStore): boolean => {
  return permissionStore.hasAnyPermission([...SYSTEM_CONFIG_PERMISSION_CODES])
}

export const canAccessSystemConfig = (
  permissionStore: PermissionStore,
  roles: readonly Pick<RoleResponse, 'code'>[] | null | undefined,
): boolean => {
  return hasSystemConfigPermission(permissionStore) || hasTeamAdminRole(roles)
}

export const useSystemConfigAccess = (
  permissionStore: PermissionStore,
  roles: ComputedRef<readonly Pick<RoleResponse, 'code'>[] | null | undefined>,
): { canAccess: ComputedRef<boolean> } => {
  const canAccess = computed(() => canAccessSystemConfig(permissionStore, roles.value))

  return {
    canAccess,
  }
}
