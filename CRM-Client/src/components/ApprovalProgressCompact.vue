<template>
  <el-card v-if="approvalDetail" class="approval-compact-card" shadow="never">
    <div class="compact-header">
      <div class="header-left">
        <span class="header-title">{{ isApprovalCompleted ? '审批记录' : '审批进度' }}</span>
        <el-tag :type="getStatusType()" size="small" class="wolf-tag">
          {{ statusText }}
        </el-tag>
      </div>
    </div>

    <div class="compact-content">
      <div v-if="isApprovalCompleted" class="approval-flow-section">
        <div class="flow-label">审批记录</div>
        <el-steps :active="displaySteps.length" direction="vertical" :space="80" class="approval-steps" finish-status="success">
          <el-step
            v-for="(step, index) in displaySteps"
            :key="index"
            :status="getStepStatus(step.status)"
            :class="getStepItemClass(step)"
          >
            <template #icon>
              <el-icon v-if="step.status === 'APPROVED'"><CircleCheck /></el-icon>
              <el-icon v-else-if="step.status === 'REJECTED'"><CircleClose /></el-icon>
              <span v-else class="step-number">{{ index + 1 }}</span>
            </template>
            <template #title>
              <div class="custom-step-title">
                <span class="step-name-text">{{ step.step_name }}</span>
                <span v-if="step.approver_role" class="step-role-text">{{ getRoleName(step.approver_role) }}</span>
              </div>
            </template>
            <template #description>
              <div v-if="step.approval_records && step.approval_records.length > 0" class="step-records">
                <template v-if="step.step_name === '已提交'">
                  <div v-for="(record, rIndex) in step.approval_records" :key="rIndex" class="record-item">
                    <span class="record-action">{{ getActionText(record.action) }}</span>
                    <span v-if="record.approver_name" class="record-user">{{ record.approver_name }}</span>
                    <span v-if="record.created_time" class="record-time">{{ formatRecordTime(record.created_time) }}</span>
                  </div>
                </template>
                <template v-else>
                  <div v-for="(record, rIndex) in step.approval_records.filter(r => r.action === 'APPROVE' || r.action === 'REJECT')" :key="rIndex" class="record-item">
                    <span v-if="record.approver_name" class="record-user">{{ record.approver_name }}</span>
                    <span v-if="record.created_time" class="record-time">{{ formatRecordTime(record.created_time) }}</span>
                  </div>
                </template>
              </div>
            </template>
          </el-step>
        </el-steps>
      </div>

      <div v-else class="approval-flow-section">
        <div class="flow-label">审批流程</div>
        <el-steps :active="currentStepIndex" direction="vertical" :space="80" class="approval-steps" finish-status="success" process-status="process">
          <el-step
            v-for="(step, index) in displaySteps"
            :key="index"
            :status="getStepStatus(step.status)"
            :class="getStepItemClass(step)"
          >
            <template #icon>
              <el-icon v-if="step.status === 'APPROVED'"><CircleCheck /></el-icon>
              <el-icon v-else-if="step.status === 'REJECTED'"><CircleClose /></el-icon>
              <el-icon v-else-if="isCurrentStep(step)"><Clock /></el-icon>
              <span v-else class="step-number">{{ index + 1 }}</span>
            </template>
            <template #title>
              <div class="custom-step-title">
                <span class="step-name-text">{{ step.step_name }}</span>
                <span v-if="step.approver_role" class="step-role-text">{{ getRoleName(step.approver_role) }}</span>
              </div>
            </template>
          </el-step>
        </el-steps>
      </div>

      <div v-if="canApprove" class="approval-actions">
        <el-button type="primary" class="wolf-btn wolf-btn--primary" @click="handleApprove">
          <el-icon><CircleCheck /></el-icon>
          同意
        </el-button>
        <el-button type="danger" class="wolf-btn wolf-btn--danger" @click="handleReject">
          <el-icon><CircleClose /></el-icon>
          拒绝
        </el-button>
      </div>

      <div class="progress-summary">
        <div v-if="approvalDetail.submitter_name" class="submitter-info">
          <span class="submitter-label">提交人：</span>
          <span class="submitter-name">{{ approvalDetail.submitter_name }}</span>
          <span v-if="approvalDetail.submitted_at" class="submitter-time">{{ formatSubmitTime(approvalDetail.submitted_at) }}</span>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ArrowRight, CircleCheck, CircleClose, Remove, Clock } from '@element-plus/icons-vue'

