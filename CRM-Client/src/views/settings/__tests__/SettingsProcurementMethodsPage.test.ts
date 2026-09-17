import { afterEach, describe, expect, it, vi, type Mock } from 'vitest'
import { nextTick } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

import { createPinia, setActivePinia } from 'pinia'
import SettingsProcurementMethodsPage from '@/views/settings/SettingsProcurementMethodsPage.vue'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'

const mocks = vi.hoisted(() => ({
  listMethods: vi.fn(),
  getProcurementMethod: vi.fn(),
  routeQuery: {} as Record<string, string | undefined>,
}))


const { listMethods } = mocks

vi.mock('@/api/procurement', () => ({
  default: {
    getProcurementMethods: mocks.listMethods,
    getProcurementMethod: mocks.getProcurementMethod,
  },
}))


vi.mock('vue-router', () => ({
  useRoute: (): { meta: { title: string }; query: Record<string, string | undefined> } => ({
    meta: { title: '采购方式管理' },
    get query(): Record<string, string | undefined> {
      return mocks.routeQuery
    },
  }),
  useRouter: (): { push: Mock } => ({
    push: vi.fn(),
  }),
}))

const pageStubs = {
  DataTable: { props: ['data'], template: '<div data-testid="methods-table">{{ data[0]?.name }} {{ data[0]?.stage_templates?.length ?? 0 }}</div>' },

  TableRowActions: true,
  SettingsContent: { template: '<main><slot /></main>' },
  Dialog: {
    name: 'Dialog',
    props: ['open'],
    template: '<div v-if="open" data-testid="method-dialog"><slot /></div>',
  },
  DialogContent: { template: '<div><slot /></div>' },
  DialogHeader: true, DialogTitle: true, DialogDescription: true, DialogFooter: true,
  FormField: { template: '<div><slot :componentField="{}" /></div>' },
}

function seedOwnerPinia(): void {
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
  permissionStore.permissions = [
    { id: 1, code: 'procurement_method:create', name: '创建采购方式', resource: 'procurement_method', action: 'create' },
    { id: 2, code: 'procurement_method:update', name: '更新采购方式', resource: 'procurement_method', action: 'update' },
    { id: 3, code: 'procurement_method:delete', name: '删除采购方式', resource: 'procurement_method', action: 'delete' },
  ]
}

describe('SettingsProcurementMethodsPage', () => {
  afterEach(() => {
    vi.clearAllMocks()
    mocks.routeQuery = {}
  })

  it('loads procurement methods into a DataTable', async () => {
    seedOwnerPinia()
    listMethods.mockResolvedValue([{ id: 1, name: '公开招标', code: 'OPEN_TENDER', is_active: true, sort_order: 0 }])
    mocks.getProcurementMethod.mockResolvedValue({
      id: 1,
      name: '公开招标',
      code: 'OPEN_TENDER',
      is_active: true,
      sort_order: 0,
      stage_templates: [{}, {}],
    })
    const wrapper = mount(SettingsProcurementMethodsPage, {
      global: { stubs: { DataTable: { props: ['data'], template: '<div>{{ data[0]?.name }}</div>' }, TableRowActions: true, SettingsContent: { template: '<main><slot /></main>' }, Dialog: true } },
    })
    await vi.waitFor(() => expect(listMethods).toHaveBeenCalled())
    await vi.waitFor(() => expect(mocks.getProcurementMethod).toHaveBeenCalledWith(1))
    await flushPromises()
    expect(wrapper.text()).toContain('公开招标')
    wrapper.unmount()
  })

  it('loads real stage counts from each method detail', async () => {
    seedOwnerPinia()
    listMethods.mockResolvedValue([{
      id: 1,
      name: '公开招标',
      code: 'OPEN_TENDER',
      is_active: 1,
      sort_order: 0,
      created_time: '2026-01-01T00:00:00Z',
      updated_time: '2026-01-01T00:00:00Z',
    }])
    mocks.getProcurementMethod.mockResolvedValue({
      id: 1,
      name: '公开招标',
      code: 'OPEN_TENDER',
      is_active: 1,
      sort_order: 0,
      created_time: '2026-01-01T00:00:00Z',
      updated_time: '2026-01-01T00:00:00Z',
      stage_templates: [{ id: 11 }, { id: 12 }],
    })
    const wrapper = mount(SettingsProcurementMethodsPage, {
      global: { stubs: pageStubs },
    })
    await vi.waitFor(() => expect(listMethods).toHaveBeenCalled())
    await vi.waitFor(() => expect(mocks.getProcurementMethod).toHaveBeenCalledWith(1))
    await flushPromises()
    expect(wrapper.text()).toContain('公开招标')
    expect(wrapper.text()).toContain('2')
    wrapper.unmount()
  })



  it('does not reopen create Dialog when the list length changes', async () => {
    seedOwnerPinia()
    mocks.routeQuery = { action: 'create' }

    let resolveMethods: ((value: unknown[]) => void) | undefined
    listMethods.mockImplementation(() => new Promise((resolve) => {
      resolveMethods = resolve
    }))

    const wrapper = mount(SettingsProcurementMethodsPage, {
      global: { stubs: pageStubs },
    })
    await nextTick()
    expect(wrapper.find('[data-testid="method-dialog"]').exists()).toBe(true)

    const dialog = wrapper.findComponent({ name: 'Dialog' }) as unknown as {
      vm: { $emit: (event: 'update:open', value: boolean) => void }
    }
    dialog.vm.$emit('update:open', false)
    await nextTick()
    expect(wrapper.find('[data-testid="method-dialog"]').exists()).toBe(false)

    resolveMethods?.([{ id: 'pm_1', name: '公开招标', code: 'OPEN_TENDER', is_active: true, stage_templates: [{}, {}] }])
    mocks.getProcurementMethod.mockResolvedValue({ id: 'pm_1', name: '公开招标', code: 'OPEN_TENDER', is_active: true, stage_templates: [{}, {}] })

    await vi.waitFor(() => expect(listMethods).toHaveBeenCalled())
    await nextTick()
    expect(wrapper.find('[data-testid="method-dialog"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
