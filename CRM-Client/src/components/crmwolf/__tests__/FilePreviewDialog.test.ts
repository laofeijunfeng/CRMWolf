import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import FileAttachment from '../FileAttachment.vue'
import FilePreviewDialog from '../FilePreviewDialog.vue'
import type { FileAttachmentItem } from '@/types/fileAttachment'

type RenderAsync = (blob: Blob, container: HTMLElement, style?: unknown, options?: Record<string, unknown>) => Promise<void>
const renderAsync = vi.hoisted(() => vi.fn<RenderAsync>())
vi.mock('docx-preview', () => ({ renderAsync }))

let wrapper: VueWrapper | null = null

beforeEach(() => {
  document.body.innerHTML = ''
})

const mountPreview = async (
  file: FileAttachmentItem,
  props: Record<string, unknown> = {}
): Promise<VueWrapper> => {
  wrapper = mount(FilePreviewDialog, {
    props: { open: true, file, ...props },
    attachTo: document.body
  })
  await flushPromises()
  return wrapper
}

const q = <T extends Element = HTMLElement>(selector: string): T | null => document.body.querySelector<T>(selector)
const button = (label: string): HTMLButtonElement | null => q<HTMLButtonElement>(`button[aria-label="${label}"]`)
const scale = (): string => q('[data-testid="file-preview-scale"]')?.textContent?.trim() ?? ''
const state = (): string | null => q('[data-state="loading"], [data-state="error"], [data-state="unsupported"]')?.getAttribute('data-state') ?? null

const loadImage = async (width = 800, height = 600): Promise<void> => {
  const image = q<HTMLImageElement>('img')
  if (image === null) throw new Error('image not rendered')
  Object.defineProperty(image, 'naturalWidth', { value: width, configurable: true })
  Object.defineProperty(image, 'naturalHeight', { value: height, configurable: true })
  image.dispatchEvent(new Event('load'))
  await nextTick()
}

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  renderAsync.mockReset()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('FilePreviewDialog', () => {
  const image: FileAttachmentItem = { id: 1, name: '凭证.png', url: 'blob:image', size: 2048 }

  it('replaces the default close control with a single toolbar close', async () => {
    await mountPreview(image)
    expect(document.body.querySelectorAll('[aria-label="关闭"]')).toHaveLength(1)
    button('关闭')?.click()
    await nextTick()
    expect(wrapper?.emitted('update:open')?.[0]).toEqual([false])
  })

  it('keeps zoom disabled while loading, then zooms, clamps and resets once ready', async () => {
    await mountPreview(image)
    expect(state()).toBe('loading')
    expect(button('放大')?.disabled).toBe(true)

    await loadImage()
    expect(state()).toBeNull()
    expect(scale()).toBe('100%')

    button('放大')?.click()
    await nextTick()
    expect(scale()).toBe('125%')

    for (let i = 0; i < 10; i += 1) button('放大')?.click()
    await nextTick()
    expect(scale()).toBe('400%')
    expect(button('放大')?.disabled).toBe(true)

    button('恢复默认比例')?.click()
    await nextTick()
    expect(scale()).toBe('100%')
    expect(button('适应页面')?.getAttribute('aria-pressed')).toBe('true')
  })

  it('supports keyboard zoom shortcuts', async () => {
    await mountPreview(image)
    await loadImage()
    const dialog = button('放大')
    dialog?.dispatchEvent(new KeyboardEvent('keydown', { key: '-', bubbles: true }))
    await nextTick()
    expect(scale()).toBe('75%')
    dialog?.dispatchEvent(new KeyboardEvent('keydown', { key: '0', bubbles: true }))
    await nextTick()
    expect(scale()).toBe('100%')
  })

  it('shows a failed state with retry and download when an image cannot load', async () => {
    await mountPreview(image)
    q('img')?.dispatchEvent(new Event('error'))
    await nextTick()
    expect(state()).toBe('error')
    expect(q('[data-state="error"]')?.textContent).toContain('图片加载失败')

    const download = Array.from(document.body.querySelectorAll('button')).find(b => b.textContent?.includes('下载查看') === true)
    download?.click()
    expect(wrapper?.emitted('download')?.[0]).toEqual([image])

    const retry = Array.from(document.body.querySelectorAll('button')).find(b => b.textContent?.includes('重试') === true)
    retry?.click()
    await nextTick()
    expect(state()).toBe('loading')
  })

  it('shows loading while the parent prepares the url', async () => {
    await mountPreview({ id: 9, name: '合同.pdf' }, { loading: true })
    expect(state()).toBe('loading')
    expect(q('iframe')).toBeNull()
  })

  it('drives the browser PDF viewer through open parameters', async () => {
    await mountPreview({ id: 2, name: '合同.pdf', url: 'blob:pdf' })
    const frame = (): HTMLIFrameElement | null => q<HTMLIFrameElement>('iframe')
    expect(frame()?.getAttribute('src')).toBe('blob:pdf#view=FitH')
    frame()?.dispatchEvent(new Event('load'))
    await nextTick()
    expect(scale()).toBe('适应宽度')

    button('适应页面')?.click()
    await nextTick()
    expect(frame()?.getAttribute('src')).toBe('blob:pdf#view=Fit')

    frame()?.dispatchEvent(new Event('load'))
    await nextTick()
    button('放大')?.click()
    await nextTick()
    expect(frame()?.getAttribute('src')).toBe('blob:pdf#zoom=125')
  })

  it('renders DOCX and reports a failure state when rendering fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(['x']) }))
    renderAsync.mockResolvedValue(undefined)
    await mountPreview({ id: 3, name: '报价.docx', url: 'blob:docx' })
    expect(renderAsync).toHaveBeenCalledTimes(1)
    expect(state()).toBeNull()

    wrapper?.unmount()
    renderAsync.mockRejectedValue(new Error('broken'))
    await mountPreview({ id: 4, name: '损坏.docx', url: 'blob:broken' })
    expect(state()).toBe('error')
    expect(q('[data-state="error"]')?.textContent).toContain('DOCX 预览加载失败')
  })

  it('offers download for unsupported formats only when downloading is allowed', async () => {
    await mountPreview({ id: 5, name: '清单.xlsx', url: 'blob:xlsx' })
    expect(state()).toBe('unsupported')
    expect(q('[data-state="unsupported"]')?.textContent).toContain('下载查看')
    expect(button('下载文件')).not.toBeNull()

    wrapper?.unmount()
    await mountPreview({ id: 5, name: '清单.xlsx', url: 'blob:xlsx' }, { allowDownload: false })
    expect(q('[data-state="unsupported"]')?.textContent).not.toContain('下载查看')
    expect(button('下载文件')).toBeNull()
  })
})

describe('FileAttachment preview integration', () => {
  it('opens the shared preview from a row and mirrors the row download policy', async () => {
    const file: FileAttachmentItem = { id: 7, name: '合同.pdf', url: 'blob:contract' }
    wrapper = mount(FileAttachment, {
      props: { files: [file], downloadDisabledLabel: '原件受限' },
      attachTo: document.body
    })
    expect(q('[data-testid="file-preview-dialog"]')).toBeNull()

    button('预览合同.pdf')?.click()
    await flushPromises()

    expect(wrapper.emitted('preview')?.[0]).toEqual([file])
    expect(q('[data-testid="file-preview-dialog"]')).not.toBeNull()
    expect(q('iframe')?.getAttribute('src')).toBe('blob:contract#view=FitH')
    expect(button('下载文件')).toBeNull()
  })
})
