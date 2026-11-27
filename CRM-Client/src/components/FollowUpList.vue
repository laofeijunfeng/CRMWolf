<template>
  <div class="follow-up-list-container">
    <DataViewStatePanel
      :state="viewState"
      loading-type="list"
      :empty-title="`暂无${recordLabel}`"
      :empty-description="`点击上方按钮添加新的${recordLabel}`"
    >
    <div class="follow-up-list">
      <div
        v-for="followUp in followUps"
        :key="followUp.id"
        class="follow-up-item"
      >
        <HoverInfo side="top" align="center" content-class="follow-up-method-hover-card">
          <template #trigger>
            <div class="follow-up-method" aria-hidden="true">
              <component :is="getMethodIcon(followUp)" class="method-icon" />
            </div>
          </template>
          <div class="follow-up-hover-text">{{ followUp.method }}</div>
        </HoverInfo>

        <div class="follow-up-body">
          <div class="follow-up-content-row">
            <div
              v-if="props.renderMarkdown"
              class="follow-up-content-cell follow-up-content-cell--markdown"
            >
              <ActivityMarkdownContent
                :content="getPrimaryContent(followUp)"
                :collapsible="true"
              />
            </div>
            <div
              v-else
              class="follow-up-content-cell"
              :class="{
                'is-expandable': hasContentOverflow(followUp.id),
                'is-expanded': isContentExpanded(followUp.id)
              }"
            >
              <HoverInfo side="top" align="start" content-class="follow-up-content-hover-card">
                <template #trigger>
                  <p
                    :ref="(el) => setContentElement(followUp.id, el)"
                    class="follow-up-content"
                    :class="{ 'follow-up-content--expanded': isContentExpanded(followUp.id) }"
                  >
                    {{ getPrimaryContent(followUp) }}
                  </p>
                </template>
                <div class="follow-up-hover-text follow-up-hover-text--preline">
                  {{ followUp.source_content || getPrimaryContent(followUp) }}
                </div>
              </HoverInfo>
              <Button
                v-if="hasContentOverflow(followUp.id)"
                variant="ghost"
                size="icon-sm"
                class="content-expand-btn"
                :aria-expanded="isContentExpanded(followUp.id)"
                :aria-label="isContentExpanded(followUp.id) ? '收起活动内容' : '展开活动内容'"
                :title="isContentExpanded(followUp.id) ? '收起' : '展开'"
                @click.stop="toggleContentExpanded(followUp.id)"
              >
                <component :is="isContentExpanded(followUp.id) ? ChevronUp : ChevronDown" class="content-expand-icon" />
              </Button>
            </div>
            <div
              v-if="shouldShowEffectiveness(followUp) || canProcess(followUp) || canDelete(followUp)"
              class="follow-up-actions"
            >
              <HoverInfo
                v-if="shouldShowEffectiveness(followUp)"
                side="top"
                align="end"
                content-class="effectiveness-hover-card"
                enable-touch
              >
                <template #trigger>
                  <button
                    type="button"
                    class="effectiveness-indicator"
                    :aria-label="getEffectivenessLabel(followUp)"
                    @click.stop
                  >
                    <span
                      class="effectiveness-indicator-visual"
                      :class="getEffectivenessClass(followUp)"
                    >
                      <Loader2
                        v-if="followUp.effectiveness_status === 'GENERATING'"
                        class="effectiveness-icon effectiveness-icon-loading"
                        aria-hidden="true"
                      />
                      <ThumbsUp
                        v-else-if="followUp.effectiveness_is_valid"
                        class="effectiveness-icon"
                        aria-hidden="true"
                      />
                      <ThumbsDown
                        v-else
                        class="effectiveness-icon"
                        aria-hidden="true"
                      />
                    </span>
                  </button>
                </template>
                <div class="effectiveness-card">
                  <div class="effectiveness-card-title">
                    {{ getEffectivenessLabel(followUp) }}
                  </div>
                  <div
                    v-if="typeof followUp.effectiveness_score === 'number'"
                    class="effectiveness-card-score"
                  >
                    {{ followUp.effectiveness_score }} / 100
                  </div>
                  <div class="effectiveness-card-text">
                    {{ getEffectivenessTooltip(followUp) }}
                  </div>
                </div>
              </HoverInfo>
              <Button
                v-if="canProcess(followUp)"
                variant="ghost"
                size="icon-sm"
                class="process-btn"
                :disabled="isRetrying(followUp.id)"
                :aria-label="`重新整理 ${formatTime(followUp.created_time)} 的${recordLabel}`"
                title="重新整理"
                @click.stop="handleProcess(followUp)"
              >
                <Loader2 v-if="isRetrying(followUp.id)" class="process-icon effectiveness-icon-loading" />
                <RefreshCw v-else class="process-icon" />
              </Button>
              <Button
                v-if="canDelete(followUp)"
                variant="ghost"
                size="icon-sm"
                class="delete-btn"
                :aria-label="`删除 ${formatTime(followUp.created_time)} 的${recordLabel}`"
                title="删除"
                @click.stop="handleDelete(followUp)"
              >
                <Trash2 class="delete-icon" />
              </Button>
            </div>
          </div>

          <div v-if="followUp.activity_category === 'MEETING'" class="meeting-detail">
            <div v-for="section in getMeetingSections(followUp)" :key="section.label" class="meeting-section">
              <span class="meeting-section-label">{{ section.label }}</span>
              <span class="meeting-section-value">{{ section.value }}</span>
            </div>
          </div>

          <div
            v-if="isProcessing(followUp)"
            class="processing-status"
            data-activity-processing-status="pending"
          >
            <Loader2 class="processing-spinner" aria-hidden="true" />
            <span>AI 正在整理与评分…</span>
          </div>
          <div
            v-else-if="isFailed(followUp)"
            class="processing-error-row"
            data-activity-processing-status="failed"
          >
            <span class="processing-error">
              {{ followUp.processing_status === 'FAILED' ? '整理失败，已保留原文' : 'AI 评分失败，可重新整理' }}
            </span>
            <Button
              v-if="canProcess(followUp)"
              type="button"
              variant="ghost"
              size="sm"
              class="processing-retry-btn"
              :disabled="isRetrying(followUp.id)"
              data-activity-retry-btn
              @click.stop="handleProcess(followUp)"
            >
              <Loader2 v-if="isRetrying(followUp.id)" class="processing-spinner" aria-hidden="true" />
              <RefreshCw v-else class="processing-retry-icon" aria-hidden="true" />
              <span>{{ isRetrying(followUp.id) ? '正在重新整理…' : '重新整理' }}</span>
            </Button>
          </div>

          <HoverInfo side="bottom" align="start" content-class="follow-up-meta-hover-card">
            <template #trigger>
              <div class="follow-up-meta" tabindex="0">
                <span class="meta-item">
                  <User class="meta-icon" />
                  {{ getCreatorName(followUp) }}
                </span>
                <span class="meta-separator">·</span>
                <span>{{ followUp.method }}</span>
                <span class="meta-separator">·</span>
                <span>{{ formatTime(followUp.created_time) }}</span>
                <template v-if="hasText(followUp.next_follow_time)">
                  <span class="meta-separator">·</span>
                  <span class="meta-item">
                    <CalendarClock class="meta-icon" />
                    {{ formatShortDate(followUp.next_follow_time) }}
                  </span>
                </template>
                <template v-if="hasText(followUp.next_action)">
                  <span class="meta-separator">·</span>
                  <span class="meta-next-action">{{ followUp.next_action }}</span>
                </template>
              </div>
            </template>
            <div class="follow-up-meta-card">
              <div v-for="item in getMetaRows(followUp)" :key="item.label" class="follow-up-meta-card-row">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>
          </HoverInfo>
        </div>
      </div>
    </div>
    </DataViewStatePanel>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Component, ComponentPublicInstance } from 'vue'
