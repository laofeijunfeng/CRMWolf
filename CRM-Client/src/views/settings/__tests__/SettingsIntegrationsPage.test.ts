import { afterEach, describe, expect, it, vi, type Mock } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import SettingsIntegrationsPage from '@/views/settings/SettingsIntegrationsPage.vue'
import { oauthApi } from '@/api/oauth'
import { useTeamStore } from '@/stores/team'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'
import type { OAuthProviderConfigResponse } from '@/api/oauth'
import type { TeamResponse } from '@/api/team'
import type { UserResponse } from '@/schemas/auth'

vi.mock('@/api/oauth', () => ({
  oauthApi: {
    getFeishuConfig: vi.fn(),
    updateFeishuConfig: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRoute: (): { meta: { title: string } } => ({ meta: { title: '第三方集成' } }),
  useRouter: (): { push: Mock } => ({ push: vi.fn() }),
  onBeforeRouteLeave: (): void => undefined,
}))

const teamFixture: TeamResponse = {
  id: 1,
  name: '演示',
  code: 'DEMO',
  owner_id: '12',
  created_at: '2026-01-01T00:00:00Z',
}

const ownerFixture: UserResponse = {
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
}

const passthrough = { template: '<div><slot /></div>' }

const setupOwner = (): Pinia => {
  const pinia = createPinia()
  setActivePinia(pinia)
  const teamStore = useTeamStore()
  const permissionStore = usePermissionStore()
  const userStore = useUserStore()
  permissionStore.loadState = 'ready'
  teamStore.currentTeam = teamFixture
  userStore.userInfo = ownerFixture
  return pinia
}

const wrappers: VueWrapper[] = []

const configFixture: OAuthProviderConfigResponse = {
  id: 1, team_id: 1, provider: 'feishu', enabled: true,
  app_id: 'cli_existing', app_secret_configured: true,
  redirect_uri: 'https://example.com/auth/feishu/callback',
  bot_enabled: true, bot_verification_token: 'old-token', bot_encrypt_key: 'old-key',
  bot_open_id: 'old-bot-id', bot_callback_path: '/v1/im/feishu/events',
  bot_callback_url: 'https://example.com/api/v1/im/feishu/events', created_at: null, updated_at: null,
}

const mountConfig = async (config: OAuthProviderConfigResponse = configFixture): Promise<VueWrapper> => {
  const pinia = setupOwner()
  vi.mocked(oauthApi.getFeishuConfig).mockResolvedValue(config)
  vi.mocked(oauthApi.updateFeishuConfig).mockResolvedValue(config)
  const wrapper = mount(SettingsIntegrationsPage, {
    global: {
      plugins: [pinia],
      stubs: {
        Card: passthrough, CardHeader: passthrough, CardTitle: passthrough,
        CardDescription: passthrough, CardContent: passthrough,
        FormItem: passthrough, FormControl: passthrough, FormLabel: passthrough,
        FormDescription: passthrough, FormMessage: true, Switch: true,
        Label: passthrough, Skeleton: true,
      },
    },
  })
  await vi.waitFor(() => expect(wrapper.find('.settings-form-actions').exists()).toBe(true))
  wrappers.push(wrapper)
  return wrapper
}

describe('SettingsIntegrationsPage', () => {
  afterEach(() => {
    wrappers.splice(0).forEach(wrapper => wrapper.unmount())
    vi.clearAllMocks()
  })

  it('renders only team Feishu login config without bot or personal binding copy', async () => {
    const wrapper = await mountConfig()
    expect(wrapper.text()).toContain('飞书应用')
    expect(wrapper.text()).toContain('当前配置只对本团队生效，用于飞书登录。')
    expect(wrapper.text()).toContain('已配置时留空保存表示保持原密钥。')
    expect(wrapper.text()).not.toContain('AI Agent 机器人')
    expect(wrapper.text()).not.toContain('启用飞书机器人')
    expect(wrapper.text()).not.toContain('Verification Token')
    expect(wrapper.text()).not.toContain('Encrypt Key')
    expect(wrapper.findAll('input')).toHaveLength(3)
    expect(wrapper.find('.settings-form-actions').text()).toContain('保存配置')
    expect(wrapper.text()).not.toContain('绑定飞书')
  })

  it.each([
    { bot_enabled: true, bot_verification_token: 'old-token', bot_encrypt_key: 'old-key', bot_open_id: 'old-bot-id' },
    { bot_enabled: false, bot_verification_token: null, bot_encrypt_key: null, bot_open_id: null },
  ])('preserves loaded hidden bot fields and an empty App Secret (%j)', async (botFields) => {
    const wrapper = await mountConfig({ ...configFixture, ...botFields })
    await wrapper.get('input[autocomplete="off"]').setValue('cli_updated')
    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => expect(oauthApi.updateFeishuConfig).toHaveBeenCalledOnce())
    expect(oauthApi.updateFeishuConfig).toHaveBeenCalledWith({
      enabled: true, app_id: 'cli_updated', redirect_uri: configFixture.redirect_uri,
      ...botFields,
    })
    expect(vi.mocked(oauthApi.updateFeishuConfig).mock.calls[0]?.[0]).not.toHaveProperty('app_secret')
  })

  it('sends a replacement App Secret only when the user provides one', async () => {
    const wrapper = await mountConfig()
    await wrapper.get('input[type="password"]').setValue('new-app-secret')
    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => expect(oauthApi.updateFeishuConfig).toHaveBeenCalledOnce())
    expect(oauthApi.updateFeishuConfig).toHaveBeenCalledWith(expect.objectContaining({
      app_secret: 'new-app-secret', bot_enabled: true, bot_encrypt_key: 'old-key',
    }))
    await vi.waitFor(() => expect(wrapper.get<HTMLInputElement>('input[type="password"]').element.value).toBe(''))
  })
})
