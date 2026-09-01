import { describe, expect, it } from 'vitest'
import {
  DEPRECATED_PERMISSION_CODES,
  getPermissionActionName,
  getPermissionResourceName,
  isAssignablePermission,
  isDeprecatedPermission,
  mergePermissionIdsPreservingDeprecated,
} from '@/constants/permissions'

const permission = (overrides: Partial<{
  code: string
  resource: string
  is_active: boolean
}> = {}): { code: string; resource: string; is_active: boolean } => ({
  code: 'customer:view:own',
  resource: 'customer',
  is_active: true,
  ...overrides,
})

describe('permission catalog', () => {
  it('localizes resource and action labels used by the role permission dialog', () => {
    expect(getPermissionResourceName('customer_profile')).toBe('客户档案')
    expect(getPermissionResourceName('approval_flow')).toBe('审批流程')
    expect(getPermissionActionName('view')).toBe('查看')
    expect(getPermissionActionName('mark_issued')).toBe('标记已开票')
  })
  it('recognizes historical API permissions as deprecated', () => {
    expect(DEPRECATED_PERMISSION_CODES.has('customer:api:list')).toBe(true)
    expect(isDeprecatedPermission(permission({ code: 'customer:api:list', resource: 'api' }))).toBe(true)
    expect(isAssignablePermission(permission({ code: 'customer:api:list', resource: 'api' }))).toBe(false)
  })

  it('hides inactive permissions without deleting them from role associations', () => {
    expect(isDeprecatedPermission(permission({ is_active: false }))).toBe(true)
    expect(isAssignablePermission(permission({ is_active: false }))).toBe(false)
  })

  it('keeps current business permissions assignable', () => {
    expect(isDeprecatedPermission(permission())).toBe(false)
    expect(isAssignablePermission(permission())).toBe(true)
  })

  it('preserves legacy associations when saving a role', () => {
    const currentPermissions = [
      permission({ code: 'customer:api:list', resource: 'api' }),
      permission({ code: 'customer:view:own' }),
    ].map((item, index) => ({ ...item, id: index + 10 }))

    expect(mergePermissionIdsPreservingDeprecated([11], currentPermissions)).toEqual([11, 10])
  })

})