import { CalendarClock, ChevronDown, ChevronUp, Loader2, Mail, MessageCircle, MessageSquare, Phone, RefreshCw, ThumbsDown, ThumbsUp, Trash2, User, Users } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { DataViewStatePanel, HoverInfo, type DataViewState } from '@/components/crmwolf'
import { confirmDialog } from '@/utils/confirmDialog'
import ActivityMarkdownContent from '@/components/ActivityMarkdownContent.vue'

interface FollowUp {
  id: number
  lead_id?: string
  customer_id?: string | null
  original_lead_id?: string | null
  activity_kind?: string
  activity_category?: string
  activity_label?: string
  title?: string | null
  source_content?: string
  content_json?: Record<string, unknown> | null
  summary?: string | null
  processing_status?: string | null
  processing_error?: string | null
  processed_at?: string | null
  content: string
  method: string
  next_follow_time?: string | null
  next_action?: string | null
  creator_id: string
  creator_info?: { id: string; name: string; avatar_url?: string | null }
  customer_info?: { id: string; account_name: string }
  created_time: string
  effectiveness_score?: number | null
  effectiveness_is_valid?: boolean | null
  effectiveness_reason?: string | null
  effectiveness_detail_json?: string | null
  effectiveness_status?: string | null
  effectiveness_evaluated_time?: string | null
  effectiveness_error_message?: string | null
}

