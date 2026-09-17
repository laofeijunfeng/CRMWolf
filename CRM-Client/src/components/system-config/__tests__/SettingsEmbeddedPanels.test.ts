import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ApprovalFlowSheet from '@/components/system-config/ApprovalFlowSheet.vue'

const mocks = vi.hoisted(() => ({
  getApprovalFlows: vi.fn(),
}))

const { getApprovalFlows } = mocks

vi.mock('@/api/approvalFlow', () => ({
  default: {
    getApprovalFlows: mocks.getApprovalFlows,
  },
}))

describe('settings embedded panels', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('does not mount SheetTitle outside DialogRoot in embedded approval flow mode', async () => {
    getApprovalFlows.mockResolvedValue([])

    const wrapper = mount(ApprovalFlowSheet, {
      props: { active: true, embedded: true },
      global: {
        stubs: {
          ScrollArea: { template: '<div><slot /></div>' },
          ListCard: { template: '<div />', props: ['items'] },
          Button: { template: '<button><slot /></button>' },
          Input: { template: '<input />' },
          Badge: { template: '<span><slot /></span>' },
          Select: { template: '<div><slot /></div>' },
          SelectContent: { template: '<div><slot /></div>' },
          SelectItem: { template: '<div><slot /></div>' },
          SelectTrigger: { template: '<button><slot /></button>' },
          SelectValue: { template: '<span><slot /></span>' },
          AmountText: { template: '<span />' },
          Empty: { template: '<div><slot /></div>' },
          EmptyHeader: { template: '<div><slot /></div>' },
          EmptyMedia: { template: '<div><slot /></div>' },
          EmptyTitle: { template: '<div><slot /></div>' },
          Dialog: { template: '<div><slot /></div>' },
          DialogContent: { template: '<div><slot /></div>' },
          DialogHeader: { template: '<div><slot /></div>' },
          DialogTitle: { template: '<h2><slot /></h2>' },
          DialogDescription: { template: '<p><slot /></p>' },
          ApprovalFlowFormDialog: { template: '<div />' },
          ApprovalFlowAIDialog: { template: '<div />' },
        },
      },
    })

    await vi.waitFor(() => expect(getApprovalFlows).toHaveBeenCalled())
    expect(wrapper.text()).not.toContain('审批流程管理')
    expect(wrapper.findComponent({ name: 'SheetTitle' }).exists()).toBe(false)
    wrapper.unmount()
  })

})
