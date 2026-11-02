export type FileAttachmentStatus = 'idle' | 'uploading' | 'processing' | 'done' | 'error'

export interface FileAttachmentItem {
  id: string | number
  name: string
  url?: string
  size?: number
  mimeType?: string
  extension?: string
  status?: FileAttachmentStatus
  progress?: number
  errorMessage?: string
  description?: string
  descriptionTone?: 'muted' | 'success'
}

export type FileAttachmentMode = 'readonly' | 'upload' | 'manage'
