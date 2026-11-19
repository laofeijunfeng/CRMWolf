<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  AlertCircle,
  CheckCircle2,
  Download,
  Eye,
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
import { Progress } from '@/components/ui/progress'
import type { FileAttachmentItem, FileAttachmentMode } from '@/types/fileAttachment'
import FilePreviewDialog from './FilePreviewDialog.vue'
import {
  formatFileSize as formatSize,
  getFileIcon as getIcon,
  getFilePreviewKind,
  getFileTypeLabel as getTypeLabel
} from './filePreview'

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
  showHeader?: boolean
  downloadDisabledLabel?: string
  downloadLabel?: string
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
  previewInDialog: true,
  showHeader: true,
  downloadDisabledLabel: '',
  downloadLabel: ''
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

const handlePreview = (file: FileAttachmentItem): void => {
  emit('preview', file)
  if (!props.previewInDialog || !isPreviewable(file) || file.url == null || file.url === '') return

  selectedPreview.value = file
  previewOpen.value = true
}

const handleDownload = (file: FileAttachmentItem): void => {
  emit('download', file)
}

const handleRemove = (file: FileAttachmentItem): void => {
  emit('remove', file)
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

const shouldShowStatus = (file: FileAttachmentItem): boolean => {
  return (file.status ?? 'done') !== 'done'
}

const hasMeta = (file: FileAttachmentItem): boolean => {
  return formatSize(file.size) !== '' || (file.description ?? '') !== '' || shouldShowStatus(file)
}

const isPreviewable = (file: FileAttachmentItem): boolean => getFilePreviewKind(file) !== 'unsupported'

/** The preview dialog mirrors the row's download affordance. */
const previewAllowsDownload = computed(() =>
  props.allowDownload && (props.downloadDisabledLabel ?? '').trim() === ''
)
</script>

<template>
  <section :class="['file-attachment', { 'file-attachment--compact': compact }]">
    <div v-if="showHeader || canUpload" class="file-attachment__header">
      <div v-if="showHeader" class="file-attachment__heading">
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
          <div v-if="hasMeta(file)" class="file-attachment__meta">
            <span v-if="formatSize(file.size)">{{ formatSize(file.size) }}</span>
            <span
              v-if="file.description"
              :class="{ 'file-attachment__description--success': file.descriptionTone === 'success' }"
            >{{ file.description }}</span>
            <span v-if="shouldShowStatus(file)" class="file-attachment__status">{{ getStatusText(file) }}</span>
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
            v-if="(downloadDisabledLabel ?? '').trim() !== ''"
            type="button"
            variant="outline"
            size="sm"
            class="file-attachment__download-disabled"
            disabled
          >
            {{ downloadDisabledLabel }}
          </Button>
          <Button
            v-else-if="(downloadLabel ?? '').trim() !== '' && allowDownload"
            type="button"
            variant="outline"
            size="sm"
            class="file-attachment__download-label"
            @click="handleDownload(file)"
          >
            {{ downloadLabel }}
          </Button>
          <Button
            v-else-if="allowDownload"
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

    <FilePreviewDialog
      v-model:open="previewOpen"
      :file="selectedPreview"
      :loading="(selectedPreview?.status ?? 'done') === 'processing'"
      :allow-download="previewAllowsDownload"
      @download="handleDownload"
    />
  </section>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.file-attachment {
  display: flex;
  flex-direction: column;
  gap: $space-2;
  min-width: 0;
}

.file-attachment__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: $space-3;
}

.file-attachment__heading {
  min-width: 0;
}

.file-attachment__title {
  margin: 0;
  color: hsl(var(--foreground));
  font-size: 14px;
  font-weight: 600;
  line-height: 20px;
}

.file-attachment__required {
  color: hsl(var(--status-danger));
}

.file-attachment__description {
  margin: $space-1 0 0;
  color: hsl(var(--muted-foreground));
  font-size: 12px;
  line-height: 20px;
}

.file-attachment__upload {
  min-height: var(--touch-target);
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
  border: 1px solid hsl(var(--border));
  border-radius: var(--radius-md);
  background: hsl(var(--card));
  overflow: hidden;
}

.file-attachment__item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: $space-2;
  min-height: 40px;
  padding: $space-2 $space-3;
  border-bottom: 1px solid hsl(var(--border));

  &:last-child {
    border-bottom: 0;
  }
}

.file-attachment__item--error {
  background: color-mix(in srgb, hsl(var(--status-danger)) var(--status-bg-mix), transparent);
}

.file-attachment__icon {
  width: 18px;
  height: 18px;
  color: hsl(var(--brand));
}

.file-attachment__content {
  display: flex;
  flex-direction: column;
  gap: $space-1;
  min-width: 0;
}

.file-attachment__name-row {
  display: flex;
  align-items: center;
  gap: $space-2;
  min-width: 0;
}

.file-attachment__name {
  color: hsl(var(--foreground));
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-attachment__type {
  flex-shrink: 0;
  padding: 2px $space-1;
  border: 1px solid hsl(var(--border));
  border-radius: var(--radius-sm);
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted));
  font-size: 12px;
  font-weight: 500;
  line-height: 1.4;
}

.file-attachment__meta {
  display: flex;
  flex-wrap: wrap;
  gap: $space-2;
  color: hsl(var(--muted-foreground));
  font-size: 12px;
  line-height: 20px;
}

.file-attachment__status {
  color: hsl(var(--muted-foreground));
}

.file-attachment__progress {
  height: 6px;
  max-width: 280px;
}

.file-attachment__error {
  display: inline-flex;
  align-items: center;
  gap: $space-1;
  margin: 0;
  color: hsl(var(--status-danger));
  font-size: 12px;
  line-height: 20px;
}

.file-attachment__actions {
  display: inline-flex;
  align-items: center;
  gap: $space-1;
}

.file-attachment__description--success {
  color: hsl(var(--status-success));
}

.file-attachment__download-disabled,
.file-attachment__download-label {
  min-width: 72px;
}

.file-attachment__download-disabled {
  color: hsl(var(--muted-foreground));
}

.file-attachment__action {
  width: 32px;
  height: 32px;
  color: hsl(var(--muted-foreground));

  &:focus-visible {
    outline: 2px solid hsl(var(--ring) / 0.5);
    outline-offset: 2px;
  }
}

.file-attachment__action--danger {
  color: hsl(var(--status-danger));
}

.file-attachment__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: $space-2;
  min-height: 56px;
  padding: $space-2 $space-3;
  border: 1px dashed hsl(var(--border));
  border-radius: var(--radius-md);
  color: hsl(var(--muted-foreground));
  background: var(--wash-hover);
  font-size: 14px;
}

.file-attachment__empty-icon {
  width: 18px;
  height: 18px;
  color: hsl(var(--muted-foreground));
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
    gap: $space-1;
    min-height: var(--touch-target);
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
    color: hsl(var(--status-success));
    font-size: 12px;
    font-weight: 500;
  }

  .file-attachment__action {
    width: var(--touch-target);
    height: var(--touch-target);
    color: hsl(var(--status-success));
    background: color-mix(in srgb, hsl(var(--status-success)) var(--status-bg-mix), transparent);

    &:hover {
      background: color-mix(in srgb, hsl(var(--status-success)) var(--status-bg-mix), transparent);
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

@media (max-width: $bp-sm - 1) {
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
    gap: $space-1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .file-attachment * {
    transition-duration: 0.01ms;
  }
}
</style>
