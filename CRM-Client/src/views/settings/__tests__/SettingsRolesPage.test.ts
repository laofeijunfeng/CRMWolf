import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import type { VNode } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import SettingsRolesPage from '@/views/settings/SettingsRolesPage.vue'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'
import type { PermissionResponse } from '@/schemas/role'

const mocks = vi.hoisted(() => ({
  getRoles: vi.fn(),
  getRole: vi.fn(),
  getAllPermissions: vi.fn(),
  deleteRole: vi.fn(),
  confirmDelete: vi.fn(),
}))

const { getRoles } = mocks

let pinia = createPinia()

vi.mock('@/api/role', () => ({
  default: {
    getRoles: mocks.getRoles,
    getRole: mocks.getRole,
    deleteRole: mocks.deleteRole,
  },
}))

vi.mock('@/utils/confirmDialog', () => ({
  confirmDelete: mocks.confirmDelete,
}))

vi.mock('@/api/permissions', () => ({
  default: {
    getAllPermissions: mocks.getAllPermissions,
  },
}))

vi.mock('vue-router', () => ({
  useRoute: (): { meta: { title: string }; query: Record<string, string | undefined> } => ({
    meta: { title: '角色管理' },
    query: {},
  }),
}))

const DataTableStub = defineComponent({
  name: 'DataTable',
  props: {
    data: { type: Array, default: () => [] },
    getRowActions: { type: Function, required: true },
  },
  setup(props): () => VNode {
    const getRowActions = props.getRowActions as (row: Record<string, unknown>) => {
      primaryActions?: { handler?: (value: Record<string, unknown>) => void }[]
      secondaryActions?: { id?: string; handler?: (value: Record<string, unknown>) => void }[]
    }
    return () => h('div', { 'data-testid': 'roles-table' },
      (props.data as Record<string, unknown>[]).flatMap(row => {
        const actions = getRowActions(row)
        return [
          h('div', { key: `name-${row['id']}` }, String(row['name'])),
          h('button', {
            key: `permissions-${row['id']}`,
            'data-testid': `permissions-${row['id']}`,
            onClick: () => actions.primaryActions?.[0]?.handler?.(row),
          }, '配置权限'),
          h('button', {
            key: `delete-${row['id']}`,
            'data-testid': `delete-${row['id']}`,
            onClick: () => actions.secondaryActions?.find(action => action.id === 'delete')?.handler?.(row),
          }, '删除'),
        ]
      }),
    )
  },
})

const permissionResponse = (id: number, code: string, resource: string, name: string, action: string): PermissionResponse => ({
  id, code, resource, name, action,
  scope: null,
  description: null,
  is_active: true,
  created_at: '2026-09-28T00:00:00Z',
  updated_at: '2026-09-28T00:00:00Z',
})

