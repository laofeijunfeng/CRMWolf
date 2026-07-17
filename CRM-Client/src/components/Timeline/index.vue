<template>
  <div class="timeline-container">
    <TimelineFilter
      v-if="showFilter"
      :event-types="filters.eventTypes"
      :date-range="filters.dateRange"
      :custom-start-date="filters.customStartDate"
      :custom-end-date="filters.customEndDate"
      :keyword="filters.keyword"
      @filter-change="handleFilterChange"
      @reset="handleReset"
    />

    <div v-if="loading && logs.length === 0" class="timeline-skeleton">
      <el-skeleton :rows="5" animated />
    </div>

    <Empty v-else-if="logs.length === 0" class="timeline-empty">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <Document class="h-5 w-5" aria-hidden="true" />
        </EmptyMedia>
        <EmptyTitle class="text-sm font-medium">暂无操作记录</EmptyTitle>
      </EmptyHeader>
    </Empty>

    <div v-else class="timeline-wrapper" @scroll="handleScroll">
      <div class="timeline-list">
        <div
          v-for="log in logs"
          :key="log.id"
          class="timeline-item"
          :class="{ 'is-system': isSystemEvent(log.event_type) }"
        >
          <div class="timeline-item-tail"></div>
          <div class="timeline-item-dot">
            <el-icon :size="12">
              <component :is="getEventIcon(log.event_type)" />
            </el-icon>
          </div>
          <div class="timeline-item-content">
            <div class="event-card">
              <!-- 非跟进记录：显示原有标题行 -->
              <div v-if="!shouldShowContent(log)" class="event-header">
                <span class="event-type-tag" :style="getEventTagStyle(log.event_type)">
                  {{ getEventLabel(log.event_type) }}
                </span>
                <span class="event-time">{{ formatTime(log.operated_at) }}</span>
              </div>
              <div class="event-body">
                <!-- 非跟进记录：显示原有描述 -->
                <div v-if="!shouldShowContent(log)" class="event-title">
                  <strong>{{ log.operator_name || '系统' }}</strong>
                  {{ getEventDescription(log) }}
                </div>
                <div v-if="log.event_type === 'LEAD_CONVERTED' && log.content?.['originalLeadName']" class="event-relation-text">
                  关联线索：{{ log.content['originalLeadName'] }}
                </div>
                <div v-if="log.remark" class="event-remark">
                  {{ log.remark }}
                </div>
                <!-- 跟进记录：显示时间 -->
                <div v-if="shouldShowContent(log)" class="follow-up-header">
                  <span class="follow-up-time">{{ formatTime(log.operated_at) }}</span>
                </div>
                <div v-if="shouldShowContent(log)" class="event-content">
                  <div class="follow-up-details">
                    <!-- 标签区域：跟进类型、跟进人、跟进方式 -->
                    <div class="follow-up-tags">
                      <span class="meta-tag type-tag">
                        {{ getEventLabel(log.event_type) }}
                      </span>
                      <span class="meta-tag operator-tag">
                        <el-icon class="tag-icon"><User /></el-icon>
                        <span>{{ log.operator_name || '系统' }}</span>
                      </span>
                      <span v-if="log.content?.['method']" class="meta-tag method-tag">
                        <el-icon class="tag-icon"><Phone /></el-icon>
                        <span>{{ formatFollowUpMethod(log.content['method']) }}</span>
                      </span>
                    </div>
                    <!-- 跟进内容（核心信息） -->
                    <div v-if="log.content?.['content']" class="follow-up-main">
                      <span class="content-value">{{ log.content?.['content'] }}</span>
                    </div>
                    <!-- 后续安排区域 -->
                    <div v-if="log.content?.['next_follow_up_date'] || log.content?.['next_action']" class="follow-up-plan">
                      <div v-if="log.content?.['next_follow_up_date']" class="plan-item">
                        <span class="plan-label">下次跟进</span>
                        <span class="plan-value">{{ log.content?.['next_follow_up_date'] }}</span>
                      </div>
                      <div v-if="log.content?.['next_action']" class="plan-item plan-action">
                        <span class="plan-label">下一步动作</span>
                        <span class="plan-value">{{ log.content?.['next_action'] }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="loading" class="timeline-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载中...</span>
      </div>

      <div v-else-if="!hasMore && logs.length > 0" class="timeline-no-more">
        没有更多记录了
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { markRaw } from 'vue'
import type { Component } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import {
  Plus,
  Refresh,
  User,
  ChatDotRound,
  StarFilled,
  Document,
  CircleCheckFilled,
  WarningFilled,
  Phone
} from '@element-plus/icons-vue'
import { EVENT_TYPE_CONFIG } from './types'
import type { EventType } from '@/api/operationLog'
import TimelineFilter from './TimelineFilter.vue'
import type { OperationLog } from '@/api/operationLog'
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle
} from '@/components/ui/empty'

