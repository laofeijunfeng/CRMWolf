import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import TeamSettings from '@/views/TeamSettings.vue'
import { teamApi, type TeamResponse } from '@/api/team'
import type { UserResponse } from '@/schemas/auth'
import { useTeamStore } from '@/stores/team'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'

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

vi.mock('@/api/team', () => ({
  teamApi: { getTeamDetail: vi.fn(), updateTeam: vi.fn(), regenerateInviteCode: vi.fn() },
}))

vi.mock('vue-router', () => ({
  useRoute: (): { meta: { title: string } } => ({ meta: { title: '团队信息与安全' } }),
}))

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

describe('TeamSettings chrome', () => {
  it('does not render a duplicate settings heading or max-width shell', () => {
    const pinia = setupOwner()
    const wrapper = mount(TeamSettings, {
      global: {
        plugins: [pinia],
        stubs: {
          ErrorState: true,
          Card: passthrough,
          CardHeader: true,
          CardTitle: true,
          CardDescription: true,
          CardContent: true,
          Button: true,
          Input: true,
          Label: true,
          Skeleton: true,
        },
      },
    })
    expect(wrapper.find('h1').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('系统设置')
    expect(wrapper.html()).not.toContain('max-w-6xl')
    wrapper.unmount()
  })

  it('keeps invite controls on the team page in a full-width stacked form', async () => {
    const pinia = setupOwner()
    vi.mocked(teamApi.getTeamDetail).mockResolvedValue(teamFixture)
    const wrapper = mount(TeamSettings, {
      global: {
        plugins: [pinia],
        stubs: {
          ErrorState: true,
          Card: passthrough,
          CardHeader: passthrough,
          CardTitle: passthrough,
          CardDescription: passthrough,
          CardContent: passthrough,
          Label: passthrough,
          Skeleton: true,
        },
      },
    })
    await vi.waitFor(() => expect(wrapper.find('.settings-form-grid').exists()).toBe(true))
    expect(wrapper.text()).toContain('邀请')
    expect(wrapper.find('.settings-form-actions').text()).toContain('保存团队信息')
    expect(wrapper.text()).toContain('复制邀请链接')
    expect(wrapper.text()).toContain('重置邀请码')
    expect(wrapper.find('.lg\\:grid-cols-2').exists()).toBe(false)
    wrapper.unmount()
  })
})
