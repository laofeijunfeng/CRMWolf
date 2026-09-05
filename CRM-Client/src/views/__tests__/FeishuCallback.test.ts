import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  route: { query: {} as Record<string, unknown> },
  router: { replace: vi.fn() },
  authCallback: vi.fn(),
  getUserInfo: vi.fn(),
  getUserRoles: vi.fn(),
  setToken: vi.fn(),
  setUserInfo: vi.fn(),
  fetchUserTeams: vi.fn(),
  hasTeam: vi.fn(),
  consumeOAuthReturnPath: vi.fn(),
  createAuthReturnQuery: vi.fn(),
  handleApiError: vi.fn(),
  toastSuccess: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: (): typeof mocks.route => mocks.route,
  useRouter: (): typeof mocks.router => mocks.router,
}))

vi.mock('@/api/oauth', () => ({
  oauthApi: { handleFeishuCallback: mocks.authCallback },
}))

vi.mock('@/api/auth', () => ({
  authApi: {
    getUserInfo: mocks.getUserInfo,
    getUserRoles: mocks.getUserRoles,
  },
}))

vi.mock('@/stores/user', () => ({
  useUserStore: (): { setToken: typeof mocks.setToken; setUserInfo: typeof mocks.setUserInfo } => ({
    setToken: mocks.setToken,
    setUserInfo: mocks.setUserInfo,
  }),
}))

vi.mock('@/stores/team', () => ({
  useTeamStore: (): { fetchUserTeams: typeof mocks.fetchUserTeams; hasTeam: typeof mocks.hasTeam } => ({
    fetchUserTeams: mocks.fetchUserTeams,
    hasTeam: mocks.hasTeam,
  }),
}))

vi.mock('@/utils/authRecovery', () => ({
  consumeOAuthReturnPath: mocks.consumeOAuthReturnPath,
  createAuthReturnQuery: mocks.createAuthReturnQuery,
}))

vi.mock('@/utils/errorHandler', () => ({
  handleApiError: mocks.handleApiError,
}))

vi.mock('vue-sonner', () => ({
  toast: { success: mocks.toastSuccess },
}))

import FeishuCallback from '@/views/FeishuCallback.vue'

// The SFC wrapper's generated instance type is intentionally inferred by Vue Test Utils.
// eslint-disable-next-line @typescript-eslint/explicit-function-return-type
const mountCallback = () => mount(FeishuCallback, {
  global: {
    stubs: {
      Card: { template: '<section><slot /></section>' },
      CardContent: { template: '<div><slot /></div>' },
      Button: { template: '<button @click="$emit(\'click\')"><slot /></button>' },
      Loader2: { template: '<span />' },
      CheckCircle2: { template: '<span />' },
      XCircle: { template: '<span />' },
    },
  },
})

describe('FeishuCallback recovery contract', () => {
  beforeEach(() => {
    mocks.route.query = { code: 'oauth-code', state: 'oauth-state' }
    mocks.router.replace.mockReset()
    mocks.authCallback.mockReset()
    mocks.getUserInfo.mockReset()
    mocks.getUserRoles.mockReset()
    mocks.setToken.mockReset()
    mocks.setUserInfo.mockReset()
    mocks.fetchUserTeams.mockReset()
    mocks.hasTeam.mockReset()
    mocks.consumeOAuthReturnPath.mockReset()
    mocks.createAuthReturnQuery.mockReset()
    mocks.handleApiError.mockReset()
    mocks.toastSuccess.mockReset()

    mocks.consumeOAuthReturnPath.mockReturnValue(null)
    mocks.createAuthReturnQuery.mockImplementation((path: string | null) => path === null ? {} : { redirect: path })
    mocks.getUserInfo.mockResolvedValue({ id: 7, name: '用户', email: 'user@example.com' })
    mocks.getUserRoles.mockResolvedValue([])
    mocks.fetchUserTeams.mockResolvedValue([])
    mocks.hasTeam.mockReturnValue(false)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('returns a binding callback to account settings', async () => {
    mocks.authCallback.mockResolvedValue({ mode: 'bind', message: '飞书绑定成功' })
    mocks.consumeOAuthReturnPath.mockReturnValue('/settings/account')

    const wrapper = mountCallback()
    await flushPromises()

    expect(mocks.router.replace).toHaveBeenCalledWith('/settings/account')
    expect(mocks.toastSuccess).toHaveBeenCalledWith('飞书绑定成功')
    expect(wrapper.text()).toContain('飞书绑定成功')
  })

  it('restores the saved path after a successful invite login', async () => {
    mocks.authCallback.mockResolvedValue({
      mode: 'invite',
      login: { access_token: 'invite-token' },
    })
    mocks.consumeOAuthReturnPath.mockReturnValue('/customers?status=active')
    mocks.hasTeam.mockReturnValue(true)

    mountCallback()
    await flushPromises()

    expect(mocks.setToken).toHaveBeenCalledWith('invite-token')
    expect(mocks.fetchUserTeams).toHaveBeenCalledOnce()
    expect(mocks.router.replace).toHaveBeenCalledWith('/customers?status=active')
  })

  it('uses leads as the default destination for invite login without a saved path', async () => {
    mocks.authCallback.mockResolvedValue({
      mode: 'invite',
      login: { access_token: 'invite-token' },
    })
    mocks.hasTeam.mockReturnValue(true)

    mountCallback()
    await flushPromises()

    expect(mocks.router.replace).toHaveBeenCalledWith('/leads')
  })

  it('routes to team-unavailable when team loading fails', async () => {
    mocks.authCallback.mockResolvedValue({
      mode: 'invite',
      login: { access_token: 'invite-token' },
    })
    mocks.fetchUserTeams.mockRejectedValue(new Error('team service unavailable'))
    mocks.consumeOAuthReturnPath.mockReturnValue('/contracts')

    mountCallback()
    await flushPromises()

    expect(mocks.createAuthReturnQuery).toHaveBeenCalledWith('/contracts')
    expect(mocks.router.replace).toHaveBeenCalledWith({
      name: 'TeamUnavailable',
      query: { redirect: '/contracts' },
    })
  })

  it('routes to onboarding when invite login has no team', async () => {
    mocks.authCallback.mockResolvedValue({
      mode: 'invite',
      login: { access_token: 'invite-token' },
    })
    mocks.consumeOAuthReturnPath.mockReturnValue('/leads')
    mocks.hasTeam.mockReturnValue(false)

    mountCallback()
    await flushPromises()

    expect(mocks.router.replace).toHaveBeenCalledWith({
      name: 'Onboarding',
      query: { redirect: '/leads' },
    })
  })

  it('shows a stable failure state when callback parameters are missing', async () => {
    mocks.route.query = {}

    const wrapper = mountCallback()
    await flushPromises()

    expect(mocks.authCallback).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('飞书授权参数缺失')
    expect(wrapper.find('button').text()).toContain('返回登录')
  })

  it('shows a failure state when invite login does not return an access token', async () => {
    mocks.authCallback.mockResolvedValue({ mode: 'invite', login: null })

    const wrapper = mountCallback()
    await flushPromises()

    expect(mocks.handleApiError).toHaveBeenCalled()
    expect(wrapper.text()).toContain('飞书授权失败')
  })
})
