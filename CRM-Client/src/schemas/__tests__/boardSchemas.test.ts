import { beforeEach, describe, expect, it, vi } from 'vitest'

const requestGet = vi.hoisted(() => vi.fn())

vi.mock('@/utils/request', () => ({
  default: {
    get: requestGet,
  },
}))

import customerApi, {
  type CustomerBoardParams,
  type CustomerQueryParams,
} from '@/api/customer'
import { contractApi, type ContractBoardParams, type ContractQueryParams } from '@/api/contract'
import { opportunityApi, type OpportunityBoardParams, type OpportunityListParams } from '@/api/opportunity'
import paymentApi, {
  type PaymentPlanBoardParams,
  type PaymentPlanListParams,
  type PaymentRecordBoardParams,
  type PaymentRecordListParams,
} from '@/api/payment'
import {
  ContractBoardResponseSchema,
  type ContractBoardResponse,
} from '@/schemas/contractBoard'
import {
  CustomerBoardResponseSchema,
  type CustomerBoardResponse,
} from '@/schemas/customerBoard'
import {
  OpportunityBoardResponseSchema,
  type OpportunityBoardResponse,
} from '@/schemas/opportunityBoard'
import {
  PaymentPlanBoardResponseSchema,
  type PaymentPlanBoardResponse,
} from '@/schemas/paymentPlanBoard'
import {
  PaymentRecordBoardResponseSchema,
  type PaymentRecordBoardResponse,
} from '@/schemas/paymentRecordBoard'

type BoardSchema = {
  safeParse: (value: unknown) => { success: boolean }
}

type ColumnKey = string

interface BoardCase {
  name: string
  schema: BoardSchema
  empty: Record<string, unknown>
  populated: Record<string, unknown>
  columnKeys: readonly ColumnKey[]
  percentageKey?: string
  secondaryKey: string
}

const owner = { id: 'user-1', name: 'Ada', avatar_url: null }

const customerColumns = ['not_started', 'following', 'repurchasing', 'won', 'lost'] as const
const contractColumns = [
  'DRAFT',
  'PENDING_REVIEW',
  'SIGNED',
  'EFFECTIVE',
  'EXPIRED',
  'TERMINATED',
  'UNCLASSIFIED',
] as const
const planColumns = ['PENDING', 'OVERDUE', 'PARTIAL', 'COMPLETED', 'UNCLASSIFIED'] as const
const recordColumns = [
  'pending_submit',
  'pending_approval',
  'rejected',
  'approved',
  'unclassified',
] as const
const opportunityColumns = [
  { key: 'stage-7', kind: 'active_stage', stage: '需求确认' },
  { key: 'won', kind: 'won', stage: null },
  { key: 'lost', kind: 'lost', stage: null },
  { key: 'unset_stage', kind: 'unset_stage', stage: null },
] as const

function action(flags: Record<string, boolean>): Record<string, boolean> {
  return flags
}

function emptyColumn(key: string, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    key,
    label: key,
    tone: 'neutral',
    count: 0,
    amount: '0.00',
    items: [],
    has_more: false,
    remaining_count: 0,
    ...extra,
  }
}

function customerItem(status: (typeof customerColumns)[number]): Record<string, unknown> {
  return {
    id: `cus-${status}`,
    title: `客户 ${status}`,
    subtitle: null,
    amount: '12.50',
    date: '2026-09-30',
    owner,
    status,
    metadata: {
      stage_hint: null,
      industry: null,
      city: null,
      company_scale: null,
      license_type: null,
      license_expiry_date: null,
    },
    action_state: action({
      can_edit: true,
      can_delete: false,
      can_assign: true,
      can_create_opportunity: true,
    }),
  }
}

function opportunityItem(status: 'active' | 'won' | 'lost' | 'unset_stage'): Record<string, unknown> {
  return {
    id: `opp-${status}`,
    title: `商机 ${status}`,
    subtitle: null,
    amount: '88.00',
    date: '2026-08-18',
    owner,
    status,
    metadata: {
      customer_name: null,
      purchase_type: null,
      license_type: null,
      expected_closing_date: null,
      win_probability: null,
      stage_name: null,
      stage_sort_order: null,
      procurement_method_name: null,
      procurement_method_code: null,
      procurement_stage_template_id: null,
      template_code: null,
    },
    action_state: action({
      can_edit: true,
      can_delete: false,
      can_move_stage: true,
      can_mark_won: true,
      can_mark_lost: true,
    }),
  }
}

