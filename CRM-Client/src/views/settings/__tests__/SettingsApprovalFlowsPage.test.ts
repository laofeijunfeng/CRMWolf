import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SettingsApprovalFlowsPage from '@/views/settings/SettingsApprovalFlowsPage.vue'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'


const mocks = vi.hoisted(() => ({
  getApprovalFlows: vi.fn(),
  routeQuery: {} as Record<string, string | undefined>,
}))

const { getApprovalFlows } = mocks

vi.mock('@/api/approvalFlow', () => ({
  default: {
    getApprovalFlows: mocks.getApprovalFlows,
  },
}))

vi.mock('vue-router', () => ({
  useRoute: (): { meta: { title: string }; query: Record<string, string | undefined> } => ({
    meta: { title: '审批流程管理' },
    get query(): Record<string, string | undefined> {
      return mocks.routeQuery
    },
  }),
}))

const pageStubs = {
  DataTable: { props: ['data'], template: '<div data-testid="flows-table">{{ data[0]?.flow_name }}</div>' },
  TableRowActions: true,
  SettingsContent: { template: '<main><slot /></main>' },
  Dialog: { template: '<div><slot /></div>' },
  DialogContent: { template: '<div><slot /></div>' },
  DialogHeader: true, DialogTitle: true, DialogDescription: true,
  ApprovalFlowFormDialog: {
    name: 'ApprovalFlowFormDialog',
    props: ['open', 'mode', 'flowId'],
    template: '<div v-if="open" data-testid="form-dialog" :data-mode="mode"></div>',
  },
  ApprovalFlowAIDialog: true,
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
}

describe('SettingsApprovalFlowsPage', () => {
  afterEach(() => {
    vi.clearAllMocks()
    mocks.routeQuery = {}
  })

  it('loads approval flows into a DataTable without a sheet title', async () => {
    seedOwnerPinia()

    getApprovalFlows.mockResolvedValue([{ id: 1, flow_name: '合同审批', flow_code: 'CONTRACT_FLOW', business_type: 'CONTRACT', is_active: true, nodes: [] }])
    const wrapper = mount(SettingsApprovalFlowsPage, {
      global: { stubs: pageStubs },
    })
    await vi.waitFor(() => expect(getApprovalFlows).toHaveBeenCalled())
    expect(getApprovalFlows.mock.calls[0]?.[0]).toBeUndefined()
    expect(wrapper.text()).toContain('合同审批')
    expect(wrapper.text()).not.toContain('审批流程管理')
    wrapper.unmount()
  })

  it('does not reopen create FormDialog when the list length changes', async () => {
    seedOwnerPinia()
    mocks.routeQuery = { action: 'create' }


    let resolveFlows: ((value: unknown[]) => void) | undefined
    getApprovalFlows.mockImplementation(() => new Promise((resolve) => {
      resolveFlows = resolve
    }))

    const wrapper = mount(SettingsApprovalFlowsPage, {
      global: { stubs: pageStubs },
    })
    await nextTick()
    expect(wrapper.find('[data-testid="form-dialog"]').exists()).toBe(true)

    const dialog = wrapper.findComponent({ name: 'ApprovalFlowFormDialog' }) as unknown as {
      vm: { $emit: (event: 'update:open', value: boolean) => void }
    }
    dialog.vm.$emit('update:open', false)
    await nextTick()
    expect(wrapper.find('[data-testid="form-dialog"]').exists()).toBe(false)

    resolveFlows?.([{ id: 1, flow_name: '合同审批', flow_code: 'CONTRACT_FLOW', business_type: 'CONTRACT', is_active: true, nodes: [] }])
    await vi.waitFor(() => expect(getApprovalFlows).toHaveBeenCalled())
    await nextTick()
    expect(wrapper.find('[data-testid="form-dialog"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
