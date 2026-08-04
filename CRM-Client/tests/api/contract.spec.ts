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
        customer_id: 'CUS202607260001',
        customer_name: '测试客户',
        opportunity_id: 20,
        opportunity_name: '测试商机',
        purchase_type: 'RENEWAL',
        signing_contact_id: 30,
        user_count: 5,
        total_amount: 10000,
        license_type: 'SUBSCRIPTION',
        subscription_years: 1,
        license_authorized_users: 8,
        license_expiry_date: '2027-07-26',
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

    const result = await contractApi.getCustomerContracts('CUS202607260001', { skip: 0, limit: 100 })

    expect(requestMock.get).toHaveBeenCalledWith('/v1/customers/CUS202607260001/contracts', {
      params: { skip: 0, limit: 100 },
    })
    expect(result[0].customer_info).toBeNull()
    expect(result[0].total_amount).toBe('10000')
    expect(result[0].purchase_type).toBe('RENEWAL')
    expect(result[0].license_authorized_users).toBe(8)
    expect(result[0].license_expiry_date).toBe('2027-07-26')
  })
})
