import { afterEach, describe, expect, it, vi } from 'vitest'
import { buildDataTableExportFileName, downloadBlob } from '../downloadBlob'

const createObjectURL = vi.fn(() => 'blob:export-url')
const revokeObjectURL = vi.fn()

vi.stubGlobal('URL', Object.assign(URL, {
  createObjectURL,
  revokeObjectURL,
}))

describe('buildDataTableExportFileName', () => {
  it('combines sanitized title, tab label, and local timestamp', () => {
    expect(buildDataTableExportFileName('客户列表', '所有客户', new Date('2026-09-21T14:35:00')))
      .toBe('客户列表-所有客户-20260921-143500.xlsx')
  })

  it('strips filesystem-unsafe characters and falls back when empty', () => {
    expect(buildDataTableExportFileName('客/户:列表', '全部*', new Date('2026-09-21T09:05:00')))
      .toBe('客户列表-全部-20260921-090500.xlsx')
    expect(buildDataTableExportFileName('???', '|||', new Date('2026-09-21T09:05:00')))
      .toBe('列表导出-20260921-090500.xlsx')
  })
})

describe('downloadBlob', () => {
  afterEach(() => {
    createObjectURL.mockClear()
    revokeObjectURL.mockClear()
  })

  it('drives the anchor lifecycle and revokes the object URL in finally', () => {
    const blob = new Blob(['xlsx'])
    const clicks: number[] = []
    const elements: HTMLAnchorElement[] = []
    const createElement = document.createElement.bind(document)
    const anchorSpy = vi
      .spyOn(document, 'createElement')
      .mockImplementation((tagName: string) => {
        const element = createElement(tagName)
        if (tagName.toLowerCase() !== 'a') return element
        return Object.assign(element, {
          click: (): void => {
            clicks.push(elements.length)
          },
        }) as HTMLAnchorElement
      })
    const appendChild = document.body.appendChild.bind(document.body)
    const appendSpy = vi
      .spyOn(document.body, 'appendChild')
      .mockImplementation((node: Node) => {
        elements.push(node as HTMLAnchorElement)
        return appendChild(node)
      })

    downloadBlob(blob, '客户列表.xlsx')

    const anchor = elements[0]
    expect(anchor?.getAttribute('href')).toBe('blob:export-url')
    expect(anchor?.download).toBe('客户列表.xlsx')
    expect(clicks).toHaveLength(1)
    expect(anchor?.isConnected).toBe(false)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:export-url')

    appendSpy.mockRestore()
    anchorSpy.mockRestore()
  })
})
