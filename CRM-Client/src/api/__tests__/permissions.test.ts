import { describe, expect, it, vi } from 'vitest'
import type { PermissionResponse } from '@/schemas/role'

const get = vi.fn()

vi.mock('@/utils/request', () => ({
  default: { get },
}))

const permissions: PermissionResponse[] = Array.from({ length: 150 }, (_, index) => ({
  id: index + 1,
  code: index >= 141 ? `resource-${index}:export` : `resource-${index}:view`,
  name: `权限 ${index + 1}`,
  resource: `resource-${index}`,
  action: index >= 141 ? 'export' : 'view',
  scope: null,
  description: null,
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}))

describe('getAllPermissions', () => {
  it('includes assignable permissions beyond the API 100-row page limit', async () => {
    get.mockImplementation((_url: string, config?: { params?: { skip?: number; limit?: number } }) => {
      const { skip = 0, limit = 100 } = config?.params ?? {}
      return Promise.resolve(permissions.slice(skip, skip + Math.min(limit, 100)))
    })

    const { default: permissionApi } = await import('../permissions')
    const catalog = await permissionApi.getAllPermissions()

    expect(catalog.map(permission => permission.id)).toEqual(permissions.map(permission => permission.id))
    expect(catalog.filter(permission => permission.action === 'export')).toHaveLength(9)
  })
})
