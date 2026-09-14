import { beforeEach, describe, expect, it, vi } from 'vitest'

const post = vi.fn()
const put = vi.fn()
const patch = vi.fn()
const get = vi.fn()

vi.mock('@/utils/request', () => ({
  default: {
    post,
    put,
    patch,
    get,
  },
}))

const customerResponse = {
  id: 'customer-1',
  public_id: 'CUS-001',
  account_name: 'Acme Corp',
  industry: null,
  city: 'Shanghai',
  address: null,
  company_scale: null,
  source: null,
  source_info: null,
  status: 0,
  owner_id: null,
  source_lead_id: null,
  default_procurement_method_id: null,
  return_reason: null,
  returned_time: null,
  creator_id: 'user-1',
  created_time: '2026-01-01T00:00:00',
  last_modified_time: '2026-01-01T00:00:00',
  version: 3,
  license_expiry_date: null,
  license_type: null,
}

describe('customerApi lifecycle, license snapshot, and industry hierarchy', () => {
  beforeEach(() => {
    post.mockReset()
    put.mockReset()
    patch.mockReset()
    get.mockReset()
  })

  it('updates ordinary customer fields with PUT and parses the customer response', async () => {
    put.mockResolvedValue(customerResponse)
    const { default: customerApi } = await import('../customer')

    const payload = {
      expected_version: 3,
      city: '深圳',
      status: 1 as const,
      license_type: 'OFFICIAL' as const,
      license_expiry_date: '2027-01-01',
    }

    const result = await customerApi.updateCustomer('customer-1', payload)

    expect(put).toHaveBeenCalledWith('/v1/customers/customer-1', payload, undefined)
    expect(result).toEqual(customerResponse)
  })

  it('rejects malformed ordinary PUT responses through the customer response schema', async () => {
    put.mockResolvedValue({ ...customerResponse, version: '3' })
    const { default: customerApi } = await import('../customer')

    await expect(customerApi.updateCustomer('customer-1', {
      expected_version: 3,
      city: '深圳',
    })).rejects.toThrow()
  })

  it('updates lifecycle status with the expected version and parses the customer response', async () => {
    patch.mockResolvedValue(customerResponse)
    const { default: customerApi } = await import('../customer')

    const result = await customerApi.updateCustomerLifecycleStatus('customer-1', {
      status: 1,
      expected_version: 3,
    })

    expect(patch).toHaveBeenCalledWith('/v1/customers/customer-1/lifecycle-status', {
      status: 1,
      expected_version: 3,
    }, undefined)
    expect(result).toEqual(customerResponse)
  })

  it('updates only the defined license snapshot fields and parses the customer response', async () => {
    patch.mockResolvedValue(customerResponse)
    const { default: customerApi } = await import('../customer')

    const result = await customerApi.updateCustomerLicenseSnapshot('customer-1', {
      expected_version: 3,
      license_type: 'OFFICIAL',
      license_expiry_date: '2027-01-01',
    })

    expect(patch).toHaveBeenCalledWith('/v1/customers/customer-1/license-snapshot', {
      expected_version: 3,
      license_type: 'OFFICIAL',
      license_expiry_date: '2027-01-01',
    }, undefined)
    expect(result).toEqual(customerResponse)
  })

  it('rejects malformed license snapshot responses through the customer response schema', async () => {
    patch.mockResolvedValue({ ...customerResponse, version: '3' })
    const { default: customerApi } = await import('../customer')

    await expect(customerApi.updateCustomerLicenseSnapshot('customer-1', {
      expected_version: 3,
      license_type: 'OFFICIAL',
      license_expiry_date: '2027-01-01',
    })).rejects.toThrow()
  })

  it('parses industry hierarchy responses with empty child arrays', async () => {
    const hierarchy = {
      technology: {
        name: 'Technology',
        children: [],
      },
    }
    get.mockResolvedValue(hierarchy)
    const { default: customerApi } = await import('../customer')

    const result = await customerApi.getIndustryHierarchy()

    expect(get).toHaveBeenCalledWith('/v1/industries/hierarchy', undefined)
    expect(result).toEqual(hierarchy)
  })

  it('rejects malformed industry hierarchy responses through the hierarchy schema', async () => {
    get.mockResolvedValue({
      technology: {
        name: 'Technology',
        children: [{ name: 'Missing code' }],
      },
    })
    const { default: customerApi } = await import('../customer')

    await expect(customerApi.getIndustryHierarchy()).rejects.toThrow()
  })

  it('rejects customer responses that do not satisfy the response schema', async () => {
    patch.mockResolvedValue({ ...customerResponse, version: '3' })
    const { default: customerApi } = await import('../customer')

    await expect(customerApi.updateCustomerLifecycleStatus('customer-1', {
      status: 1,
      expected_version: 3,
    })).rejects.toThrow()
  })
})
