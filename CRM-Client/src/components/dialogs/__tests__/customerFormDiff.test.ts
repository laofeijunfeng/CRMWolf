import { describe, expect, it } from 'vitest'
import { buildCustomerUpdatePayload } from '../customerFormDiff'

const baseline = {
  account_name: '客户 A',
  city: '上海',
  address: '浦东',
  company_scale: '51-200人',
  source_public_id: 'acq_source',
  default_procurement_method_id: 8,
  industry: 'internet.enterprise',
}

describe('buildCustomerUpdatePayload', () => {
  it('sends only the changed field and expected version', () => {
    expect(buildCustomerUpdatePayload(
      { ...baseline, industry: 'finance.securities' },
      baseline,
      12,
    )).toEqual({ expected_version: 12, industry: 'finance.securities' })
  })

  it('does not send untouched collapsed fields', () => {
    expect(buildCustomerUpdatePayload(baseline, baseline, 12)).toBeNull()
  })

  it('normalizes a cleared address to null only when the address changed', () => {
    expect(buildCustomerUpdatePayload(
      { ...baseline, address: '' },
      baseline,
      12,
    )).toEqual({ expected_version: 12, address: null })
  })
})
