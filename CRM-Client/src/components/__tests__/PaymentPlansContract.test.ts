import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const readSource = (relativePath: string): string => {
  return readFileSync(resolve(process.cwd(), relativePath), 'utf-8')
}

describe('ContractPaymentPlans V2 migration contract', () => {
  it('uses ListCard and shadcn-vue primitives', () => {
    const source = readSource('src/components/ContractPaymentPlans.vue')

    expect(source).toContain("@/components/crmwolf/ListCard.vue")
    expect(source).toContain("@/components/ui/button")
    expect(source).toContain("@/components/ui/dialog")
    expect(source).toContain("@/styles/variables-v2.scss")
  })

  it('keeps payment-plan dialogs outside the ListCard content shell', () => {
    const source = readSource('src/components/ContractPaymentPlans.vue')
    const listCardStart = source.indexOf('<ListCard')
    const listCardEnd = source.indexOf('</ListCard>')
    const firstDialog = source.indexOf('<Dialog')

    expect(listCardStart).toBeGreaterThan(-1)
    expect(listCardEnd).toBeGreaterThan(listCardStart)
    expect(firstDialog).toBeGreaterThan(listCardEnd)
  })

  it('keeps payment dialog controls and menu items at accessible touch target sizes', () => {
    const source = readSource('src/components/ContractPaymentPlans.vue')

    expect(source).toMatch(/<DropdownMenuItem[^>]*class="min-h-11"/)
    expect(source).toContain('PaymentRecordDialog')
    expect(source).toContain('PaymentPlanFormDialog')
    expect(source).toContain('text-wolf-danger-text')
    expect(source).not.toContain('text-wolf-danger-text-v2')
  })
})

describe('DealJourneyDetailContent payment-plan fixed contract', () => {
  it('passes contract total_amount instead of remaining allocatable amount', () => {
    const source = readSource('src/components/panels/DealJourneyDetailContent.vue')
    const blockStart = source.indexOf('const fixedContractForPaymentPlan')
    const blockEnd = source.indexOf('const paymentRecordDefaultAmount')
    const block = source.slice(blockStart, blockEnd)

    expect(block).toContain('total_amount: contract.total_amount')
    expect(block).not.toContain('remainingPaymentPlanAmount')
  })
})