function contractItem(status: (typeof contractColumns)[number]): Record<string, unknown> {
  return {
    id: 11,
    title: `合同 ${status}`,
    subtitle: null,
    amount: '100.00',
    date: '2026-07-01',
    owner,
    status,
    metadata: {
      customer_name: null,
      opportunity_name: null,
      license_type: null,
      purchase_type: null,
      signing_date: null,
      effective_date: null,
      expiry_date: null,
      license_expiry_date: null,
      authorized_users: null,
    },
    action_state: action({
      can_edit: true,
      can_delete: false,
      can_submit_approval: true,
      can_approve: false,
      can_reject: false,
    }),
  }
}

function planItem(status: (typeof planColumns)[number]): Record<string, unknown> {
  return {
    id: 21,
    title: `计划 ${status}`,
    subtitle: null,
    amount: '50.00',
    planned_amount: '50.00',
    paid_amount: '20.00',
    remaining_amount: '30.00',
    date: '2026-06-15',
    owner,
    status,
    metadata: {
      customer_name: null,
      contract_name: null,
      opportunity_name: null,
      paid_amount: '20.00',
      remaining_amount: '30.00',
    },
    action_state: action({
      can_edit: true,
      can_delete: false,
      can_view_detail: true,
    }),
  }
}

function recordItem(status: (typeof recordColumns)[number]): Record<string, unknown> {
  return {
    id: 31,
    title: `回款 ${status}`,
    subtitle: null,
    amount: '40.00',
    actual_amount: '40.00',
    date: '2026-05-20',
    owner,
    status,
    metadata: {
      customer_name: null,
      contract_name: null,
      actual_payer_name: null,
      creator_name: null,
      owner_name: null,
      commission_member_name: null,
      approval_phase: null,
      approval_id: null,
      confirmation_status: null,
    },
    action_state: action({
      can_edit: true,
      can_delete: false,
      can_resubmit: true,
    }),
  }
}

function customerColumn(key: (typeof customerColumns)[number], populated: boolean): Record<string, unknown> {
  return populated
    ? {
        ...emptyColumn(key, { amount: null, count: 1, items: [customerItem(key)] }),
      }
    : emptyColumn(key, { amount: null })
}

function opportunityColumn(
  spec: (typeof opportunityColumns)[number],
  populated: boolean,
): Record<string, unknown> {
  const itemStatus = spec.kind === 'active_stage' ? 'active' : spec.kind
  return {
    key: spec.key,
    label: spec.stage ?? spec.key,
    tone: 'info',
    column_kind: spec.kind,
    stage_name: spec.stage,
    template_code: spec.kind === 'active_stage' ? 'standard' : null,
    template_sort_order: spec.kind === 'active_stage' ? 2 : null,
    procurement_method_id: spec.kind === 'active_stage' ? 4 : null,
    procurement_stage_template_id: spec.kind === 'active_stage' ? 9 : null,
    count: populated ? 1 : 0,
    amount: populated ? '88.00' : '0.00',
    items: populated ? [opportunityItem(itemStatus)] : [],
    has_more: false,
    remaining_count: 0,
  }
}

function contractColumn(key: (typeof contractColumns)[number], populated: boolean): Record<string, unknown> {
  return populated
    ? { ...emptyColumn(key), count: 1, amount: '100.00', items: [contractItem(key)] }
    : emptyColumn(key)
}

function planColumn(key: (typeof planColumns)[number], populated: boolean): Record<string, unknown> {
  const amounts = {
    amount: populated ? '50.00' : '0.00',
    planned_amount: populated ? '50.00' : '0.00',
    paid_amount: populated ? '20.00' : '0.00',
    remaining_amount: populated ? '30.00' : '0.00',
    overdue_remaining_amount: key === 'OVERDUE' && populated ? '30.00' : '0.00',
  }
  return populated
    ? { ...emptyColumn(key), ...amounts, count: 1, items: [planItem(key)] }
    : { ...emptyColumn(key), ...amounts }
}

