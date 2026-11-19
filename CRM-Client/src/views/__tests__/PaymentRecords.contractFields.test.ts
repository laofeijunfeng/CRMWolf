import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VNode } from 'vue'
import { projectListFieldCatalog, type ListFieldDefinition } from '@/components/crmwolf/listFieldCatalog'
import { formatCurrency } from '@/utils/format'

const mocks = vi.hoisted(() => ({
  listPaymentRecords: vi.fn(),
  loadCustomViews: vi.fn(),
}))

const headerStore = vi.hoisted(() => ({
  activeTab: 'all',
  setActiveTab: vi.fn(),
  setTabs: vi.fn(),
  setActions: vi.fn(),
}))

vi.mock('vue-router', (): Record<string, unknown> => ({ useRouter: (): Record<string, unknown> => ({ push: vi.fn() }) }))
vi.mock('@/api/payment', () => ({
  default: {
    listPaymentRecords: mocks.listPaymentRecords,
    exportPaymentRecords: vi.fn(),
    updatePaymentRecord: vi.fn(),
    deletePaymentRecord: vi.fn(),
  },
}))
vi.mock('@/stores/permissions', () => ({
  usePermissionStore: (): Record<string, unknown> => ({
    permissions: [{ code: 'payment:record:export' }],
    loadState: 'ready',
    hasPermission: (): boolean => true,
    hasAnyPermission: (): boolean => true,
  }),
}))
vi.mock('@/stores/approval', () => ({
  useApprovalStore: (): Record<string, unknown> => ({ submitEntity: vi.fn() }),
}))
vi.mock('@/stores/header', () => ({ useHeaderStore: (): typeof headerStore => headerStore }))
vi.mock('@/stores/team', () => ({ useTeamStore: (): Record<string, unknown> => ({ currentTeam: { id: 11 } }) }))
vi.mock('@/stores/user', () => ({ useUserStore: (): Record<string, unknown> => ({ userInfo: { id: 1 } }) }))
vi.mock('@/composables/usePageTitle', () => ({ usePageTitle: (): void => undefined }))
vi.mock('@/composables/useTopBarRegistration', () => ({ useTopBarRegistration: (): void => undefined }))
vi.mock('@/composables/useDataTableExport', () => ({
  useDataTableExport: (): Record<string, unknown> => ({ exportFields: vi.fn() }),
}))
vi.mock('@/composables/useCustomFilterViews', async (): Promise<Record<string, unknown>> => {
  const { ref } = await import('vue')
  return {
    isCustomFilterViewTab: (): boolean => false,
    useCustomFilterViews: (): Record<string, unknown> => ({
      saving: ref(false),
      applying: ref(false),
      applyError: ref(null),
      mergeTabs: (tabs: unknown[]): unknown[] => tabs,
      loadCustomViews: mocks.loadCustomViews,
      updateActiveCustomViewConfig: vi.fn().mockResolvedValue(undefined),
      saveAsCustomView: vi.fn().mockResolvedValue(undefined),
      saveActiveCustomViewColumns: vi.fn().mockResolvedValue(undefined),
      consumeFailedViewApply: (): boolean => false,
      applyCustomViewTab: (): boolean => false,
      applyBuiltInTab: (): boolean => false,
      retryViewApply: vi.fn().mockResolvedValue(undefined),
    }),
  }
})

