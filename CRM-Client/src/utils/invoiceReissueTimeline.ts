import type {
  InvoiceApplicationResponse,
  InvoiceReissueApplicationResponse,
  InvoiceType,
} from '@/api/invoice'

const OPEN_REISSUE_STATUSES = new Set(['DRAFT', 'PENDING_REVIEW', 'APPROVED'])

export interface ReissuePrefill {
  invoice_title_type: 'COMPANY' | 'PERSONAL'
  invoice_title_text: string
  invoice_taxpayer_id: string
  invoice_bank_name: string
  invoice_bank_account: string
  invoice_address: string
  invoice_phone: string
  invoice_amount: number
  invoice_type: InvoiceType
}

export interface ReissueTimelineCard {
  reissue: InvoiceReissueApplicationResponse
  ordinal: number
  heading: string
  isCurrent: boolean
  redFileName: string
  newFileName: string
  redCaption: string
  newCaption: string
}

const createdSortValue = (reissue: InvoiceReissueApplicationResponse): number => {
  const parsed = Date.parse(reissue.created_time)
  return Number.isNaN(parsed) ? 0 : parsed
}

export const compareReissueChronological = (
  left: InvoiceReissueApplicationResponse,
  right: InvoiceReissueApplicationResponse,
): number => {
  const timeDiff = createdSortValue(left) - createdSortValue(right)
  if (timeDiff !== 0) return timeDiff
  return left.id - right.id
}

export const chronologicalReissues = (
  reissues: readonly InvoiceReissueApplicationResponse[],
): InvoiceReissueApplicationResponse[] => {
  return [...reissues].sort(compareReissueChronological)
}

export const hasOpenReissue = (reissues: readonly InvoiceReissueApplicationResponse[]): boolean => {
  return reissues.some((reissue) => OPEN_REISSUE_STATUSES.has(reissue.status))
}

const hasCurrentNewInvoice = (reissue: InvoiceReissueApplicationResponse): boolean => {
  return reissue.status === 'COMPLETED' && (reissue.new_invoice_file_path?.trim() ?? '') !== ''
}

const completedSortValue = (reissue: InvoiceReissueApplicationResponse): number => {
  const parsed = Date.parse(reissue.completed_time ?? reissue.last_modified_time ?? reissue.created_time)
  return Number.isNaN(parsed) ? 0 : parsed
}

export const latestCompletedReissue = (
  reissues: readonly InvoiceReissueApplicationResponse[],
): InvoiceReissueApplicationResponse | null => {
  const completed = reissues.filter(hasCurrentNewInvoice)
  if (completed.length === 0) return null
  return completed.reduce((latest, reissue) => {
    const latestValue = completedSortValue(latest)
    const nextValue = completedSortValue(reissue)
    if (nextValue > latestValue) return reissue
    if (nextValue < latestValue) return latest
    return reissue.id > latest.id ? reissue : latest
  })
}

export const hasManualRedOffset = (invoice: InvoiceApplicationResponse): boolean => {
  return invoice.red_offsets.some((item) => item.source_type === 'MANUAL' || item.reissue_application_id === null)
}

export const canCreateAnotherReissue = (invoice: InvoiceApplicationResponse): boolean => {
  if (invoice.status !== 'ISSUED') return false
  if (invoice.invoice_effective_status === 'RED_OFFSET') return false
  if (hasManualRedOffset(invoice)) return false
  return !hasOpenReissue(invoice.reissue_applications)
}

export const canReviseReissue = (
  reissue: InvoiceReissueApplicationResponse,
  reissues: readonly InvoiceReissueApplicationResponse[],
): boolean => {
  if (reissue.status !== 'DRAFT' && reissue.status !== 'REJECTED') return false
  const othersOpen = reissues.some((item) => item.id !== reissue.id && OPEN_REISSUE_STATUSES.has(item.status))
  if (othersOpen) return false
  const ordered = chronologicalReissues(reissues)
  const index = ordered.findIndex((item) => item.id === reissue.id)
  if (index < 0) return false
  return index === ordered.length - 1
}

export const isOriginalBlueInvoiceBlocked = (invoice: InvoiceApplicationResponse): boolean => {
  if (invoice.invoice_effective_status === 'RED_OFFSET' || invoice.invoice_effective_status === 'REISSUED') {
    return true
  }
  if (latestCompletedReissue(invoice.reissue_applications) !== null) return true
  return invoice.red_offsets.length > 0
}