function recordColumn(key: (typeof recordColumns)[number], populated: boolean): Record<string, unknown> {
  const amounts = {
    amount: populated ? '40.00' : '0.00',
    actual_amount: populated ? '40.00' : '0.00',
    confirmed_amount: key === 'approved' && populated ? '40.00' : '0.00',
    unconfirmed_amount: key === 'approved' || !populated ? '0.00' : '40.00',
  }
  return populated
    ? { ...emptyColumn(key), ...amounts, count: 1, items: [recordItem(key)] }
    : { ...emptyColumn(key), ...amounts }
}

function customerPayload(populated: boolean): Record<string, unknown> {
  return {
    summary: populated
      ? [
          { key: 'total_count', label: '客户总数', value_type: 'count', value: 6 },
          {
            key: 'following_percentage',
            label: '跟进占比',
            value_type: 'percentage',
            value: null,
          },
        ]
      : [],
    columns: customerColumns.map((key, index) => customerColumn(key, populated && index === 0)),
    trends: populated ? [{ date: '2026-09', count: 2 }] : [],
  }
}

function opportunityPayload(populated: boolean): Record<string, unknown> {
  return {
    summary: populated
      ? [
          { key: 'total_count', label: '商机数', value_type: 'count', value: 4 },
          { key: 'pipeline_amount', label: '管道金额', value_type: 'amount', value: '88.00' },
        ]
      : [],
    columns: opportunityColumns.map((spec, index) => opportunityColumn(spec, populated && index === 0)),
    trends: populated ? [{ date: '2026-08', count: 1, amount: '88.00' }] : [],
  }
}

function contractPayload(populated: boolean): Record<string, unknown> {
  return {
    summary: populated
      ? [
          { key: 'total_count', label: '合同数', value_type: 'count', value: 7 },
          { key: 'total_amount', label: '合同金额', value_type: 'amount', value: '100.00' },
        ]
      : [],
    columns: contractColumns.map((key, index) => contractColumn(key, populated && index === 0)),
    trends: populated ? [{ date: '2026-07', count: 1, amount: '100.00' }] : [],
  }
}

function planPayload(populated: boolean): Record<string, unknown> {
  return {
    summary: populated
      ? [
          { key: 'overdue_count', label: '逾期数', value_type: 'count', value: 1 },
          { key: 'planned_amount', label: '计划金额', value_type: 'amount', value: '50.00' },
        ]
      : [],
    columns: planColumns.map((key, index) => planColumn(key, populated && index === 0)),
    trends: populated
      ? [{
          date: '2026-06',
          count: 1,
          planned_amount: '50.00',
          paid_amount: '20.00',
          remaining_amount: '30.00',
        }]
      : [],
  }
}

function recordPayload(populated: boolean): Record<string, unknown> {
  return {
    summary: populated
      ? [
          { key: 'total_count', label: '回款数', value_type: 'count', value: 1 },
          { key: 'actual_total', label: '实收', value_type: 'amount', value: '40.00' },
        ]
      : [],
    columns: recordColumns.map((key, index) => recordColumn(key, populated && index === 0)),
    trends: populated
      ? [{
          date: '2026-05',
          count: 1,
          actual_amount: '40.00',
          confirmed_amount: '0.00',
          unconfirmed_amount: '40.00',
        }]
      : [],
  }
}

