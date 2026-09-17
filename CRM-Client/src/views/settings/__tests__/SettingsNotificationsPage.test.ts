import { afterEach, describe, expect, it, vi, type Mock } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import SettingsNotificationsPage from '@/views/settings/SettingsNotificationsPage.vue'
import { notificationConfigApi } from '@/api/notificationConfig'
import { useTeamStore } from '@/stores/team'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'
import type { TeamResponse } from '@/api/team'
import type { UserResponse } from '@/schemas/auth'

vi.mock('@/api/notificationConfig', () => ({
  notificationConfigApi: {
    getConfig: vi.fn(),
    updateConfig: vi.fn(),
    testNotification: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRoute: (): { meta: { title: string } } => ({ meta: { title: '通知配置' } }),
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

describe('SettingsNotificationsPage', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders notification channels with in-card test and bottom save', async () => {
    const pinia = setupOwner()
    vi.mocked(notificationConfigApi.getConfig).mockResolvedValue({
      id: 1,
      team_id: 1,
      notification_method: 'webhook',
      feishu_webhook_url: null,
      feishu_webhook_enabled: false,
      notification_group_name: null,
      feishu_app_id: null,
      feishu_app_secret: null,
      feishu_api_enabled: null,
      created_time: '2026-01-01T00:00:00Z',
      updated_time: '2026-01-01T00:00:00Z',
    })

    const wrapper = mount(SettingsNotificationsPage, {
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
          Alert: passthrough,
          AlertDescription: passthrough,
          Skeleton: true,
        },
      },
    })

    await vi.waitFor(() => expect(wrapper.find('.settings-form-actions').exists()).toBe(true))
    expect(wrapper.text().includes('飞书群通知') || wrapper.text().includes('群名称')).toBe(true)
    expect(wrapper.text()).toContain('发送测试')
    expect(wrapper.find('.settings-form-actions').text()).toContain('保存配置')
    expect(wrapper.text()).not.toContain('配置说明')

    wrapper.unmount()
  })
})
