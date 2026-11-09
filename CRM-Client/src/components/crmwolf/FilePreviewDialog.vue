<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useResizeObserver } from '@vueuse/core'
import {
  AlertCircle,
  Download,
  ExternalLink,
  File,
  LoaderCircle,
  Maximize2,
  Minimize2,
  MoveHorizontal,
  RotateCcw,
  Scan,
  X,
  ZoomIn,
  ZoomOut
} from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import type { FileAttachmentItem } from '@/types/fileAttachment'
import LiveRegion from './LiveRegion.vue'
import {
  MAX_PREVIEW_SCALE,
  MIN_PREVIEW_SCALE,
  buildPdfViewerUrl,
  computeFitScale,
  formatFileSize,
  getDefaultFitMode,
  getFileIcon,
  getFilePreviewKind,
  getFileTypeLabel,
  zoomInScale,
  zoomOutScale,
  type FilePreviewFitMode,
  type PreviewSize
} from './filePreview'

type ContentStatus = 'loading' | 'ready' | 'error'
type ViewState = ContentStatus | 'unsupported'

const props = withDefaults(defineProps<{
  open: boolean
  file: FileAttachmentItem | null
  /** Parent is still preparing `file.url` (e.g. fetching a blob). */
  loading?: boolean
  allowDownload?: boolean
  /** Offer opening `file.url` in a new tab, for external links. */
  allowOpenInNewTab?: boolean
}>(), {
  loading: false,
  allowDownload: true,
  allowOpenInNewTab: false
})

const emit = defineEmits<{
  'update:open': [open: boolean]
  download: [file: FileAttachmentItem]
}>()

const DOCX_ERROR = 'DOCX 预览加载失败，请下载后查看'
const IMAGE_ERROR = '图片加载失败，请下载后查看'

const readerRef = ref<HTMLElement | null>(null)
const docxRef = ref<HTMLElement | null>(null)
const maximized = ref(false)
const fitMode = ref<FilePreviewFitMode>('width')
const customScale = ref(1)
const contentStatus = ref<ContentStatus>('loading')
const errorMessage = ref('')
const naturalSize = ref<PreviewSize | null>(null)
const viewportSize = ref<PreviewSize>({ width: 0, height: 0 })
const reloadKey = ref(0)
let docxRenderToken = 0
/** Token of the DOCX render waiting for its container; 0 when nothing is pending. */
const pendingDocxToken = ref(0)

const kind = computed(() => (props.file ? getFilePreviewKind(props.file) : 'unsupported'))
const fileUrl = computed(() => props.file?.url ?? '')
const fileIcon = computed(() => (props.file ? getFileIcon(props.file) : File))
const fileMeta = computed(() => {
  if (!props.file) return ''
  return [getFileTypeLabel(props.file), formatFileSize(props.file.size)].filter(Boolean).join(' · ')
})
const canDownload = computed(() => props.allowDownload && props.file !== null)
const canOpenInNewTab = computed(() => props.allowOpenInNewTab && fileUrl.value !== '')

const viewState = computed<ViewState>(() => {
  if (props.loading) return 'loading'
  if (kind.value === 'unsupported') return 'unsupported'
  if (fileUrl.value === '') return 'error'
  return contentStatus.value
})

const effectiveScale = computed(() => {
  if (fitMode.value === 'custom') return customScale.value
  if (kind.value === 'pdf' || naturalSize.value === null) return 1
  return computeFitScale(
    fitMode.value,
    viewportSize.value,
    naturalSize.value,
    kind.value === 'image' ? 1 : MAX_PREVIEW_SCALE
  )
})

const scaleLabel = computed(() => {
  if (kind.value === 'pdf' && fitMode.value !== 'custom') {
    return fitMode.value === 'width' ? '适应宽度' : '适应页面'
  }
  return `${Math.round(effectiveScale.value * 100)}%`
})

const zoomEnabled = computed(() => viewState.value === 'ready')
const canZoomIn = computed(() => zoomEnabled.value && effectiveScale.value < MAX_PREVIEW_SCALE)
const canZoomOut = computed(() => zoomEnabled.value && effectiveScale.value > MIN_PREVIEW_SCALE)