interface Props {
  followUps: FollowUp[]
  loading: boolean
  currentUserId?: string
  recordLabel?: string
  allowProcess?: boolean
  renderMarkdown?: boolean
  retryingIds?: number[]
}

interface Emits {
  delete: [followUp: FollowUp]
  process: [followUp: FollowUp]
}

const props = withDefaults(defineProps<Props>(), {
  currentUserId: '',
  recordLabel: '跟进记录',
  allowProcess: false,
  renderMarkdown: false,
  retryingIds: () => []
})
const emit = defineEmits<Emits>()
const recordLabel = props.recordLabel
const viewState = computed<DataViewState>(() => {
  if (props.followUps.length > 0) return 'ready'
  return props.loading ? 'loading' : 'empty'
})
const expandedContentIds = ref<Set<number>>(new Set())
const overflowingContentIds = ref<Set<number>>(new Set())
const contentElements = new Map<number, HTMLElement>()
let resizeObserver: ResizeObserver | null = null
let measureFrame: number | null = null

const queueMeasureContentOverflow = (): void => {
  if (typeof window === 'undefined') return
  if (measureFrame !== null) window.cancelAnimationFrame(measureFrame)
  measureFrame = window.requestAnimationFrame(() => {
    measureFrame = null
    measureContentOverflow()
  })
}

const setContentElement = (id: number, el: Element | ComponentPublicInstance | null): void => {
  const existing = contentElements.get(id)
  const element = el instanceof HTMLElement ? el : null

  if (existing !== undefined && existing !== element) {
    resizeObserver?.unobserve(existing)
    contentElements.delete(id)
  }

  if (element !== null) {
    contentElements.set(id, element)
    resizeObserver?.observe(element)
  }

  queueMeasureContentOverflow()
}

const measureContentOverflow = (): void => {
  const visibleIds = new Set(props.followUps.map((followUp) => followUp.id))
  const nextOverflowingIds = new Set<number>()

  for (const id of visibleIds) {
    const element = contentElements.get(id)
    if (element === undefined) continue

    const styles = window.getComputedStyle(element)
    const parsedLineHeight = Number.parseFloat(styles.lineHeight)
    const parsedFontSize = Number.parseFloat(styles.fontSize)
    const lineHeight = Number.isFinite(parsedLineHeight)
      ? parsedLineHeight
      : (Number.isFinite(parsedFontSize) ? parsedFontSize * 1.5 : 20)
    const twoLineHeight = lineHeight * 2

    if (element.scrollHeight > twoLineHeight + 1) {
      nextOverflowingIds.add(id)
    }
  }

  overflowingContentIds.value = nextOverflowingIds
  expandedContentIds.value = new Set([...expandedContentIds.value].filter((id) => visibleIds.has(id)))
}

const hasContentOverflow = (id: number): boolean => overflowingContentIds.value.has(id)

const isContentExpanded = (id: number): boolean => expandedContentIds.value.has(id)

const toggleContentExpanded = (id: number): void => {
  const nextIds = new Set(expandedContentIds.value)
  if (nextIds.has(id)) {
    nextIds.delete(id)
  } else {
    nextIds.add(id)
  }
  expandedContentIds.value = nextIds
  void nextTick(queueMeasureContentOverflow)
}