const fileExtension = (filePath: string | null): string => {
  if (filePath === null || filePath.trim() === '') return ''
  const base = filePath.toLowerCase().split('?')[0]?.split('/').pop() ?? ''
  const dot = base.lastIndexOf('.')
  if (dot <= 0 || dot === base.length - 1) return ''
  return base.slice(dot + 1)
}

const labeledFileName = (label: string, ordinal: number, filePath: string | null): string => {
  const extension = fileExtension(filePath)
  return extension === '' ? `${label}-第${ordinal}次` : `${label}-第${ordinal}次.${extension}`
}

export const originalBlueFileName = (filePath: string | null): string => {
  const extension = fileExtension(filePath)
  return extension === '' ? '原蓝字发票' : `原蓝字发票.${extension}`
}

export const buildReissueTimeline = (
  reissues: readonly InvoiceReissueApplicationResponse[],
): ReissueTimelineCard[] => {
  const ordered = chronologicalReissues(reissues)
  const current = latestCompletedReissue(ordered)
  return [...ordered].reverse().map((reissue) => {
    const ordinal = ordered.findIndex((item) => item.id === reissue.id) + 1
    const laterCompleted = ordered.some(
      (item) => hasCurrentNewInvoice(item) && compareReissueChronological(item, reissue) > 0,
    )
    const isCurrent = current !== null && current.id === reissue.id
    let heading = `第 ${ordinal} 次`
    if (OPEN_REISSUE_STATUSES.has(reissue.status)) {
      heading = `第 ${ordinal} 次 · 重开处理中`
    } else if (reissue.status === 'REJECTED') {
      heading = `第 ${ordinal} 次 · 已拒绝`
    } else if (isCurrent) {
      heading = `第 ${ordinal} 次 · 当前有效`
    } else if (reissue.status === 'COMPLETED' && laterCompleted) {
      heading = `第 ${ordinal} 次 · 已被下一次红冲`
    } else if (reissue.status === 'COMPLETED') {
      heading = `第 ${ordinal} 次 · 已重开`
    }
    return {
      reissue,
      ordinal,
      heading,
      isCurrent,
      redFileName: labeledFileName('红字发票', ordinal, reissue.red_invoice_file_path),
      newFileName: labeledFileName('新发票', ordinal, reissue.new_invoice_file_path),
      redCaption: ordinal <= 1 ? '作废最初的蓝字发票' : '作废上一次重开的蓝字发票',
      newCaption: isCurrent
        ? '当前有效发票。列表和详情的下载都是这一份'
        : '已被下一次红冲，不是当前有效发票',
    }
  })
}

const titleType = (value: string): 'COMPANY' | 'PERSONAL' => {
  return value === 'PERSONAL' ? 'PERSONAL' : 'COMPANY'
}

const amount = (value: string | number): number => {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

export const reissuePrefill = (invoice: InvoiceApplicationResponse): ReissuePrefill => {
  const completed = latestCompletedReissue(invoice.reissue_applications)
  if (completed !== null) {
    return {
      invoice_title_type: titleType(completed.invoice_title_type),
      invoice_title_text: completed.invoice_title_text,
      invoice_taxpayer_id: completed.invoice_taxpayer_id,
      invoice_bank_name: completed.invoice_bank_name ?? '',
      invoice_bank_account: completed.invoice_bank_account ?? '',
      invoice_address: completed.invoice_address ?? '',
      invoice_phone: completed.invoice_phone ?? '',
      invoice_amount: amount(completed.invoice_amount),
      invoice_type: completed.invoice_type,
    }
  }
  return {
    invoice_title_type: titleType(invoice.invoice_title_type),
    invoice_title_text: invoice.invoice_title_text,
    invoice_taxpayer_id: invoice.invoice_taxpayer_id,
    invoice_bank_name: invoice.invoice_bank_name ?? '',
    invoice_bank_account: invoice.invoice_bank_account ?? '',
    invoice_address: invoice.invoice_address ?? '',
    invoice_phone: invoice.invoice_phone ?? '',
    invoice_amount: amount(invoice.invoice_amount),
    invoice_type: invoice.invoice_type,
  }
}
