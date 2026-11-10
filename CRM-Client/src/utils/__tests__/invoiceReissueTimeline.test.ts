import { describe, expect, it } from 'vitest'
import type { InvoiceApplicationResponse, InvoiceReissueApplicationResponse } from '@/api/invoice'
import {
  buildReissueTimeline,
  canCreateAnotherReissue,
  canReviseReissue,
  isOriginalBlueInvoiceBlocked,
  reissuePrefill,
} from '../invoiceReissueTimeline'

const reissue = (
  overrides: Partial<InvoiceReissueApplicationResponse> = {},
): InvoiceReissueApplicationResponse => ({
  id: 1,
  application_number: 'INVR-1',
  original_invoice_application_id: 18,
  applicant_id: '7',
  applicant_name: '林晓',
  reason: '抬头写错',
  status: 'COMPLETED',
  invoice_title_type: 'COMPANY',
  invoice_title_text: '武汉微派网络科技有限公司',
  invoice_taxpayer_id: '91420100MA4K2N3X1A',
  invoice_bank_name: null,
  invoice_bank_account: null,
  invoice_address: null,
  invoice_phone: null,
  invoice_amount: '86000.00',
  invoice_type: 'VAT_SPECIAL',
  red_invoice_file_path: 'invoices/red-1.pdf',
  red_invoice_number: '244220000000012349999',
  red_issued_time: '2026-08-03T09:12:00',
  new_invoice_file_path: 'invoices/new-1.pdf',
  new_invoice_number: '244220000000012348888',
  new_issued_time: '2026-08-03T09:12:00',
  completed_time: '2026-08-03T09:12:00',
  created_time: '2026-08-01T09:00:00',
  last_modified_time: '2026-08-03T09:12:00',
  ...overrides,
})

const invoice = (
  reissues: InvoiceReissueApplicationResponse[],
  overrides: Partial<InvoiceApplicationResponse> = {},
): InvoiceApplicationResponse => ({
  id: 18,
  application_number: 'INV202607220001',
  customer_id: 'cus_weipai',
  contract_id: 7,
  opportunity_id: 3,
  payment_plan_id: null,
  invoice_title_id: 4,
  invoice_type: 'VAT_SPECIAL',
  invoice_amount: '86000.00',
  payment_record_id: null,
  status: 'ISSUED',
  applicant_id: '7',
  reviewer_id: null,
  review_comment: null,
  reviewed_time: null,
  invoice_title_type: 'COMPANY',
  invoice_title_text: '武汉微派网络科技有限公司',
  invoice_taxpayer_id: '91420100MA4K2N3X00',
  invoice_bank_name: null,
  invoice_bank_account: null,
  invoice_address: null,
  invoice_phone: null,
  invoice_number: '244220000000012345678',
  invoice_file_path: 'invoices/original.pdf',
  issued_time: '2026-07-22T16:40:00',
  created_time: '2026-07-22T10:18:00',
  last_modified_time: '2026-07-22T16:40:00',
  customer_name: '武汉微派网络科技有限公司',
  contract_name: null,
  opportunity_name: null,
  payment_plan_stage_name: null,
  invoice_title_title: null,
  applicant_name: null,
  reviewer_name: null,
  invoice_effective_status: 'REISSUED',
  current_invoice_file_kind: 'reissue_new',
  current_invoice_file_path: 'invoices/new-2.ofd',
  current_invoice_number: '244220000000032345678',
  current_reissue_id: 2,
  red_offsets: [],
  reissue_applications: reissues,
  ...overrides,
  remark: overrides.remark ?? null,
})

