<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import {
  AlertCircle,
  CheckCircle2,
  Download,
  Eye,
  File,
  FileArchive,
  FileImage,
  FileSpreadsheet,
  FileText,
  Trash2,
  Upload
} from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle
} from '@/components/ui/empty'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { Progress } from '@/components/ui/progress'
import type { FileAttachmentItem, FileAttachmentMode } from '@/types/fileAttachment'

const props = withDefaults(defineProps<{
  files: FileAttachmentItem[]
  mode?: FileAttachmentMode
  title?: string
  description?: string
  emptyText?: string
  accept?: string
  multiple?: boolean
  required?: boolean
  maxSizeMb?: number
  disabled?: boolean
  compact?: boolean
  allowPreview?: boolean
  allowDownload?: boolean
  allowRemove?: boolean
  previewInDialog?: boolean
}>(), {
  mode: 'readonly',
  title: '附件',
  description: '',
  emptyText: '暂无附件',
  accept: '.pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx,.ofd',
  multiple: false,
  required: false,
  maxSizeMb: 20,
  disabled: false,
  compact: false,
  allowPreview: true,
  allowDownload: true,
  allowRemove: true,
  previewInDialog: true
})

const emit = defineEmits<{
  upload: [files: File[]]
  download: [file: FileAttachmentItem]
  preview: [file: FileAttachmentItem]
  remove: [file: FileAttachmentItem]
  error: [message: string]
}>()

const inputRef = ref<HTMLInputElement | null>(null)
const selectedPreview = ref<FileAttachmentItem | null>(null)
const previewOpen = ref(false)
const docxPreviewRef = ref<HTMLElement | null>(null)
const docxPreviewLoading = ref(false)
const docxPreviewError = ref('')

const canUpload = computed(() => props.mode === 'upload' || props.mode === 'manage')
const canRemove = computed(() => props.mode === 'manage' && props.allowRemove)
const hasFiles = computed(() => props.files.length > 0)

const acceptedExtensions = computed(() =>
  props.accept
    .split(',')
    .map(item => item.trim().toLowerCase())
    .filter(Boolean)
)

const triggerUpload = (): void => {
  if (!canUpload.value || props.disabled) return
  inputRef.value?.click()
}

const handleInputChange = (event: Event): void => {
  const target = event.target as HTMLInputElement
  const selectedFiles = Array.from(target.files ?? [])
  target.value = ''
  if (selectedFiles.length === 0) return

  const invalidMessage = validateFiles(selectedFiles)
  if (invalidMessage) {
    emit('error', invalidMessage)
    return
  }

  emit('upload', selectedFiles)
}

const validateFiles = (files: File[]): string => {
  const maxBytes = props.maxSizeMb * 1024 * 1024
  const oversized = files.find(file => file.size > maxBytes)
  if (oversized) {
    return `${oversized.name} 超过 ${props.maxSizeMb}MB 限制`
  }

  const invalid = files.find(file => !matchesAccept(file))
  if (invalid) {
    return `${invalid.name} 文件类型不支持`
  }

  return ''
}

const matchesAccept = (file: File): boolean => {
  if (acceptedExtensions.value.length === 0) return true
  const fileName = file.name.toLowerCase()
  const mimeType = file.type.toLowerCase()

  return acceptedExtensions.value.some(rule => {
    if (rule === '*/*') return true
    if (rule.endsWith('/*')) return mimeType.startsWith(rule.replace('/*', '/'))
    if (rule.startsWith('.')) return fileName.endsWith(rule)
    return mimeType === rule
  })
}

const handlePreview = async (file: FileAttachmentItem): Promise<void> => {
  emit('preview', file)
  if (!props.previewInDialog || !isPreviewable(file) || !file.url) return

  selectedPreview.value = file
  previewOpen.value = true
  docxPreviewError.value = ''

  if (isDocx(file)) {
    await nextTick()
    await renderDocxPreview(file)
  }
}

const handleDownload = (file: FileAttachmentItem): void => {
  emit('download', file)
}

const handleRemove = (file: FileAttachmentItem): void => {
  emit('remove', file)
}

