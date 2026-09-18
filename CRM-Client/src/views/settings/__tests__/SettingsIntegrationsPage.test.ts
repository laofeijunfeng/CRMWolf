import { afterEach, describe, expect, it, vi, type Mock } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import SettingsIntegrationsPage from '@/views/settings/SettingsIntegrationsPage.vue'
import { oauthApi } from '@/api/oauth'
import { useTeamStore } from '@/stores/team'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'
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

describe('SettingsIntegrationsPage', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders team Feishu app config without personal binding copy', async () => {
    const pinia = setupOwner()
    vi.mocked(oauthApi.getFeishuConfig).mockResolvedValue({
      id: 1,
      team_id: 1,
      provider: 'feishu',
      enabled: false,
      app_id: '',
      app_secret_configured: false,
      redirect_uri: 'https://example.com/auth/feishu/callback',
      bot_enabled: false,
      bot_verification_token: '',
      bot_encrypt_key: '',
      bot_open_id: '',
      bot_callback_path: '',
      bot_callback_url: '',
      created_at: null,
      updated_at: null,
    })

    const wrapper = mount(SettingsIntegrationsPage, {
      global: {
        plugins: [pinia],
        stubs: {
          Card: passthrough,
          CardHeader: passthrough,
          CardTitle: passthrough,
          CardDescription: passthrough,
          CardContent: passthrough,
          FormItem: passthrough,
          FormControl: passthrough,
          FormLabel: passthrough,
          FormDescription: passthrough,
          FormMessage: true,
          Switch: true,
          Label: passthrough,
          Skeleton: true,
        },
      },
    })

    await vi.waitFor(() => expect(wrapper.find('.settings-form-actions').exists()).toBe(true))
    expect(wrapper.text()).toContain('飞书应用')
    expect(wrapper.text()).toContain('AI Agent 机器人')
    expect(wrapper.find('.settings-form-actions').text()).toContain('保存配置')
    expect(wrapper.text()).not.toContain('绑定飞书')

    wrapper.unmount()
  })
})
