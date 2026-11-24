import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { createPinia, defineStore } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import contractApi, { type ContractChangeResponse, type ContractResponse } from '@/api/contract'
import ContractDetailContent from '@/components/panels/ContractDetailContent.vue'
import approvalGenericApi from '@/api/approvalGeneric'
import request from '@/utils/request'


vi.mock('@/utils/request', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
vi.mock('@/stores/user', () => ({
  useUserStore: defineStore('contract-test-user', {
    state: () => ({ userInfo: { id: 'creator-1' } })
  })
}))

vi.mock('@/stores/permissions', () => ({
  usePermissionStore: (): { canEditAll: () => boolean; canEditOwn: () => boolean; canApproveAll: () => boolean; canApproveOwn: () => boolean } => ({ canEditAll: (): boolean => false, canEditOwn: (): boolean => true, canApproveAll: (): boolean => false, canApproveOwn: (): boolean => false })
}))
vi.mock('@/components/ui/dialog', () => ({
  Dialog: { props: ['open'], template: '<div v-if="open" role="dialog"><slot /></div>' },
  DialogContent: { template: '<div><slot /></div>' },
  DialogHeader: { template: '<header><slot /></header>' },
  DialogTitle: { template: '<h2><slot /></h2>' },
  DialogDescription: { template: '<p><slot /></p>' },
  DialogFooter: { template: '<footer><slot /></footer>' }
}))

const change = (overrides: Partial<ContractChangeResponse> = {}): ContractChangeResponse => ({
  id: 31, contract_id: 11, creator_id: 'creator-1',
  change_items: [{ key: 'contract_amount', old_value: '120000.00', new_value: '102000.00' }],
  reason: '录入时多填一位折扣', approval_phase: 'pending_review',
  attachment_name: null, attachment_size: null, attachment_mime_type: null,
  created_time: '2026-11-10T03:20:00Z', updated_time: '2026-11-10T03:20:00Z', ...overrides
})

const contract = (overrides: Partial<ContractResponse> = {}): ContractResponse => ({
  id: 11, contract_number: 'HT-001', contract_name: '华东物流年度合同', customer_id: 'customer-1',
  opportunity_id: null, signing_contact_id: 1, user_count: 60, total_amount: '120000.00',
  license_type: 'SUBSCRIPTION', subscription_years: 1, standard_unit_price: '2000.00', status: 'SIGNED',
  approval_phase: 'approved', signing_date: '2026-10-21', effective_date: null, expiry_date: null,
  owner_id: 'creator-1', creator_id: 'creator-1', created_time: '2026-10-21T00:00:00Z',
  last_modified_time: '2026-10-21T00:00:00Z', can_request_change: true, change_disabled_reason: null,
  pending_change: null, change_history: [],
  financial_snapshot: { paid_amount: '60000.00', invoiced_amount: '60000.00', planned_amount: '100000.00', floor_amount: '100000.00' },
  ...overrides
})

const wrappers: VueWrapper[] = []
const renderDetail = async (data = contract(), readonly = false, configureFetch = true): Promise<VueWrapper> => {
  if (configureFetch) vi.spyOn(contractApi, 'getContract').mockResolvedValue(data)
  const wrapper = mount(ContractDetailContent, {
    props: { contractId: data.id, readonly }, attachTo: document.body,
    global: {
      plugins: [createPinia()],
      stubs: {
        SheetHeader: { template: '<header><slot /></header>' },
        SheetTitle: { template: '<h1><slot /></h1>' },
        SheetDescription: { template: '<div><slot /></div>' },
        SheetFooter: { template: '<footer><slot /></footer>' },
        ScrollArea: { template: '<div><slot /></div>' },
        ContractFormDialog: true, ContractPaymentPlans: true,
        ApprovalProcessGeneric: {
          props: ['entityType', 'entityId', 'title'],
          template: '<section :data-entity-type="entityType" :data-entity-id="entityId">{{ title }}</section>'
        }
      }
    }
  })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
}

const button = (wrapper: VueWrapper, label: string): DOMWrapper<Element> | undefined => wrapper.findAll('button').find(item => item.text() === label)

beforeEach(() => vi.clearAllMocks())
afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  vi.restoreAllMocks()
})

