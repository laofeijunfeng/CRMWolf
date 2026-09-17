import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SettingsMembersPage from '@/views/settings/SettingsMembersPage.vue'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'

const mocks = vi.hoisted(() => ({
  getTeamMembers: vi.fn(),
}))

const { getTeamMembers } = mocks

vi.mock('@/api/team', () => ({
  teamApi: {
    getTeamMembers: mocks.getTeamMembers,
  },
}))

vi.mock('@/api/role', () => ({
  default: {
    getRoles: vi.fn().mockResolvedValue([]),
  },
}))

vi.mock('@/api/user', () => ({
  default: {
    searchUsers: vi.fn(),
  },
}))

vi.mock('@/utils/confirmDialog', () => ({
  confirmDialog: vi.fn(),
  confirmDelete: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: (): { meta: { title: string } } => ({ meta: { title: '团队成员' } }),
}))

describe('SettingsMembersPage', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('loads members into a DataTable and keeps invite code off this page', async () => {
    setActivePinia(createPinia())
    const teamStore = useTeamStore()
    const userStore = useUserStore()
    teamStore.currentTeam = {
      id: 7,
      name: '演示团队',
      code: 'DEMO',
      owner_id: '42',
      created_at: '2026-01-01T00:00:00Z',
    }
    userStore.userInfo = {
      id: 42,
      name: '团队所有者',
      email: 'owner@example.com',
      status: 'active',
      created_at: null,
      updated_at: null,
    }
    getTeamMembers.mockResolvedValue([{
      id: 'member-1',
      name: '成员一',
      email: 'member@example.com',
      joined_at: '2026-01-01T00:00:00Z',
      roles: [],
    }])

    const wrapper = mount(SettingsMembersPage, {
      global: {
        stubs: {
          DataTable: {
            props: ['data', 'fields'],
            template: '<div data-testid="members-table"><slot name="cell-member" v-for="row in data" :row="row" :index="0" /></div>',
          },
          TableRowActions: true,
          Dialog: { template: '<div><slot /></div>' },
          DialogContent: { template: '<div><slot /></div>' },
          DialogHeader: true, DialogTitle: true, DialogDescription: true, DialogFooter: true,
          FormField: { template: '<div><slot :componentField="{}" /></div>' },
          SettingsContent: { template: '<main><slot /></main>' },
        },
      },
    })
    await vi.waitFor(() => expect(getTeamMembers).toHaveBeenCalledWith(7))
    expect(wrapper.text()).toContain('成员一')
    expect(wrapper.text()).not.toContain('邀请码')
    expect(wrapper.text()).not.toContain('重置邀请码')
    expect(wrapper.html()).toContain('data-testid="members-table"')
    wrapper.unmount()
  })
})