const pdfSrc = computed(() => buildPdfViewerUrl(fileUrl.value, fitMode.value, effectiveScale.value))

const imageStyle = computed<Record<string, string>>(() => {
  if (naturalSize.value === null) return {}
  return {
    width: `${naturalSize.value.width * effectiveScale.value}px`,
    height: `${naturalSize.value.height * effectiveScale.value}px`
  }
})

// Zoom is applied only after the natural page size has been measured at 1x.
const docxStyle = computed<Record<string, string>>(() =>
  naturalSize.value === null ? {} : { zoom: String(effectiveScale.value) }
)

const announcement = computed(() => {
  switch (viewState.value) {
    case 'loading': return '正在加载预览'
    case 'error': return errorMessage.value || '预览加载失败'
    case 'unsupported': return '当前格式暂不支持在线预览'
    default: return `预览已加载，当前比例 ${scaleLabel.value}`
  }
})

useResizeObserver(readerRef, (entries) => {
  const rect = entries[0]?.contentRect
  if (rect) viewportSize.value = { width: rect.width, height: rect.height }
})

const resetView = (): void => {
  fitMode.value = getDefaultFitMode(kind.value)
  customScale.value = 1
}

const startPreview = (): void => {
  naturalSize.value = null
  errorMessage.value = ''
  contentStatus.value = 'loading'
  docxRenderToken += 1
  const needsDocx = kind.value === 'docx' && fileUrl.value !== '' && !props.loading
  pendingDocxToken.value = needsDocx ? docxRenderToken : 0
}

// The DOCX container lives inside the portalled dialog, so render once it is actually mounted.
watch([docxRef, pendingDocxToken], ([container, token]) => {
  if (container === null || token === 0 || token !== docxRenderToken) return
  pendingDocxToken.value = 0
  void renderDocx(fileUrl.value, token, container)
}, { flush: 'post' })

const renderDocx = async (url: string, token: number, container: HTMLElement): Promise<void> => {
  container.innerHTML = ''

  try {
    const [{ renderAsync }, response] = await Promise.all([import('docx-preview'), fetch(url)])
    if (!response.ok) throw new Error(`DOCX fetch failed: ${response.status}`)
    const blob = await response.blob()
    if (token !== docxRenderToken || docxRef.value !== container) return
    await renderAsync(blob, container, undefined, {
      className: 'docx',
      inWrapper: false,
      ignoreWidth: false,
      ignoreHeight: false,
      breakPages: true
    })
    if (token !== docxRenderToken) return
    naturalSize.value = measureDocx(container)
    contentStatus.value = 'ready'
  } catch {
    if (token !== docxRenderToken) return
    errorMessage.value = DOCX_ERROR
    contentStatus.value = 'error'
  }
}

const measureDocx = (container: HTMLElement): PreviewSize => {
  const pages = Array.from(container.querySelectorAll<HTMLElement>('section.docx'))
  const first = pages[0]
  if (first === undefined) return { width: container.scrollWidth, height: container.scrollHeight }
  return {
    width: Math.max(...pages.map(page => page.offsetWidth)),
    height: first.offsetHeight
  }
}

watch(
  () => [props.open, props.file?.id, fileUrl.value, props.loading] as const,
  ([open], previous) => {
    if (!open) {
      docxRenderToken += 1
      return
    }
    const reopened = previous?.[0] !== true
    const fileChanged = previous?.[1] !== props.file?.id
    if (reopened) maximized.value = false
    if (reopened || fileChanged) resetView()
    startPreview()
  },
  { immediate: true }
)

const handleImageLoad = (event: Event): void => {
  const image = event.target as HTMLImageElement
  naturalSize.value = { width: image.naturalWidth, height: image.naturalHeight }
  contentStatus.value = 'ready'
}

const handleImageError = (): void => {
  errorMessage.value = IMAGE_ERROR
  contentStatus.value = 'error'
}

const handlePdfLoad = (): void => {
  contentStatus.value = 'ready'
}

const setFitMode = (mode: Exclude<FilePreviewFitMode, 'custom'>): void => {
  fitMode.value = mode
}

const zoomIn = (): void => {
  if (!canZoomIn.value) return
  customScale.value = zoomInScale(effectiveScale.value)
  fitMode.value = 'custom'
}

