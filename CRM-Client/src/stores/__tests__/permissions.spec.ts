import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const permissionApi = vi.hoisted(() => ({
  getUserPermissions: vi.fn(),
}))

vi.mock('@/api/permissions', () => ({ default: permissionApi }))

import { usePermissionStore } from '@/stores/permissions'

const permissionsResponse = {
  permissions: [{
    id: 1,
    code: 'customer:edit:all',
    name: '编辑全部客户',
    resource: 'customer',
    action: 'edit',
    scope: 'all',
    description: null,
  }],
  total: 1,
  cached: false,
}

describe('usePermissionStore loading contract', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('exposes a ready state only after a successful permission response', async () => {
    const store = usePermissionStore()
    permissionApi.getUserPermissions.mockResolvedValueOnce(permissionsResponse)

    const result = await store.fetchPermissions()

    expect(result).toEqual(permissionsResponse)
    expect(store.loadState).toBe('ready')
    expect(store.loadError).toBeNull()
    expect(store.initialized).toBe(true)
    expect(store.hasPermission('customer:edit:all')).toBe(true)
  })

  it('fails closed for direct permission consumers while a refresh is pending', async () => {
    const store = usePermissionStore()
    permissionApi.getUserPermissions.mockResolvedValueOnce(permissionsResponse)
    await store.fetchPermissions()

    let resolveRefresh: ((value: typeof permissionsResponse) => void) | undefined
    permissionApi.getUserPermissions.mockReturnValueOnce(new Promise<typeof permissionsResponse>((resolve) => {
      resolveRefresh = resolve
    }))

    const refresh = store.refreshPermissions()
    await Promise.resolve()

    expect(store.loadState).toBe('loading')
    expect(store.hasPermission('customer:edit:all')).toBe(false)
    expect(store.hasAnyPermission(['customer:edit:all'])).toBe(false)
    expect(store.hasAllPermissions(['customer:edit:all'])).toBe(false)

    resolveRefresh?.(permissionsResponse)
    await refresh
    expect(store.hasPermission('customer:edit:all')).toBe(true)
  })

  it('fails closed and exposes an actionable error state when loading fails', async () => {
    const store = usePermissionStore()
    permissionApi.getUserPermissions.mockRejectedValueOnce(new Error('permission service unavailable'))

    await expect(store.fetchPermissions()).rejects.toThrow('permission service unavailable')

    expect(store.loadState).toBe('error')
    expect(store.loadError).toBeInstanceOf(Error)
    expect(store.initialized).toBe(false)
    expect(store.hasPermission('customer:edit:all')).toBe(false)
  })


  it('does not let an invalidated request overwrite the refreshed permission set', async () => {
    const store = usePermissionStore()
    let resolveInitial: ((value: typeof permissionsResponse) => void) | undefined
    const initialRequest = new Promise<typeof permissionsResponse>((resolve) => {
      resolveInitial = resolve
    })
    permissionApi.getUserPermissions
      .mockReturnValueOnce(initialRequest)
      .mockResolvedValueOnce({ ...permissionsResponse, permissions: [], total: 0 })

    const initialFetch = store.fetchPermissions()
    await Promise.resolve()
    const refresh = store.refreshPermissions()

    expect(store.loadState).toBe('idle')
    resolveInitial?.(permissionsResponse)

    await expect(initialFetch).resolves.toBeUndefined()
    await expect(refresh).resolves.toEqual({ ...permissionsResponse, permissions: [], total: 0 })

    expect(permissionApi.getUserPermissions).toHaveBeenCalledTimes(2)
    expect(store.loadState).toBe('ready')
    expect(store.permissions).toEqual([])
    expect(store.hasPermission('customer:edit:all')).toBe(false)
  })

  it('clears the previous permission snapshot before a new request settles', async () => {
    const store = usePermissionStore()
    permissionApi.getUserPermissions.mockResolvedValueOnce(permissionsResponse)
    await store.fetchPermissions()

    let resolveRefresh: ((value: typeof permissionsResponse) => void) | undefined
    const pendingRefresh = new Promise<typeof permissionsResponse>((resolve) => {
      resolveRefresh = resolve
    })
    permissionApi.getUserPermissions.mockReturnValueOnce(pendingRefresh)

    const refresh = store.refreshPermissions()
    await Promise.resolve()

    expect(store.loadState).toBe('loading')
    expect(store.permissions).toEqual([])
    expect(store.hasPermission('customer:edit:all')).toBe(false)

    resolveRefresh?.(permissionsResponse)
    await refresh
    expect(store.loadState).toBe('ready')
    expect(store.hasPermission('customer:edit:all')).toBe(true)
  })

  it('keeps the refreshed request authoritative when the invalidated request fails', async () => {
    const store = usePermissionStore()
    let rejectInitial: ((reason?: unknown) => void) | undefined
    const initialRequest = new Promise<typeof permissionsResponse>((_resolve, reject) => {
      rejectInitial = reject
    })
    permissionApi.getUserPermissions
      .mockReturnValueOnce(initialRequest)
      .mockResolvedValueOnce(permissionsResponse)

    const initialFetch = store.fetchPermissions()
    await Promise.resolve()
    const refresh = store.refreshPermissions()

    rejectInitial?.(new Error('old team request failed'))

    await expect(initialFetch).rejects.toThrow('old team request failed')
    await expect(refresh).resolves.toEqual(permissionsResponse)

    expect(store.loadState).toBe('ready')
    expect(store.loadError).toBeNull()
    expect(store.hasPermission('customer:edit:all')).toBe(true)
  })

  it('clears stale permissions before a refresh and returns to ready after retry', async () => {
    const store = usePermissionStore()
    permissionApi.getUserPermissions
      .mockResolvedValueOnce(permissionsResponse)
      .mockResolvedValueOnce({ ...permissionsResponse, permissions: [] , total: 0 })

    await store.fetchPermissions()
    await store.refreshPermissions()

    expect(store.loadState).toBe('ready')
    expect(store.permissions).toEqual([])
    expect(store.hasPermission('customer:edit:all')).toBe(false)
  })
})
