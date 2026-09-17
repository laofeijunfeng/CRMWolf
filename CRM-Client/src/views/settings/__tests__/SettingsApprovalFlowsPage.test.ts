import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SettingsApprovalFlowsPage from '@/views/settings/SettingsApprovalFlowsPage.vue'

const mocks = vi.hoisted(() => ({
  getApprovalFlows: vi.fn(),
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
    query: {},
  }),
}))

describe('SettingsApprovalFlowsPage', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('loads approval flows into a DataTable without a sheet title', async () => {
    setActivePinia(createPinia())
    getApprovalFlows.mockResolvedValue([{ id: 1, flow_name: '合同审批', flow_code: 'CONTRACT_FLOW', business_type: 'CONTRACT', is_active: true, nodes: [] }])
    const wrapper = mount(SettingsApprovalFlowsPage, {
      global: {
        stubs: {
          DataTable: { props: ['data'], template: '<div data-testid="flows-table">{{ data[0]?.flow_name }}</div>' },
          TableRowActions: true,
          SettingsContent: { template: '<main><slot /></main>' },
          Dialog: { template: '<div><slot /></div>' },
          DialogContent: { template: '<div><slot /></div>' },
          DialogHeader: true, DialogTitle: true, DialogDescription: true,
          ApprovalFlowFormDialog: true,
          ApprovalFlowAIDialog: true,
        },
      },
    })
    await vi.waitFor(() => expect(getApprovalFlows).toHaveBeenCalled())
    expect(getApprovalFlows.mock.calls[0]?.[0]).toBeUndefined()
    expect(wrapper.text()).toContain('合同审批')
    expect(wrapper.text()).not.toContain('审批流程管理')
    wrapper.unmount()
  })
})