const zoomOut = (): void => {
  if (!canZoomOut.value) return
  customScale.value = zoomOutScale(effectiveScale.value)
  fitMode.value = 'custom'
}

const resetZoom = (): void => {
  if (zoomEnabled.value) resetView()
}

const retry = (): void => {
  reloadKey.value += 1
  startPreview()
}

const handleDownload = (): void => {
  if (props.file && props.allowDownload) emit('download', props.file)
}

const handleKeydown = (event: KeyboardEvent): void => {
  if (event.metaKey || event.ctrlKey || event.altKey) return
  const target = event.target as HTMLElement | null
  if (target?.closest('input, textarea, select, [contenteditable="true"]')) return
  const actions: Record<string, () => void> = { '+': zoomIn, '=': zoomIn, '-': zoomOut, '0': resetZoom }
  const action = actions[event.key]
  if (!action) return
  event.preventDefault()
  action()
}

const contentClass = computed(() => cn(
  'flex flex-col gap-0 overflow-hidden p-0 max-w-none',
  'max-sm:h-dvh max-sm:w-screen max-sm:rounded-none max-sm:border-0',
  maximized.value
    ? 'h-dvh w-screen rounded-none border-0'
    : 'h-[calc(100dvh-48px)] w-[min(1280px,calc(100vw-48px))]'
))
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent
      :class="contentClass"
      hide-close
    >
      <!-- `contents` keeps DialogContent's flex layout; it only gives keyboard events a listener. -->
      <div class="contents" data-testid="file-preview-dialog" @keydown="handleKeydown">
      <header class="file-preview__header">
        <component :is="fileIcon" class="file-preview__file-icon" aria-hidden="true" />
        <div class="file-preview__heading">
          <DialogTitle class="file-preview__title">{{ file?.name ?? '文件预览' }}</DialogTitle>
          <DialogDescription class="file-preview__meta">{{ fileMeta || '文件' }}</DialogDescription>
        </div>
        <div class="file-preview__header-actions">
          <Button
            v-if="canDownload"
            type="button"
            variant="outline"
            size="sm"
            class="file-preview__button"
            aria-label="下载文件"
            @click="handleDownload"
          >
            <Download aria-hidden="true" />
            <span class="file-preview__button-text">下载</span>
          </Button>
          <Button
            v-if="canOpenInNewTab"
            as="a"
            :href="fileUrl"
            target="_blank"
            rel="noopener noreferrer"
            variant="outline"
            size="sm"
            class="file-preview__button"
            aria-label="在新标签页打开"
          >
            <ExternalLink aria-hidden="true" />
            <span class="file-preview__button-text">新标签打开</span>
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            class="file-preview__icon-button file-preview__maximize"
            :aria-label="maximized ? '还原窗口' : '最大化'"
            :aria-pressed="maximized"
            @click="maximized = !maximized"
          >
            <Minimize2 v-if="maximized" aria-hidden="true" />
            <Maximize2 v-else aria-hidden="true" />
          </Button>
          <DialogClose as-child>
            <Button type="button" variant="ghost" size="icon" class="file-preview__icon-button" aria-label="关闭">
              <X aria-hidden="true" />
            </Button>
          </DialogClose>
        </div>
      </header>

      <div class="file-preview__toolbar" role="toolbar" aria-label="阅读工具">
        <Button
          type="button"
          :variant="fitMode === 'width' ? 'secondary' : 'ghost'"
          size="sm"
          class="file-preview__button"
          aria-label="适应宽度"
          :aria-pressed="fitMode === 'width'"
          :disabled="!zoomEnabled"
          @click="setFitMode('width')"
        >
          <MoveHorizontal aria-hidden="true" />
          <span class="file-preview__button-text">适应宽度</span>
        </Button>
        <Button
          type="button"
          :variant="fitMode === 'page' ? 'secondary' : 'ghost'"
          size="sm"
          class="file-preview__button"
          aria-label="适应页面"
          :aria-pressed="fitMode === 'page'"
          :disabled="!zoomEnabled"
          @click="setFitMode('page')"
        >
          <Scan aria-hidden="true" />
          <span class="file-preview__button-text">适应页面</span>
        </Button>
        <span class="file-preview__divider" aria-hidden="true" />
        <Button
          type="button"
          variant="ghost"
          size="icon"
          class="file-preview__icon-button"
          aria-label="缩小"
          :disabled="!canZoomOut"
          @click="zoomOut"
        >
          <ZoomOut aria-hidden="true" />
        </Button>
        <span class="file-preview__scale" data-testid="file-preview-scale">{{ scaleLabel }}</span>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          class="file-preview__icon-button"
          aria-label="放大"
          :disabled="!canZoomIn"
          @click="zoomIn"
        >
          <ZoomIn aria-hidden="true" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          class="file-preview__button"
          aria-label="恢复默认比例"
          :disabled="!zoomEnabled"
          @click="resetZoom"
        >
          <RotateCcw aria-hidden="true" />
          <span class="file-preview__button-text">恢复默认</span>
        </Button>
      </div>

      <div
        ref="readerRef"
        :class="['file-preview__reader', `file-preview__reader--${kind}`]"
        data-testid="file-preview-reader"
      >
        <template v-if="!loading && fileUrl !== '' && kind !== 'unsupported'">
          <img
            v-if="kind === 'image'"
            :key="`image-${reloadKey}`"
            :src="fileUrl"
            :alt="file?.name ?? '图片预览'"
            :style="imageStyle"
            :class="['file-preview__image', { 'file-preview__content--pending': viewState !== 'ready' }]"
            @load="handleImageLoad"
            @error="handleImageError"
          >
          <iframe
            v-else-if="kind === 'pdf'"
            :key="`${pdfSrc}-${reloadKey}`"
            :src="pdfSrc"
            :title="file?.name ?? 'PDF 预览'"
            class="file-preview__frame"
            @load="handlePdfLoad"
          />
          <div
            v-else-if="kind === 'docx'"
            ref="docxRef"
            :style="docxStyle"
            :class="['file-preview__docx', { 'file-preview__content--pending': viewState !== 'ready' }]"
          />
        </template>

        <div v-if="viewState === 'loading'" class="file-preview__state" data-state="loading">
          <LoaderCircle class="file-preview__state-icon file-preview__spinner" aria-hidden="true" />
          <p class="file-preview__state-title">正在加载预览…</p>
        </div>
        <div v-else-if="viewState === 'error'" class="file-preview__state" data-state="error">
          <AlertCircle class="file-preview__state-icon file-preview__state-icon--danger" aria-hidden="true" />
          <p class="file-preview__state-title">{{ errorMessage || '预览加载失败，请下载后查看' }}</p>
          <div class="file-preview__state-actions">
            <Button v-if="fileUrl !== ''" type="button" variant="outline" size="sm" @click="retry">
              <RotateCcw aria-hidden="true" />
              重试
            </Button>
            <Button v-if="canDownload" type="button" size="sm" @click="handleDownload">
              <Download aria-hidden="true" />
              下载查看
            </Button>
            <Button
              v-else-if="canOpenInNewTab"
              as="a"
              :href="fileUrl"
              target="_blank"
              rel="noopener noreferrer"
              size="sm"
            >
              <ExternalLink aria-hidden="true" />
              新标签打开
            </Button>
          </div>
        </div>
        <div v-else-if="viewState === 'unsupported'" class="file-preview__state" data-state="unsupported">
          <component :is="fileIcon" class="file-preview__state-icon" aria-hidden="true" />
          <p class="file-preview__state-title">当前格式暂不支持在线预览</p>
          <p class="file-preview__state-hint">支持图片、PDF 和 DOCX，其他格式请下载后查看</p>
          <div class="file-preview__state-actions">
            <Button v-if="canDownload" type="button" size="sm" @click="handleDownload">
              <Download aria-hidden="true" />
              下载查看
            </Button>
            <Button
              v-else-if="canOpenInNewTab"
              as="a"
              :href="fileUrl"
              target="_blank"
              rel="noopener noreferrer"
              size="sm"
            >
              <ExternalLink aria-hidden="true" />
              新标签打开
            </Button>
          </div>
        </div>
      </div>

      <LiveRegion class="sr-only">{{ announcement }}</LiveRegion>
      </div>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.file-preview__header {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  min-height: 56px;
  padding: $wolf-space-sm-v2 $wolf-space-sm-v2 $wolf-space-sm-v2 $wolf-space-lg-v2;
  padding-top: max(#{$wolf-space-sm-v2}, env(safe-area-inset-top, 0px));
  border-bottom: 1px solid hsl(var(--border));
}

.file-preview__file-icon {
  flex: none;
  width: 20px;
  height: 20px;
  color: hsl(var(--muted-foreground));
}

.file-preview__heading {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.file-preview__title {
  overflow: hidden;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-preview__meta {
  font-size: $wolf-font-size-caption-v2;
}

.file-preview__header-actions,
.file-preview__toolbar,
.file-preview__state-actions {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
}

.file-preview__header-actions {
  flex: none;
}

.file-preview__toolbar {
  flex-wrap: nowrap;
  min-height: 48px;
  padding: $wolf-space-xs-v2 $wolf-space-lg-v2;
  overflow-x: auto;
  border-bottom: 1px solid hsl(var(--border));
}

.file-preview__divider {
  width: 1px;
  height: 20px;
  margin: 0 $wolf-space-xs-v2;
  background: hsl(var(--border));
}

.file-preview__scale {
  min-width: 64px;
  color: hsl(var(--muted-foreground));
  font-size: $wolf-font-size-caption-v2;
  font-variant-numeric: tabular-nums;
  text-align: center;
}

.file-preview__reader {
  position: relative;
  display: flex;
  flex: 1;
  align-items: safe center;
  justify-content: safe center;
  min-height: 0;
  padding: $wolf-space-lg-v2;
  padding-bottom: max(#{$wolf-space-lg-v2}, env(safe-area-inset-bottom, 0px));
  overflow: auto;
  background: hsl(var(--muted));
  overscroll-behavior: contain;
}

.file-preview__reader--docx {
  align-items: flex-start;
}

.file-preview__reader--pdf {
  padding: 0;
}

.file-preview__image {
  display: block;
  flex: none;
  max-width: none;
  background: hsl(var(--background));
  box-shadow: $wolf-shadow-card-v2;
}

.file-preview__frame {
  width: 100%;
  height: 100%;
  border: 0;
  background: hsl(var(--background));
}

.file-preview__docx {
  display: flex;
  flex: none;
  flex-direction: column;
  align-items: center;
  gap: $wolf-space-lg-v2;

  :deep(section.docx) {
    flex: none;
    margin: 0;
    background: $wolf-bg-card-v2;
    box-shadow: $wolf-shadow-card-v2;
  }
}

.file-preview__content--pending {
  visibility: hidden;
}

.file-preview__state {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: $wolf-space-sm-v2;
  padding: $wolf-space-xl-v2;
  text-align: center;
}

.file-preview__state-icon {
  width: 32px;
  height: 32px;
  color: hsl(var(--muted-foreground));
}

.file-preview__state-icon--danger {
  color: hsl(var(--destructive));
}

.file-preview__spinner {
  animation: file-preview-spin 1s linear infinite;
}

.file-preview__state-title {
  margin: 0;
  color: hsl(var(--foreground));
  font-size: $wolf-font-size-body-v2;
}

.file-preview__state-hint {
  margin: 0;
  color: hsl(var(--muted-foreground));
  font-size: $wolf-font-size-caption-v2;
}

.file-preview__state-actions {
  margin-top: $wolf-space-xs-v2;
}

@keyframes file-preview-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 899px) {
  .file-preview__button-text,
  .file-preview__scale {
    display: none;
  }
}

@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .file-preview__header {
    padding-left: $wolf-space-md-v2;
  }

  .file-preview__toolbar {
    justify-content: space-between;
    padding: $wolf-space-xs-v2 $wolf-space-sm-v2;
  }

  .file-preview__button,
  .file-preview__icon-button {
    min-width: $wolf-touch-target-min-v2;
    min-height: $wolf-touch-target-min-v2;
  }

  .file-preview__maximize,
  .file-preview__divider {
    display: none;
  }

  .file-preview__reader {
    padding: $wolf-space-sm-v2;
  }
}

@media (prefers-reduced-motion: reduce) {
  .file-preview__spinner {
    animation-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>
