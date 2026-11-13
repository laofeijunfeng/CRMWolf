import type { ApprovalEntityDetail } from '@/schemas/approvalGeneric'

export interface ApprovalInvoiceBillingField {
  key: string
  label: string
  copyValue: string
  displayValue: string
  originalValue?: string
  changed: boolean
  wide: boolean
  isAmount: boolean
}

type BillingSnapshot = NonNullable<ApprovalEntityDetail['original_invoice']>
type BillingFieldKey = keyof BillingSnapshot | 'remark'
type BillingValue = string | number | null | undefined

interface BillingFieldDefinition {
  key: BillingFieldKey
  label: string
  wide?: boolean
}

const BILLING_FIELDS: readonly BillingFieldDefinition[] = [
  { key: 'invoice_type', label: '发票类型' },
  { key: 'invoice_title_type', label: '抬头类型' },
  { key: 'invoice_title_text', label: '发票抬头', wide: true },
  { key: 'invoice_taxpayer_id', label: '纳税人识别号' },
  { key: 'invoice_address', label: '地址', wide: true },
  { key: 'invoice_phone', label: '电话' },
  { key: 'invoice_bank_name', label: '开户银行' },
  { key: 'invoice_bank_account', label: '银行账号' },
]

const REMARK_FIELD: BillingFieldDefinition = { key: 'remark', label: '备注', wide: true }
const AMOUNT_FIELD: BillingFieldDefinition = { key: 'invoice_amount', label: '开票金额' }

const numericAmount = (value: BillingValue): number | undefined => {
  if (value == null || value === '' || (typeof value === 'string' && !/\S/.test(value))) {
    return undefined
  }
  const amount = Number(value)
  return Number.isFinite(amount) ? amount : undefined
}

const billingCopyValue = (key: BillingFieldKey, value: BillingValue): string => {
  if (value == null || value === '') return ''
  if (key === 'invoice_type') {
    if (value === 'VAT_SPECIAL') return '增值税专用发票'
    if (value === 'VAT_NORMAL') return '增值税普通发票'
  }
  if (key === 'invoice_title_type') {
    if (value === 'COMPANY') return '企业'
    if (value === 'PERSONAL') return '个人'
  }
  if (key === 'invoice_amount') {
    const amount = numericAmount(value)
    if (amount !== undefined) return amount.toFixed(2)
  }
  return String(value)
}

export const buildApprovalInvoiceBillingFields = (
  type: 'INVOICE' | 'INVOICE_REISSUE',
  detail: ApprovalEntityDetail,
): ApprovalInvoiceBillingField[] => {
  const original = type === 'INVOICE_REISSUE' ? detail.original_invoice : undefined
  const definitions = [...BILLING_FIELDS, type === 'INVOICE' ? REMARK_FIELD : AMOUNT_FIELD]
  return definitions.map(({ key, label, wide }) => {
    const value = detail[key]
    const copyValue = billingCopyValue(key, value)
    const originalValue = original && key !== 'remark' ? original[key] : undefined
    const originalCopyValue = billingCopyValue(key, originalValue)
    const isAmount = key === 'invoice_amount'
    const amount = isAmount ? numericAmount(value) : undefined
    const originalAmount = isAmount ? numericAmount(originalValue) : undefined
    const equal = amount !== undefined && originalAmount !== undefined
      ? amount === originalAmount
      : copyValue === originalCopyValue
    return {
      key,
      label,
      copyValue,
      displayValue: copyValue === '' ? '-' : copyValue,
      ...(original ? { originalValue: originalCopyValue === '' ? '-' : originalCopyValue } : {}),
      changed: original != null && !equal,
      wide: wide ?? false,
      isAmount,
    }
  })
}

export const formatApprovalInvoiceBillingCopy = (fields: ApprovalInvoiceBillingField[]): string => {
  return fields.map(({ label, copyValue }) => `${label}：${copyValue}`).join('\n')
}
