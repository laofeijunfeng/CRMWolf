import { toast } from 'vue-sonner'

export const COPY_FAILURE_MESSAGE = '复制失败，请手动选择复制'

function copyWithSelection(text: string): void {
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  try {
    textarea.select()
    if (!document.execCommand('copy')) throw new Error('execCommand copy rejected')
  } finally {
    textarea.remove()
  }
}

async function writeClipboardText(text: string): Promise<void> {
  if (typeof navigator.clipboard?.writeText === 'function') {
    await navigator.clipboard.writeText(text)
    return
  }
  copyWithSelection(text)
}

/**
 * 复制文本并给出统一提示：成功「已复制<项名>」，失败「复制失败，请手动选择复制」。
 * 返回是否复制成功，调用方无需再自行提示。
 */
export async function copyToClipboard(text: string, label: string): Promise<boolean> {
  try {
    await writeClipboardText(text)
    toast.success(`已复制${label}`)
    return true
  } catch {
    toast.error(COPY_FAILURE_MESSAGE)
    return false
  }
}
