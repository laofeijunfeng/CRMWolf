import { describe, expect, it } from 'vitest'
import {
  buildPdfViewerUrl,
  computeFitScale,
  getFileExtension,
  getFilePreviewKind,
  zoomInScale,
  zoomOutScale
} from '../filePreview'

describe('filePreview helpers', () => {
  it('detects the preview kind from extension, name or url', () => {
    expect(getFilePreviewKind({ id: 1, name: '合同.PDF' })).toBe('pdf')
    expect(getFilePreviewKind({ id: 2, name: '报价.docx' })).toBe('docx')
    expect(getFilePreviewKind({ id: 3, name: '旧版.doc' })).toBe('unsupported')
    expect(getFilePreviewKind({ id: 4, name: '', url: 'https://cdn.test/a/proof.JPG?x=1#y' })).toBe('image')
    expect(getFilePreviewKind({ id: 5, name: 'blob', extension: '.png' })).toBe('image')
    expect(getFileExtension({ id: 6, name: 'README' })).toBe('')
  })

  it('steps zoom through presets and clamps to 10%–400%', () => {
    expect(zoomInScale(1)).toBe(1.25)
    expect(zoomInScale(1.1)).toBe(1.25)
    expect(zoomInScale(4)).toBe(4)
    expect(zoomOutScale(1)).toBe(0.75)
    expect(zoomOutScale(0.1)).toBe(0.1)
  })

  it('fits width or whole page, honouring the upscale cap', () => {
    const viewport = { width: 800, height: 600 }
    const page = { width: 400, height: 600 }
    expect(computeFitScale('width', viewport, page)).toBe(2)
    expect(computeFitScale('page', viewport, page)).toBe(1)
    expect(computeFitScale('width', viewport, page, 1)).toBe(1)
    expect(computeFitScale('width', { width: 10000, height: 10 }, { width: 1, height: 1 })).toBe(4)
    expect(computeFitScale('page', { width: 0, height: 0 }, page)).toBe(1)
  })

  it('builds PDF viewer open parameters, replacing any existing fragment', () => {
    expect(buildPdfViewerUrl('blob:x#page=2', 'width', 1)).toBe('blob:x#view=FitH')
    expect(buildPdfViewerUrl('blob:x', 'page', 1)).toBe('blob:x#view=Fit')
    expect(buildPdfViewerUrl('blob:x', 'custom', 1.5)).toBe('blob:x#zoom=150')
    expect(buildPdfViewerUrl('blob:x', 'custom', 9)).toBe('blob:x#zoom=400')
  })
})
