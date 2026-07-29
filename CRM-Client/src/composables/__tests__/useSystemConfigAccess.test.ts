import { describe, expect, it } from 'vitest'
import {
  canAccessSystemConfig,
  hasTeamAdminRole,
  SYSTEM_CONFIG_PERMISSION_CODES,
} from '../useSystemConfigAccess'

type PermissionStore = Parameters<typeof canAccessSystemConfig>[0]

const makePermissionStore = (codes: string[]): PermissionStore => ({
  hasAnyPermission: (requestedCodes: string[]) => requestedCodes.some(code => codes.includes(code)),
}) as unknown as PermissionStore

describe('useSystemConfigAccess', () => {
  it('allows access when the user has any system config permission', () => {
    for (const code of SYSTEM_CONFIG_PERMISSION_CODES) {
      expect(canAccessSystemConfig(makePermissionStore([code]) as never, [])).toBe(true)
    }
  })

  it('allows access for team admins even when no permission code is loaded', () => {
    expect(canAccessSystemConfig(makePermissionStore([]) as never, [{ code: 'TEAM_ADMIN' }])).toBe(true)
    expect(hasTeamAdminRole([{ code: 'SALES_MEMBER' }])).toBe(false)
  })

  it('denies access when the user has neither config permissions nor team admin role', () => {
    expect(canAccessSystemConfig(makePermissionStore(['lead:view_all']) as never, [{ code: 'SALES_MEMBER' }])).toBe(false)
  })
})
