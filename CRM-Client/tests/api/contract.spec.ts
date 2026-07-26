import { beforeEach, describe, expect, it, vi } from 'vitest'

const { requestMock } = vi.hoisted(() => ({
  requestMock: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('@/utils/request', () => ({
  default: requestMock,
}))

import contractApi from '@/api/contract'

describe('contract API', () => {
  beforeEach(() => {
    requestMock.get.mockReset()
    requestMock.post.mockReset()
    requestMock.put.mockReset()
    requestMock.delete.mockReset()
  })

  it('accepts nullable related info from customer contract list responses', async () => {
    requestMock.get.mockResolvedValue([
      {
        id: 1,
        contract_number: 'CT202607260001',
        contract_name: '测试合同',
        customer_id: 10,
        opportunity_id: 20,
        signing_contact_id: 30,
        user_count: 5,
        total_amount: 10000,
        license_type: 'SUBSCRIPTION',
        subscription_years: 1,
        standard_unit_price: 2000,
        status: 'EFFECTIVE',
        signing_date: null,
        effective_date: null,
        expiry_date: null,
        owner_id: '2',
        creator_id: '3',
        created_time: '2026-07-26T10:00:00',
        last_modified_time: '2026-07-26T10:00:00',
        customer_info: null,
        opportunity_info: null,
        owner_info: null,
        creator_info: null,
        contract_file_path: null,
        contract_file_name: null,
        contract_file_size: null,
        contract_file_mime_type: null,
      },
    ])

    const result = await contractApi.getCustomerContracts(10, { skip: 0, limit: 100 })

    expect(requestMock.get).toHaveBeenCalledWith('/v1/customers/10/contracts', {
      params: { skip: 0, limit: 100 },
    })
    expect(result[0].customer_info).toBeNull()
    expect(result[0].total_amount).toBe('10000')
  })
})