describe('SettingsRolesPage', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('loads roles into a DataTable without a sheet title', async () => {
    pinia = createPinia()
    setActivePinia(pinia)
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
        plugins: [pinia],
        stubs: {
          DataTable: DataTableStub,
          TableRowActions: true,
          SettingsContent: { template: '<main><slot /></main>' },
          Dialog: { template: '<div><slot /></div>' },
          DialogContent: { template: '<div><slot /></div>' },
          DialogHeader: true, DialogTitle: true, DialogDescription: true, DialogFooter: true,
        },
      },
    })
    await vi.waitFor(() => expect(getRoles).toHaveBeenCalled())
    expect(getRoles.mock.calls[0]?.[0]).toBeUndefined()
    expect(wrapper.text()).toContain('管理员')
    expect(wrapper.find('[data-testid="roles-table"]').exists()).toBe(true)
    wrapper.unmount()
  })
  it('shows one payment group containing the record export permission', async () => {
    pinia = createPinia()
    setActivePinia(pinia)
    const teamStore = useTeamStore()
    const userStore = useUserStore()
    const permissionStore = usePermissionStore()
    teamStore.currentTeam = {
      id: 7, name: '演示团队', code: 'DEMO', owner_id: '42',
      created_at: '2026-01-01T00:00:00Z',
    }
    userStore.userInfo = {
      id: 42, name: '团队所有者', email: 'owner@example.com',
      status: 'active', created_at: null, updated_at: null,
    }
    permissionStore.loadState = 'ready'

    const role = {
      id: 1, code: 'FINANCE', name: '财务人员', description: null,
      created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    }
    mocks.getRoles.mockResolvedValue([role])
    mocks.getRole.mockResolvedValue({ ...role, permissions: [] })
    mocks.getAllPermissions.mockResolvedValue([
      permissionResponse(1, 'payment:approve', 'payment', '审批回款', 'approve'),
      permissionResponse(2, 'payment:plan:export', 'payment_plan', '导出回款计划', 'export'),
      permissionResponse(3, 'payment:record:export', 'payment_record', '导出回款记录', 'export'),
    ])

    const wrapper = mount(SettingsRolesPage, {
      global: {
        plugins: [pinia],
        stubs: {
          DataTable: DataTableStub,
          TableRowActions: true,
          SettingsContent: { template: '<main><slot /></main>' },
          Dialog: { template: '<div><slot /></div>' },
          DialogContent: { template: '<div><slot /></div>' },
          DialogHeader: true, DialogTitle: true, DialogDescription: true, DialogFooter: true,
          Checkbox: { template: '<input type="checkbox">' },
          Label: { template: '<label><slot /></label>' },
          Badge: { template: '<span><slot /></span>' },
        },
      },
    })
    await vi.waitFor(() => expect(mocks.getRoles).toHaveBeenCalled())
    await wrapper.get('[data-testid="permissions-1"]').trigger('click')
    await flushPromises()

    const groupHeadings = wrapper.findAll('.font-semibold').map(item => item.text())
    expect(groupHeadings.filter(heading => heading === '回款')).toHaveLength(1)
    expect(groupHeadings).not.toContain('回款计划')
    expect(groupHeadings).not.toContain('回款记录')
    expect(wrapper.text()).toContain('导出回款记录')
    expect(wrapper.text()).toContain('payment:record:export')
    wrapper.unmount()
  })

  const mountWithRole = (): VueWrapper => {
    pinia = createPinia()
    setActivePinia(pinia)
    useTeamStore().currentTeam = {
      id: 7, name: '演示团队', code: 'DEMO', owner_id: '42',
      created_at: '2026-01-01T00:00:00Z',
    }
    useUserStore().userInfo = {
      id: 42, name: '团队所有者', email: 'owner@example.com',
      status: 'active', created_at: null, updated_at: null,
    }
    usePermissionStore().loadState = 'ready'
    mocks.getRoles.mockResolvedValue([{
      id: 3, code: 'SALES', name: '销售', description: null,
      created_at: '2026-01-01T00:00:00Z',
    }])
    return mount(SettingsRolesPage, {
      global: {
        plugins: [pinia],
        stubs: {
          DataTable: DataTableStub,
          TableRowActions: true,
          SettingsContent: { template: '<main><slot /></main>' },
          Dialog: { template: '<div><slot /></div>' },
          DialogContent: { template: '<div><slot /></div>' },
          DialogHeader: true, DialogTitle: true, DialogDescription: true, DialogFooter: true,
        },
      },
    })
  }

  it('keeps the role when delete confirmation is cancelled', async () => {
    mocks.confirmDelete.mockResolvedValue(false)
    const wrapper = mountWithRole()
    await vi.waitFor(() => expect(wrapper.find('[data-testid="delete-3"]').exists()).toBe(true))

    await wrapper.get('[data-testid="delete-3"]').trigger('click')
    await flushPromises()

    expect(mocks.confirmDelete).toHaveBeenCalledWith('角色"销售"')
    expect(mocks.deleteRole).not.toHaveBeenCalled()
    expect(mocks.getRoles).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('deletes the role and reloads the list after confirmation', async () => {
    mocks.confirmDelete.mockResolvedValue(true)
    mocks.deleteRole.mockResolvedValue(undefined)
    const wrapper = mountWithRole()
    await vi.waitFor(() => expect(wrapper.find('[data-testid="delete-3"]').exists()).toBe(true))

    await wrapper.get('[data-testid="delete-3"]').trigger('click')
    await flushPromises()

    expect(mocks.deleteRole).toHaveBeenCalledWith(3)
    expect(mocks.getRoles).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
})
