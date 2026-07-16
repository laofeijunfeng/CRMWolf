import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const readSource = (relativePath: string): string => {
  return readFileSync(resolve(process.cwd(), relativePath), 'utf-8')
}

describe('Customer opportunity drilldown motion contract', () => {
  it('uses transition wrappers and reduced-motion tokens for the drilldown content swap', () => {
    const customerDetailSource = readSource('src/views/CustomerDetailSheet.vue')
    const opportunityDetailSource = readSource('src/components/panels/OpportunityDetailContent.vue')

    expect(customerDetailSource).toContain('<Transition name="drilldown-fade"')
    expect(customerDetailSource).toContain('.drilldown-fade-enter-active')
    expect(customerDetailSource).toContain('$wolf-motion-state-duration-v2')
    expect(customerDetailSource).toContain('$wolf-reduced-motion-duration-v2')
    expect(opportunityDetailSource).toContain('$wolf-safe-area-bottom-v2')
  })
})
