const padDatePart = (value: number): string => String(value).padStart(2, '0')

const getLocalCompactDate = (date: Date = new Date()): string => {
  return `${date.getFullYear()}${padDatePart(date.getMonth() + 1)}${padDatePart(date.getDate())}`
}

const sanitizeFileNamePart = (value: string): string => {
  return value
    .replace(/[\\/:*?"<>|]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

const getFileExtension = (filePath: string | null | undefined): string => {
  if (filePath == null || filePath.trim() === '') return ''
  const extension = filePath.toLowerCase().split('?')[0]?.split('.').pop() ?? ''
  return extension.replace(/[^a-z0-9]/g, '')
}

export const buildInvoiceDownloadFileName = (
  customerName: string | null | undefined,
  filePath: string | null | undefined,
  date: Date = new Date(),
): string => {
  const safeCustomerName = sanitizeFileNamePart(customerName || '未知客户') || '未知客户'
  const extension = getFileExtension(filePath)
  const suffix = extension === '' ? '' : `.${extension}`

  return `发票-${safeCustomerName}-${getLocalCompactDate(date)}${suffix}`
}
