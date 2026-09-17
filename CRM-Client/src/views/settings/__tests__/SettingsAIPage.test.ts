import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import SettingsAIPage from '@/views/settings/SettingsAIPage.vue'
import { aiConfigApi } from '@/api/aiConfig'
import { useTeamStore } from '@/stores/team'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'
import type { TeamResponse } from '@/api/team'
import type { UserResponse } from '@/schemas/auth'

vi.mock('@/api/aiConfig', () => ({
  aiConfigApi: {
    getConfig: vi.fn(),
    saveConfig: vi.fn(),
    testConnectionSSE: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRoute: (): { meta: { title: string } } => ({ meta: { title: 'AI 配置' } }),
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

describe('SettingsAIPage', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders a full-width AI form with a password key field and bottom save', async () => {
    const pinia = setupOwner()
    vi.mocked(aiConfigApi.getConfig).mockResolvedValue({
      code: 0,
      message: 'ok',
      data: {
        id: 1,
        api_host: 'https://api.deepseek.com/v1',
        api_key_masked: 'sk-xxxxx****',
        model_name: 'deepseek-chat',
        temperature: 0.1,
        max_tokens: 1024,
        updated_at: '2026-01-01T00:00:00Z',
      },
    })

    const wrapper = mount(SettingsAIPage, {
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
          Select: passthrough,
          SelectTrigger: true,
          SelectValue: true,
          SelectContent: true,
          SelectItem: true,
          Alert: passthrough,
          AlertDescription: passthrough,
          Skeleton: true,
        },
      },
    })

    await vi.waitFor(() => expect(wrapper.find('.settings-form-actions').exists()).toBe(true))
    expect(wrapper.text()).toContain('服务配置')
    expect(wrapper.text()).toContain('连接测试')
    expect(wrapper.text()).toContain('保存配置')
    expect(wrapper.text()).not.toContain('配置说明')
    expect(wrapper.find('input[type="password"]').exists()).toBe(true)

    const saveButton = wrapper.findAll('button').find((button) => button.text().includes('保存配置'))
    expect(saveButton).toBeDefined()
    expect(saveButton?.element.parentElement?.classList.contains('settings-form-actions')).toBe(true)

    wrapper.unmount()
  })
})