defineOptions({
  name: 'OperationTimeline'
})

const iconMap: Record<string, Component> = {
  'icon-plus-circle': markRaw(Plus),
  'icon-sync': markRaw(Refresh),
  'icon-user-group': markRaw(User),
  'icon-message': markRaw(ChatDotRound),
  'icon-heart-fill': markRaw(StarFilled),
  'icon-file': markRaw(Document),
  'icon-check-circle': markRaw(CircleCheckFilled),
  'icon-exclamation-circle': markRaw(WarningFilled)
}

interface Props {
  logs: OperationLog[]
  loading: boolean
  hasMore: boolean
  filters: { eventTypes: string[]; dateRange: string | null; customStartDate: string | null; customEndDate: string | null; keyword: string }
  showFilter?: boolean
}

interface Emits {
  (e: 'loadMore' | 'reset'): void
  (e: 'filterChange', filters: { eventTypes: EventType[]; dateRange: string | null; customStartDate: string | null; customEndDate: string | null; keyword: string }): void
}

const props = withDefaults(defineProps<Props>(), {
  showFilter: true
})
const emit = defineEmits<Emits>()

const isSystemEvent = (eventType: EventType) => {
  return !eventType.includes('MANUAL')
}

const getEventIcon = (eventType: EventType) => {
  const iconKey = EVENT_TYPE_CONFIG[eventType]?.icon || 'icon-message'
  return iconMap[iconKey] || iconMap['icon-message']
}

const getEventLabel = (eventType: EventType) => {
  return EVENT_TYPE_CONFIG[eventType]?.label || eventType
}

const getEventTagStyle = (eventType: EventType) => {
  const config = EVENT_TYPE_CONFIG[eventType]
  if (!config) return {}
  return {
    backgroundColor: config.bgColor,
    color: config.color
  }
}

const getEventDescription = (log: OperationLog) => {
  const config = EVENT_TYPE_CONFIG[log.event_type]
  return config?.description || log.event_type
}

const formatTime = (dateStr: string) => {
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

const shouldShowContent = (log: OperationLog) => {
  return log.event_type === 'MANUAL_FOLLOW_UP' && 
         log.content && 
         Object.keys(log.content).length > 0
}

const formatFollowUpMethod = (method: string) => {
  const methodMap: Record<string, string> = {
    PHONE: '电话',
    EMAIL: '邮件',
    WECHAT: '微信',
    VISIT: '上门拜访',
    OTHER: '其他'
  }
  return methodMap[method] || method
}

const handleScroll = (event: Event) => {
  const target = event.target as HTMLElement
  const scrollTop = target.scrollTop
  const scrollHeight = target.scrollHeight
  const clientHeight = target.clientHeight

  if (scrollHeight - scrollTop - clientHeight < 100 && props.hasMore && !props.loading) {
    emit('loadMore')
  }
}

const handleFilterChange = () => {
  emit('filterChange', props.filters)
}

const handleReset = () => {
  emit('reset')
}
</script>

<style scoped>
.timeline-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
}

.timeline-skeleton {
  padding: 24px;
}

