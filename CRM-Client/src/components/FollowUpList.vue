<template>
  <div class="follow-up-list-container">
    <!-- Loading Skeleton -->
    <div v-if="loading && followUps.length === 0" class="follow-up-skeleton">
      <div class="skeleton-wrapper">
        <Skeleton class="skeleton-line skeleton-line-1" />
        <Skeleton class="skeleton-line skeleton-line-2" />
        <Skeleton class="skeleton-line skeleton-line-3" />
      </div>
    </div>

    <!-- Empty State -->
    <div v-else-if="followUps.length === 0" class="follow-up-empty">
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <MessageSquare class="empty-icon" />
          </EmptyMedia>
          <EmptyTitle>暂无{{ recordLabel }}</EmptyTitle>
          <EmptyDescription>
            点击上方按钮添加新的{{ recordLabel }}
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    </div>

    <!-- Follow-up List -->
    <div v-else class="follow-up-list">
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
              >
                <template #trigger>
                  <button
                    type="button"
                    class="effectiveness-indicator"
                    :class="getEffectivenessClass(followUp)"
                    :aria-label="getEffectivenessLabel(followUp)"
                    @click.stop
                  >
                    <Loader2
                      v-if="followUp.effectiveness_status === 'GENERATING'"
                      class="effectiveness-icon effectiveness-icon-loading"
                    />
                    <ThumbsUp
                      v-else-if="followUp.effectiveness_is_valid"
                      class="effectiveness-icon"
                    />
                    <ThumbsDown
                      v-else
                      class="effectiveness-icon"
                    />
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
                :aria-label="`重新整理 ${formatTime(followUp.created_time)} 的${recordLabel}`"
                title="重新整理"
                @click.stop="handleProcess(followUp)"
              >
                <RefreshCw class="process-icon" />
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

          <div v-if="followUp.processing_status === 'FAILED'" class="processing-error">
            整理失败，已保留原文
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
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Component, ComponentPublicInstance } from 'vue'
import { CalendarClock, ChevronDown, ChevronUp, Loader2, Mail, MessageCircle, MessageSquare, Phone, RefreshCw, ThumbsDown, ThumbsUp, Trash2, User, Users } from 'lucide-vue-next'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { HoverInfo } from '@/components/crmwolf'
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription,
} from '@/components/ui/empty'
import { confirmDelete } from '@/utils/confirmDialog'

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
}

interface Emits {
  delete: [followUp: FollowUp]
  process: [followUp: FollowUp]
}

const props = withDefaults(defineProps<Props>(), {
  currentUserId: '',
  recordLabel: '跟进记录',
  allowProcess: false
})
const emit = defineEmits<Emits>()
const recordLabel = props.recordLabel
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

const canProcess = (followUp: FollowUp): boolean => {
  return props.allowProcess === true &&
    followUp.customer_id !== undefined &&
    followUp.customer_id !== null &&
    (followUp.processing_status === 'FAILED' || followUp.processing_status === 'PENDING')
}

const handleDelete = async (followUp: FollowUp): Promise<void> => {
  const confirmed = await confirmDelete(`这条${recordLabel}`)
  if (confirmed) {
    emit('delete', followUp)
  }
}

const handleProcess = (followUp: FollowUp): void => {
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
@use '@/styles/variables-v2.scss' as *;

.follow-up-list-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: transparent;
}

.follow-up-skeleton {
  padding: $wolf-space-lg-v2;
}

.skeleton-wrapper {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm-v2;
}

.skeleton-line {
  height: 16px;
}

.skeleton-line-1 {
  width: 60%;
}

.skeleton-line-2 {
  width: 80%;
}

.skeleton-line-3 {
  width: 40%;
}

.follow-up-empty {
  padding: $wolf-space-2xl-v2 0;
  text-align: center;
}

.empty-icon {
  width: 24px;
  height: 24px;
  opacity: 0.5;
}

.follow-up-list {
  display: flex;
  flex-direction: column;
}

