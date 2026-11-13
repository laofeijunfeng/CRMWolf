import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PaymentRecordResponse } from '@/api/payment'
import PaymentNextStepDialog from '../PaymentNextStepDialog.vue'


const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  submitEntity: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.push }),
}))

vi.mock('@/stores/approval', () => ({
  useApprovalStore: () => ({ submitEntity: mocks.submitEntity }),
}))

const record: PaymentRecordResponse = {
  id: 42,
  payment_plan_id: 7,
  actual_amount: 1000,
  payment_date: '2026-11-13',
  created_time: '2026-11-13T00:00:00Z',
  last_modified_time: '2026-11-13T00:00:00Z',
}

describe('PaymentNextStepDialog', () => {
  beforeEach(() => {
    mocks.push.mockReset()
    mocks.submitEntity.mockReset()
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('keeps the dialog active and prevents duplicate or detail actions while submitting', async () => {
    let resolveSubmit: ((value: { approval_id: number; status: string }) => void) | undefined
    mocks.submitEntity.mockImplementation(() => new Promise((resolve) => {
      resolveSubmit = resolve
    }))

    const wrapper = mount(PaymentNextStepDialog, {
      props: { visible: true, record },
      attachTo: document.body,
    })
    await flushPromises()
    const dialog = new DOMWrapper(document.body)

    const submit = dialog.findAll('button').find((button) => button.text().includes('立即提交审批'))
    if (!submit) throw new Error('submit card not found')
    await submit.trigger('click')
    expect(mocks.submitEntity).toHaveBeenCalledTimes(1)
    expect(submit.attributes('disabled')).toBeDefined()
    expect(submit.attributes('aria-busy')).toBe('true')

    const later = dialog.findAll('button').find((button) => button.text().includes('稍后提交'))
    const detail = dialog.findAll('button').find((button) => button.text().includes('查看详情'))
    if (!later || !detail) throw new Error('pending actions not found')
    await later.trigger('click')
    await detail.trigger('click')
    await submit.trigger('click')
    expect(wrapper.emitted('update:visible')).toBeUndefined()
    expect(mocks.push).not.toHaveBeenCalled()
    expect(mocks.submitEntity).toHaveBeenCalledTimes(1)

    resolveSubmit?.({ approval_id: 1, status: 'PENDING' })
    await flushPromises()
    expect(wrapper.emitted('update:visible')).toEqual([[false]])
    wrapper.unmount()
  })

})
