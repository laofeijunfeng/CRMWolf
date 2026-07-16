import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const permissionStore = vi.hoisted(() => ({ clearPermissions: vi.fn() }))
const teamStore = vi.hoisted(() => ({ clearTeam: vi.fn() }))

vi.mock('@/stores/permissions', () => ({
  usePermissionStore: () => permissionStore,
}))
vi.mock('@/stores/team', () => ({
  useTeamStore: () => teamStore,
}))

import { useUserStore } from '@/stores/user'

describe('useUserStore.logout', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    permissionStore.clearPermissions.mockClear()
    teamStore.clearTeam.mockClear()
  })

  it('clears user, permission, team, and persisted authentication state', () => {
    const store = useUserStore()
    store.setToken('access-token')
    store.setUserInfo({
      id: 1, name: '王小明', email: 'wang@example.com', status: 'ACTIVE',
      created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-02T00:00:00Z',
    })

    store.logout()

    expect(store.token).toBe('')
    expect(store.userInfo).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
    expect(permissionStore.clearPermissions).toHaveBeenCalledOnce()
    expect(teamStore.clearTeam).toHaveBeenCalledOnce()
  })
})