// Render the real page slots against API rows without mounting the full DataTable controls.
vi.mock('@/components/crmwolf', async (): Promise<Record<string, unknown>> => {
  const { defineComponent, h } = await import('vue')
  const AmountText = defineComponent({
    name: 'AmountText',
    props: { value: { type: [Number, String], default: null } },
    setup: (props): (() => VNode) => () => h('span', formatCurrency(props.value as number | string | null)),
  })
  const DataTable = defineComponent({
    name: 'DataTable',
    props: {
      fields: { type: Array, default: () => [] },
      data: { type: Array, default: () => [] },
    },
    setup(props, { slots }): () => VNode {
      return () => h('div', { 'data-testid': 'payment-records-table' },
        (props.data as Record<string, unknown>[]).map((row) => h('section', {
          key: String(row['id']),
          'data-testid': `record-${row['id']}`,
        }, [
          h('div', { 'data-testid': `desktop-${row['id']}` }, [
            h('div', { 'data-testid': `cell-license_type-${row['id']}` }, slots['cell-license_type']?.({ row, value: row['license_type'] })),
            h('div', { 'data-testid': `cell-purchase_type-${row['id']}` }, slots['cell-purchase_type']?.({ row, value: row['purchase_type'] })),
            ...['purchase_headcount', 'purchase_amount', 'actual_amount'].map(key =>
              h('div', { 'data-testid': `cell-${key}-${row['id']}` },
                slots[`cell-${key}`]?.({ row, value: row[key] })),
            ),
          ]),
          h('div', { 'data-testid': `mobile-${row['id']}` },
            slots['mobile-card']?.({ row })),
        ])),
      )
    },
  })
  const TableRowActions = defineComponent({ name: 'TableRowActions', setup: (): (() => VNode) => () => h('div') })
  return { DataTable, AmountText, TableRowActions }
})
vi.mock('@/components/panels/PaymentRecordDetailSheet.vue', async (): Promise<Record<string, unknown>> => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ name: 'PaymentRecordDetailSheet', setup: (): (() => VNode) => () => h('div') }) }
})
vi.mock('@/components/dialogs/EditRecordDialog.vue', async (): Promise<Record<string, unknown>> => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ name: 'EditRecordDialog', setup: (): (() => VNode) => () => h('div') }) }
})
vi.mock('vue-sonner', () => ({ toast: { info: vi.fn(), success: vi.fn() } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

import PaymentRecords from '@/views/PaymentRecords.vue'

const record = (overrides: Record<string, unknown>): Record<string, unknown> => ({
  id: 1,
  payment_plan_id: 10,
  record_number: 'PAY-001',
  actual_amount: 1200,
  payment_date: '2026-09-28',
  created_time: '2026-09-28T10:00:00',
  last_modified_time: '2026-09-28T10:00:00',
  confirmation_status: 'PENDING',
  customer_name: '测试客户',
  contract_name: '测试合同',
  ...overrides,
})

const showRecords = (items: Record<string, unknown>[]): void => {
  mocks.listPaymentRecords.mockResolvedValue({ items, total: items.length, page: 1, page_size: 20, total_pages: 1 })
}

describe('PaymentRecords contract fields', () => {
  beforeEach(() => {
    mocks.listPaymentRecords.mockReset().mockResolvedValue({
      items: [
        record({ id: 1, license_type: 'SUBSCRIPTION', purchase_type: 'RENEWAL' }),
        record({ id: 2, record_number: 'PAY-002', license_type: null, purchase_type: null }),
        record({ id: 3, record_number: 'PAY-003', license_type: 'PERPETUAL', purchase_type: 'EXPANSION' }),
      ],
      total: 3,
      page: 1,
      page_size: 20,
      total_pages: 1,
    })
    mocks.loadCustomViews.mockReset().mockResolvedValue(undefined)
    headerStore.activeTab = 'all'
  })


  it('shows adjacent purchase type, headcount, purchase amount and actual amount columns with purchase type queries', async () => {
    const wrapper = mount(PaymentRecords)
    await flushPromises()

    const fields = wrapper.getComponent({ name: 'DataTable' }).props('fields') as ListFieldDefinition[]
    const projected = projectListFieldCatalog(fields)
    const purchaseIndex = projected.columns.findIndex(column => column.key === 'purchase_type')
    expect(purchaseIndex).toBeGreaterThanOrEqual(0)
    expect(projected.columns.slice(purchaseIndex, purchaseIndex + 4)).toMatchObject([
      { key: 'purchase_type', title: '采购类型' },
      { key: 'purchase_headcount', title: '采购人数', align: 'right' },
      { key: 'purchase_amount', title: '采购金额', align: 'right' },
      { key: 'actual_amount', title: '回款金额', align: 'right' },
    ])
    expect(projected.columns.slice(purchaseIndex, purchaseIndex + 4).every(column => column.visible !== false)).toBe(true)

    for (const key of ['license_type', 'purchase_type']) {
      expect(projected.columns.find(column => column.key === key)?.hideable).not.toBe(false)
      expect(projected.filterFields.find(field => field.key === key)).toMatchObject({ type: 'enum' })
      expect(projected.sortFields.find(field => field.key === key)).toMatchObject({ type: 'enum' })
      expect(projected.exportFields.find(field => field.key === key)).toMatchObject({ source: 'column' })
    }
    expect(projected.filterFields.find(field => field.key === 'purchase_type')?.options).toMatchObject([
      { value: 'NEW' }, { value: 'RENEWAL' }, { value: 'EXPANSION' },
    ])
    wrapper.unmount()
  })

  it('keeps the old four composition fields export-only and outside columns, filters and sorts', async () => {
    const wrapper = mount(PaymentRecords)
    await flushPromises()

    const fields = wrapper.getComponent({ name: 'DataTable' }).props('fields') as ListFieldDefinition[]
    const projected = projectListFieldCatalog(fields)
    for (const key of ['renewal_headcount', 'renewal_amount', 'expansion_headcount', 'expansion_amount']) {
      expect(projected.columns.some(column => column.key === key)).toBe(false)
      expect(projected.filterFields.some(field => field.key === key)).toBe(false)
      expect(projected.sortFields.some(field => field.key === key)).toBe(false)
      expect(projected.exportFields.find(field => field.key === key)).toMatchObject({ source: 'export-only' })
    }
    wrapper.unmount()
  })

  it('excludes derived purchase columns from queries and exports with explicit query-disabled reasons', async () => {
    const wrapper = mount(PaymentRecords)
    await flushPromises()

    const fields = wrapper.getComponent({ name: 'DataTable' }).props('fields') as ListFieldDefinition[]
    const projected = projectListFieldCatalog(fields)
    for (const key of ['purchase_headcount', 'purchase_amount']) {
      const field = fields.find(item => item.key === key)
      expect(field).toMatchObject({ filter: false, sort: false, export: false })
      expect(field?.filterDisabledReason?.trim()).toBeTruthy()
      expect(field?.sortDisabledReason?.trim()).toBeTruthy()
      expect(projected.filterFields.some(item => item.key === key)).toBe(false)
      expect(projected.sortFields.some(item => item.key === key)).toBe(false)
      expect(projected.exportFields.some(item => item.key === key)).toBe(false)
    }
    expect(projected.exportFields.some(field => field.key === 'contract_user_count')).toBe(false)
    wrapper.unmount()
  })

  it('renders mixed renewal and expansion in one record with ordered purchase cells and one actual total per surface', async () => {
    showRecords([record({
      purchase_type: 'RENEWAL',
      contract_user_count: 999,
      actual_amount: 150000,
      composition: {
        renewal: { headcount: 100, amount: 100000 },
        expansion: { headcount: 50, amount: 50000 },
      },
    })])
    const wrapper = mount(PaymentRecords)
    await flushPromises()

    expect(wrapper.get('[data-testid="payment-records-table"]').findAll('section')).toHaveLength(1)
    expect(wrapper.get('[data-testid="cell-purchase_type-1"]').text()).toMatch(/^续购\s*增购$/)
    expect(wrapper.get('[data-testid="cell-purchase_headcount-1"]').text()).toMatch(/^100\s*人\s*50\s*人$/)
    expect(wrapper.get('[data-testid="cell-purchase_amount-1"]').text()).toMatch(/^¥100,000\.00\s*¥50,000\.00$/)
    expect(wrapper.get('[data-testid="cell-actual_amount-1"]').text()).toBe('¥150,000.00')
    expect(wrapper.get('[data-testid="desktop-1"]').text().match(/¥150,000\.00/g)).toHaveLength(1)

    const mobile = wrapper.get('[data-testid="mobile-1"]').text()
    expect(mobile).toMatch(/续购.*100\s*人.*¥100,000\.00.*增购.*50\s*人.*¥50,000\.00/)
    expect(mobile.match(/¥150,000\.00/g)).toHaveLength(1)
    expect(mobile).not.toContain('999')
    wrapper.unmount()
  })

  it('omits a zero-headcount zero-amount segment from purchase cells and the mobile card', async () => {
    showRecords([record({
      purchase_type: 'RENEWAL',
      actual_amount: 100000,
      composition: {
        renewal: { headcount: 100, amount: 100000 },
        expansion: { headcount: 0, amount: 0 },
      },
    })])
    const wrapper = mount(PaymentRecords)
    await flushPromises()

    expect(wrapper.get('[data-testid="cell-purchase_type-1"]').text()).toBe('续购')
    expect(wrapper.get('[data-testid="cell-purchase_headcount-1"]').text()).toMatch(/^100\s*人$/)
    expect(wrapper.get('[data-testid="cell-purchase_amount-1"]').text()).toBe('¥100,000.00')
    const mobile = wrapper.get('[data-testid="mobile-1"]').text()
    expect(mobile).toMatch(/续购.*100\s*人.*¥100,000\.00/)
    expect(mobile).not.toContain('增购')
    expect(mobile).not.toMatch(/(?:^|\D)0\s*人/)
    expect(mobile).not.toContain('¥0.00')
    wrapper.unmount()
  })

  it('falls back to the legacy purchase type, contract headcount and actual amount without composition', async () => {
    showRecords([record({ purchase_type: 'NEW', contract_user_count: 80, actual_amount: 80000 })])
    const wrapper = mount(PaymentRecords)
    await flushPromises()

    expect(wrapper.get('[data-testid="cell-purchase_type-1"]').text()).toBe('新购')
    expect(wrapper.get('[data-testid="cell-purchase_headcount-1"]').text()).toMatch(/^80\s*人$/)
    expect(wrapper.get('[data-testid="cell-purchase_amount-1"]').text()).toBe('¥80,000.00')
    expect(wrapper.get('[data-testid="cell-actual_amount-1"]').text()).toBe('¥80,000.00')
    const mobile = wrapper.get('[data-testid="mobile-1"]').text()
    expect(mobile).toMatch(/新购.*80\s*人.*¥80,000\.00/)
    expect(mobile).not.toContain('续购')
    expect(mobile).not.toContain('增购')
    wrapper.unmount()
  })

  it('shows an em dash rather than zero for a legacy record with no contract headcount', async () => {
    showRecords([record({ purchase_type: 'EXPANSION', actual_amount: 50000 })])
    const wrapper = mount(PaymentRecords)
    await flushPromises()

    expect(wrapper.get('[data-testid="cell-purchase_type-1"]').text()).toBe('增购')
    expect(wrapper.get('[data-testid="cell-purchase_headcount-1"]').text()).toBe('—')
    expect(wrapper.get('[data-testid="cell-purchase_headcount-1"]').text()).not.toContain('0')
    expect(wrapper.get('[data-testid="cell-purchase_amount-1"]').text()).toBe('¥50,000.00')
    const mobile = wrapper.get('[data-testid="mobile-1"]').text()
    expect(mobile).toMatch(/增购.*—.*¥50,000\.00/)
    expect(mobile).not.toMatch(/(?:^|\D)0\s*人/)
    wrapper.unmount()
  })

  it('renders localized desktop and mobile badges while omitting null mobile values', async () => {
    const wrapper = mount(PaymentRecords)
    await flushPromises()

    expect(wrapper.get('[data-testid="cell-license_type-1"]').text()).toBe('订阅制')
    expect(wrapper.get('[data-testid="cell-purchase_type-1"]').text()).toBe('续购')
    expect(wrapper.get('[data-testid="cell-license_type-3"]').text()).toBe('买断制')
    expect(wrapper.get('[data-testid="cell-purchase_type-3"]').text()).toBe('增购')
    expect(wrapper.get('[data-testid="cell-license_type-2"]').text()).toBe('-')
    expect(wrapper.get('[data-testid="cell-purchase_type-2"]').text()).toBe('—')

    for (const [id, labels] of [[1, ['待确认', '订阅制', '续购']], [3, ['待确认', '买断制', '增购']]] as const) {
      const badges = wrapper.get(`[data-testid="mobile-${id}"]`).findAll('[role="status"]')
      expect(badges.map(badge => badge.attributes('aria-label'))).toEqual(labels)
    }
    const emptyMobile = wrapper.get('[data-testid="mobile-2"]')
    expect(emptyMobile.findAll('[role="status"]')).toHaveLength(1)
    expect(emptyMobile.text()).not.toContain('未知')
    wrapper.unmount()
  })
})
