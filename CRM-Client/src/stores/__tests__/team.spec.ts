import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const teamApi = vi.hoisted((): {
  getUserTeams: ReturnType<typeof vi.fn>
  switchTeam: ReturnType<typeof vi.fn>
  createTeam: ReturnType<typeof vi.fn>
  joinTeam: ReturnType<typeof vi.fn>
} => ({
  getUserTeams: vi.fn(),
  switchTeam: vi.fn(),
  createTeam: vi.fn(),
  joinTeam: vi.fn(),
}))
const permissionStore = vi.hoisted((): {
  refreshPermissions: ReturnType<typeof vi.fn>
} => ({
  refreshPermissions: vi.fn(),
}))

vi.mock('@/api/team', () => ({ teamApi }))
vi.mock('@/stores/permissions', () => ({ usePermissionStore: (): typeof permissionStore => permissionStore }))

import { useTeamStore } from '@/stores/team'

const team = {
  id: 1,
  name: '团队 A',
  code: 'TEAM-A',
  owner_id: '1',
  created_at: '2026-01-01T00:00:00Z',
}

const otherTeam = { ...team, id: 2, name: '团队 B', code: 'TEAM-B' }

describe('useTeamStore team context state', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    permissionStore.refreshPermissions.mockResolvedValue(undefined)
  })

  it('distinguishes an empty successful response from a failed request', async () => {
    const store = useTeamStore()
    teamApi.getUserTeams.mockResolvedValueOnce({ teams: [], current_team_id: null })

    await store.fetchUserTeams()

    expect(store.loadState).toBe('ready')
    expect(store.hasTeam()).toBe(false)

    teamApi.getUserTeams.mockRejectedValueOnce(new Error('network down'))
    await expect(store.fetchUserTeams()).rejects.toThrow('network down')

    expect(store.loadState).toBe('error')
    expect(store.loadError).toBeInstanceOf(Error)
    expect(store.teams).toEqual([])
  })

  it('keeps the last known team on a transient refresh failure', async () => {
    const store = useTeamStore()
    teamApi.getUserTeams.mockResolvedValueOnce({ teams: [team], current_team_id: 1 })
    await store.fetchUserTeams()

    teamApi.getUserTeams.mockRejectedValueOnce(new Error('timeout'))
    await expect(store.fetchUserTeams()).rejects.toThrow('timeout')

    expect(store.currentTeam?.id).toBe(1)
    expect(store.teams).toHaveLength(1)
  })

  it('keeps a completed team switch successful when permission refresh fails', async () => {
    const store = useTeamStore()
    store.teams = [team, otherTeam]
    teamApi.switchTeam.mockResolvedValueOnce({ message: 'ok', team_id: 2 })
    permissionStore.refreshPermissions.mockRejectedValueOnce(new Error('permission timeout'))

    await expect(store.switchTeam(2)).resolves.toBeUndefined()

    expect(store.currentTeam?.id).toBe(2)
    expect(store.switchRevision).toBe(1)
    expect(store.permissionSyncState).toBe('error')
    expect(store.permissionSyncError).toBeInstanceOf(Error)
  })

  it('allows retrying permission sync after a team switch', async () => {
    const store = useTeamStore()
    permissionStore.refreshPermissions.mockRejectedValueOnce(new Error('temporary failure'))
    expect(await store.retryPermissionSync()).toBe(false)

    permissionStore.refreshPermissions.mockResolvedValueOnce(undefined)
    expect(await store.retryPermissionSync()).toBe(true)
    expect(store.permissionSyncState).toBe('ready')
    expect(store.permissionSyncError).toBeNull()
  })

  it('increments the view refresh revision without changing the route', async () => {
    const store = useTeamStore()
    store.teams = [team, otherTeam]
    teamApi.switchTeam.mockResolvedValueOnce({ message: 'ok', team_id: 2 })

    await store.switchTeam(2)

    expect(store.currentTeam?.id).toBe(2)
    expect(store.switchRevision).toBe(1)
    expect(permissionStore.refreshPermissions).toHaveBeenCalledOnce()
  })
})
