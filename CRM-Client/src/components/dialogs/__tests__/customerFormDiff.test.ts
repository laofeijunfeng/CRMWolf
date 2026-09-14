import { describe, expect, it } from 'vitest'
import { buildCustomerUpdatePayload } from '../customerFormDiff'
import type { CustomerEditableSnapshot } from '../customerFormDiff'

const baselineSnapshot: CustomerEditableSnapshot = {
  account_name: '客户 A',
  city: '上海',
  address: '浦东',
  company_scale: '51-200人',
  source_public_id: 'acq_source',
  default_procurement_method_id: 8,
  industry: 'internet_saas',
  status: 0,
  license_type: 'TRIAL',
  license_expiry_date: '2026-12-31',
}

describe('buildCustomerUpdatePayload', () => {
  it('sends one changed ordinary field and expected version', () => {
    const current: CustomerEditableSnapshot = {
      account_name: '客户 A',
      city: '深圳',
      address: '浦东',
      company_scale: '51-200人',
      source_public_id: 'acq_source',
      default_procurement_method_id: 8,
      industry: 'internet_saas',
      status: 0,
      license_type: 'TRIAL',
      license_expiry_date: '2026-12-31',
    }
    expect(buildCustomerUpdatePayload(current, baselineSnapshot, 12)).toEqual({
      expected_version: 12,
      city: '深圳',
    })
  })

  it('includes status in the ordinary update diff', () => {
    const current: CustomerEditableSnapshot = {
      account_name: '客户 A',
      city: '上海',
      address: '浦东',
      company_scale: '51-200人',
      source_public_id: 'acq_source',
      default_procurement_method_id: 8,
      industry: 'internet_saas',
      status: 1,
      license_type: 'TRIAL',
      license_expiry_date: '2026-12-31',
    }
    expect(buildCustomerUpdatePayload(current, baselineSnapshot, 12)).toEqual({
      expected_version: 12,
      status: 1,
    })
  })

  it('sends the complete license pair when only the type changes', () => {
    const current: CustomerEditableSnapshot = {
      account_name: '客户 A',
      city: '上海',
      address: '浦东',
      company_scale: '51-200人',
      source_public_id: 'acq_source',
      default_procurement_method_id: 8,
      industry: 'internet_saas',
      status: 0,
      license_type: 'OFFICIAL',
      license_expiry_date: '2026-12-31',
    }
    expect(buildCustomerUpdatePayload(current, baselineSnapshot, 12)).toEqual({
      expected_version: 12,
      license_type: 'OFFICIAL',
      license_expiry_date: '2026-12-31',
    })
  })

  it('normalizes an empty license date to an empty pair', () => {
    const current: CustomerEditableSnapshot = {
      account_name: '客户 A',
      city: '上海',
      address: '浦东',
      company_scale: '51-200人',
      source_public_id: 'acq_source',
      default_procurement_method_id: 8,
      industry: 'internet_saas',
      status: 0,
      license_type: 'OFFICIAL',
      license_expiry_date: '',
    }
    expect(buildCustomerUpdatePayload(current, baselineSnapshot, 12)).toEqual({
      expected_version: 12,
      license_type: null,
      license_expiry_date: null,
    })
  })

  it('returns null when every business value is unchanged', () => {
    expect(buildCustomerUpdatePayload(baselineSnapshot, baselineSnapshot, 12)).toBeNull()
  })

  it('normalizes a cleared address to null only when the address changed', () => {
    const current: CustomerEditableSnapshot = {
      ...baselineSnapshot,
      address: '',
    }
    expect(buildCustomerUpdatePayload(current, baselineSnapshot, 12)).toEqual({
      expected_version: 12,
      address: null,
    })
  })
})
