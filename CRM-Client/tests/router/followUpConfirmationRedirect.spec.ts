import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/stores/user', () => ({
  useUserStore: () => ({ isLoggedIn: () => true }),
}))
vi.mock('@/stores/team', () => ({
  useTeamStore: () => ({ hasTeam: () => true, fetchUserTeams: vi.fn() }),
}))

import router from '@/router'

describe('legacy follow-up confirmation route', () => {
  beforeEach(async () => {
    await router.replace('/agent')
  })

  it('redirects to the ordinary customer tracking page without a confirmation module query', async () => {
    await router.push('/follow-up-confirmations')

    expect(router.currentRoute.value.fullPath).toBe('/customer-tracking')
    expect(router.currentRoute.value.query).toEqual({})
  })
})