const getExtension = (file: FileAttachmentItem): string => {
  if (file.extension) return file.extension.toLowerCase().replace(/^\./, '')
  const name = file.name || file.url || ''
  return name.toLowerCase().split('?')[0]?.split('.').pop() ?? ''
}

const getIcon = (file: FileAttachmentItem) => {
  const ext = getExtension(file)
  if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) return FileImage
  if (['pdf', 'ofd', 'doc', 'docx'].includes(ext)) return FileText
  if (['xls', 'xlsx', 'csv'].includes(ext)) return FileSpreadsheet
  if (['zip', 'rar', '7z'].includes(ext)) return FileArchive
  return File
}

const getTypeLabel = (file: FileAttachmentItem): string => {
  const ext = getExtension(file)
  const labels: Record<string, string> = {
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
  return labels[ext] ?? (ext ? ext.toUpperCase() : '文件')
}

const formatSize = (size?: number): string => {
  if (!size || size <= 0) return ''
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

const getStatusText = (file: FileAttachmentItem): string => {
  const status = file.status ?? 'done'
  const statusMap: Record<string, string> = {
    idle: '待上传',
    uploading: '上传中',
    processing: '处理中',
    done: '已完成',
    error: '失败'
  }
  return statusMap[status] ?? '未知'
}

const isPreviewable = (file: FileAttachmentItem): boolean => {
  const ext = getExtension(file)
  return ['pdf', 'docx', 'jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)
}

const isImage = (file: FileAttachmentItem): boolean => {
  const ext = getExtension(file)
  return ['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)
}

const isPdf = (file: FileAttachmentItem): boolean => getExtension(file) === 'pdf'

const isDocx = (file: FileAttachmentItem): boolean => getExtension(file) === 'docx'

const renderDocxPreview = async (file: FileAttachmentItem): Promise<void> => {
  if (!file.url || docxPreviewRef.value === null) return

  docxPreviewLoading.value = true
  docxPreviewError.value = ''
  docxPreviewRef.value.innerHTML = ''

  try {
    const [{ renderAsync }, response] = await Promise.all([
      import('docx-preview'),
      fetch(file.url)
    ])
    if (!response.ok) throw new Error('DOCX fetch failed')

    const blob = await response.blob()
    if (docxPreviewRef.value === null) return
    await renderAsync(blob, docxPreviewRef.value)
  } catch {
    docxPreviewError.value = 'DOCX 预览加载失败，请下载后查看'
  } finally {
    docxPreviewLoading.value = false
  }
}
</script>

<template>
  <section :class="['file-attachment', { 'file-attachment--compact': compact }]">
    <div class="file-attachment__header">
      <div class="file-attachment__heading">
        <h3 class="file-attachment__title">
          {{ title }}
          <span v-if="required" class="file-attachment__required">*</span>
        </h3>
        <p v-if="description" class="file-attachment__description">{{ description }}</p>
      </div>

      <Button
        v-if="canUpload"
        type="button"
        size="sm"
        :disabled="disabled"
        class="file-attachment__upload"
        @click="triggerUpload"
      >
        <Upload class="w-4 h-4" aria-hidden="true" />
        上传文件
      </Button>

      <input
        ref="inputRef"
        class="file-attachment__input"
        type="file"
        :accept="accept"
        :multiple="multiple"
        :disabled="disabled"
        @change="handleInputChange"
      />
    </div>

    <div v-if="hasFiles" class="file-attachment__list">
      <article
        v-for="file in files"
        :key="file.id"
        :class="['file-attachment__item', `file-attachment__item--${file.status ?? 'done'}`]"
      >
        <component :is="getIcon(file)" class="file-attachment__icon" aria-hidden="true" />

        <div class="file-attachment__content">
          <div class="file-attachment__name-row">
            <span class="file-attachment__name">{{ file.name }}</span>
            <span class="file-attachment__type">{{ getTypeLabel(file) }}</span>
          </div>
          <div class="file-attachment__meta">
            <span v-if="formatSize(file.size)">{{ formatSize(file.size) }}</span>
            <span v-if="file.description">{{ file.description }}</span>
            <span class="file-attachment__status">{{ getStatusText(file) }}</span>
          </div>
          <Progress
            v-if="file.status === 'uploading' || file.status === 'processing'"
            :model-value="file.progress ?? 0"
            class="file-attachment__progress"
          />
          <p v-if="file.status === 'error' && file.errorMessage" class="file-attachment__error">
            <AlertCircle class="w-3.5 h-3.5" aria-hidden="true" />
            {{ file.errorMessage }}
          </p>
        </div>

        <div class="file-attachment__actions">
          <Button
            v-if="allowPreview && file.url && isPreviewable(file)"
            type="button"
            variant="ghost"
            size="icon"
            class="file-attachment__action"
            :aria-label="`预览${file.name}`"
            @click="handlePreview(file)"
          >
            <Eye class="w-4 h-4" aria-hidden="true" />
          </Button>
          <Button
            v-if="allowDownload"
            type="button"
            variant="ghost"
            size="icon"
            class="file-attachment__action"
            :aria-label="`下载${file.name}`"
            @click="handleDownload(file)"
          >
            <Download class="w-4 h-4" aria-hidden="true" />
          </Button>
          <Button
            v-if="canRemove"
            type="button"
            variant="ghost"
            size="icon"
            class="file-attachment__action file-attachment__action--danger"
            :aria-label="`删除${file.name}`"
            :disabled="disabled"
            @click="handleRemove(file)"
          >
            <Trash2 class="w-4 h-4" aria-hidden="true" />
          </Button>
        </div>
      </article>
    </div>

    <Empty v-else class="file-attachment__empty">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <CheckCircle2 v-if="mode === 'readonly'" class="h-5 w-5" aria-hidden="true" />
          <Upload v-else class="h-5 w-5" aria-hidden="true" />
        </EmptyMedia>
        <EmptyTitle class="text-sm font-medium">{{ emptyText }}</EmptyTitle>
      </EmptyHeader>
    </Empty>

    <Dialog v-model:open="previewOpen">
      <DialogContent class="file-preview-dialog">
        <DialogHeader>
          <DialogTitle>{{ selectedPreview?.name ?? '文件预览' }}</DialogTitle>
          <DialogDescription>
            {{ selectedPreview ? getTypeLabel(selectedPreview) : '文件' }}
          </DialogDescription>
        </DialogHeader>

        <div v-if="selectedPreview?.url" class="file-preview-dialog__body">
          <img
            v-if="isImage(selectedPreview)"
            :src="selectedPreview.url"
            :alt="selectedPreview.name"
            class="file-preview-dialog__image"
          />
          <iframe
            v-else-if="isPdf(selectedPreview)"
            :src="selectedPreview.url"
            :title="selectedPreview.name"
            class="file-preview-dialog__frame"
          />
          <div
            v-else-if="isDocx(selectedPreview)"
            class="file-preview-dialog__docx-shell"
          >
            <div v-if="docxPreviewLoading" class="file-preview-dialog__loading">
              DOCX 预览加载中...
            </div>
            <div v-if="docxPreviewError" class="file-preview-dialog__error">
              {{ docxPreviewError }}
            </div>
            <div ref="docxPreviewRef" class="file-preview-dialog__docx" />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  </section>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.file-attachment {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
  min-width: 0;
}

.file-attachment__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: $wolf-space-md-v2;
}

.file-attachment__heading {
  min-width: 0;
}

.file-attachment__title {
  margin: 0;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  line-height: $wolf-line-height-title-v2;
}

.file-attachment__required {
  color: $wolf-danger-v2;
}

.file-attachment__description {
  margin: $wolf-space-xs-v2 0 0;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
}

.file-attachment__upload {
  min-height: $wolf-touch-target-min-v2;
  flex-shrink: 0;
}

.file-attachment__input {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
}

.file-attachment__list {
  display: flex;
  flex-direction: column;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-bg-card-v2;
  overflow: hidden;
}

.file-attachment__item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: $wolf-space-md-v2;
  min-height: $wolf-touch-target-min-v2;
  padding: $wolf-space-md-v2;
  border-bottom: 1px solid $wolf-border-light-v2;

  &:last-child {
    border-bottom: 0;
  }
}

.file-attachment__item--error {
  background: $wolf-danger-bg-v2;
}

.file-attachment__icon {
  width: 20px;
  height: 20px;
  color: $wolf-primary-v2;
}

.file-attachment__content {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  min-width: 0;
}

.file-attachment__name-row {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  min-width: 0;
}

.file-attachment__name {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: $wolf-line-height-body-v2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-attachment__type {
  flex-shrink: 0;
  padding: 2px $wolf-space-xs-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-sm-v2;
  color: $wolf-text-secondary-v2;
  background: $wolf-bg-muted-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: 1.4;
}

.file-attachment__meta {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-sm-v2;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
}

.file-attachment__status {
  color: $wolf-text-secondary-v2;
}

.file-attachment__progress {
  height: 6px;
  max-width: 280px;
}

.file-attachment__error {
  display: inline-flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
  margin: 0;
  color: $wolf-danger-text-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
}

.file-attachment__actions {
  display: inline-flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
}

.file-attachment__action {
  width: $wolf-touch-target-min-v2;
  height: $wolf-touch-target-min-v2;
  color: $wolf-text-secondary-v2;

  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }
}

.file-attachment__action--danger {
  color: $wolf-danger-v2;
}

.file-attachment__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: $wolf-space-sm-v2;
  min-height: 72px;
  padding: $wolf-space-md-v2;
  border: 1px dashed $wolf-border-default-v2;
  border-radius: $wolf-radius-v2;
  color: $wolf-text-tertiary-v2;
  background: $wolf-bg-hover-v2;
  font-size: $wolf-font-size-body-v2;
}

.file-attachment__empty-icon {
  width: 18px;
  height: 18px;
  color: $wolf-text-tertiary-v2;
}

.file-attachment--compact {
  display: inline-flex;
  gap: 0;

  .file-attachment__header {
    display: none;
  }

  .file-attachment__list {
    border: 0;
    border-radius: 0;
    background: transparent;
  }

  .file-attachment__item {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: $wolf-space-xs-v2;
    min-height: $wolf-touch-target-min-v2;
    padding: 0;
    border: 0;
    background: transparent;
  }

  .file-attachment__icon,
  .file-attachment__type,
  .file-attachment__meta {
    display: none;
  }

  .file-attachment__content {
    gap: 0;
  }

  .file-attachment__name {
    color: $wolf-success-text-v2;
    font-size: $wolf-font-size-caption-v2;
    font-weight: $wolf-font-weight-medium-v2;
  }

  .file-attachment__action {
    width: $wolf-touch-target-min-v2;
    height: $wolf-touch-target-min-v2;
    color: $wolf-success-text-v2;
    background: $wolf-success-bg-v2;

    &:hover {
      background: $wolf-success-bg-v2;
      opacity: 0.86;
    }
  }

  .file-attachment__empty {
    min-height: 0;
    padding: 0;
    border: 0;
    background: transparent;
  }
}

.file-preview-dialog {
  max-width: min(960px, calc(100vw - 32px));
}

.file-preview-dialog__body {
  min-height: 420px;
}

.file-preview-dialog__image {
  display: block;
  max-width: 100%;
  max-height: 70vh;
  margin: 0 auto;
  object-fit: contain;
}

.file-preview-dialog__frame {
  width: 100%;
  min-height: 70vh;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-sm-v2;
}

.file-preview-dialog__docx-shell {
  min-height: 70vh;
  max-height: 70vh;
  overflow: auto;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-sm-v2;
  background: $wolf-bg-muted-v2;
}

.file-preview-dialog__docx {
  padding: $wolf-space-md-v2;
}

.file-preview-dialog__loading,
.file-preview-dialog__error {
  padding: $wolf-space-md-v2;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-body-v2;
}

.file-preview-dialog__error {
  color: $wolf-danger-text-v2;
}

@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .file-attachment__header,
  .file-attachment__item {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .file-attachment__header {
    flex-direction: column;
    align-items: stretch;
  }

  .file-attachment__actions {
    grid-column: 1 / -1;
    justify-content: flex-end;
  }

  .file-attachment__name-row {
    align-items: flex-start;
    flex-direction: column;
    gap: $wolf-space-xs-v2;
  }
}

@media (prefers-reduced-motion: reduce) {
  .file-attachment *,
  .file-preview-dialog * {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>