watch(
  () => props.followUps.map((followUp) => [
    followUp.id,
    followUp.content,
    followUp.summary,
    followUp.source_content,
    JSON.stringify(followUp.content_json ?? {})
  ].join(':')).join('|'),
  () => {
    void nextTick(queueMeasureContentOverflow)
  },
  { flush: 'post' }
)

onMounted(() => {
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(queueMeasureContentOverflow)
    for (const element of contentElements.values()) {
      resizeObserver.observe(element)
    }
  }
  queueMeasureContentOverflow()
})

onBeforeUnmount(() => {
  if (measureFrame !== null) window.cancelAnimationFrame(measureFrame)
  resizeObserver?.disconnect()
})

const canDelete = (followUp: FollowUp): boolean => {
  const creatorIdStr = String(followUp.creator_id ?? '')
  const currentUserIdStr = String(props.currentUserId ?? '')

  return props.currentUserId !== undefined && props.currentUserId !== '' && creatorIdStr === currentUserIdStr
}

const isProcessing = (followUp: FollowUp): boolean => {
  return followUp.processing_status === 'PENDING' || followUp.processing_status === 'PROCESSING'
}

const isFailed = (followUp: FollowUp): boolean => {
  return followUp.processing_status === 'FAILED' || followUp.effectiveness_status === 'FAILED'
}

const isRetrying = (id: number): boolean => {
  return props.retryingIds.includes(id)
}

const canProcess = (followUp: FollowUp): boolean => {
  return props.allowProcess === true &&
    followUp.customer_id !== undefined &&
    followUp.customer_id !== null &&
    isFailed(followUp)
}

const handleDelete = async (followUp: FollowUp): Promise<void> => {
  const method = getText(followUp.method) || '该条活动'
  const content = getPrimaryContent(followUp).trim()
  const summary = content.length > 0 ? `“${content.slice(0, 40)}${content.length > 40 ? '…' : ''}”` : method
  const confirmed = await confirmDialog(
    `确定删除${recordLabel}吗？${method}，${summary}。删除后无法恢复。`,
    `删除${recordLabel}`,
    { variant: 'destructive', confirmText: '删除' },
  )
  if (confirmed) {
    emit('delete', followUp)
  }
}

const handleProcess = (followUp: FollowUp): void => {
  if (isRetrying(followUp.id)) return
  emit('process', followUp)
}

const getMethodIcon = (followUp: FollowUp): Component => {
  const iconKey = getText(followUp.activity_kind) ||
    getText(followUp.activity_label) ||
    getText(followUp.method)
  const methodMap: Record<string, Component> = {
    PHONE_FOLLOW_UP: Phone,
    WECHAT_FOLLOW_UP: MessageCircle,
    EMAIL_FOLLOW_UP: Mail,
    VISIT_FOLLOW_UP: Users,
    ONLINE_MEETING: Users,
    OFFLINE_MEETING: Users,
    OTHER_FOLLOW_UP: MessageSquare,
    电话: Phone,
    电话跟进: Phone,
    微信: MessageCircle,
    微信跟进: MessageCircle,
    邮件: Mail,
    邮件跟进: Mail,
    拜访: Users,
    拜访跟进: Users,
    面谈: Users,
    会议: Users,
    线上会议: Users,
    线下会议: Users
  }

  return methodMap[iconKey] ?? MessageSquare
}

const getText = (value: unknown): string => {
  return typeof value === 'string' ? value.trim() : ''
}

const isGenericActivityTitle = (followUp: FollowUp, value: string): boolean => {
  return value === followUp.method ||
    value === followUp.activity_label ||
    value === followUp.activity_kind
}

const getStructuredPrimaryContent = (followUp: FollowUp): string => {
  const content = followUp.content_json
  if (content === undefined || content === null) return ''

  if (followUp.activity_category === 'MEETING') {
    const subject = getText(content['meeting_subject'])
    const minutes = asStringList(content['key_minutes'])
    const firstMinute = minutes[0] ?? ''
    if (subject !== '' && firstMinute !== '') return `${subject}：${firstMinute}`
    if (firstMinute !== '') return firstMinute
    return subject
  }

  const primaryContent = getText(content['content'])
  if (primaryContent !== '') return primaryContent

  return uniqueTextParts([
    getText(content['customer_feedback']),
    getText(content['current_progress']),
    ...asStringList(content['risks'])
  ]).join('；')
}