const cases: readonly BoardCase[] = [
  {
    name: 'customer',
    schema: CustomerBoardResponseSchema,
    empty: customerPayload(false),
    populated: customerPayload(true),
    columnKeys: customerColumns,
    percentageKey: 'following_percentage',
    secondaryKey: 'total_count',
  },
  {
    name: 'opportunity',
    schema: OpportunityBoardResponseSchema,
    empty: opportunityPayload(false),
    populated: opportunityPayload(true),
    columnKeys: opportunityColumns.map((column) => column.key),
    secondaryKey: 'total_count',
  },
  {
    name: 'contract',
    schema: ContractBoardResponseSchema,
    empty: contractPayload(false),
    populated: contractPayload(true),
    columnKeys: contractColumns,
    secondaryKey: 'total_count',
  },
  {
    name: 'payment plan',
    schema: PaymentPlanBoardResponseSchema,
    empty: planPayload(false),
    populated: planPayload(true),
    columnKeys: planColumns,
    secondaryKey: 'overdue_count',
  },
  {
    name: 'payment record',
    schema: PaymentRecordBoardResponseSchema,
    empty: recordPayload(false),
    populated: recordPayload(true),
    columnKeys: recordColumns,
    secondaryKey: 'total_count',
  },
]


function firstColumn(payload: Record<string, unknown>): Record<string, unknown> {
  const columns = payload.columns as Record<string, unknown>[]
  return columns[0]
}

function firstMetric(payload: Record<string, unknown>): Record<string, unknown> {
  const summary = payload.summary as Record<string, unknown>[]
  return summary[0]
}

describe('strict board response schemas', () => {
  it.each(cases)('parses empty and populated $name boards', ({ schema, empty, populated }) => {
    expect(schema.safeParse(empty).success).toBe(true)
    expect(schema.safeParse(populated).success).toBe(true)
  })

  it.each(cases)('rejects malformed $name counts, amounts, and status keys', ({ name, schema, populated, columnKeys }) => {
    for (const count of [true, 1.5, -1]) {
      const payload = structuredClone(populated)
      firstColumn(payload).count = count
      expect(schema.safeParse(payload).success, `${name} count ${String(count)}`).toBe(false)
    }

    const amountPayload = structuredClone(populated)
    firstColumn(amountPayload).amount = '12'
    expect(schema.safeParse(amountPayload).success).toBe(false)

    const unknownPayload = structuredClone(populated)
    unknownPayload.unexpected = true
    expect(schema.safeParse(unknownPayload).success).toBe(false)

    const statusPayload = structuredClone(populated)
    const column = firstColumn(statusPayload)
    if (name === 'opportunity') {
      const items = column.items as Record<string, unknown>[]
      items[0].status = 'not-a-status'
    } else {
      column.key = 'not-a-column'
    }
    expect(schema.safeParse(statusPayload).success).toBe(false)
    expect(columnKeys).not.toContain('not-a-column')
  })

  it('rejects non-finite and out-of-range percentages while accepting null', () => {
    const valid = structuredClone(customerPayload(true))
    expect(CustomerBoardResponseSchema.safeParse(valid).success).toBe(true)

    for (const value of [Number.POSITIVE_INFINITY, Number.NaN, -0.1, 100.1]) {
      const payload = structuredClone(customerPayload(true))
      const percentage = (payload.summary as Record<string, unknown>[])[1]
      percentage.value = value
      expect(CustomerBoardResponseSchema.safeParse(payload).success).toBe(false)
    }
  })

  it.each(cases)('rejects a $name secondary label without its value', ({ schema, populated, secondaryKey }) => {
    const payload = structuredClone(populated)
    const metric = firstMetric(payload)
    metric.key = secondaryKey
    metric.secondary_label = '对比'
    metric.secondary_value = null
    expect(schema.safeParse(payload).success).toBe(false)
  })
})

