import { beforeEach, describe, expect, it, vi } from 'vitest'

const { requestMock } = vi.hoisted(() => ({
  requestMock: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('@/utils/request', () => ({
  default: requestMock,
}))

import permissionApi from '@/api/permissions'

describe('permissionApi', () => {
  beforeEach(() => {
    requestMock.get.mockReset()
    requestMock.post.mockReset()
    requestMock.delete.mockReset()
  })

  it('accepts current-user permissions without audit timestamps', async () => {
    requestMock.get.mockResolvedValue({
      permissions: [
        {
          id: 1,
          code: 'sales_dashboard:view:own',
          name: '查看自己的销售看板',
          resource: 'sales_dashboard',
          action: 'view',
          scope: 'own',
          description: null,
        },
      ],
      total: 1,
      cached: false,
    })

    const response = await permissionApi.getUserPermissions({ use_cache: false })

    expect(requestMock.get).toHaveBeenCalledWith('/v1/auth/me/permissions', {
      params: { use_cache: false },
    })
    expect(response.permissions[0]?.code).toBe('sales_dashboard:view:own')
  })
})