const getPrimaryContent = (followUp: FollowUp): string => {
  if (props.renderMarkdown && followUp.activity_category === 'MEETING') {
    const summary = getText(followUp.summary)
    if (summary !== '') return summary
  }

  const structuredContent = getStructuredPrimaryContent(followUp)
  if (structuredContent !== '') return structuredContent

  const summary = getText(followUp.summary)
  if (summary !== '') return summary

  const sourceContent = getText(followUp.source_content)
  if (sourceContent !== '') return sourceContent

  const legacyContent = getText(followUp.content)
  if (legacyContent !== '' && !isGenericActivityTitle(followUp, legacyContent)) return legacyContent

  const title = getText(followUp.title)
  if (title !== '' && !isGenericActivityTitle(followUp, title)) return title

  return legacyContent !== '' ? legacyContent : title
}

const asStringList = (value: unknown): string[] => {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => {
      if (typeof item === 'string') return item
      if (item !== null && typeof item === 'object') {
        return Object.values(item as Record<string, unknown>)
          .map((part) => getText(part))
          .filter((part) => part !== '')
          .join('：')
      }
      return ''
    })
    .filter((item) => item.trim() !== '')
}

const uniqueTextParts = (parts: string[]): string[] => {
  const result: string[] = []
  for (const part of parts.map((item) => item.trim()).filter(Boolean)) {
    if (result.some((existing) => existing.includes(part) || part.includes(existing))) continue
    result.push(part)
  }
  return result
}

const getMeetingSections = (followUp: FollowUp): { label: string; value: string }[] => {
  const content = followUp.content_json ?? {}
  const sections: { label: string; value: string }[] = []
  const participants = content['participants']
  if (participants !== null && participants !== undefined && typeof participants === 'object') {
    const p = participants as Record<string, unknown>
    const internal = asStringList(p['internal']).join('、')
    const customer = asStringList(p['customer']).join('、')
    const value = [
      internal !== '' ? `我方：${internal}` : '',
      customer !== '' ? `客户方：${customer}` : ''
    ].filter((item) => item !== '').join('；')
    if (value !== '') sections.push({ label: '参会', value })
  }
  const minutes = asStringList(content['key_minutes']).slice(0, 3).join('；')
  if (minutes !== '') sections.push({ label: '纪要', value: minutes })
  const risks = asStringList(content['risks']).slice(0, 2).join('；')
  if (risks !== '') sections.push({ label: '风险', value: risks })
  const actions = asStringList(content['action_items']).slice(0, 2).join('；')
  if (actions !== '') sections.push({ label: '行动', value: actions })
  return sections
}

const hasText = (value: string | null | undefined): value is string => {
  return value !== undefined && value !== null && value.trim() !== ''
}

const shouldShowEffectiveness = (followUp: FollowUp): boolean => {
  return followUp.effectiveness_status === 'GENERATING' ||
    followUp.effectiveness_status === 'COMPLETED'
}

const getEffectivenessClass = (followUp: FollowUp): string => {
  if (followUp.effectiveness_status === 'GENERATING') return 'is-loading'
  return followUp.effectiveness_is_valid === true ? 'is-valid' : 'is-invalid'
}

const getEffectivenessLabel = (followUp: FollowUp): string => {
  if (followUp.effectiveness_status === 'GENERATING') return `正在评估${recordLabel}有效性`
  return followUp.effectiveness_is_valid === true ? `有效${recordLabel}` : `无效${recordLabel}`
}

const getEffectivenessTooltip = (followUp: FollowUp): string => {
  if (followUp.effectiveness_status === 'GENERATING') return `正在评估${recordLabel}有效性`

  const scoreText = typeof followUp.effectiveness_score === 'number'
    ? `${followUp.effectiveness_score} 分`
    : '未评分'

  if (followUp.effectiveness_is_valid === true) {
    return `有效${recordLabel}：${scoreText}`
  }

  return hasText(followUp.effectiveness_reason)
    ? followUp.effectiveness_reason
    : `无效${recordLabel}：${scoreText}`
}

