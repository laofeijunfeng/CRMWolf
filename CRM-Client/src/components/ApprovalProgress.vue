<template>
  <el-card v-if="approvalDetail" class="approval-progress-card" shadow="never">
    <template #header>
      <div class="card-header">
        <span class="card-title">{{ title }}</span>
        <el-tag :type="getStatusType()" size="small">
          {{ statusText }}
        </el-tag>
      </div>
    </template>

    <div class="approval-content">
      <el-steps 
        :active="currentStep" 
        direction="vertical"
        align-center
        class="approval-steps"
      >
        <el-step
          v-for="(step, index) in approvalSteps"
          :key="step.node_id"
          :status="getStepStatus(index)"
          class="approval-step"
        >
          <template #title>
            <div class="step-header">
              <span class="step-name">{{ step.step_name }}</span>
              <div class="step-status-tags">
                <el-tag v-if="index === currentStep && status === 'REJECTED'" type="danger" size="small">
                  已拒绝
                </el-tag>
                <el-tag v-else-if="index === currentStep" type="warning" size="small">
                  进行中
                </el-tag>
                <el-tag v-else-if="index < currentStep" type="success" size="small">
                  已完成
                </el-tag>
                <el-tag v-else type="info" size="small">
                  待处理
                </el-tag>
              </div>
            </div>
          </template>
          
          <template #description>
            <div class="step-content">
              <div v-if="step.approvers && step.approvers.length > 0" class="approvers-section">
                <div class="section-label">审批人</div>
                <div class="approvers-list">
                  <div
                    v-for="approver in step.approvers"
                    :key="approver.approver_id"
                    class="approver-item"
                  >
                    <div class="approver-info">
                      <span class="approver-name">{{ approver.approver_name || approver.approver_id }}</span>
                      <div class="approver-status">
                        <el-icon v-if="approver.approved_at" color="#00B42A" :size="16">
                          <CircleCheck />
                        </el-icon>
                        <el-icon v-else-if="approver.rejected_at" color="#F53F3F" :size="16">
                          <CircleClose />
                        </el-icon>
                        <span v-else class="pending-text">待审批</span>
                      </div>
                    </div>
                    <div v-if="approver.approved_at || approver.rejected_at" class="approver-time">
                      {{ formatRelativeTime(approver.approved_at || approver.rejected_at || '') }}
                    </div>
                    <div v-if="approver.comment" class="approver-comment">
                      <span class="comment-label">备注：</span>
                      {{ approver.comment }}
                    </div>
                  </div>
                </div>
              </div>
              
              <div v-if="step.approver_role && (!step.approvers || step.approvers.length === 0)" class="role-section">
                <div class="section-label">审批角色</div>
                <el-tag type="info" size="small">{{ step.approver_role || '待配置' }}</el-tag>
              </div>
              
              <div v-if="step.approval_records && step.approval_records.filter(r => r.action !== 'SUBMIT').length > 0" class="records-section">
                <div class="section-label">审批记录</div>
                <div class="records-list">
                  <div
                    v-for="(record, idx) in step.approval_records.filter(r => r.action !== 'SUBMIT')"
                    :key="idx"
                    class="record-item"
                  >
                    <div class="record-header">
                      <span class="record-user">{{ record.approver_name || record.approver_id }}</span>
                      <el-tag :type="record.action === 'APPROVE' ? 'success' : 'danger'" size="small">
                        {{ record.action === 'APPROVE' ? '同意' : '拒绝' }}
                      </el-tag>
                      <span class="record-time">{{ formatRelativeTime(record.created_time) }}</span>
                    </div>
                    <div v-if="record.comment" class="record-comment">
                      <span class="comment-label">备注：</span>{{ record.comment }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </el-step>
      </el-steps>
    </div>

    <el-divider v-if="showHistory && approvalHistory.length > 0" />

    <div v-if="showHistory && approvalHistory.length > 0" class="history-section">
      <div class="section-title">完整审批记录</div>
      <el-timeline class="approval-timeline">
        <el-timeline-item
          v-for="(record, index) in approvalHistory"
          :key="index"
          :timestamp="formatDateTime(record.created_time)"
          placement="top"
          :type="getTimelineType(record.action)"
        >
          <div class="timeline-item">
            <div class="timeline-header">
              <span class="timeline-user">{{ record.approver_name || record.approver_id }}</span>
              <el-tag :type="getActionTagType(record.action)" size="small">
                {{ getActionText(record.action) }}
              </el-tag>
            </div>
            <div v-if="record.node_name" class="timeline-node">{{ record.node_name }}</div>
            <div v-if="record.comment" class="timeline-comment">
              <span class="comment-label">备注：</span>{{ record.comment }}
            </div>
          </div>
        </el-timeline-item>
      </el-timeline>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CircleCheck, CircleClose } from '@element-plus/icons-vue'

