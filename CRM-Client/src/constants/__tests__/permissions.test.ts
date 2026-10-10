import { describe, expect, it } from 'vitest'
import type { PermissionResponse } from '@/schemas/role'
import {
  DEPRECATED_PERMISSION_CODES,
  getPermissionActionName,
  getPermissionResourceName,
  isAssignablePermission,
  isDeprecatedPermission,
  groupAssignablePermissions,
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
const permissionResponse = (
  id: number,
  code: string,
  resource: string,
  name: string,
  action: string,
  isActive = true,
): PermissionResponse => ({
  id,
  code,
  name,
  resource,
  action,
  scope: null,
  description: null,
  is_active: isActive,
  created_at: '2026-09-28T00:00:00Z',
  updated_at: '2026-09-28T00:00:00Z',
})


describe('permission catalog', () => {
  it('localizes resource and action labels used by the role permission dialog', () => {
    expect(getPermissionResourceName('customer_profile')).toBe('客户数据')
    expect(getPermissionResourceName('approval_flow')).toBe('审批流程')
    expect(getPermissionActionName('view')).toBe('查看')
    expect(getPermissionActionName('mark_issued')).toBe('标记已开票')
    expect(getPermissionActionName('export')).toBe('导出')
    expect(getPermissionResourceName('follow_up_task')).toBe('客户追踪')
    expect(getPermissionResourceName('approval')).toBe('审批')
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

  it('groups assignable payment permissions in API order without changing their resources', () => {
    const entries = [
      permissionResponse(1, 'payment:approve', 'payment', '审批回款', 'approve'),
      permissionResponse(2, 'payment:plan:export', 'payment_plan', '导出回款计划', 'export'),
      permissionResponse(3, 'payment:record:export', 'payment_record', '导出回款记录', 'export'),
      permissionResponse(4, 'customer:view:all', 'customer', '查看所有客户', 'view'),
      permissionResponse(5, 'payment:api:list', 'api', '旧回款 API', 'view'),
      permissionResponse(6, 'payment:record:inactive', 'payment_record', '停用回款权限', 'view', false),
    ]
    const groups = groupAssignablePermissions(entries)

    expect(groups.map(group => group.resource)).toEqual(['payment', 'customer'])
    expect(groups[0]?.permissions).toEqual(entries.slice(0, 3))
    expect(groups[0]?.permissions.map(item => item.resource)).toEqual([
      'payment', 'payment_plan', 'payment_record',
    ])
    expect(groups[0]?.permissions[2]).toBe(entries[2])
  })

})