.timeline-empty {
  padding: 60px 0;
  text-align: center;
}

.timeline-wrapper {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.timeline-list {
  position: relative;
  padding-left: 20px;
}

.timeline-item {
  position: relative;
  padding-bottom: 24px;
  padding-left: 24px;
}

.timeline-item-tail {
  position: absolute;
  left: 0;
  top: 12px;
  height: calc(100% - 12px);
  width: 2px;
  background: #e8e8e8;
}

.timeline-item:last-child .timeline-item-tail {
  display: none;
}

.timeline-item-dot {
  position: absolute;
  left: -6px;
  top: 0;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #fff;
  border: 2px solid #1890ff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: #1890ff;
  z-index: 1;
}

.timeline-item.is-system .timeline-item-dot {
  border-color: #52c41a;
  color: #52c41a;
}

.timeline-item-content {
  background: #fafafa;
  border-radius: 8px;
  padding: 12px;
  transition: all 0.3s;
}

.timeline-item-content:hover {
  background: #f0f0f0;
}

.event-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.event-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.event-type-tag {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.event-time {
  font-size: 12px;
  color: #999;
}

.event-title {
  font-size: 14px;
  color: #333;
  line-height: 1.5;
}

.event-remark {
  font-size: 13px;
  color: #666;
  padding: 8px;
  background: #fff;
  border-radius: 4px;
  border-left: 2px solid #1890ff;
}

.event-relation-text {
  font-size: 13px;
  color: var(--wolf-primary, #165DFF);
  padding: 6px 12px;
  background: var(--wolf-primary-light, #E8F3FF);
  border-radius: var(--wolf-radius-sm, 4px);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-weight: 500;
}

.event-content {
  margin-top: 0;
}

.follow-up-details {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.follow-up-time {
  font-size: 12px;
  color: var(--wolf-text-tertiary, #909399);
  margin-bottom: 8px;
}

.follow-up-tags {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.follow-up-main {
  flex: 1;
}

.content-value {
  color: var(--wolf-text-primary, #1D2129);
  font-size: 14px;
  line-height: 1.6;
  font-weight: 500;
}

.follow-up-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.meta-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: var(--wolf-radius-sm, 4px);
  font-size: 12px;
}

.type-tag {
  background: var(--wolf-primary-light, #E8F3FF);
  color: var(--wolf-primary, #165DFF);
  font-weight: 500;
}

.operator-tag {
  background: var(--wolf-bg-elevated, #FFFFFF);
  color: var(--wolf-text-secondary, #4E5969);
  border: 1px solid var(--wolf-border-default, #E5E6EB);
}

.operator-tag .tag-icon {
  color: var(--wolf-text-tertiary, #909399);
}

.method-tag {
  background: var(--wolf-bg-elevated, #FFFFFF);
  color: var(--wolf-text-secondary, #4E5969);
  border: 1px solid var(--wolf-border-default, #E5E6EB);
}

.method-tag .tag-icon {
  color: var(--wolf-primary, #165DFF);
}

.next-tag {
  background: var(--wolf-warning-bg, #FFF7E8);
  color: var(--wolf-warning-text, #FF7D00);
}

.next-tag .tag-icon {
  color: var(--wolf-warning, #FF7D00);
}

.follow-up-plan {
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--wolf-bg-hover, #F7F8FA);
  border-radius: var(--wolf-radius-sm, 4px);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.plan-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 12px;
}

.plan-label {
  color: var(--wolf-text-tertiary, #909399);
  min-width: 70px;
}

.plan-value {
  color: var(--wolf-text-secondary, #4E5969);
  flex: 1;
}

.plan-action .plan-value {
  color: var(--wolf-text-primary, #1D2129);
}

.tag-icon {
  font-size: 12px;
}

.follow-up-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.follow-up-header .follow-up-time {
  margin-bottom: 0;
}

.timeline-loading,
.timeline-no-more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px;
  color: #999;
  font-size: 13px;
}
</style>