describe('non-paginated board API methods', () => {
  beforeEach(() => {
    requestGet.mockReset()
  })

  it('parses customer board responses and serializes absent filters and sorts', async () => {
    const payload = customerPayload(true)
    requestGet.mockResolvedValue(payload)

    const result: CustomerBoardResponse = await customerApi.getCustomerBoard({
      source_public_id: 'src-public',
      keyword: 'north',
    })

    expect(result.columns.map((column) => column.key)).toEqual([...customerColumns])
    expect(requestGet).toHaveBeenCalledWith('/v1/customers/board', {
      params: {
        source_public_id: 'src-public',
        keyword: 'north',
        filters: '[]',
        sorts: '[]',
      },
    })
  })

  it('serializes opportunity, contract, and payment board queries without pagination', async () => {
    requestGet.mockResolvedValueOnce(opportunityPayload(false))
    await opportunityApi.getOpportunityBoard({ search: 'renewal' })
    expect(requestGet).toHaveBeenNthCalledWith(1, '/v1/opportunities/board', {
      params: { search: 'renewal', filters: '[]', sorts: '[]' },
    })

    requestGet.mockResolvedValueOnce(contractPayload(false))
    const contract: ContractBoardResponse = await contractApi.getContractBoard({ customer_id: 'cus-1' })
    expect(contract.columns).toHaveLength(contractColumns.length)
    expect(requestGet).toHaveBeenNthCalledWith(2, '/v1/contracts/board', {
      params: { customer_id: 'cus-1', filters: '[]', sorts: '[]' },
    })

    requestGet.mockResolvedValueOnce(planPayload(false))
    const plan: PaymentPlanBoardResponse = await paymentApi.getPaymentPlanBoard({ me: true, status: 'OVERDUE' })
    expect(plan.summary).toEqual([])
    expect(requestGet).toHaveBeenNthCalledWith(3, '/v1/payments/payment-plans/board', {
      params: { me: true, status: 'OVERDUE', filters: '[]', sorts: '[]' },
    })

    requestGet.mockResolvedValueOnce(recordPayload(false))
    const record: PaymentRecordBoardResponse = await paymentApi.getPaymentRecordBoard({ me: false })
    expect(record.trends).toEqual([])
    expect(requestGet).toHaveBeenNthCalledWith(4, '/v1/payments/payment-records/board', {
      params: { me: false, filters: '[]', sorts: '[]' },
    })
  })

  it('keeps me on payment params and excludes pagination from every board param type', () => {
    const customer: CustomerBoardParams = { source_public_id: 'src-public', filters: '[]' }
    const opportunity: OpportunityBoardParams = { search: 'renewal' }
    const contract: ContractBoardParams = { customer_id: 'cus-1' }
    const plan: PaymentPlanBoardParams = { me: true }
    const record: PaymentRecordBoardParams = { me: false }

    expect(customer.source_public_id).toBe('src-public')
    expect(opportunity.search).toBe('renewal')
    expect(contract.customer_id).toBe('cus-1')
    expect(plan.me).toBe(true)
    expect(record.me).toBe(false)

    type ForbiddenPaginationKeys = 'page' | 'page_size' | 'skip' | 'limit'
    type HasForbiddenKey<T> = Extract<keyof T, ForbiddenPaginationKeys> extends never ? false : true
    const paginationExcluded = false satisfies HasForbiddenKey<CustomerBoardParams>
      | HasForbiddenKey<OpportunityBoardParams>
      | HasForbiddenKey<ContractBoardParams>
      | HasForbiddenKey<PaymentPlanBoardParams>
      | HasForbiddenKey<PaymentRecordBoardParams>
    expect(paginationExcluded).toBe(false)

    const paymentScopeAccepted = true satisfies ('me' extends keyof PaymentPlanBoardParams ? true : false)
      & ('me' extends keyof PaymentRecordBoardParams ? true : false)
    expect(paymentScopeAccepted).toBe(true)

    const rejectsPagination = (value: object): void => {
      expect(value).not.toHaveProperty('page')
      expect(value).not.toHaveProperty('page_size')
      expect(value).not.toHaveProperty('skip')
      expect(value).not.toHaveProperty('limit')
    }
    rejectsPagination(customer)
    rejectsPagination(opportunity)
    rejectsPagination(contract)
    rejectsPagination(plan)
    rejectsPagination(record)

    const customerPagination: CustomerQueryParams = { skip: 0, limit: 20 }
    const opportunityPagination: OpportunityListParams = { skip: 0, limit: 20 }
    const contractPagination: ContractQueryParams = { skip: 0, limit: 20 }
    const planPagination: PaymentPlanListParams = { page: 1, page_size: 20 }
    const recordPagination: PaymentRecordListParams = { page: 1, page_size: 20 }
    expect(customerPagination.skip).toBe(0)
    expect(opportunityPagination.limit).toBe(20)
    expect(contractPagination.limit).toBe(20)
    expect(planPagination.page).toBe(1)
    expect(recordPagination.page_size).toBe(20)
  })
})
