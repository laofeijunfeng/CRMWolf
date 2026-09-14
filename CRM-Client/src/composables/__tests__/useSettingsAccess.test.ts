import { describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { getSettingsNavigationItem, type SettingsNavigationItem } from '@/settingsNavigation'
import { usePermissionStore } from '@/stores/permissions'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'
import type { UserResponse } from '@/schemas/auth'
import { isTeamOwner, useSettingsAccess } from '../useSettingsAccess'

const setupOwner = (): void => {
  setActivePinia(createPinia())
  const teamStore = useTeamStore()
  const userStore = useUserStore()
  teamStore.currentTeam = {
    id: 1,
    name: '团队',
    code: 'TEAM',
    owner_id: '12',
    created_at: '',
  }
  userStore.userInfo = {
    id: 12,
    name: '所有者',
    email: 'owner@example.com',
    mobile: null,
    avatar_url: null,
    employee_no: null,
    region: null,
    status: 'active',
    created_at: null,
    updated_at: null,
    roles: null,
  } satisfies UserResponse
}
const productsItem = (): SettingsNavigationItem => {
  const item = getSettingsNavigationItem('products')
  if (item === undefined) throw new Error('products settings item is not registered')
  return item
}

describe('useSettingsAccess', () => {
  it('compares owner identifiers without depending on response primitive types', () => {
    expect(isTeamOwner(12, '12')).toBe(true)
    expect(isTeamOwner('12', 13)).toBe(false)
  })

  it('does not treat missing team or user context as owner', () => {
    expect(isTeamOwner(undefined, '12')).toBe(false)
    expect(isTeamOwner(12, null)).toBe(false)
  })
  it.each(['idle', 'loading'] as const)('keeps owner access pending for products while permissions are %s', (loadState) => {
    setupOwner()
    const permissionStore = usePermissionStore()
    permissionStore.loadState = loadState

    const access = useSettingsAccess()
    const products = productsItem()

    expect(access.permissionsPending.value).toBe(true)
    expect(access.canAccess(products)).toBe(false)
  })

  it('denies products to an owner without product:view after permissions are ready', () => {
    setupOwner()
    const permissionStore = usePermissionStore()
    permissionStore.loadState = 'ready'

    const access = useSettingsAccess()
    expect(access.canAccess(productsItem())).toBe(false)
  })

  it('allows an owner with product:view after permissions are ready', () => {
    setupOwner()
    const permissionStore = usePermissionStore()
    permissionStore.loadState = 'ready'
    permissionStore.permissions = [{
      id: 1,
      code: 'product:view',
      name: 'product:view',
      resource: 'product',
      action: 'view',
      scope: null,
      description: null,
    }]

    const access = useSettingsAccess()
    expect(access.canAccess(productsItem())).toBe(true)
  })

  it('keeps owner bypass for team settings that do not require explicit permission', () => {
    setupOwner()
    const permissionStore = usePermissionStore()
    permissionStore.loadState = 'loading'

    const access = useSettingsAccess()
    const members = getSettingsNavigationItem('members')
    if (members === undefined) throw new Error('members settings item is not registered')
    expect(access.canAccess(members)).toBe(true)
  })
})
