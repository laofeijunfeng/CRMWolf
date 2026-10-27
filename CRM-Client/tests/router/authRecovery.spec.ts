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

  it.each(['/', '/login', '/login?redirect=https%3A%2F%2Fexample.com'])('defaults %s to the sales assistant', async (path) => {
    authState.loggedIn = true
    teamState.hasTeam = true
    await router.push('/signup')
    await router.push(path)
    expect(router.currentRoute.value.path).toBe('/assistant')
  })

  it('uses the assistant as the return destination for a signed-out root visit', async () => {
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('Login')
    expect(router.currentRoute.value.query).toEqual({ redirect: '/assistant' })
  })

  it('retires old Agent links without carrying their conversation parameters', async () => {
    authState.loggedIn = true
    teamState.hasTeam = true
    await router.push('/agent?session_id=17&session_key=old#turn-3')
    expect(router.currentRoute.value.fullPath).toBe('/assistant')
    expect(router.getRoutes().find(route => route.path === '/agent')?.components).toBeUndefined()
  })

  it('keeps query and hash when returning to a business deep link', async () => {
    authState.loggedIn = true
    teamState.hasTeam = true
    await router.push({ path: '/login', query: { redirect: '/opportunities?stage=won#deal-42' } })
    expect(router.currentRoute.value.fullPath).toBe('/opportunities?stage=won#deal-42')
  })

  it('renders the retired run-log URL as a missing page in the normal CRM shell', async () => {
    authState.loggedIn = true
    teamState.hasTeam = true
    await router.push('/settings/agent-run-log')
    expect(router.currentRoute.value.name).toBe('NotFound')
    expect(router.currentRoute.value.meta['title']).toBe('找不到页面')
    expect(router.currentRoute.value.meta['settingsContext']).toBe(false)
    expect(router.currentRoute.value.meta['settingsKey']).toBeUndefined()
  })

})