interface ApprovalRecord {
  approver_id: string
  approver_name?: string
  action: string
  created_time: string
  comment?: string
}

interface ApprovalStep {
  step_order: number
  step_name: string
  approver_role: string
  status: string
  approval_records: ApprovalRecord[]
}

interface ApprovalDetail {
  current_step: number
  approval_steps: ApprovalStep[]
  status: string
  submitter_name?: string
  submitted_at?: string
  flow_name?: string
}

interface Props {
  approvalDetail: ApprovalDetail
  canApprove?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  canApprove: false
})

const emit = defineEmits<{
  approve: []
  reject: []
  viewDetail: []
}>()

const statusText = computed(() => {
  const statusMap: Record<string, string> = {
    'PENDING': '审批中',
    'APPROVED': '已通过',
    'REJECTED': '已拒绝',
    'CANCELLED': '已撤回'
  }
  return statusMap[props.approvalDetail.status] || props.approvalDetail.status
})

const isApprovalCompleted = computed(() => {
  return ['APPROVED', 'REJECTED', 'CANCELLED'].includes(props.approvalDetail.status)
})

const statusIconClass = computed(() => {
  const classMap: Record<string, string> = {
    'APPROVED': 'success',
    'REJECTED': 'danger',
    'CANCELLED': 'info'
  }
  return classMap[props.approvalDetail.status] || 'info'
})

const completionStatusText = computed(() => {
  const textMap: Record<string, string> = {
    'APPROVED': '审批已通过',
    'REJECTED': '审批已拒绝',
    'CANCELLED': '审批已撤回'
  }
  return textMap[props.approvalDetail.status] || '审批已完成'
})

const completionStatusDesc = computed(() => {
  const descMap: Record<string, string> = {
    'APPROVED': '该合同已通过所有审批流程',
    'REJECTED': '该合同在审批过程中被拒绝',
    'CANCELLED': '该合同的审批已被撤回'
  }
  return descMap[props.approvalDetail.status] || ''
})

const currentStepInfo = computed(() => {
  if (props.approvalDetail.status !== 'PENDING') {
    return null
  }
  return props.approvalDetail.approval_steps[props.approvalDetail.current_step]
})

const waitingDuration = computed(() => {
  if (!currentStepInfo.value) return ''
  
  const records = currentStepInfo.value.approval_records || []
  if (records.length === 0) return ''
  
  const submitRecord = records.find(r => r.action === 'SUBMIT')
  if (!submitRecord) return ''
  
  const submitTime = new Date(submitRecord.created_time).getTime()
  const now = Date.now()
  const diff = now - submitTime
  
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
  
  if (days > 0) {
    return `${days}天${hours}小时`
  } else if (hours > 0) {
    return `${hours}小时`
  } else {
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
    return `${minutes}分钟`
  }
})

const totalSteps = computed(() => {
  return props.approvalDetail.approval_steps.length
})

const completedSteps = computed(() => {
  return props.approvalDetail.current_step
})

const getStatusType = () => {
  const typeMap: Record<string, string> = {
    'PENDING': 'warning',
    'APPROVED': 'success',
    'REJECTED': 'danger',
    'CANCELLED': 'info'
  }
  return typeMap[props.approvalDetail.status] || 'info'
}

const getRoleName = (roleCode: string) => {
  const roleMap: Record<string, string> = {
    'SALES_MANAGER': '销售总监',
    'SALES_DIRECTOR': '销售总监',
    'FINANCE_MANAGER': '财务经理',
    'GENERAL_MANAGER': '总经理',
    'SYSTEM_ADMIN': '系统管理员'
  }
  return roleMap[roleCode] || roleCode
}

const formatSubmitTime = (dateStr: string) => {
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
  
  if (days > 0) {
    return `${days}天前`
  } else if (hours > 0) {
    return `${hours}小时前`
  } else {
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
    return `${minutes}分钟前`
  }
}

const handleApprove = () => {
  emit('approve')
}

const handleReject = () => {
  emit('reject')
}

const handleViewDetail = () => {
  emit('viewDetail')
}

const displaySteps = computed(() => {
  return props.approvalDetail.approval_steps
})

const isCurrentStep = (step: ApprovalStep) => {
  return props.approvalDetail.approval_steps[props.approvalDetail.current_step] === step
}

