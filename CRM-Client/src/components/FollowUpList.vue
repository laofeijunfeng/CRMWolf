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
        <div class="follow-up-method" :title="followUp.method" aria-hidden="true">
          <component :is="getMethodIcon(followUp.method)" class="method-icon" />
        </div>

        <div class="follow-up-body">
          <div class="follow-up-content-row">
            <p class="follow-up-content" :title="followUp.content">
              {{ followUp.content }}
            </p>
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

          <div class="follow-up-meta" :title="getMetaTitle(followUp)">
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
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue'
import { CalendarClock, Mail, MessageCircle, MessageSquare, Phone, Trash2, User, Users } from 'lucide-vue-next'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
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
}

interface Props {
  followUps: FollowUp[]
  loading: boolean
  currentUserId?: string
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

const getMetaTitle = (followUp: FollowUp): string => {
  const meta = [
    `跟进人：${getCreatorName(followUp)}`,
    `方式：${followUp.method}`,
    `时间：${formatTime(followUp.created_time)}`
  ]

  if (hasText(followUp.next_follow_time)) {
    meta.push(`下次跟进：${formatShortDate(followUp.next_follow_time)}`)
  }
  if (hasText(followUp.next_action)) {
    meta.push(`下一步：${followUp.next_action}`)
  }

  return meta.join('，')
}
</script>

<style scoped lang="scss">
@import '@/styles/variables-v2.scss';

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
  margin-top: -4px;
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
  .delete-btn {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>
