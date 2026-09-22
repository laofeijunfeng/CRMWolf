const INVALID_FILENAME_CHARS = /[\\/:*?"<>|\r\n]/g
const FALLBACK_TITLE = '列表导出'

function sanitizeSegment(value: string): string {
  const cleaned = value.replace(INVALID_FILENAME_CHARS, '').replace(/^[. ]+|[. ]+$/g, '')
  return cleaned.length > 0 ? cleaned : ''
}

export function buildDataTableExportFileName(title: string, tabLabel: string, now: Date): string {
  const titleSegment = sanitizeSegment(title)
  const tabSegment = sanitizeSegment(tabLabel)
  const timestamp = [
    String(now.getFullYear()).padStart(4, '0'),
    String(now.getMonth() + 1).padStart(2, '0'),
    String(now.getDate()).padStart(2, '0'),
  ].join('') + '-' + [
    String(now.getHours()).padStart(2, '0'),
    String(now.getMinutes()).padStart(2, '0'),
    String(now.getSeconds()).padStart(2, '0'),
  ].join('')
  const stem = [titleSegment, tabSegment, timestamp]
    .filter((segment) => segment.length > 0)
    .join('-')
  return `${stem.length > timestamp.length ? stem : `${FALLBACK_TITLE}-${timestamp}`}.xlsx`
}

export function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob)
  try {
    const link = window.document.createElement('a')
    link.href = url
    link.download = fileName
    window.document.body.appendChild(link)
    link.click()
    link.remove()
  } finally {
    URL.revokeObjectURL(url)
  }
}