const getStepClass = (step: ApprovalStep) => {
  if (step.status === 'APPROVED') {
    return 'step-completed'
  } else if (step.status === 'REJECTED') {
    return 'step-rejected'
  } else if (isCurrentStep(step)) {
    return 'step-current'
  } else {
    return 'step-pending'
  }
}

const getStepRoleClass = (step: ApprovalStep) => {
  if (step.status === 'APPROVED') {
    return 'role-completed'
  } else if (isCurrentStep(step)) {
    return 'role-current'
  } else {
    return 'role-pending'
  }
}

const getFlowStepClass = (step: ApprovalStep) => {
  if (step.status === 'APPROVED') {
    return 'flow-step-completed'
  } else if (step.status === 'REJECTED') {
    return 'flow-step-rejected'
  } else if (isCurrentStep(step)) {
    return 'flow-step-current'
  } else {
    return 'flow-step-pending'
  }
}

const getActionText = (action: string) => {
  const actionMap: Record<string, string> = {
    'SUBMIT': '提交',
    'APPROVE': '通过',
    'REJECT': '拒绝',
    'CANCEL': '撤回'
  }
  return actionMap[action] || action
}

const formatRecordTime = (dateStr: string) => {
  const date = new Date(dateStr)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  
  return `${year}-${month}-${day} ${hours}:${minutes}`
}

const currentStepIndex = computed(() => {
  return props.approvalDetail.current_step
})

const getStepStatus = (stepStatus: string) => {
  const statusMap: Record<string, string> = {
    'APPROVED': 'success',
    'REJECTED': 'error',
    'PENDING': 'wait'
  }
  return statusMap[stepStatus] || 'wait'
}

const getStepItemClass = (step: ApprovalStep) => {
  if (step.status === 'APPROVED') {
    return 'step-item-completed'
  } else if (step.status === 'REJECTED') {
    return 'step-item-rejected'
  } else if (isCurrentStep(step)) {
    return 'step-item-current'
  } else {
    return 'step-item-pending'
  }
}
</script>

<style scoped lang="scss">
.approval-compact-card {
  height: 100%;
  background: var(--wolf-bg-card);
  border-radius: var(--wolf-radius-lg);

  :deep(.el-card__body) {
    padding: 20px;
    height: 100%;
    display: flex;
    flex-direction: column;
  }
}

.compact-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--wolf-border-color);

  .header-left {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .header-title {
    font-size: var(--wolf-font-size-lg);
    font-weight: var(--wolf-font-weight-semibold);
    color: var(--wolf-text-primary);
  }
}

.compact-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--wolf-space-4);
}

.current-step-section {
  background: var(--wolf-bg-soft);
  border-radius: var(--wolf-radius-md);
  padding: var(--wolf-space-4);

  .step-label {
    font-size: var(--wolf-font-size-label);
    color: var(--wolf-text-tertiary);
    margin-bottom: var(--wolf-space-2);
  }

  .step-info {
    .step-name {
      font-size: var(--wolf-font-size-subtitle);
      font-weight: var(--wolf-font-weight-semibold);
      color: var(--wolf-text-primary);
      margin-bottom: var(--wolf-space-2);
    }

    .step-meta {
      display: flex;
      align-items: center;
      gap: var(--wolf-space-4);
      flex-wrap: wrap;
    }

    .step-role {
      display: inline-flex;
      align-items: center;
      padding: var(--wolf-space-1) var(--wolf-space-3);
      border-radius: var(--wolf-radius-sm);
      font-size: var(--wolf-font-size-small);
      font-weight: var(--wolf-font-weight-medium);

      &.role-completed {
        background: var(--wolf-success-bg);
        color: var(--wolf-success);
      }

      &.role-current {
        background: var(--wolf-primary-light);
        color: var(--wolf-primary);
      }

      &.role-pending {
        background: var(--wolf-danger-bg);
        color: var(--wolf-danger);
      }
    }

    .waiting-time {
      font-size: var(--wolf-font-size-small);
      color: var(--wolf-text-secondary);
    }
  }
}

.approval-flow-section {
  background: var(--wolf-bg-soft);
  border-radius: var(--wolf-radius-md);
  padding: var(--wolf-space-4);

  .flow-label {
    font-size: var(--wolf-font-size-label);
    color: var(--wolf-text-tertiary);
    margin-bottom: var(--wolf-space-4);
  }
}

