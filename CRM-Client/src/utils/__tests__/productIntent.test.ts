import { describe, expect, it } from 'vitest'
import { formatProductIntentName, productPublicIdFromIntent } from '../productIntent'

describe('formatProductIntentName', () => {
  it('prefers product_name', () => {
    expect(formatProductIntentName({
      product_name: 'CRM',
      product_public_id: 'prd_crm',
      products: [{ public_id: 'prd_oa', name: 'OA' }],
    })).toBe('CRM')
  })

  it('falls back to the associated products list', () => {
    expect(formatProductIntentName({
      product_public_id: 'prd_oa',
      products: [{ public_id: 'prd_oa', name: 'OA' }],
    })).toBe('OA')
    expect(formatProductIntentName({
      products: [{ public_id: 'prd_crm', name: 'CRM' }],
    })).toBe('CRM')
    expect(formatProductIntentName({ product_public_id: 'prd_crm' })).toBe('-')
    expect(formatProductIntentName({})).toBe('-')
  })
})

describe('productPublicIdFromIntent', () => {
  it('hydrates a missing public id from the products list', () => {
    expect(productPublicIdFromIntent({
      products: [{ public_id: 'prd_crm', name: 'CRM' }],
    })).toBe('prd_crm')
    expect(productPublicIdFromIntent({ product_public_id: 'prd_oa' })).toBe('prd_oa')
    expect(productPublicIdFromIntent({})).toBe('')
  })
})
