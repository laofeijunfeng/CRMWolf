import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SettingsRolesPage from '@/views/settings/SettingsRolesPage.vue'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'


const mocks = vi.hoisted(() => ({
  getRoles: vi.fn(),
}))

const { getRoles } = mocks

vi.mock('@/api/role', () => ({
  default: {
    getRoles: mocks.getRoles,
  },
}))

vi.mock('@/api/permissions', () => ({
  default: {
    getAllPermissions: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRoute: (): { meta: { title: string }; query: Record<string, string | undefined> } => ({
    meta: { title: '角色管理' },
    query: {},
  }),
}))

describe('SettingsRolesPage', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('loads roles into a DataTable without a sheet title', async () => {
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

    getRoles.mockResolvedValue([{
      id: 1,
      code: 'ADMIN',
      name: '管理员',
      description: null,
      created_at: '2026-01-01T00:00:00Z',
    }])

    const wrapper = mount(SettingsRolesPage, {
      global: {
        stubs: {
          DataTable: {
            props: ['data'],
            template: '<div data-testid="roles-table"><div v-for="row in data" :key="row.id">{{ row.name }}</div></div>',
          },
          TableRowActions: true,
          SettingsContent: { template: '<main><slot /></main>' },
          Dialog: { template: '<div><slot /></div>' },
          DialogContent: { template: '<div><slot /></div>' },
          DialogHeader: true, DialogTitle: true, DialogDescription: true, DialogFooter: true,
          FormField: { template: '<div><slot :componentField="{}" /></div>' },
        },
      },
    })
    await vi.waitFor(() => expect(getRoles).toHaveBeenCalled())
    expect(getRoles.mock.calls[0]?.[0]).toBeUndefined()
    expect(wrapper.text()).toContain('管理员')
    expect(wrapper.find('[data-testid="roles-table"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
