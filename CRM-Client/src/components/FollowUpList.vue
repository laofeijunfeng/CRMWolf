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
          <EmptyTitle>暂无跟进记录</EmptyTitle>
          <EmptyDescription>
            点击上方按钮添加新的跟进记录
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
              <component :is="getMethodIcon(followUp.method)" class="method-icon" />
            </div>
          </template>
          <div class="follow-up-hover-text">{{ followUp.method }}</div>
        </HoverInfo>

        <div class="follow-up-body">
          <div class="follow-up-content-row">
            <HoverInfo side="top" align="start" content-class="follow-up-content-hover-card">
              <template #trigger>
                <p class="follow-up-content">
                  {{ followUp.content }}
                </p>
              </template>
              <div class="follow-up-hover-text follow-up-hover-text--preline">
                {{ followUp.content }}
              </div>
            </HoverInfo>
            <div
              v-if="shouldShowEffectiveness(followUp) || canDelete(followUp)"
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
                v-if="canDelete(followUp)"
                variant="ghost"
                size="icon-sm"
                class="delete-btn"
                :aria-label="`删除 ${formatTime(followUp.created_time)} 的跟进记录`"
                title="删除"
                @click.stop="handleDelete(followUp)"
              >
                <Trash2 class="delete-icon" />
              </Button>
            </div>
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
import type { Component } from 'vue'
import { CalendarClock, Loader2, Mail, MessageCircle, MessageSquare, Phone, ThumbsDown, ThumbsUp, Trash2, User, Users } from 'lucide-vue-next'
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
  lead_id?: number
  customer_id?: number | null
  original_lead_id?: number | null
  content: string
  method: string
  next_follow_time?: string | null
  next_action?: string | null
  creator_id: string
  creator_info?: { id: string; name: string; avatar_url?: string | null }
  customer_info?: { id: number; account_name: string }
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
  currentUserId?: string | undefined
}

type Emits = (e: 'delete', followUp: FollowUp) => void

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const canDelete = (followUp: FollowUp): boolean => {
  const creatorIdStr = String(followUp.creator_id ?? '')
  const currentUserIdStr = String(props.currentUserId ?? '')

  return props.currentUserId !== undefined && props.currentUserId !== '' && creatorIdStr === currentUserIdStr
}

const handleDelete = async (followUp: FollowUp): Promise<void> => {
  const confirmed = await confirmDelete('这条跟进记录')
  if (confirmed) {
    emit('delete', followUp)
  }
}

const getMethodIcon = (method: string): Component => {
  const methodMap: Record<string, Component> = {
    电话: Phone,
    微信: MessageCircle,
    邮件: Mail,
    拜访: Users,
    面谈: Users,
    会议: Users
  }

  return methodMap[method] ?? MessageSquare
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
  if (followUp.effectiveness_status === 'GENERATING') return '正在评估跟进有效性'
  return followUp.effectiveness_is_valid === true ? '有效跟进记录' : '无效跟进记录'
}

const getEffectivenessTooltip = (followUp: FollowUp): string => {
  if (followUp.effectiveness_status === 'GENERATING') return '正在评估跟进有效性'

  const scoreText = typeof followUp.effectiveness_score === 'number'
    ? `${followUp.effectiveness_score} 分`
    : '未评分'

  if (followUp.effectiveness_is_valid === true) {
    return `有效跟进：${scoreText}`
  }

  return hasText(followUp.effectiveness_reason)
    ? followUp.effectiveness_reason
    : `无效跟进：${scoreText}`
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
    { label: '方式', value: followUp.method },
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

.delete-btn {
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

.delete-icon {
  width: 14px;
  height: 14px;
  color: $wolf-danger-v2;
}

.follow-up-item:hover .delete-btn,
.delete-btn:focus-visible {
  opacity: 1;
}

@media (hover: none) {
  .delete-btn {
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .follow-up-item,
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