describe('buildReissueTimeline', () => {
  it('puts the latest application first and marks the latest completed invoice as current', () => {
    const cards = buildReissueTimeline([
      reissue(),
      reissue({
        id: 2,
        application_number: 'INVR-2',
        reason: '税号再次更正',
        invoice_taxpayer_id: '91420100MA4K2N3X8C',
        red_invoice_file_path: 'invoices/red-2.pdf',
        new_invoice_file_path: 'invoices/new-2.ofd',
        new_invoice_number: '244220000000032345678',
        completed_time: '2026-10-18T11:26:00',
        created_time: '2026-10-01T09:00:00',
      }),
    ])

    expect(cards.map((card) => card.heading)).toEqual([
      '第 2 次 · 当前有效',
      '第 1 次 · 已被下一次红冲',
    ])
    expect(cards[0]?.newFileName).toBe('新发票-第2次.ofd')
    expect(cards[0]?.redCaption).toBe('作废上一次重开的蓝字发票')
    expect(cards[0]?.newCaption).toBe('当前有效发票。列表和详情的下载都是这一份')
    expect(cards[1]?.redFileName).toBe('红字发票-第1次.pdf')
    expect(cards[1]?.redCaption).toBe('作废最初的蓝字发票')
    expect(cards[1]?.newCaption).toBe('已被下一次红冲，不是当前有效发票')
  })

  it('keeps the previous completed invoice current while the next one is still open', () => {
    const cards = buildReissueTimeline([
      reissue(),
      reissue({
        id: 3,
        status: 'PENDING_REVIEW',
        reason: '还在审批',
        red_invoice_file_path: null,
        new_invoice_file_path: null,
        new_invoice_number: null,
        completed_time: null,
        created_time: '2026-11-01T09:00:00',
      }),
    ])

    expect(cards.map((card) => card.heading)).toEqual([
      '第 2 次 · 重开处理中',
      '第 1 次 · 当前有效',
    ])
    expect(cards[1]?.isCurrent).toBe(true)
  })
})

describe('reissue actions', () => {
  it('allows another reissue after completion and blocks an open or manually red-offset invoice', () => {
    const completed = invoice([reissue()])
    expect(canCreateAnotherReissue(completed)).toBe(true)
    expect(canCreateAnotherReissue(invoice([
      reissue(),
      reissue({ id: 9, status: 'APPROVED', created_time: '2026-11-01T09:00:00' }),
    ], { invoice_effective_status: 'REISSUE_PENDING' }))).toBe(false)
    expect(canCreateAnotherReissue(invoice([], {
      invoice_effective_status: 'RED_OFFSET',
      red_offsets: [{
        id: 4,
        invoice_application_id: 18,
        source_type: 'MANUAL',
        reissue_application_id: null,
        red_invoice_file_path: 'invoices/manual.pdf',
        red_invoice_number: null,
        reason: '单独冲红',
        created_by: '7',
        created_by_name: null,
        red_offset_time: '2026-08-01T00:00:00',
        created_time: '2026-08-01T00:00:00',
        last_modified_time: '2026-08-01T00:00:00',
      }],
    }))).toBe(false)
  })

  it('lets the latest rejected reissue be revised until a newer application exists', () => {
    const rejected = reissue({
      id: 5,
      status: 'REJECTED',
      new_invoice_file_path: null,
      completed_time: null,
    })
    const newer = reissue({ id: 6, created_time: '2026-11-02T09:00:00' })
    expect(canReviseReissue(rejected, [rejected])).toBe(true)
    expect(canReviseReissue(rejected, [rejected, newer])).toBe(false)
  })

  it('prefills the latest completed reissue and keeps the original blue file blocked', () => {
    const source = invoice([
      reissue(),
      reissue({
        id: 2,
        invoice_taxpayer_id: '91420100MA4K2N3X8C',
        completed_time: '2026-10-18T11:26:00',
        created_time: '2026-10-01T09:00:00',
      }),
    ])
    expect(reissuePrefill(source).invoice_taxpayer_id).toBe('91420100MA4K2N3X8C')
    expect(isOriginalBlueInvoiceBlocked(source)).toBe(true)
    expect(isOriginalBlueInvoiceBlocked(invoice([], { invoice_effective_status: 'ACTIVE' }))).toBe(false)
  })
})
