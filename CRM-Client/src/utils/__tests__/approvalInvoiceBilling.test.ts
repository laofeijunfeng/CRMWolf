import { describe, expect, it } from 'vitest'
import { buildApprovalInvoiceBillingFields, formatApprovalInvoiceBillingCopy } from '../approvalInvoiceBilling'

const snapshot = {
  invoice_type: 'VAT_SPECIAL',
  invoice_title_type: 'COMPANY',
  invoice_title_text: '原始抬头',
  invoice_taxpayer_id: '00123456789',
  invoice_address: null,
  invoice_phone: '',
  invoice_bank_name: '开户银行',
  invoice_bank_account: '000123456789',
  invoice_amount: '1000.00',
}

describe('approval invoice billing', () => {
  it('compares amounts numerically and treats null and empty as the same while preserving cleared values', () => {
    const fields = buildApprovalInvoiceBillingFields('INVOICE_REISSUE', {
      ...snapshot,
      invoice_title_text: '新抬头',
      invoice_bank_name: '',
      invoice_amount: 1000,
      original_invoice: snapshot,
    })
    expect(fields.filter(field => field.changed).map(field => [field.key, field.copyValue, field.originalValue])).toEqual([
      ['invoice_title_text', '新抬头', '原始抬头'],
      ['invoice_bank_name', '', '开户银行'],
    ])
    expect(fields.find(field => field.key === 'invoice_bank_name')?.displayValue).toBe('-')
    expect(fields.find(field => field.key === 'invoice_bank_account')?.copyValue).toBe('000123456789')
    expect(fields.find(field => field.key === 'invoice_amount')?.copyValue).toBe('1000.00')
  })

  it('copies every new billing item once, includes empty lines, and never includes old values or remarks for reissues', () => {
    const fields = buildApprovalInvoiceBillingFields('INVOICE_REISSUE', {
      ...snapshot,
      invoice_title_text: '新抬头',
      original_invoice: snapshot,
      remark: '不应复制',
    })
    expect(formatApprovalInvoiceBillingCopy(fields)).toBe([
      '发票类型：增值税专用发票',
      '抬头类型：企业',
      '发票抬头：新抬头',
      '纳税人识别号：00123456789',
      '地址：',
      '电话：',
      '开户银行：开户银行',
      '银行账号：000123456789',
      '开票金额：1000.00',
    ].join('\n'))
  })

  it('keeps invoice remarks, handles unknown codes honestly, and avoids false changes without a baseline', () => {
    const invoice = buildApprovalInvoiceBillingFields('INVOICE', {
      ...snapshot,
      invoice_type: 'FUTURE_TYPE',
      remark: '第一行\n第二行',
    })
    expect(invoice.find(field => field.key === 'invoice_type')?.displayValue).toBe('FUTURE_TYPE')
    expect(invoice.find(field => field.key === 'remark')?.copyValue).toBe('第一行\n第二行')
    const reissue = buildApprovalInvoiceBillingFields('INVOICE_REISSUE', { ...snapshot, original_invoice: null })
    expect(reissue.filter(field => field.changed)).toEqual([])
  })
})
