import { afterEach, describe, expect, it, vi, type Mock } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import SettingsNotificationsPage from '@/views/settings/SettingsNotificationsPage.vue'
import { notificationConfigApi, type NotificationConfigResponse } from '@/api/notificationConfig'
import { useTeamStore } from '@/stores/team'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'
import type { TeamResponse } from '@/api/team'
import type { UserResponse } from '@/schemas/auth'
import type {
  SettingsUnsavedLeaveGuard,
  SettingsUnsavedLeaveOptions,
} from '@/composables/useSettingsUnsavedLeave'

const unsavedLeave = vi.hoisted(() => ({
  isDirty: (): boolean => false,
}))

vi.mock('@/api/notificationConfig', () => ({
  notificationConfigApi: {
    getConfig: vi.fn(),
    updateConfig: vi.fn(),
    testNotification: vi.fn(),
  },
}))

vi.mock('@/composables/useSettingsUnsavedLeave', async (importOriginal) => {
  const actual = await importOriginal<{
    useSettingsUnsavedLeave: (options: SettingsUnsavedLeaveOptions) => SettingsUnsavedLeaveGuard
  }>()
  return {
    useSettingsUnsavedLeave: (options: SettingsUnsavedLeaveOptions): SettingsUnsavedLeaveGuard => {
      unsavedLeave.isDirty = options.isDirty
      return actual.useSettingsUnsavedLeave(options)
    },
  }
})

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

const loadedConfig: NotificationConfigResponse = {
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
}

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

const mountPage = (): VueWrapper => {
  return mount(SettingsNotificationsPage, {
    global: {
      plugins: [setupOwner()],
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
}

describe('SettingsNotificationsPage', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders notification channels with in-card test and bottom save', async () => {
    vi.mocked(notificationConfigApi.getConfig).mockResolvedValue(loadedConfig)

    const wrapper = mountPage()

    await vi.waitFor(() => expect(wrapper.find('.settings-form-actions').exists()).toBe(true))
    expect(wrapper.text().includes('飞书群通知') || wrapper.text().includes('群名称')).toBe(true)
    expect(wrapper.text()).toContain('发送测试')
    expect(wrapper.find('.settings-form-actions').text()).toContain('保存配置')
    expect(wrapper.text()).not.toContain('配置说明')

    wrapper.unmount()
  })

  it('clears unsaved dirty state after a successful save', async () => {
    const initialConfig = {
      ...loadedConfig,
      feishu_webhook_enabled: true,
      notification_group_name: '审批通知群',
    }
    vi.mocked(notificationConfigApi.getConfig).mockResolvedValue(initialConfig)
    vi.mocked(notificationConfigApi.updateConfig).mockResolvedValue({
      ...initialConfig,
      notification_group_name: '销售通知群',
    })

    const wrapper = mountPage()
    await vi.waitFor(() => expect(wrapper.find('.settings-form-actions').exists()).toBe(true))

    const groupName = wrapper.get('input[placeholder="如：审批通知群"]')
    expect((groupName.element as HTMLInputElement).value).toBe('审批通知群')
    expect(unsavedLeave.isDirty()).toBe(false)

    await groupName.setValue('销售通知群')
    await flushPromises()
    expect(unsavedLeave.isDirty()).toBe(true)

    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => {
      expect(notificationConfigApi.updateConfig).toHaveBeenCalled()
    })
    await flushPromises()

    expect(unsavedLeave.isDirty()).toBe(false)

    wrapper.unmount()
  })
})