interface ApprovalStep {
  node_id: number
  step_name: string
  approver_role?: string
  approvers?: ApproverInfo[]
  approval_records?: ApprovalRecord[]
  completed_at?: string
}

interface ApproverInfo {
  approver_id: string
  approver_name?: string
  approved_at?: string
  rejected_at?: string
  comment?: string
}

interface ApprovalRecord {
  id: number
  approver_id: string
  approver_name?: string
  action: string
  node_name?: string
  comment?: string
  created_time: string
}

interface ApprovalDetail {
  status: string
  current_step: number
  approval_steps: ApprovalStep[]
  records?: ApprovalRecord[]
}

interface Props {
  approvalDetail: ApprovalDetail | null
  title?: string
  showHistory?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '审批进度',
  showHistory: true
})

const approvalSteps = computed(() => {
  return props.approvalDetail?.approval_steps || []
})

const currentStep = computed(() => {
  return props.approvalDetail?.current_step || 0
})

const approvalHistory = computed(() => {
  return props.approvalDetail?.records || []
})

const status = computed(() => {
  return props.approvalDetail?.status || ''
})

const statusText = computed(() => {
  const statusMap: Record<string, string> = {
    'PENDING': '审批中',
    'APPROVED': '已通过',
    'REJECTED': '已拒绝',
    'CANCELLED': '已撤回'
  }
  return statusMap[status.value] || status.value || '未知'
})

const getStepStatus = (index: number): 'success' | 'process' | 'wait' | 'error' => {
  if (index < currentStep.value) return 'success'
  if (index === currentStep.value) {
    if (status.value === 'REJECTED') return 'error'
    return 'process'
  }
  return 'wait'
}

const getStatusType = (): 'success' | 'warning' | 'danger' | 'info' => {
  const statusMap: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
    'PENDING': 'warning',
    'APPROVED': 'success',
    'REJECTED': 'danger',
    'CANCELLED': 'info'
  }
  return statusMap[status.value] || 'info'
}

const getTimelineType = (action: string): 'primary' | 'success' | 'danger' | 'warning' | 'info' => {
  const typeMap: Record<string, 'primary' | 'success' | 'danger' | 'warning' | 'info'> = {
    'SUBMIT': 'primary',
    'APPROVE': 'success',
    'REJECT': 'danger',
    'ROLLBACK': 'warning',
    'CANCEL': 'info'
  }
  return typeMap[action] || 'info'
}

const getActionTagType = (action: string): 'success' | 'danger' | 'info' => {
  if (action === 'APPROVE') return 'success'
  if (action === 'REJECT') return 'danger'
  return 'info'
}

const getActionText = (action: string): string => {
  const actionMap: Record<string, string> = {
    'SUBMIT': '提交',
    'APPROVE': '同意',
    'REJECT': '拒绝',
    'ROLLBACK': '回退',
    'CANCEL': '撤回'
  }
  return actionMap[action] || action
}

const formatRelativeTime = (dateStr: string): string => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  
  if (diff < 60000) return '刚刚'
  const minutes = Math.floor(diff / 60000)
  if (minutes < 60) return `${minutes}分钟前`
  
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}小时前`
  
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}天前`
  
  return date.toLocaleDateString('zh-CN')
}

const formatDateTime = (dateStr: string): string => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}
</script>

<style scoped>
.approval-progress-card {
  background: var(--wolf-bg-card);
  border-radius: var(--wolf-radius-lg);
  box-shadow: var(--wolf-shadow-card);
  margin-bottom: var(--wolf-card-gap);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: var(--wolf-font-size-card-title);
  font-weight: var(--wolf-font-weight-semibold);
  color: var(--wolf-text-primary);
}

.approval-content {
  padding: var(--wolf-card-padding) 0;
}

.approval-steps {
  --el-process-text-color: var(--wolf-text-secondary);
}

.approval-steps :deep(.el-step__head) {
  padding-bottom: 16px;
}