describe('approved contract amount changes', () => {
  it('submits an immutable request and refreshes pending details without changing the effective amount', async () => {
    const wrapper = await renderDetail()
    const pending = change()
    const create = vi.spyOn(contractApi, 'createContractChange').mockResolvedValue(pending)
    vi.spyOn(contractApi, 'getContract').mockResolvedValue(contract({ can_request_change: false, pending_change: pending, change_history: [pending] }))
    await button(wrapper, '申请变更合同')?.trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('通过前合同保持原样')
    await wrapper.get('#contract-change-new-amount').setValue('102000.00')
    await wrapper.get('#contract-change-reason').setValue('录入时多填一位折扣')
    await wrapper.get('#contract-change-form').trigger('submit')
    await flushPromises()
    expect(create).toHaveBeenCalledWith(11, { new_amount: '102000.00', reason: '录入时多填一位折扣' }, undefined)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('.amount-summary').text()).toContain('120,000.00')
    expect(wrapper.text()).toContain('合同变更审批中：金额拟改为 ¥102,000.00')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })

  it('blocks a second request, keeps rejected history newest-first and renders the independent change approval', async () => {
    const pending = change()
    const rejected = change({ id: 30, approval_phase: 'rejected', reason: '金额填错', created_time: '2026-11-03T01:12:00Z' })
    const wrapper = await renderDetail(contract({ can_request_change: false, pending_change: pending, change_history: [rejected, pending] }))
    expect(button(wrapper, '申请变更合同')?.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('已有一条变更在审批中，审批结束前不能再次发起')
    expect(wrapper.get('[data-entity-type="CONTRACT_CHANGE"]').attributes('data-entity-id')).toBe('31')
    expect(wrapper.text()).toContain('合同变更审批')
    const rows = wrapper.findAll('[data-testid="contract-change-history-row"]')
    expect(rows[0]?.text()).toContain('审批中')
    expect(rows[1]?.text()).toContain('已驳回')
    expect(rows[1]?.text()).toContain('金额填错')
    expect(rows.some(row => row.text().includes('重新提交') || row.text().includes('撤回'))).toBe(false)
  })

  it('permits a new request after rejection and downloads the retained attachment through authorized approval API', async () => {
    const rejected = change({ approval_phase: 'rejected', attachment_name: '说明.pdf', attachment_size: 2048, attachment_mime_type: 'application/pdf' })
    const wrapper = await renderDetail(contract({ change_history: [rejected] }))
    const download = vi.spyOn(approvalGenericApi, 'downloadApprovalAttachment').mockResolvedValue()
    expect(button(wrapper, '申请变更合同')?.attributes('disabled')).toBeUndefined()
    await wrapper.get('[aria-label="下载说明.pdf"]').trigger('click')
    await flushPromises()
    expect(download).toHaveBeenCalledWith('CONTRACT_CHANGE', rejected.id, '说明.pdf')
  })

  it.each([
    { readonly: true, data: contract() },
    { readonly: false, data: contract({ creator_id: 'other', can_request_change: false }) },
    { readonly: false, data: contract({ status: 'TERMINATED', can_request_change: false }) },
    { readonly: false, data: contract({ status: 'DRAFT', approval_phase: 'draft', can_request_change: false }) }
  ])('does not expose change mutation controls for ineligible or readonly detail %#', async ({ readonly, data }) => {
    const wrapper = await renderDetail(data, readonly)
    expect(button(wrapper, '申请变更合同')).toBeUndefined()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('rejects below-floor amounts and retains form values when the server rejects submission', async () => {
    const wrapper = await renderDetail()
    const create = vi.spyOn(contractApi, 'createContractChange').mockRejectedValue(new Error('审批流程不存在'))
    await button(wrapper, '申请变更合同')?.trigger('click')
    await wrapper.get('#contract-change-new-amount').setValue('99999.99')
    await wrapper.get('#contract-change-reason').setValue('客户调整采购')
    await wrapper.get('#contract-change-form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).toContain('新金额不能低于 ¥100,000.00')
    expect(create).not.toHaveBeenCalled()
    await wrapper.get('#contract-change-new-amount').setValue('102000.00')
    await wrapper.get('#contract-change-form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).toContain('提交失败')
    expect((wrapper.get('#contract-change-new-amount').element as HTMLInputElement).value).toBe('102000.00')
    expect((wrapper.get('#contract-change-reason').element as HTMLTextAreaElement).value).toBe('客户调整采购')
  })

  it('ignores an older contract response after the selected contract changes', async () => {
    let resolveOld: ((value: ContractResponse) => void) | undefined
    // This project targets ES2020, so Promise.withResolvers is not available.
    const oldResponse = new Promise<ContractResponse>(resolve => { resolveOld = resolve })
    const fetchContract = vi.spyOn(contractApi, 'getContract').mockReturnValueOnce(oldResponse)
    const wrapper = await renderDetail(contract(), false, false)
    fetchContract.mockResolvedValue(contract({ id: 12, contract_name: '新合同', pending_change: null }))
    await wrapper.setProps({ contractId: 12 })
    await flushPromises()
    resolveOld?.(contract({ contract_name: '旧合同', pending_change: change() }))
    await flushPromises()
    expect(wrapper.text()).toContain('新合同')
    expect(wrapper.text()).not.toContain('旧合同')
    expect(wrapper.find('[data-entity-type="CONTRACT_CHANGE"]').exists()).toBe(false)
  })
})

describe('contract change API boundary', () => {
  it('posts a string-valued multipart payload with an optional file and rejects malformed response data', async () => {
    const file = new File(['agreement'], '补充协议.pdf', { type: 'application/pdf' })
    vi.mocked(request.post).mockResolvedValueOnce(change())
    await contractApi.createContractChange(11, { new_amount: '102000.00', reason: '客户扩容' }, file)
    const payload = vi.mocked(request.post).mock.calls[0]?.[1]
    expect(payload).toBeInstanceOf(FormData)
    if (!(payload instanceof FormData)) throw new Error('Expected multipart change request')
    expect(payload.get('change_payload')).toBe('{"new_amount":"102000.00","reason":"客户扩容"}')
    expect(payload.get('file')).toBe(file)
    vi.mocked(request.post).mockResolvedValueOnce({ id: 31 })
    await expect(contractApi.createContractChange(11, { new_amount: '102000.00', reason: '客户扩容' })).rejects.toThrow()
  })
})
