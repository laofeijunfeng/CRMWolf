import { describe, expect, it } from 'vitest'
import { validatePaymentComposition } from '@/components/dialogs/paymentComposition'

const empty = {
  renewalHeadcount: '',
  renewalAmount: '',
  expansionHeadcount: '',
  expansionAmount: '',
}

describe('validatePaymentComposition', () => {
  it('treats a blank composition as one unchanged payment', () => {
    const result = validatePaymentComposition(empty, '150000.00')
    expect(result.valid).toBe(true)
    expect(result.empty).toBe(true)
    expect(result.composition).toBeNull()
  })

  it('explains the shortfall when only the renewal row is filled', () => {
    const result = validatePaymentComposition({
      renewalHeadcount: '100',
      renewalAmount: '100000.00',
      expansionHeadcount: '',
      expansionAmount: '',
    }, '150000.00')
    expect(result.valid).toBe(false)
    expect(result.message).toContain('两段合计 ¥100,000.00，比这笔回款少 ¥50,000.00。')
    expect(result.message).toContain('请填完续购和增购的人数。')
    expect(result.message).toContain('请填完续购和增购的金额。')
  })

  it('accepts both rows when the cents match, including a zero segment', () => {
    const result = validatePaymentComposition({
      renewalHeadcount: '100',
      renewalAmount: '100000.00',
      expansionHeadcount: '50',
      expansionAmount: '50000.00',
    }, '150000.00')
    expect(result.valid).toBe(true)
    expect(result.message).toBe('两段合计 ¥150,000.00，等于这笔回款。')
    expect(result.composition).toEqual({
      renewal: { headcount: 100, amount: 100000 },
      expansion: { headcount: 50, amount: 50000 },
    })
  })

  it('does not rewrite the typed amounts when the payment amount changes', () => {
    const form = {
      renewalHeadcount: '100',
      renewalAmount: '100000.00',
      expansionHeadcount: '50',
      expansionAmount: '50000.00',
    }
    const changed = validatePaymentComposition(form, '160000.00')
    expect(form.renewalAmount).toBe('100000.00')
    expect(form.expansionAmount).toBe('50000.00')
    expect(changed.valid).toBe(false)
    expect(changed.message).toContain('少 ¥10,000.00')
  })

  it('rejects a fractional headcount', () => {
    const result = validatePaymentComposition({
      renewalHeadcount: '100.5',
      renewalAmount: '100000.00',
      expansionHeadcount: '50',
      expansionAmount: '50000.00',
    }, '150000.00')
    expect(result.valid).toBe(false)
    expect(result.message).toContain('人数需为大于等于 0 的整数。')
  })
})
