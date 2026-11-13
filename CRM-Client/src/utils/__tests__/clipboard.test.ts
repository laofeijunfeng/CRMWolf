import { afterEach, describe, expect, it, vi, type Mock } from 'vitest'
import { defineComponent, h, type VNode } from 'vue'
import { mount } from '@vue/test-utils'
import { toast } from 'vue-sonner'
import CopyableText from '@/components/crmwolf/CopyableText.vue'
import { copyToClipboard } from '../clipboard'

vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const originalClipboard = Object.getOwnPropertyDescriptor(navigator, 'clipboard')

function setClipboard(value: Pick<Clipboard, 'writeText'> | undefined): void {
  Object.defineProperty(navigator, 'clipboard', { value, configurable: true })
}

function setExecCommand(result: boolean): Mock<() => boolean> {
  const execCommand = vi.fn(() => result)
  Object.defineProperty(document, 'execCommand', { value: execCommand, configurable: true })
  return execCommand
}

afterEach(() => {
  vi.clearAllMocks()
  if (originalClipboard) Object.defineProperty(navigator, 'clipboard', originalClipboard)
  else Reflect.deleteProperty(navigator, 'clipboard')
})

describe('copyToClipboard', () => {
  it('writes the text and announces the copied item by label', async () => {
    const writeText = vi.fn(() => Promise.resolve())
    setClipboard({ writeText })

    await expect(copyToClipboard('AP-001', '审批单号')).resolves.toBe(true)

    expect(writeText).toHaveBeenCalledWith('AP-001')
    expect(toast.success).toHaveBeenCalledWith('已复制审批单号')
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('falls back to a selected textarea when the Clipboard API is unavailable', async () => {
    setClipboard(undefined)
    const execCommand = setExecCommand(true)

    await expect(copyToClipboard('42', '用户 ID')).resolves.toBe(true)

    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(document.querySelector('textarea')).toBeNull()
    expect(toast.success).toHaveBeenCalledWith('已复制用户 ID')
  })

  it('reports the unified failure message when the Clipboard API rejects', async () => {
    setClipboard({ writeText: vi.fn(() => Promise.reject(new Error('denied'))) })

    await expect(copyToClipboard('x', '邀请链接')).resolves.toBe(false)

    expect(toast.error).toHaveBeenCalledWith('复制失败，请手动选择复制')
    expect(toast.success).not.toHaveBeenCalled()
  })

  it('reports failure when the fallback copy command is rejected', async () => {
    setClipboard(undefined)
    setExecCommand(false)

    await expect(copyToClipboard('x', '完整日志')).resolves.toBe(false)

    expect(toast.error).toHaveBeenCalledWith('复制失败，请手动选择复制')
    expect(document.querySelector('textarea')).toBeNull()
  })
})

describe('CopyableText', () => {
  it('copies its value on click without triggering the surrounding row click', async () => {
    const writeText = vi.fn(() => Promise.resolve())
    setClipboard({ writeText })
    const onRowClick = vi.fn()
    const Row = defineComponent(() => (): VNode => h('div', { onClick: onRowClick }, [
      h(CopyableText, { value: 'AP-001', label: '审批单号' }),
    ]))

    const wrapper = mount(Row)
    const button = wrapper.get('button')
    expect(button.attributes('aria-label')).toBe('复制审批单号 AP-001')

    await button.trigger('click')
    await Promise.resolve()

    expect(writeText).toHaveBeenCalledWith('AP-001')
    expect(toast.success).toHaveBeenCalledWith('已复制审批单号')
    expect(onRowClick).not.toHaveBeenCalled()
  })
})
