import { usePermissionStore } from '@/stores/permissions'

export const checkPermission = (permission: string): boolean => {
  const permissionStore = usePermissionStore()
  return permissionStore.hasPermission(permission)
}

export const checkAnyPermission = (permissions: string[]): boolean => {
  const permissionStore = usePermissionStore()
  return permissionStore.hasAnyPermission(permissions)
}

export const checkAllPermissions = (permissions: string[]): boolean => {
  const permissionStore = usePermissionStore()
  return permissionStore.hasAllPermissions(permissions)
}

export const checkResourcePermission = (
  resource: string,
  action: string,
  scope?: string
): boolean => {
  const permissionStore = usePermissionStore()
  const code = scope ? `${resource}:${action}:${scope}` : `${resource}:${action}`
  return permissionStore.hasPermission(code)
}

export const canCreateResource = (resource: string): boolean => {
  const permissionStore = usePermissionStore()
  return permissionStore.canCreate(resource)
}

export const canEditOwnResource = (resource: string): boolean => {
  const permissionStore = usePermissionStore()
  return permissionStore.canEditOwn(resource)
}

export const canEditAllResource = (resource: string): boolean => {
  const permissionStore = usePermissionStore()
  return permissionStore.canEditAll(resource)
}

export const canDeleteOwnResource = (resource: string): boolean => {
  const permissionStore = usePermissionStore()
  return permissionStore.canDeleteOwn(resource)
}

export const canViewOwnResource = (resource: string): boolean => {
  const permissionStore = usePermissionStore()
  return permissionStore.canViewOwn(resource)
}

export const canViewAllResource = (resource: string): boolean => {
  const permissionStore = usePermissionStore()
  return permissionStore.canViewAll(resource)
}

export const canApproveOwnResource = (resource: string): boolean => {
  const permissionStore = usePermissionStore()
  return permissionStore.canApproveOwn(resource)
}

export const canApproveAllResource = (resource: string): boolean => {
  const permissionStore = usePermissionStore()
  return permissionStore.canApproveAll(resource)
}

export const canSubmitApproval = (resource: string): boolean => {
  const permissionStore = usePermissionStore()
  return permissionStore.canSubmitApproval(resource)
}

export const canCancelApproval = (resource: string): boolean => {
  const permissionStore = usePermissionStore()
  return permissionStore.canCancelApproval(resource)
}
