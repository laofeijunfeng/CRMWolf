import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SettingsMembersPage from '@/views/settings/SettingsMembersPage.vue'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'


const mocks = vi.hoisted(() => ({
  getTeamMembers: vi.fn(),
  assignMemberRoles: vi.fn(),
  getRoles: vi.fn(),
}))

const { getTeamMembers, assignMemberRoles, getRoles } = mocks

vi.mock('@/api/team', () => ({
  teamApi: {
    getTeamMembers: mocks.getTeamMembers,
    assignMemberRoles: mocks.assignMemberRoles,
  },
}))

vi.mock('@/api/role', () => ({
  default: {
    getRoles: mocks.getRoles,
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
  function seedTeamUser(): void {
    setActivePinia(createPinia())
    const teamStore = useTeamStore()
    const userStore = useUserStore()
    const permissionStore = usePermissionStore()
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
    permissionStore.loadState = 'ready'
  }


  const pageStubs = {
    DataTable: {
      props: ['data', 'fields', 'getRowActions'],
      template: `<div data-testid="members-table">
        <div v-for="row in data" :key="row.id">
          <slot name="cell-member" :row="row" :index="0" />
          <template v-for="action in (getRowActions(row, 0)?.primaryActions ?? [])" :key="action.id ?? action.label">
            <button
              v-if="action.visible !== false"
              :data-testid="'assign-role-' + row.id"
              @click="action.handler(row)"
            >{{ action.label }}</button>
          </template>
        </div>
      </div>`,
    },
    TableRowActions: true,
    Dialog: { props: ['open'], template: '<div v-if="open" data-testid="open-dialog"><slot /></div>' },
    DialogContent: { template: '<div><slot /></div>' },
    DialogHeader: true, DialogTitle: true, DialogDescription: true,
    DialogFooter: { template: '<footer><slot /></footer>' },
    FormField: { template: '<div><slot :componentField="{}" /></div>' },
    SettingsContent: { template: '<main><slot /></main>' },
    ErrorState: {
      props: ['title'],
      template: '<div role="alert">{{ title }}</div>',
    },
  }


  it('loads members into a DataTable and keeps invite code off this page', async () => {
    seedTeamUser()
    getTeamMembers.mockResolvedValue([{
      id: 8,
      name: '成员一',
      email: 'member@example.com',
      joined_at: '2026-01-01T00:00:00Z',
      roles: [],
    }])

    const wrapper = mount(SettingsMembersPage, {
      global: { stubs: pageStubs },
    })
    await vi.waitFor(() => expect(getTeamMembers).toHaveBeenCalledWith(7))
    expect(wrapper.text()).toContain('成员一')
    expect(wrapper.text()).not.toContain('邀请码')
    expect(wrapper.text()).not.toContain('重置邀请码')
    expect(wrapper.html()).toContain('data-testid="members-table"')
    wrapper.unmount()
  })

  it('does not list members when the current user cannot access the members setting', async () => {
    seedTeamUser()
    const userStore = useUserStore()
    userStore.userInfo = {
      id: 99,
      name: '普通成员',
      email: 'member@example.com',
      status: 'active',
      created_at: null,
      updated_at: null,
    }
    const permissionStore = usePermissionStore()
    permissionStore.loadState = 'ready'
    permissionStore.permissions = []
    getTeamMembers.mockResolvedValue([])

    const wrapper = mount(SettingsMembersPage, {
      global: { stubs: pageStubs },
    })
    await flushPromises()
    expect(getTeamMembers).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('暂无访问权限')
    wrapper.unmount()
  })

  it('lists members after permissions become ready', async () => {
    seedTeamUser()
    const userStore = useUserStore()
    userStore.userInfo = {
      id: 99,
      name: '普通成员',
      email: 'member@example.com',
      status: 'active',
      created_at: null,
      updated_at: null,
    }
    const permissionStore = usePermissionStore()
    permissionStore.loadState = 'loading'
    permissionStore.permissions = []
    getTeamMembers.mockResolvedValue([{
      id: 7,
      name: '成员一',
      email: 'member@example.com',
      joined_at: '2026-01-01T00:00:00Z',
      roles: [],
    }])

    const wrapper = mount(SettingsMembersPage, {
      global: { stubs: pageStubs },
    })
    await flushPromises()
    expect(getTeamMembers).not.toHaveBeenCalled()

    permissionStore.permissions = [{
      id: 1,
      code: 'team:member:view',
      name: 'team:member:view',
      resource: 'team',
      action: 'view',
    }]
    permissionStore.loadState = 'ready'
    await vi.waitFor(() => expect(getTeamMembers).toHaveBeenCalledWith(7))
    expect(wrapper.text()).toContain('成员一')
    wrapper.unmount()
  })

  it('opens role assignment for a numeric member id and keeps the current role selected', async () => {
    seedTeamUser()
    getRoles.mockResolvedValue([{ id: 3, name: '销售成员', code: 'SALES_MEMBER' }])
    getTeamMembers.mockResolvedValue([{
      id: 8,
      name: '成员一',
      email: 'member@example.com',
      joined_at: '2026-01-01T00:00:00Z',
      roles: [{ id: 3, name: '销售成员', code: 'SALES_MEMBER' }],
    }])

    const wrapper = mount(SettingsMembersPage, {
      global: { stubs: pageStubs },
    })
    await vi.waitFor(() => expect(getTeamMembers).toHaveBeenCalledWith(7))

    await wrapper.get('[data-testid="assign-role-8"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="open-dialog"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('销售成员')
    expect(wrapper.find('[role="checkbox"]').attributes('aria-checked')).toBe('true')

    assignMemberRoles.mockResolvedValue({ message: '角色已分配' })
    const saveButton = wrapper.findAll('button').find(button => button.text() === '保存')
    if (saveButton === undefined) throw new Error('保存按钮未渲染')
    await saveButton.trigger('click')
    await vi.waitFor(() => expect(assignMemberRoles).toHaveBeenCalledWith(7, 8, [3]))
    await vi.waitFor(() => expect(getTeamMembers).toHaveBeenCalledTimes(2))
    expect(wrapper.find('[data-testid="open-dialog"]').exists()).toBe(false)
    wrapper.unmount()
  })

})
