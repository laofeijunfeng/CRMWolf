import { describe, expect, it } from 'vitest'
import { formatOpportunityModuleNames, formatOpportunityProductName, formatOpportunityProductSummary } from '../opportunityProduct'

describe('formatOpportunityProductSummary', () => {
  it('stacks product and module names for list scanning', () => {
    expect(formatOpportunityProductSummary({
      product_name: 'CRM',
      product_modules: [
        { name: '基础版' },
        { name: '专业版' },
      ],
    })).toBe('CRM · 基础版、专业版')
  })

  it('falls back to product, modules, or the empty label', () => {
    expect(formatOpportunityProductSummary({ product_name: 'OA' })).toBe('OA')
    expect(formatOpportunityModuleNames({
      product_modules: [{ name: '基础版' }, { name: '  ' }],
    })).toBe('基础版')
    expect(formatOpportunityProductSummary({
      product_modules: [{ name: '基础版' }],
    })).toBe('基础版')
    expect(formatOpportunityProductSummary({}, '未关联产品')).toBe('未关联产品')
  })
})

describe('formatOpportunityProductName', () => {
  it('keeps the product line free of module names', () => {
    expect(formatOpportunityProductName({
      product_name: 'Apifox',
      product_modules: [{ name: '基础版' }],
    })).toBe('Apifox')
  })

  it('falls back to the empty label when the product is missing', () => {
    expect(formatOpportunityProductName({
      product_modules: [{ name: '基础版' }],
    })).toBe('-')
  })
})
