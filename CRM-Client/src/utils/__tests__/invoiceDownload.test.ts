import { describe, expect, it } from 'vitest'
import type { InvoiceApplicationResponse } from '@/api/invoice'
import {
  MISSING_INVOICE_FILE_MESSAGE,
  RED_OFFSET_INVOICE_DOWNLOAD_MESSAGE,
  hasDownloadableInvoiceFile,
  resolveInvoiceDownload,
} from '../invoiceDownload'

const DOWNLOAD_DATE = new Date(2026, 9, 20)

const invoice = (overrides: Partial<InvoiceApplicationResponse> = {}): InvoiceApplicationResponse => ({
  id: 18,
  application_number: 'INV-18',
  customer_id: 'cus_weipai',
  contract_id: 7,
  opportunity_id: 3,
  payment_plan_id: null,
  invoice_title_id: 4,
  invoice_type: 'VAT_NORMAL',
  invoice_amount: '1280.00',
  payment_record_id: null,
  status: 'ISSUED',
  applicant_id: 'user_1',
  reviewer_id: null,
  review_comment: null,
  reviewed_time: null,
  invoice_title_type: 'COMPANY',
  invoice_title_text: '武汉微派网络科技有限公司',
  invoice_taxpayer_id: '91420100MA4K00000X',
  invoice_bank_name: null,
  invoice_bank_account: null,
  invoice_address: null,
  invoice_phone: null,
  invoice_number: 'NO-88421',
  invoice_file_path: 'invoices/original.pdf',
  issued_time: '2026-10-20T08:00:00',
  created_time: '2026-10-20T08:00:00',
  last_modified_time: '2026-10-20T08:00:00',
  customer_name: '武汉微派网络科技有限公司',
  contract_name: null,
  opportunity_name: null,
  payment_plan_stage_name: null,
  invoice_title_title: null,
  applicant_name: null,
  reviewer_name: null,
  invoice_effective_status: 'ACTIVE',
  current_invoice_file_kind: 'original',
  current_invoice_file_path: 'invoices/original.pdf',
  current_invoice_number: 'NO-88421',
  current_reissue_id: null,
  red_offsets: [],
  reissue_applications: [],
  ...overrides,
})

describe('resolveInvoiceDownload', () => {
  it('names an issued invoice with the customer and the download date', () => {
    expect(resolveInvoiceDownload(invoice(), DOWNLOAD_DATE)).toEqual({
      kind: 'original',
      applicationId: 18,
      reissueId: null,
      fileName: '发票-武汉微派网络科技有限公司-20261020.pdf',
    })
  })

  it('uses the same sanitized customer name on both download surfaces', () => {
    const named = invoice({ customer_name: '武汉微派/网络:科技*有限公司' })

    expect(resolveInvoiceDownload(named, DOWNLOAD_DATE)).toMatchObject({
      fileName: '发票-武汉微派网络科技有限公司-20261020.pdf',
    })
    expect(resolveInvoiceDownload(invoice({ customer_name: '   ' }), DOWNLOAD_DATE)).toMatchObject({
      fileName: '发票-未知客户-20261020.pdf',
    })
  })

  it('downloads the current reissued blue invoice instead of the original number', () => {
    const reissued = invoice({
      invoice_effective_status: 'REISSUED',
      invoice_number: 'OLD-NO',
      invoice_file_path: 'invoices/original.pdf',
      current_invoice_file_kind: 'reissue_new',
      current_invoice_file_path: 'invoices/reissue-new.ofd',
      current_reissue_id: 91,
    })

    expect(resolveInvoiceDownload(reissued, DOWNLOAD_DATE)).toEqual({
      kind: 'reissue_new',
      applicationId: 18,
      reissueId: 91,
      fileName: '发票-武汉微派网络科技有限公司-20261020.ofd',
    })
  })

  it('blocks a red-offset invoice and an application without a file', () => {
    expect(resolveInvoiceDownload(invoice({ invoice_effective_status: 'RED_OFFSET' }), DOWNLOAD_DATE))
      .toBe(RED_OFFSET_INVOICE_DOWNLOAD_MESSAGE)
    expect(resolveInvoiceDownload(invoice({
      invoice_file_path: '   ',
      current_invoice_file_path: null,
    }), DOWNLOAD_DATE)).toBe(MISSING_INVOICE_FILE_MESSAGE)
  })
})

describe('hasDownloadableInvoiceFile', () => {
  it('follows the current file, including a reissue that replaced an empty original', () => {
    expect(hasDownloadableInvoiceFile(invoice())).toBe(true)
    expect(hasDownloadableInvoiceFile(invoice({
      invoice_file_path: null,
      current_invoice_file_kind: 'reissue_new',
      current_invoice_file_path: 'invoices/reissue-new.pdf',
      current_reissue_id: 91,
    }))).toBe(true)
    expect(hasDownloadableInvoiceFile(invoice({ invoice_effective_status: 'RED_OFFSET' }))).toBe(false)
    expect(hasDownloadableInvoiceFile(invoice({ status: 'APPROVED' }))).toBe(false)
  })
})
