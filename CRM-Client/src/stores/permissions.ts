import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import permissionApi, { type PermissionResponse } from '@/api/permissions'

export const usePermissionStore = defineStore('permissions', () => {
  const permissions = ref<PermissionResponse[]>([])
  const loading = ref(false)
  const initialized = ref(false)

  const permissionSet = computed(() => {
    return new Set(permissions.value.map(p => p.code))
  })

  const hasPermission = (code: string): boolean => {
    return permissionSet.value.has(code)
  }

  const hasAnyPermission = (codes: string[]): boolean => {
    return codes.some(code => permissionSet.value.has(code))
  }

  const hasAllPermissions = (codes: string[]): boolean => {
    return codes.every(code => permissionSet.value.has(code))
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

  const fetchPermissions = async () => {
    if (loading.value) return
    
    loading.value = true
    try {
      const response = await permissionApi.getUserPermissions({ use_cache: false }) as any
      permissions.value = response.permissions || []
      initialized.value = true
      
      console.log('========== 权限信息调试 ==========')
      console.log('原始权限数据:', response)
      console.log('权限列表:', permissions.value)
      console.log('权限代码列表:', permissions.value.map(p => p.code))
      console.log('权限集合:', Array.from(permissionSet.value))
      console.log('=================================')
      
      return response
    } catch (error) {
      console.error('获取权限失败', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  const clearPermissions = () => {
    permissions.value = []
    initialized.value = false
  }

  const refreshPermissions = async () => {
    clearPermissions()
    return await fetchPermissions()
  }

  return {
    permissions,
    permissionSet,
    loading,
    initialized,
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
