import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PaymentRecordList from '@/components/PaymentRecordList.vue'
import type { PaymentRecordInfo } from '@/api/payment'

const paymentRecordsFixture = (): PaymentRecordInfo[] => [
  {
    id: 501,
    actual_amount: 12345.67,
    payment_date: '2026-07-10',
    proof_attachment: 'https://example.com/proof.pdf',
    creator_name: '张三',
    notes: '首笔到账',
    confirmation_status: 'PENDING',
    created_time: '2026-07-10T09:30:00.000Z',
    approval_id: 9001,
    invoice_application_count: 2,
  },
  {
    id: 502,
    actual_amount: 88000,
    payment_date: '2026-07-12',
    creator_name: '李四',
    confirmation_status: 'CONFIRMED',
    created_time: '2026-07-12T10:00:00.000Z',
    invoice_application_count: 0,
  },
]

const sourceText = (): string => readFileSync(
  `${process.cwd()}/src/components/PaymentRecordList.vue`,
  'utf8'
)

describe('PaymentRecordList V2 card layout', () => {
  it('renders payment records as interactive ListCard rows with edit and approval seams', async () => {
    const records = paymentRecordsFixture()
    const wrapper = mount(PaymentRecordList, {
      props: { records },
    })

    expect(wrapper.find('table').exists()).toBe(false)
    expect(wrapper.find('.list-card').exists()).toBe(true)

    const rows = wrapper.findAll('.list-card-item')
    expect(rows).toHaveLength(2)
    expect(wrapper.text()).toContain('¥12,345.67')
    expect(wrapper.text()).toContain('2026-07-10')
    expect(wrapper.text()).toContain('张三')
    expect(wrapper.text()).toContain('待确认')
    expect(wrapper.text()).toContain('2 张发票')

    await rows[0].trigger('click')
    expect(wrapper.emitted('record-click')?.[0]).toEqual([records[0]])

    await wrapper.get('[aria-label="编辑 2026-07-10 回款记录"]').trigger('click')
    expect(wrapper.emitted('edit-record')?.[0]).toEqual([records[0]])
    expect(wrapper.emitted('record-click')).toHaveLength(1)

    await wrapper.get('[aria-label="查看 2026-07-10 回款审批"]').trigger('click')
    expect(wrapper.emitted('view-approval')?.[0]).toEqual([records[0]])
    expect(wrapper.emitted('record-click')).toHaveLength(1)
  })

  it('emits register from the empty state action', async () => {
    const wrapper = mount(PaymentRecordList, {
      props: { records: [] },
    })

    expect(wrapper.text()).toContain('暂无回款记录')
    await wrapper.get('[aria-label="登记回款"]').trigger('click')

    expect(wrapper.emitted('register')).toHaveLength(1)
  })

  it('uses V2 primitives and removes Element Plus table markup from the component source', () => {
    const source = sourceText()

    expect(source).toContain('ListCard')
    expect(source).toContain('variables-v2.scss')
    expect(source).not.toMatch(/<el-/)
    expect(source).not.toContain('element-plus')
    expect(source).not.toContain('@element-plus')
    expect(source).not.toContain('variables.scss')
  })
})
