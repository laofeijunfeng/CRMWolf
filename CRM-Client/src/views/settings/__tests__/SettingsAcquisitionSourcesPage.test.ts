import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SettingsAcquisitionSourcesPage from '@/views/settings/SettingsAcquisitionSourcesPage.vue'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'

const mocks = vi.hoisted(() => ({
  listSources: vi.fn(),
  routeQuery: {} as Record<string, string | undefined>,
}))

const { listSources } = mocks

vi.mock('@/api/acquisition-source', () => ({
  default: {
    list: mocks.listSources,
  },
}))

vi.mock('vue-router', () => ({
  useRoute: (): { meta: { title: string }; query: Record<string, string | undefined> } => ({
    meta: { title: '获客来源' },
    get query(): Record<string, string | undefined> {
      return mocks.routeQuery
    },
  }),
}))

const pageStubs = {
  DataTable: { props: ['data'], template: '<div data-testid="sources-table">{{ data[0]?.name }}</div>' },
  TableRowActions: true,
  SettingsContent: { template: '<main><slot /></main>' },
  Dialog: {
    name: 'Dialog',
    props: ['open'],
    template: '<div v-if="open" data-testid="source-dialog"><slot /></div>',
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
    { id: 1, code: 'acquisition_source:create', name: '创建获客来源', resource: 'acquisition_source', action: 'create' },
    { id: 2, code: 'acquisition_source:update', name: '更新获客来源', resource: 'acquisition_source', action: 'update' },
  ]
}

describe('SettingsAcquisitionSourcesPage', () => {
  afterEach(() => {
    vi.clearAllMocks()
    mocks.routeQuery = {}
  })

  it('loads acquisition sources into a DataTable', async () => {
    seedOwnerPinia()
    listSources.mockResolvedValue([{ public_id: 'src_1', name: '官网咨询', is_active: true, reference_count: 24, sort_order: 1 }])
    const wrapper = mount(SettingsAcquisitionSourcesPage, {
      global: { stubs: { DataTable: { props: ['data'], template: '<div>{{ data[0]?.name }}</div>' }, TableRowActions: true, SettingsContent: { template: '<main><slot /></main>' }, Dialog: true } },
    })
    await vi.waitFor(() => expect(listSources).toHaveBeenCalled())
    expect(wrapper.text()).toContain('官网咨询')
    wrapper.unmount()
  })

  it('does not reopen create Dialog when the list length changes', async () => {
    seedOwnerPinia()
    mocks.routeQuery = { action: 'create' }

    let resolveSources: ((value: unknown[]) => void) | undefined
    listSources.mockImplementation(() => new Promise((resolve) => {
      resolveSources = resolve
    }))

    const wrapper = mount(SettingsAcquisitionSourcesPage, {
      global: { stubs: pageStubs },
    })
    await nextTick()
    expect(wrapper.find('[data-testid="source-dialog"]').exists()).toBe(true)

    const dialog = wrapper.findComponent({ name: 'Dialog' }) as unknown as {
      vm: { $emit: (event: 'update:open', value: boolean) => void }
    }
    dialog.vm.$emit('update:open', false)
    await nextTick()
    expect(wrapper.find('[data-testid="source-dialog"]').exists()).toBe(false)

    resolveSources?.([{ public_id: 'src_1', name: '官网咨询', is_active: true, reference_count: 24, sort_order: 1 }])
    await vi.waitFor(() => expect(listSources).toHaveBeenCalled())
    await nextTick()
    expect(wrapper.find('[data-testid="source-dialog"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
