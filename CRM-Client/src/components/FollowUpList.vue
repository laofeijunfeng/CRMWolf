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
        v-for="(followUp, index) in followUps"
        :key="followUp.id"
        class="follow-up-item"
        :class="{ 'is-last': index === followUps.length - 1 }"
      >
        <!-- Left vertical line -->
        <div class="follow-up-item-tail" />
        <!-- Left dot -->
        <div class="follow-up-item-dot">
          <MessageSquare class="dot-icon" />
        </div>

        <!-- Content card -->
        <div class="follow-up-item-content">
          <div class="follow-up-card">
            <!-- Time and delete button -->
            <div class="follow-up-header">
              <span class="follow-up-time">{{ formatTime(followUp.created_time) }}</span>
              <Button
                v-if="canDelete(followUp)"
                variant="ghost"
                size="icon-sm"
                class="delete-btn"
                @click.stop="handleDelete(followUp)"
              >
                <Trash2 class="delete-icon" />
              </Button>
            </div>

            <!-- Follow-up details -->
            <div class="follow-up-details">
              <div class="follow-up-tags">
                <span class="meta-tag type-tag">跟进记录</span>
                <span class="meta-tag operator-tag">
                  <User class="tag-icon" />
                  <span>{{ followUp.creator_info?.name || '系统' }}</span>
                </span>
                <span class="meta-tag method-tag">
                  <Phone class="tag-icon" />
                  <span>{{ followUp.method }}</span>
                </span>
              </div>

              <div class="follow-up-main">
                <span class="content-value">{{ followUp.content }}</span>
              </div>

              <div v-if="followUp.next_follow_time || followUp.next_action" class="follow-up-plan">
                <div v-if="followUp.next_follow_time" class="plan-item">
                  <span class="plan-label">下次跟进</span>
                  <span class="plan-value">{{ formatDate(followUp.next_follow_time) }}</span>
                </div>
                <div v-if="followUp.next_action" class="plan-item plan-action">
                  <span class="plan-label">下一步动作</span>
                  <span class="plan-value">{{ followUp.next_action }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { MessageSquare, User, Phone, Trash2 } from 'lucide-vue-next'
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

const formatDate = (dateStr: string): string => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
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
  position: relative;
  padding-left: $wolf-space-lg-v2;
}

.follow-up-item {
  position: relative;
  padding-bottom: $wolf-space-xl-v2;
  padding-left: $wolf-space-xl-v2;
}

/* Left vertical line */
.follow-up-item-tail {
  position: absolute;
  left: 0;
  top: 12px;
  height: calc(100% - 12px);
  width: 2px;
  background: $wolf-border-default-v2;
}

.follow-up-item.is-last .follow-up-item-tail {
  display: none;
}

/* Left dot */
.follow-up-item-dot {
  position: absolute;
  left: -6px;
  top: 0;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: $wolf-bg-card-v2;
  border: 2px solid $wolf-primary-v2;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
}

.dot-icon {
  width: 10px;
  height: 10px;
  color: $wolf-primary-v2;
}

/* Content card */
.follow-up-item-content {
  background: $wolf-bg-muted-v2;
  border-radius: $wolf-radius-v2;
  padding: $wolf-space-md-v2;
  transition: $wolf-transition-v2;
}

.follow-up-item-content:hover {
  background: $wolf-bg-hover-v2;
}

.follow-up-card {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm-v2;
}

.follow-up-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.follow-up-time {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
}

.follow-up-details {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
}

.follow-up-tags {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  flex-wrap: wrap;
}

.follow-up-main {
  flex: 1;
}

.content-value {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  line-height: $wolf-line-height-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.meta-tag {
  display: inline-flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
  padding: $wolf-space-xs-v2 $wolf-space-sm-v2;
  border-radius: $wolf-radius-sm-v2;
  font-size: $wolf-font-size-caption-v2;
}

.type-tag {
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.operator-tag {
  background: $wolf-bg-elevated-v2;
  color: $wolf-text-secondary-v2;
  border: 1px solid $wolf-border-default-v2;
}

.operator-tag .tag-icon {
  color: $wolf-text-tertiary-v2;
}

.method-tag {
  background: $wolf-bg-elevated-v2;
  color: $wolf-text-secondary-v2;
  border: 1px solid $wolf-border-default-v2;
}

.method-tag .tag-icon {
  color: $wolf-primary-v2;
}

.follow-up-plan {
  margin-top: $wolf-space-sm-v2;
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
  background: $wolf-bg-hover-v2;
  border-radius: $wolf-radius-sm-v2;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.plan-item {
  display: flex;
  align-items: flex-start;
  gap: $wolf-space-sm-v2;
  font-size: $wolf-font-size-caption-v2;
}

.plan-label {
  color: $wolf-text-tertiary-v2;
  min-width: 70px;
}

.plan-value {
  color: $wolf-text-secondary-v2;
  flex: 1;
}

.plan-action .plan-value {
  color: $wolf-text-primary-v2;
}

.tag-icon {
  width: 12px;
  height: 12px;
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

.follow-up-card:hover .delete-btn {
  opacity: 1;
}
</style>