const getCreatorName = (followUp: FollowUp): string => {
  const name = followUp.creator_info?.name
  return hasText(name) ? name : '系统'
}

const formatTime = (dateStr: string): string => {
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))

  if (days === 0) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  } else if (days === 1) {
    return '昨天 ' + date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  } else if (days < 7) {
    return date.toLocaleDateString('zh-CN', { weekday: 'short', hour: '2-digit', minute: '2-digit' })
  } else {
    return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  }
}

const formatShortDate = (dateStr: string): string => {
  if (!hasText(dateStr)) return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

const getMetaRows = (followUp: FollowUp): { label: string; value: string }[] => {
  const meta = [
    { label: '跟进人', value: getCreatorName(followUp) },
    { label: '类型', value: followUp.method },
    { label: '时间', value: formatTime(followUp.created_time) }
  ]

  if (hasText(followUp.next_follow_time)) {
    meta.push({ label: '下次跟进', value: formatShortDate(followUp.next_follow_time) })
  }
  if (hasText(followUp.next_action)) {
    meta.push({ label: '下一步', value: followUp.next_action })
  }

  return meta
}
</script>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.follow-up-list-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: transparent;
}

.follow-up-list {
  display: flex;
  flex-direction: column;
}

.follow-up-item {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  gap: $space-2;
  min-height: var(--touch-target);
  padding: $space-2 $space-4;
  border-bottom: 1px solid hsl(var(--border));
  transition: background 150ms ease;

  &:hover {
    background: var(--wash-hover);
  }

  &:last-child {
    border-bottom: none;
  }
}

.follow-up-method {
  width: 28px;
  height: 28px;
  margin-top: 1px;
  border-radius: var(--radius-sm);
  background: hsl(var(--muted));
  color: hsl(var(--muted-foreground));
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: help;
}

.method-icon {
  width: 15px;
  height: 15px;
}

.follow-up-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: $space-1;
}

.follow-up-content-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: start;
  gap: $space-2;
  min-width: 0;
}

.follow-up-content-cell {
  position: relative;
  min-width: 0;
}

.follow-up-content {
  margin: 0;
  color: hsl(var(--foreground));
  font-size: var(--font-size-body);
  line-height: 20px;
  font-weight: 500;
  overflow: hidden;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  cursor: help;
}

.follow-up-content-cell.is-expandable .follow-up-content {
  padding-right: 28px;
}

.follow-up-content--expanded {
  display: block;
  overflow: visible;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  -webkit-line-clamp: unset;
  line-clamp: unset;
}

.content-expand-btn {
  position: absolute;
  right: 0;
  bottom: -2px;
  width: 24px !important;
  height: 24px !important;
  min-width: 24px !important;
  padding: 0 !important;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--card)) !important;
  border: 1px solid hsl(var(--border));
  opacity: 0;
  transition: opacity 150ms ease, background 150ms ease, color 150ms ease;

  &:hover {
    color: hsl(var(--muted-foreground));
    background: var(--wash-hover) !important;
  }
}

.content-expand-icon {
  width: 14px;
  height: 14px;
}

.follow-up-item:hover .content-expand-btn,
.content-expand-btn:focus-visible,
.follow-up-content-cell.is-expanded .content-expand-btn {
  opacity: 1;
}

:global(.follow-up-method-hover-card) {
  width: auto;
  min-width: 56px;
  padding: $space-1 $space-2;
}

:global(.follow-up-content-hover-card) {
  width: 320px;
  max-width: min(320px, calc(100vw - 32px));
  padding: $space-2 $space-3;
}

:global(.follow-up-meta-hover-card) {
  width: 280px;
  padding: $space-2 $space-3;
}

.follow-up-hover-text {
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-caption);
  line-height: 18px;
}

.follow-up-hover-text--preline {
  white-space: pre-wrap;
}

.follow-up-meta-card {
  display: grid;
  gap: $space-1;
  font-size: var(--font-size-caption);
  line-height: 18px;
}

