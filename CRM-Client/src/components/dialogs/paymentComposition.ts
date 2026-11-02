export interface PaymentCompositionSegment {
  headcount: number
  amount: number
}

export interface PaymentComposition {
  renewal: PaymentCompositionSegment
  expansion: PaymentCompositionSegment
}

export interface PaymentCompositionForm {
  renewalHeadcount: string
  renewalAmount: string
  expansionHeadcount: string
  expansionAmount: string
}

export interface PaymentCompositionCheck {
  empty: boolean
  valid: boolean
  message: string
  composition: PaymentComposition | null
  focusSuffix: 'renewal-headcount' | 'renewal-amount' | 'expansion-headcount' | 'expansion-amount' | null
}

const COUNT = /^\d+$/
const MONEY = /^\d+(\.\d{1,2})?$/

export function emptyCompositionForm(): PaymentCompositionForm {
  return {
    renewalHeadcount: '',
    renewalAmount: '',
    expansionHeadcount: '',
    expansionAmount: '',
  }
}

export function compositionFormFrom(value: PaymentComposition | null | undefined): PaymentCompositionForm {
  if (value == null) return emptyCompositionForm()
  return {
    renewalHeadcount: String(value.renewal.headcount),
    renewalAmount: formatAmountInput(value.renewal.amount),
    expansionHeadcount: String(value.expansion.headcount),
    expansionAmount: formatAmountInput(value.expansion.amount),
  }
}

export function formatPaymentYuan(cents: number): string {
  const sign = cents < 0 ? '-' : ''
  const absolute = Math.abs(cents)
  const whole = Math.trunc(absolute / 100)
  const fraction = String(absolute % 100).padStart(2, '0')
  return `${sign}¥${whole.toLocaleString('en-US')}.${fraction}`
}

export function validatePaymentComposition(
  form: PaymentCompositionForm,
  actualAmount: string,
): PaymentCompositionCheck {
  const renewalHeadcount = form.renewalHeadcount.trim()
  const renewalAmount = form.renewalAmount.trim()
  const expansionHeadcount = form.expansionHeadcount.trim()
  const expansionAmount = form.expansionAmount.trim()
  const cells = [renewalHeadcount, renewalAmount, expansionHeadcount, expansionAmount]
  if (cells.every((cell) => cell.length === 0)) {
    return { empty: true, valid: true, message: '', composition: null, focusSuffix: null }
  }

  const messages: string[] = []
  let focusSuffix: PaymentCompositionCheck['focusSuffix'] = null
  const renewalHeadcountOk = renewalHeadcount.length > 0 && COUNT.test(renewalHeadcount)
  const expansionHeadcountOk = expansionHeadcount.length > 0 && COUNT.test(expansionHeadcount)
  const renewalAmountCents = moneyCents(renewalAmount)
  const expansionAmountCents = moneyCents(expansionAmount)
  const renewalAmountOk = renewalAmount.length > 0 && renewalAmountCents !== null
  const expansionAmountOk = expansionAmount.length > 0 && expansionAmountCents !== null

  const headcountMissing = renewalHeadcount.length === 0 || expansionHeadcount.length === 0
  const headcountInvalid = (renewalHeadcount.length > 0 && !renewalHeadcountOk)
    || (expansionHeadcount.length > 0 && !expansionHeadcountOk)
  const amountMissing = renewalAmount.length === 0 || expansionAmount.length === 0
  const amountInvalid = (renewalAmount.length > 0 && !renewalAmountOk)
    || (expansionAmount.length > 0 && !expansionAmountOk)

  const paymentCents = moneyCents(actualAmount.trim())
  if (!amountInvalid && paymentCents !== null) {
    const total = (renewalAmountCents ?? 0) + (expansionAmountCents ?? 0)
    if (total !== paymentCents) {
      const delta = Math.abs(paymentCents - total)
      const direction = total < paymentCents ? '少' : '多'
      messages.push(`两段合计 ${formatPaymentYuan(total)}，比这笔回款${direction} ${formatPaymentYuan(delta)}。`)
      focusSuffix = renewalAmount.length === 0 ? 'renewal-amount' : 'expansion-amount'
    }
  }
  if (headcountMissing || headcountInvalid) {
    messages.push(headcountInvalid && !headcountMissing
      ? '人数需为大于等于 0 的整数。'
      : '请填完续购和增购的人数。')
    focusSuffix ??= renewalHeadcountOk ? 'expansion-headcount' : 'renewal-headcount'
  }
  if (amountMissing || amountInvalid) {
    messages.push(amountInvalid && !amountMissing
      ? '金额需大于等于 0，且只精确到分。'
      : '请填完续购和增购的金额。')
    focusSuffix ??= renewalAmountOk ? 'expansion-amount' : 'renewal-amount'
  }

  if (paymentCents === null) {
    messages.push('回款金额需精确到分，才能核对构成。')
    focusSuffix ??= 'renewal-amount'
  }
  if (messages.length > 0 || paymentCents === null) {
    return {
      empty: false,
      valid: false,
      message: messages.join(''),
      composition: null,
      focusSuffix,
    }
  }

  return {
    empty: false,
    valid: true,
    message: `两段合计 ${formatPaymentYuan(paymentCents)}，等于这笔回款。`,
    composition: {
      renewal: { headcount: Number(renewalHeadcount), amount: centsToAmount(renewalAmountCents ?? 0) },
      expansion: { headcount: Number(expansionHeadcount), amount: centsToAmount(expansionAmountCents ?? 0) },
    },
    focusSuffix: null,
  }
}

function moneyCents(value: string): number | null {
  if (!MONEY.test(value)) return null
  const [whole = '0', fraction = ''] = value.split('.')
  return Number(whole) * 100 + Number(fraction.padEnd(2, '0'))
}

function centsToAmount(cents: number): number {
  return cents / 100
}

function formatAmountInput(amount: number): string {
  if (!Number.isFinite(amount)) return ''
  return amount.toFixed(2)
}
