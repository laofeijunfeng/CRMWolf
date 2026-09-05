import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import permissionApi from '@/api/permissions'
import { logger } from '@/utils/logger'
import type {
  PermissionResponse as UserPermissionResponse,
  UserPermissionsResponse
} from '@/schemas/auth'

export type PermissionLoadState = 'idle' | 'loading' | 'ready' | 'error'

export const usePermissionStore = defineStore('permissions', () => {
  const permissions = ref<UserPermissionResponse[]>([])
  const loading = ref(false)
  const initialized = ref(false)
  const loadState = ref<PermissionLoadState>('idle')
  const loadError = ref<unknown | null>(null)

  const permissionSet = computed(() => {
    return new Set(permissions.value.map(p => p.code))
  })

  // Permission consumers must fail closed until the current team's snapshot
  // has been confirmed. This protects direct callers that do not render
  // through v-permission/Permission.vue (for example row actions and route
  // guards), including the short window during a team switch or refresh.
  const hasPermission = (code: string): boolean => {
    return loadState.value === 'ready' && permissionSet.value.has(code)
  }

  const hasAnyPermission = (codes: string[]): boolean => {
    return loadState.value === 'ready' && codes.some(code => permissionSet.value.has(code))
  }

  const hasAllPermissions = (codes: string[]): boolean => {
    return loadState.value === 'ready' && codes.every(code => permissionSet.value.has(code))
  }

  const canViewOwn = (resource: string): boolean => {
    return hasPermission(`${resource}:view_own`)
  }

  const canViewAll = (resource: string): boolean => {
    return hasPermission(`${resource}:view_all`)
  }

  const canCreate = (resource: string): boolean => {
    return hasPermission(`${resource}:create`)
  }

  const canEditOwn = (resource: string): boolean => {
    return hasPermission(`${resource}:edit_own`)
  }

  const canEditAll = (resource: string): boolean => {
    return hasPermission(`${resource}:edit_all`)
  }

  const canDeleteOwn = (resource: string): boolean => {
    return hasPermission(`${resource}:delete_own`)
  }

  const canDeleteAll = (resource: string): boolean => {
    return hasPermission(`${resource}:delete_all`)
  }

  const canApproveOwn = (resource: string): boolean => {
    return hasPermission(`${resource}:approve:own`)
  }

  const canApproveAll = (resource: string): boolean => {
    return hasPermission(`${resource}:approve:all`)
  }

  const canSubmitApproval = (resource: string): boolean => {
    return hasPermission(`${resource}:submit`)
  }

  const canCancelApproval = (resource: string): boolean => {
    return hasPermission(`${resource}:cancel`)
  }

  let permissionRequestRevision = 0
  let inFlightRequest: Promise<UserPermissionsResponse | undefined> | null = null

  const fetchPermissions = async (): Promise<UserPermissionsResponse | undefined> => {
    if (inFlightRequest !== null) return inFlightRequest

    const requestRevision = permissionRequestRevision + 1
    permissionRequestRevision = requestRevision
    loading.value = true
    loadState.value = 'loading'
    loadError.value = null
    // Never expose the previous team's grants while a new snapshot is being
    // fetched. Direct permission consumers may render before the response
    // settles, so loading must fail closed just like an error does.
    permissions.value = []
    initialized.value = false

    const request = (async (): Promise<UserPermissionsResponse | undefined> => {
      try {
        const response = await permissionApi.getUserPermissions({ use_cache: false })
        // A team switch or explicit refresh may invalidate this response while
        // the network request is still pending. Never publish old-team grants.
        if (requestRevision !== permissionRequestRevision) return undefined

        permissions.value = response.permissions
        initialized.value = true
        loadState.value = 'ready'

        return response
      } catch (error) {
        if (requestRevision === permissionRequestRevision) {
          loadState.value = 'error'
          loadError.value = error
          // Keep the permission set empty when the current team permissions are
          // unavailable. Callers must fail closed instead of allowing a
          // potentially privileged action during an indeterminate state.
          permissions.value = []
          initialized.value = false
          logger.error('[PermissionStore]', 'fetchPermissions:failed', { error })
        }
        throw error
      } finally {
        if (requestRevision === permissionRequestRevision) loading.value = false
      }
    })()

    inFlightRequest = request
    try {
      return await request
    } finally {
      if (inFlightRequest === request) inFlightRequest = null
    }
  }

  const clearPermissions = (): void => {
    permissionRequestRevision += 1
    permissions.value = []
    initialized.value = false
    loadState.value = 'idle'
    loadError.value = null
  }

  const refreshPermissions = async (): Promise<UserPermissionsResponse | undefined> => {
    clearPermissions()
    // Wait for an invalidated request before starting the new team-scoped
    // request. Its response is ignored by the revision guard above.
    if (inFlightRequest !== null) {
      try {
        await inFlightRequest
      } catch {
        // The next request is the actionable refresh attempt.
      }
    }
    return await fetchPermissions()
  }

  return {
    permissions,
    permissionSet,
    loading,
    initialized,
    loadState,
    loadError,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    canViewOwn,
    canViewAll,
    canCreate,
    canEditOwn,
    canEditAll,
    canDeleteOwn,
    canDeleteAll,
    canApproveOwn,
    canApproveAll,
    canSubmitApproval,
    canCancelApproval,
    fetchPermissions,
    clearPermissions,
    refreshPermissions
  }
})
