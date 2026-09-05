import { beforeEach, describe, expect, it, vi } from 'vitest'

const authState = vi.hoisted(() => ({ loggedIn: false }))
const teamState = vi.hoisted(() => ({
  hasTeam: false,
  fetchUserTeams: vi.fn(),
}))

vi.mock('@/stores/user', () => ({
  useUserStore: () => ({ isLoggedIn: () => authState.loggedIn }),
}))
vi.mock('@/stores/team', () => ({
  useTeamStore: () => ({
    hasTeam: () => teamState.hasTeam,
    fetchUserTeams: teamState.fetchUserTeams,
  }),
}))

import router from '@/router'

describe('auth and team route recovery', () => {
  beforeEach(async () => {
    authState.loggedIn = false
    teamState.hasTeam = false
    teamState.fetchUserTeams.mockReset()
    await router.replace('/login')
  })

  it('preserves the protected route and query when redirecting an unauthenticated user', async () => {
    await router.push('/customers?page=2&customerId=42')

    expect(router.currentRoute.value.name).toBe('Login')
    expect(router.currentRoute.value.query).toEqual({ redirect: '/customers?page=2&customerId=42' })
  })

  it('returns a logged-in user to the requested route after authentication', async () => {
    authState.loggedIn = true
    teamState.hasTeam = true

    await router.push('/login?redirect=%2Fcustomers%3Fpage%3D2%26customerId%3D42')

    expect(router.currentRoute.value.fullPath).toBe('/customers?page=2&customerId=42')
  })

  it('routes team request failures to a recoverable error state instead of onboarding', async () => {
    authState.loggedIn = true
    teamState.fetchUserTeams.mockRejectedValueOnce(new Error('network down'))

    await router.push('/customers?page=2')

    expect(router.currentRoute.value.name).toBe('TeamUnavailable')
    expect(router.currentRoute.value.query).toEqual({ redirect: '/customers?page=2' })
  })

  it('routes a successful empty team response to onboarding', async () => {
    authState.loggedIn = true
    teamState.fetchUserTeams.mockResolvedValueOnce([])

    await router.push('/customers?page=2')

    expect(router.currentRoute.value.name).toBe('Onboarding')
    expect(router.currentRoute.value.query).toEqual({ redirect: '/customers?page=2' })
  })
})