.follow-up-item {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  gap: $wolf-space-sm-v2;
  min-height: $wolf-touch-target-min-v2;
  padding: $wolf-space-sm-v2 $wolf-space-lg-v2;
  border-bottom: 1px solid $wolf-border-light-v2;
  transition: background 150ms ease;

  &:hover {
    background: $wolf-bg-hover-v2;
  }

  &:last-child {
    border-bottom: none;
  }
}

.follow-up-method {
  width: 28px;
  height: 28px;
  margin-top: 1px;
  border-radius: $wolf-radius-sm-v2;
  background: $wolf-bg-muted-v2;
  color: $wolf-text-secondary-v2;
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
  gap: $wolf-space-xs-v2;
}

.follow-up-content-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: start;
  gap: $wolf-space-sm-v2;
  min-width: 0;
}

.follow-up-content-cell {
  position: relative;
  min-width: 0;
}

.follow-up-content {
  margin: 0;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  line-height: $wolf-line-height-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
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
  color: $wolf-text-tertiary-v2;
  background: $wolf-bg-card-v2 !important;
  border: 1px solid $wolf-border-light-v2;
  opacity: 0;
  transition: opacity 150ms ease, background 150ms ease, color 150ms ease;

  &:hover {
    color: $wolf-text-secondary-v2;
    background: $wolf-bg-muted-v2 !important;
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
  padding: $wolf-space-xs-v2 $wolf-space-sm-v2;
}

:global(.follow-up-content-hover-card) {
  width: 320px;
  max-width: min(320px, calc(100vw - 32px));
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
}

:global(.follow-up-meta-hover-card) {
  width: 280px;
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
}

.follow-up-hover-text {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: 18px;
}

.follow-up-hover-text--preline {
  white-space: pre-wrap;
}

.follow-up-meta-card {
  display: grid;
  gap: $wolf-space-xs-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: 18px;
}

.follow-up-meta-card-row {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: $wolf-space-sm-v2;
  color: $wolf-text-tertiary-v2;

  strong {
    min-width: 0;
    color: $wolf-text-secondary-v2;
    font-weight: $wolf-font-weight-medium-v2;
    overflow-wrap: anywhere;
  }
}

.meeting-detail {
  display: grid;
  gap: $wolf-space-xs-v2;
  padding: $wolf-space-xs-v2 0;
}

.meeting-section {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr);
  gap: $wolf-space-xs-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: 18px;
}

.meeting-section-label {
  color: $wolf-text-tertiary-v2;
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
  color: $wolf-danger-v2;
  font-size: $wolf-font-size-caption-v2;
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
  border: none;
  padding: 0;
  width: 24px;
  height: 24px;
  border-radius: $wolf-radius-sm-v2;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: $wolf-text-tertiary-v2;
  background: transparent;
  cursor: help;
}

.effectiveness-indicator.is-valid {
  color: $wolf-success-v2;
}

.effectiveness-indicator.is-invalid {
  color: $wolf-danger-v2;
  background: $wolf-danger-bg-v2;
}

.effectiveness-indicator.is-loading {
  color: $wolf-text-tertiary-v2;
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
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
}

.effectiveness-card {
  font-size: $wolf-font-size-caption-v2;
  line-height: 18px;
}

.effectiveness-card-title {
  color: $wolf-text-primary-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.effectiveness-card-score {
  margin-top: 2px;
  color: $wolf-text-secondary-v2;
  font-variant-numeric: tabular-nums;
}

.effectiveness-card-text {
  margin-top: $wolf-space-xs-v2;
  color: $wolf-text-secondary-v2;
  white-space: pre-wrap;
}

.follow-up-meta {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
  min-width: 0;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
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
  color: $wolf-disabled-text-v2;
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
  background: $wolf-danger-bg-v2 !important;
}

.process-btn:hover {
  background: $wolf-bg-muted-v2 !important;
}

.delete-icon {
  width: 14px;
  height: 14px;
  color: $wolf-danger-v2;
}

.process-icon {
  width: 14px;
  height: 14px;
  color: $wolf-text-tertiary-v2;
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
    transition-duration: $wolf-reduced-motion-duration-v2;
    animation-duration: $wolf-reduced-motion-duration-v2;
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
</style>