.approval-steps {
  :deep(.el-step) {
    &.step-item-pending {
      opacity: 0.5;
    }

    &.step-item-current {
      .el-step__head.is-process {
        .el-step__icon {
          background: var(--wolf-primary);
          color: white;
          border-color: var(--wolf-primary);
        }
      }

      .custom-step-title .step-name-text {
        color: var(--wolf-primary);
        font-weight: var(--wolf-font-weight-semibold);
      }
    }

    &.step-item-rejected {
      .el-step__head.is-error {
        .el-step__icon {
          color: var(--wolf-danger);
        }
      }

      .custom-step-title .step-name-text {
        color: var(--wolf-danger);
      }
    }
  }

  :deep(.el-step__head) {
    .step-number {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 24px;
      height: 24px;
      font-size: 14px;
      font-weight: var(--wolf-font-weight-semibold);
    }
  }

  :deep(.el-step__line) {
    background-color: var(--wolf-border-color);

    .el-step__line-inner {
      background-color: var(--wolf-success);
    }
  }

  :deep(.el-step.is-flex) {
    .el-step__description {
      padding-top: var(--wolf-space-2);
    }
  }
}

.custom-step-title {
  display: flex;
  align-items: center;
  gap: var(--wolf-space-2);
  flex-wrap: wrap;

  .step-name-text {
    font-size: var(--wolf-font-size-body);
    font-weight: var(--wolf-font-weight-medium);
    color: var(--wolf-text-primary);
  }

  .step-role-text {
    font-size: var(--wolf-font-size-small);
    color: var(--wolf-text-secondary);
  }
}

.step-records {
  margin-top: var(--wolf-space-2);
  display: flex;
  flex-direction: column;
  gap: var(--wolf-space-2);
}

.record-item {
  display: flex;
  align-items: center;
  gap: var(--wolf-space-2);
  padding: var(--wolf-space-2);
  background: var(--wolf-bg-card);
  border-radius: var(--wolf-radius-sm);
  font-size: var(--wolf-font-size-small);
}

.record-action {
  font-weight: var(--wolf-font-weight-medium);
  color: var(--wolf-text-primary);
}

.record-user {
  color: var(--wolf-primary);
}

.record-time {
  margin-left: auto;
  color: var(--wolf-text-tertiary);
}

.completion-status {
  display: flex;
  align-items: center;
  gap: var(--wolf-space-4);
  padding: var(--wolf-space-4);
  background: var(--wolf-bg-soft);
  border-radius: var(--wolf-radius-md);

  .status-icon {
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--wolf-radius-full);
    flex-shrink: 0;

    .el-icon {
      font-size: 28px;
    }

    &.success {
      background: var(--wolf-success-bg);
      color: var(--wolf-success);
    }

    &.danger {
      background: var(--wolf-danger-bg);
      color: var(--wolf-danger);
    }

    &.info {
      background: var(--wolf-info-bg);
      color: var(--wolf-info);
    }
  }

  .status-text {
    flex: 1;

    .status-title {
      font-size: var(--wolf-font-size-subtitle);
      font-weight: var(--wolf-font-weight-semibold);
      color: var(--wolf-text-primary);
      margin-bottom: var(--wolf-space-1);
    }

    .status-desc {
      font-size: var(--wolf-font-size-body);
      color: var(--wolf-text-secondary);
    }
  }
}

.approval-actions {
  display: flex;
  gap: 12px;

  .el-button {
    flex: 1;
    height: 44px;
    font-size: var(--wolf-font-size-md);
  }
}

.progress-summary {
  display: flex;
  flex-direction: column;
  gap: var(--wolf-space-3);
  padding: var(--wolf-space-4);
  background: var(--wolf-bg-soft);
  border-radius: var(--wolf-radius-md);

  .submitter-info {
    display: flex;
    align-items: center;
    gap: var(--wolf-space-2);

    .submitter-label {
      font-size: var(--wolf-font-size-label);
      color: var(--wolf-text-tertiary);
    }

    .submitter-name {
      font-size: var(--wolf-font-size-body);
      font-weight: var(--wolf-font-weight-medium);
      color: var(--wolf-text-primary);
    }

    .submitter-time {
      margin-left: auto;
      font-size: var(--wolf-font-size-small);
      color: var(--wolf-text-tertiary);
    }
  }
}

@media (max-width: 768px) {
  .compact-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .current-step-section .step-meta {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .approval-actions {
    flex-direction: column;
  }

  .progress-summary {
    .summary-item {
      .summary-value {
        font-size: var(--wolf-font-size-lg);
      }
    }
  }
}
</style>