.approval-steps :deep(.el-step__head.is-process) {
  color: var(--wolf-primary);
}

.approval-steps :deep(.el-step__head.is-finish) {
  color: var(--wolf-success);
}

.approval-steps :deep(.el-step__head.is-wait) {
  color: var(--wolf-text-tertiary);
}

.approval-steps :deep(.el-step__line) {
  background-color: var(--wolf-border-light);
  height: 32px;
}

.approval-steps :deep(.el-step__line.is-finish) {
  background-color: var(--wolf-success);
}

.approval-steps :deep(.el-step__icon.is-text) {
  border: 2px solid var(--wolf-border-color);
  font-size: 14px;
  font-weight: var(--wolf-font-weight-medium);
}

.approval-steps :deep(.el-step__icon.is-process) {
  border-color: var(--wolf-primary);
  background-color: var(--wolf-primary-light);
  color: var(--wolf-primary);
}

.approval-steps :deep(.el-step__icon.is-finish) {
  border-color: var(--wolf-success);
  background-color: var(--wolf-success-bg);
  color: var(--wolf-success);
}

.approval-steps :deep(.el-step__icon.is-wait) {
  border-color: var(--wolf-border-color);
  background-color: var(--wolf-bg-hover);
}

.step-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.step-name {
  font-size: var(--wolf-font-size-body);
  font-weight: var(--wolf-font-weight-medium);
  color: var(--wolf-text-primary);
}

.step-status-tags {
  display: flex;
  gap: 4px;
}

.step-content {
  padding: 12px 0 0 0;
}

.section-label {
  font-size: var(--wolf-font-size-small);
  color: var(--wolf-text-tertiary);
  margin-bottom: 8px;
}

.approvers-section,
.records-section {
  margin-bottom: 12px;
}

.approvers-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.approver-item {
  padding: 10px;
  background: var(--wolf-bg-hover);
  border-radius: var(--wolf-radius-md);
}

.approver-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.approver-name {
  font-size: var(--wolf-font-size-body);
  color: var(--wolf-text-primary);
  font-weight: var(--wolf-font-weight-medium);
}

.approver-status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pending-text {
  font-size: var(--wolf-font-size-small);
  color: var(--wolf-text-tertiary);
}

.approver-time {
  font-size: var(--wolf-font-size-small);
  color: var(--wolf-text-tertiary);
}

.approver-comment {
  font-size: var(--wolf-font-size-small);
  color: var(--wolf-text-secondary);
  line-height: 1.5;
}

.comment-label {
  color: var(--wolf-text-tertiary);
}

.role-section {
  padding: 10px;
  background: var(--wolf-bg-hover);
  border-radius: var(--wolf-radius-md);
}

.records-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.record-item {
  padding: 10px;
  background: var(--wolf-bg-page);
  border-radius: var(--wolf-radius-sm);
}

.record-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.record-user {
  font-size: var(--wolf-font-size-body);
  font-weight: var(--wolf-font-weight-medium);
  color: var(--wolf-text-primary);
}

.record-time {
  font-size: var(--wolf-font-size-small);
  color: var(--wolf-text-tertiary);
}

.record-comment {
  font-size: var(--wolf-font-size-small);
  color: var(--wolf-text-secondary);
}

.history-section {
  padding: var(--wolf-card-padding);
}

.section-title {
  font-size: var(--wolf-font-size-card-title);
  font-weight: var(--wolf-font-weight-semibold);
  color: var(--wolf-text-primary);
  margin-bottom: 16px;
}

.approval-timeline {
  --el-timeline-node-size-large: 16px;
}

.approval-timeline :deep(.el-timeline-item__timestamp) {
  color: var(--wolf-text-tertiary);
  font-size: var(--wolf-font-size-small);
}

.timeline-item {
  padding: 8px;
}

.timeline-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.timeline-user {
  font-size: var(--wolf-font-size-body);
  font-weight: var(--wolf-font-weight-medium);
  color: var(--wolf-text-primary);
}

.timeline-node {
  font-size: var(--wolf-font-size-small);
  color: var(--wolf-text-secondary);
  margin-bottom: 4px;
}

.timeline-comment {
  font-size: var(--wolf-font-size-small);
  color: var(--wolf-text-secondary);
  background: var(--wolf-bg-hover);
  padding: 8px;
  border-radius: var(--wolf-radius-sm);
  margin-top: 4px;
}
</style>
