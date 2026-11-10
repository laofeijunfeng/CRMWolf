import type { Component } from 'vue'
import { File, FileArchive, FileImage, FileSpreadsheet, FileText } from 'lucide-vue-next'
import type { FileAttachmentItem } from '@/types/fileAttachment'

export type FilePreviewKind = 'image' | 'pdf' | 'docx' | 'unsupported'
export type FilePreviewFitMode = 'width' | 'page' | 'custom'

export interface PreviewSize {
  width: number
  height: number
}

export const MIN_PREVIEW_SCALE = 0.1
export const MAX_PREVIEW_SCALE = 4

const ZOOM_STEPS: readonly number[] = [0.1, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4]
const SCALE_EPSILON = 0.001
const IMAGE_EXTENSIONS: readonly string[] = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg']

const TYPE_LABELS: Record<string, string> = {
  pdf: 'PDF',
  ofd: 'OFD',
  jpg: 'JPG',
  jpeg: 'JPEG',
  png: 'PNG',
  doc: 'Word',
  docx: 'Word',
  xls: 'Excel',
  xlsx: 'Excel',
  csv: 'CSV'
}

export const getFileExtension = (file: FileAttachmentItem): string => {
  if (file.extension != null && file.extension !== '') return file.extension.toLowerCase().replace(/^\./, '')
  const name = file.name !== '' ? file.name : file.url ?? ''
  const lastSegment = name.toLowerCase().split(/[?#]/)[0]?.split('/').pop() ?? ''
  return lastSegment.includes('.') ? lastSegment.split('.').pop() ?? '' : ''
}

export const getFilePreviewKind = (file: FileAttachmentItem): FilePreviewKind => {
  const ext = getFileExtension(file)
  if (IMAGE_EXTENSIONS.includes(ext)) return 'image'
  if (ext === 'pdf') return 'pdf'
  if (ext === 'docx') return 'docx'
  return 'unsupported'
}

export const getFileTypeLabel = (file: FileAttachmentItem): string => {
  const ext = getFileExtension(file)
  return TYPE_LABELS[ext] ?? (ext !== '' ? ext.toUpperCase() : '文件')
}

export const getFileIcon = (file: FileAttachmentItem): Component => {
  const ext = getFileExtension(file)
  if (IMAGE_EXTENSIONS.includes(ext)) return FileImage
  if (['pdf', 'ofd', 'doc', 'docx'].includes(ext)) return FileText
  if (['xls', 'xlsx', 'csv'].includes(ext)) return FileSpreadsheet
  if (['zip', 'rar', '7z'].includes(ext)) return FileArchive
  return File
}

export const formatFileSize = (size?: number): string => {
  if (size == null || size <= 0) return ''
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

/** Images open fully visible; documents open readable across the available width. */
export const getDefaultFitMode = (kind: FilePreviewKind): FilePreviewFitMode =>
  kind === 'image' ? 'page' : 'width'

export const clampPreviewScale = (scale: number): number =>
  Math.min(MAX_PREVIEW_SCALE, Math.max(MIN_PREVIEW_SCALE, scale))

export const zoomInScale = (current: number): number =>
  ZOOM_STEPS.find(step => step > current + SCALE_EPSILON) ?? MAX_PREVIEW_SCALE

export const zoomOutScale = (current: number): number =>
  [...ZOOM_STEPS].reverse().find(step => step < current - SCALE_EPSILON) ?? MIN_PREVIEW_SCALE

/**
 * Scale that fits `content` into `viewport`. `maxScale` lets images refuse to upscale
 * past their natural size while documents may grow to fill wide screens.
 */
export const computeFitScale = (
  mode: Exclude<FilePreviewFitMode, 'custom'>,
  viewport: PreviewSize,
  content: PreviewSize,
  maxScale: number = MAX_PREVIEW_SCALE
): number => {
  if (content.width <= 0 || content.height <= 0 || viewport.width <= 0 || viewport.height <= 0) return 1
  const widthScale = viewport.width / content.width
  const scale = mode === 'width' ? widthScale : Math.min(widthScale, viewport.height / content.height)
  return clampPreviewScale(Math.min(scale, maxScale))
}

/** Browser PDF viewers read open parameters from the fragment (Chromium honours all three). */
export const buildPdfViewerUrl = (url: string, mode: FilePreviewFitMode, scale: number): string => {
  const base = url.split('#')[0] ?? url
  if (mode === 'width') return `${base}#view=FitH`
  if (mode === 'page') return `${base}#view=Fit`
  return `${base}#zoom=${Math.round(clampPreviewScale(scale) * 100)}`
}
