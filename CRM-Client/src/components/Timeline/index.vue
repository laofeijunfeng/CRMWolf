<template>
  <div class="timeline-container">
    <TimelineFilter
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

    <div v-else-if="logs.length === 0" class="timeline-empty">
      <el-empty description="暂无操作记录" />
    </div>

    <div v-else class="timeline-wrapper" @scroll="handleScroll">
      <div class="timeline-list">
        <div
          v-for="(log, index) in logs"
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
              <div class="event-header">
                <span class="event-type-tag" :style="getEventTagStyle(log.event_type)">
                  {{ getEventLabel(log.event_type) }}
                </span>
                <span class="event-time">{{ formatTime(log.operated_at) }}</span>
              </div>
              <div class="event-body">
                <div class="event-title">
                  <strong>{{ log.operator_name || '系统' }}</strong>
                  {{ getEventDescription(log) }}
                </div>
                <div v-if="log.event_type === 'LEAD_CONVERTED' && log.content?.originalLeadName" class="event-relation-text">
                  关联线索：{{ log.content.originalLeadName }}
                </div>
                <div v-if="log.remark" class="event-remark">
                  {{ log.remark }}
                </div>
                <div v-if="shouldShowContent(log)" class="event-content">
                  <div class="follow-up-details">
                    <div v-if="log.content?.method" class="follow-up-method">
                      <el-icon class="method-icon"><Phone /></el-icon>
                      <span class="method-label">跟进方式：</span>
                      <span class="method-value">{{ formatFollowUpMethod(log.content.method) }}</span>
                    </div>
                    <div v-if="log.content?.content" class="follow-up-content">
                      <span class="content-label">跟进内容：</span>
                      <span class="content-value">{{ log.content.content }}</span>
                    </div>
                    <div v-if="log.content?.next_follow_up_date" class="follow-up-next">
                      <el-icon class="next-icon"><Calendar /></el-icon>
                      <span class="next-label">下次跟进：</span>
                      <span class="next-value">{{ log.content.next_follow_up_date }}</span>
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
import { computed, markRaw } from 'vue'
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
  Phone,
  Calendar
} from '@element-plus/icons-vue'
import { EVENT_TYPE_CONFIG } from './types'
import type { EventType } from '@/api/operationLog'
import TimelineFilter from './TimelineFilter.vue'
import type { OperationLog } from '@/api/operationLog'

const iconMap: Record<string, any> = {
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
  filters: any
}

interface Emits {
  (e: 'loadMore'): void
  (e: 'filterChange', filters: any): void
  (e: 'reset'): void
}

const props = defineProps<Props>()
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

const formatContentKey = (key: string) => {
  const keyMap: Record<string, string> = {
    account_name: '客户名称',
    amount: '金额',
    stage: '阶段',
    status: '状态',
    contract_number: '合同编号',
    expected_payment_date: '预计付款日期',
    actual_payment_date: '实际付款日期'
  }
  return keyMap[key] || key
}

const formatContentValue = (value: any) => {
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

const getResourceTypeLabel = (type: string) => {
  const labelMap: Record<string, string> = {
    LEAD: '线索',
    CUSTOMER: '客户',
    OPPORTUNITY: '商机',
    CONTRACT: '合同',
    INVOICE: '发票',
    PAYMENT_PLAN: '回款计划',
    PAYMENT_RECORD: '回款记录'
  }
  return labelMap[type] || type
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
  margin-top: 4px;
}

.follow-up-details {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  background: var(--wolf-bg-page, #F5F7FA);
  border-radius: var(--wolf-radius-md, 8px);
  border-left: 3px solid var(--wolf-info, #165DFF);
}

.follow-up-method,
.follow-up-content,
.follow-up-next {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
}

.method-icon,
.next-icon {
  color: var(--wolf-info, #165DFF);
  font-size: 14px;
  margin-top: 2px;
}

.method-label,
.content-label,
.next-label {
  color: var(--wolf-text-secondary, #4E5969);
  font-weight: 500;
  min-width: 70px;
  flex-shrink: 0;
}

.method-value {
  color: var(--wolf-text-primary, #1D2129);
  font-weight: 600;
}

.content-value {
  color: var(--wolf-text-primary, #1D2129);
  line-height: 1.6;
  flex: 1;
}

.next-value {
  color: var(--wolf-primary, #165DFF);
  font-weight: 500;
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