.follow-up-meta-card-row {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: $space-2;
  color: hsl(var(--muted-foreground));

  strong {
    min-width: 0;
    color: hsl(var(--muted-foreground));
    font-weight: 500;
    overflow-wrap: anywhere;
  }
}

.meeting-detail {
  display: grid;
  gap: $space-1;
  padding: $space-1 0;
}

.meeting-section {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr);
  gap: $space-1;
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-caption);
  line-height: 18px;
}

.meeting-section-label {
  color: hsl(var(--muted-foreground));
}

.meeting-section-value {
  min-width: 0;
  overflow: hidden;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
}

.processing-error {
  color: hsl(var(--status-danger));
  font-size: var(--font-size-caption);
  line-height: 18px;
}

.follow-up-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  min-width: 24px;
  margin-top: -4px;
}

.effectiveness-indicator {
  width: var(--touch-target);
  height: var(--touch-target);
  min-width: var(--touch-target);
  min-height: var(--touch-target);
  padding: 0;
  border: none;
  border-radius: var(--radius-sm);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  cursor: help;
}

.effectiveness-indicator-visual {
  width: 24px;
  height: 24px;
  border-radius: var(--radius-sm);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.effectiveness-indicator-visual.is-valid {
  color: hsl(var(--status-success));
}

.effectiveness-indicator-visual.is-invalid {
  color: hsl(var(--status-danger));
  background: color-mix(in srgb, hsl(var(--status-danger)) var(--status-bg-mix), transparent);
}

.effectiveness-indicator-visual.is-loading {
  color: hsl(var(--muted-foreground));
}

.effectiveness-icon {
  width: 14px;
  height: 14px;
}

.effectiveness-icon-loading {
  animation: spin 1s linear infinite;
}

:global(.effectiveness-hover-card) {
  width: 280px;
  padding: $space-2 $space-3;
}

.effectiveness-card {
  font-size: var(--font-size-caption);
  line-height: 18px;
}

.effectiveness-card-title {
  color: hsl(var(--foreground));
  font-weight: 600;
}

.effectiveness-card-score {
  margin-top: 2px;
  color: hsl(var(--muted-foreground));
  font-variant-numeric: tabular-nums;
}

.effectiveness-card-text {
  margin-top: $space-1;
  color: hsl(var(--muted-foreground));
  white-space: pre-wrap;
}

.follow-up-meta {
  display: flex;
  align-items: center;
  gap: $space-1;
  min-width: 0;
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-caption);
  line-height: 16px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  min-width: 0;
}

.meta-icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}

.meta-separator {
  color: hsl(var(--muted-foreground));
}

.meta-next-action {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.delete-btn,
.process-btn {
  width: 24px !important;
  height: 24px !important;
  padding: 0 !important;
  min-width: 24px !important;
  opacity: 0;
  transition: opacity 0.2s;
}

.delete-btn:hover {
  background: color-mix(in srgb, hsl(var(--status-danger)) var(--status-bg-mix), transparent) !important;
}

.process-btn:hover {
  background: var(--wash-hover) !important;
}

.delete-icon {
  width: 14px;
  height: 14px;
  color: hsl(var(--status-danger));
}

.process-icon {
  width: 14px;
  height: 14px;
  color: hsl(var(--muted-foreground));
}

.follow-up-item:hover .delete-btn,
.follow-up-item:hover .process-btn,
.delete-btn:focus-visible,
.process-btn:focus-visible {
  opacity: 1;
}

@media (hover: none) {
  .content-expand-btn,
  .delete-btn,
  .process-btn {
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .follow-up-item,
  .content-expand-btn,
  .delete-btn,
  .effectiveness-icon-loading {
    transition-duration: 0.01ms;
    animation-duration: 0.01ms;
  }
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

.follow-up-content-cell--markdown {
  display: block;
}

.processing-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  font-size: var(--font-size-caption);
  color: hsl(var(--muted-foreground));
}

.processing-spinner {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  animation: spin 1s linear infinite;
}

.processing-error-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
}

.processing-retry-btn {
  height: 24px !important;
  padding: 0 8px !important;
  font-size: var(--font-size-caption) !important;
  color: hsl(var(--primary)) !important;
  gap: 4px;
}

.processing-retry-icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}
</style>
