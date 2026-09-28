import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { projectListFieldCatalog, type ListFieldDefinition } from '@/components/crmwolf/listFieldCatalog'

enableAutoUnmount(afterEach)

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

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/api/payment', () => ({
  default: {
    listPaymentRecords: mocks.listPaymentRecords,
    exportPaymentRecords: vi.fn(),
    updatePaymentRecord: vi.fn(),
    deletePaymentRecord: vi.fn(),
  },
}))
vi.mock('@/stores/permissions', () => ({
  usePermissionStore: () => ({ hasPermission: () => true, hasAnyPermission: () => true }),
}))
vi.mock('@/stores/approval', () => ({
  useApprovalStore: () => ({ submitEntity: vi.fn() }),
}))
vi.mock('@/stores/header', () => ({ useHeaderStore: () => headerStore }))
vi.mock('@/stores/user', () => ({ useUserStore: () => ({ userInfo: { id: 1 } }) }))
vi.mock('@/composables/usePageTitle', () => ({ usePageTitle: () => undefined }))
vi.mock('@/composables/useTopBarRegistration', () => ({ useTopBarRegistration: () => undefined }))
vi.mock('@/composables/useDataTableExport', () => ({
  useDataTableExport: () => ({ exportFields: vi.fn() }),
}))
vi.mock('@/composables/useCustomFilterViews', async () => {
  const { ref } = await import('vue')
  return {
    isCustomFilterViewTab: () => false,
    useCustomFilterViews: () => ({
      saving: ref(false),
      applying: ref(false),
      applyError: ref(null),
      mergeTabs: (tabs: unknown[]) => tabs,
      loadCustomViews: mocks.loadCustomViews,
      updateActiveCustomViewConfig: vi.fn().mockResolvedValue(undefined),
      saveAsCustomView: vi.fn().mockResolvedValue(undefined),
      saveActiveCustomViewColumns: vi.fn().mockResolvedValue(undefined),
      consumeFailedViewApply: () => false,
      applyCustomViewTab: () => false,
      applyBuiltInTab: () => false,
      retryViewApply: vi.fn().mockResolvedValue(undefined),
    }),
  }
})

// Render the real page slots against API rows without mounting the full DataTable controls.
vi.mock('@/components/crmwolf', async () => {
  const { defineComponent, h } = await import('vue')
  const DataTable = defineComponent({
    name: 'DataTable',
    props: {
      fields: { type: Array, default: () => [] },
      data: { type: Array, default: () => [] },
    },
    setup(props, { slots }) {
      return () => h('div', { 'data-testid': 'payment-records-table' },
        (props.data as Array<Record<string, unknown>>).map((row) => h('section', { key: String(row['id']) }, [
          h('div', { 'data-testid': `desktop-license-${row['id']}` },
            slots['cell-license_type']?.({ row, value: row['license_type'] })),
          h('div', { 'data-testid': `desktop-purchase-${row['id']}` },
            slots['cell-purchase_type']?.({ row, value: row['purchase_type'] })),
          h('div', { 'data-testid': `mobile-${row['id']}` },
            slots['mobile-card']?.({ row })),
        ])),
      )
    },
  })
  const AmountText = defineComponent({
    name: 'AmountText',
    props: { value: { type: [Number, String], default: null } },
    setup: (props) => () => h('span', String(props.value ?? '')),
  })
  const TableRowActions = defineComponent({ name: 'TableRowActions', setup: () => () => h('div') })
  return { DataTable, AmountText, TableRowActions }
})
vi.mock('@/views/PaymentRecordDetailSheet.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ name: 'PaymentRecordDetailSheet', setup: () => () => h('div') }) }
})
vi.mock('@/components/dialogs/EditRecordDialog.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ name: 'EditRecordDialog', setup: () => () => h('div') }) }
})
vi.mock('vue-sonner', () => ({ toast: { info: vi.fn(), success: vi.fn() } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

import PaymentRecords from '@/views/PaymentRecords.vue'

const record = (overrides: Record<string, unknown>) => ({
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

  it('exposes adjacent enum columns and their filter, sort, preference and export capabilities', async () => {
    const wrapper = mount(PaymentRecords)
    await flushPromises()

    const fields = wrapper.getComponent({ name: 'DataTable' }).props('fields') as ListFieldDefinition[]
    const contractIndex = fields.findIndex(field => field.key === 'contract_name')
    expect(contractIndex).toBeGreaterThanOrEqual(0)
    expect(fields.slice(contractIndex + 1, contractIndex + 3)).toMatchObject([
      {
        key: 'license_type', label: '授权模式', type: 'enum', filter: true, sort: true,
        options: [{ value: 'SUBSCRIPTION' }, { value: 'PERPETUAL' }],
        column: { align: 'center', width: '110px' },
      },
      {
        key: 'purchase_type', label: '采购类型', type: 'enum', filter: true, sort: true,
        options: [{ value: 'NEW' }, { value: 'RENEWAL' }, { value: 'EXPANSION' }],
        column: { align: 'center', width: '110px' },
      },
    ])

    const projected = projectListFieldCatalog(fields)
    for (const key of ['license_type', 'purchase_type']) {
      expect(projected.columns.find(column => column.key === key)?.hideable).not.toBe(false)
      expect(projected.filterFields.find(field => field.key === key)).toMatchObject({ type: 'enum' })
      expect(projected.sortFields.find(field => field.key === key)).toMatchObject({ type: 'enum' })
      expect(projected.exportFields.find(field => field.key === key)).toMatchObject({ source: 'column' })
    }
  })

  it('renders localized desktop and mobile badges while omitting null mobile values', async () => {
    const wrapper = mount(PaymentRecords)
    await flushPromises()

    expect(wrapper.get('[data-testid="desktop-license-1"]').text()).toBe('订阅制')
    expect(wrapper.get('[data-testid="desktop-purchase-1"]').text()).toBe('续购')
    expect(wrapper.get('[data-testid="desktop-license-3"]').text()).toBe('买断制')
    expect(wrapper.get('[data-testid="desktop-purchase-3"]').text()).toBe('增购')
    expect(wrapper.get('[data-testid="desktop-license-2"]').text()).toBe('-')
    expect(wrapper.get('[data-testid="desktop-purchase-2"]').text()).toBe('-')

    for (const [id, labels] of [[1, ['待确认', '订阅制', '续购']], [3, ['待确认', '买断制', '增购']]] as const) {
      const badges = wrapper.get(`[data-testid="mobile-${id}"]`).findAll('[role="status"]')
      expect(badges.map(badge => badge.attributes('aria-label'))).toEqual(labels)
    }
    const emptyMobile = wrapper.get('[data-testid="mobile-2"]')
    expect(emptyMobile.findAll('[role="status"]')).toHaveLength(1)
    expect(emptyMobile.text()).not.toContain('未知')
  })
})
