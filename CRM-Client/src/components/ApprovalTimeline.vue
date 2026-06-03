<template>
  <div class="approval-timeline">
    <el-card shadow="never" class="timeline-card">
      <template #header>
        <span>审批流程时间线</span>
      </template>
      <div class="timeline-container">
        <div
          v-for="(step, index) in steps"
          :key="index"
          class="timeline-item"
          :class="{
            'active': isCurrentStep(index),
            'completed': isCompletedStep(index),
            'pending': isPendingStep(index),
            'rejected': isRejectedStep(index)
          }"
        >
          <div class="timeline-node" @mouseenter="handleMouseEnter(step)" @mouseleave="handleMouseLeave">
            <div class="timeline-icon">
              <el-icon v-if="isCompletedStep(index)" class="icon-completed" :size="28"><CircleCheckFilled /></el-icon>
              <el-icon v-else-if="isRejectedStep(index)" class="icon-rejected" :size="28"><CircleCloseFilled /></el-icon>
              <el-icon v-else-if="isCurrentStep(index)" class="icon-current" :size="28"><Clock /></el-icon>
              <el-icon v-else class="icon-pending" :size="28"><Minus /></el-icon>
            </div>
            
            <div class="timeline-content">
              <div class="step-header">
                <div class="step-title">{{ step.step_name }}</div>
                <div class="step-badge">
                  <el-tag v-if="isRejectedStep(index)" type="danger" size="small">
                    已拒绝
                  </el-tag>
                  <el-tag v-else-if="isCompletedStep(index)" type="success" size="small">
                    已完成
                  </el-tag>
                  <el-tag v-else-if="isCurrentStep(index)" type="primary" size="small">
                    审批中
                  </el-tag>
                  <el-tag v-else type="info" size="small">
                    待审批
                  </el-tag>
                </div>
              </div>

              <div class="step-details">
                <div v-if="isCompletedStep(index)" class="detail-item">
                  <span class="detail-label">审批人：</span>
                  <span class="detail-value">{{ getCompletedApproverName(step) }}</span>
                </div>
                
                <div v-if="isCompletedStep(index) && step.completed_at" class="detail-item">
                  <span class="detail-label">完成时间：</span>
                  <span class="detail-value">{{ formatDateTime(step.completed_at) }}</span>
                </div>
                
                <div v-if="isCurrentStep(index)" class="detail-item">
                  <span class="detail-label">当前责任人：</span>
                  <span class="detail-value highlight">{{ getCurrentApprovers(index) }}</span>
                </div>
                
                <div v-if="isCurrentStep(index)" class="detail-item">
                  <span class="detail-label">状态：</span>
                  <span class="detail-value highlight">审批中</span>
                </div>
                
                <div v-if="isRejectedStep(index)" class="detail-item">
                  <span class="detail-label">拒绝人：</span>
                  <span class="detail-value">{{ getRejectedApproverName(step) }}</span>
                </div>
                
                <div v-if="isRejectedStep(index) && getRejectedTime(step)" class="detail-item">
                  <span class="detail-label">拒绝时间：</span>
                  <span class="detail-value">{{ formatDateTime(getRejectedTime(step)) }}</span>
                </div>
                
                <div v-if="getRejectReason(step)" class="detail-item detail-reject">
                  <span class="detail-label">拒绝理由：</span>
                  <span class="detail-value">{{ getRejectReason(step) }}</span>
                </div>
                
                <div v-if="isPendingStep(index)" class="detail-item">
                  <span class="detail-label">预计审批角色：</span>
                  <span class="detail-value">{{ getApproverRole(step) }}</span>
                </div>
              </div>

              <div v-if="isCurrentStep(index) && canApproveCurrentStep(step)" class="step-actions">
                <el-button type="success" size="small" @click="handleApprove(step)">
                  <el-icon class="mr-1"><CircleCheckFilled /></el-icon>
                  同意
                </el-button>
                <el-button type="danger" size="small" @click="handleReject(step)">
                  <el-icon class="mr-1"><CircleCloseFilled /></el-icon>
                  拒绝
                </el-button>
              </div>
            </div>
          </div>
          
          <div v-if="index < steps.length - 1" class="timeline-line">
            <div class="line-fill" :class="{ 'completed': isCompletedStep(index) }"></div>
          </div>
        </div>
      </div>

      <el-tooltip
        v-if="hoveredStep && getTooltipContent(hoveredStep)"
        :content="getTooltipContent(hoveredStep)"
        placement="top"
        class="timeline-tooltip"
      />
    </el-card>

    <el-dialog
      v-model="rejectModalVisible"
      title="拒绝审批"
      width="500px"
      @close="rejectModalVisible = false"
    >
      <el-form label-position="top">
        <el-form-item label="拒绝原因" required>
          <el-input
            v-model="rejectForm.reason"
            type="textarea"
            placeholder="请输入拒绝原因"
            :maxlength="500"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rejectModalVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmReject">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { 
  CircleCheckFilled, 
  Clock,
  Minus,
  CircleCloseFilled
} from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'

interface ApprovalStep {
  step_order: number
  step_name: string
  node_code?: string
  node_id?: number
  approvers: Array<{
    approver_id: string
    approver_name: string
    approved_at?: string
    rejected_at?: string
    comment?: string
  }>
  completed_at?: string
  comment?: string
}

interface Props {
  approvalDetail: {
    current_step: number
    approval_steps: ApprovalStep[]
    status: string
    flow?: any
    records?: any[]
  }
  showHistoryOnly?: boolean
}

const props = defineProps<Props>()
const emit = defineEmits(['approve', 'reject'])

const userStore = useUserStore()
const currentUserId = userStore.userInfo?.id ? String(userStore.userInfo.id) : ''

const rejectModalVisible = ref(false)
const rejectForm = ref({
  reason: ''
})
const currentRejectStep = ref<ApprovalStep | null>(null)
const hoveredStep = ref<ApprovalStep | null>(null)

const steps = computed(() => {
  return props.approvalDetail?.approval_steps || []
})

const isCurrentStep = (index: number) => {
  return index === props.approvalDetail?.current_step
}

const isCompletedStep = (index: number) => {
  return index < props.approvalDetail?.current_step && !isRejectedStep(index)
}

const isRejectedStep = (index: number) => {
  const step = steps.value[index]
  if (!step || !step.approvers) return false
  return step.approvers.some(a => a.rejected_at)
}

const isPendingStep = (index: number) => {
  return index > props.approvalDetail?.current_step
}

const getCompletedApproverName = (step: ApprovalStep) => {
  if (!step.approvers || step.approvers.length === 0) return '-'
  const approver = step.approvers.find(a => a.approved_at)
  return approver?.approver_name || '-'
}

const getRejectedApproverName = (step: ApprovalStep) => {
  if (!step.approvers || step.approvers.length === 0) return '-'
  const approver = step.approvers.find(a => a.rejected_at)
  return approver?.approver_name || '-'
}

const getRejectedTime = (step: ApprovalStep): string | undefined => {
  if (!step.approvers || step.approvers.length === 0) return undefined
  const approver = step.approvers.find(a => a.rejected_at)
  return approver?.rejected_at
}

const getRejectReason = (step: ApprovalStep) => {
  if (!step.approvers || step.approvers.length === 0) return undefined
  const approver = step.approvers.find(a => a.rejected_at)
  return approver?.comment
}

const getCurrentApprovers = (index: number) => {
  const step = steps.value[index]
  if (!step || !step.approvers) return '-'
  
  const pendingApprovers = step.approvers
    .filter(a => !a.approved_at && !a.rejected_at)
    .map(a => a.approver_name)
  
  return pendingApprovers.length > 0 ? pendingApprovers.join('、') : '-'
}

const getApproverRole = (step: ApprovalStep) => {
  const roleMap: Record<string, string> = {
    'SALES_DIRECTOR': '销售总监',
    'SALES_MANAGER': '销售经理',
    'FINANCE': '财务',
    'LEGAL': '法务',
    'GENERAL_MANAGER': '总经理',
    'ADMIN': '管理员'
  }
  return roleMap[step.node_code || ''] || '待定'
}

const canApproveCurrentStep = (step: ApprovalStep) => {
  if (!step.approvers) return false
  return step.approvers.some(
    a => a.approver_id === currentUserId && !a.approved_at && !a.rejected_at
  )
}

const handleMouseEnter = (step: ApprovalStep) => {
  hoveredStep.value = step
}

const handleMouseLeave = () => {
  hoveredStep.value = null
}

const getTooltipContent = (step: ApprovalStep): string => {
  if (!step.approvers || step.approvers.length === 0) return ''
  
  const approvedApprovers = step.approvers.filter(a => a.approved_at)
  const rejectedApprovers = step.approvers.filter(a => a.rejected_at)
  
  let content = `${step.step_name}\n\n`
  
  if (approvedApprovers.length > 0) {
    content += '已通过：\n'
    approvedApprovers.forEach(a => {
      const time = a.approved_at ? formatDateTime(a.approved_at) : ''
      content += `  ${a.approver_name} - ${time}\n`
      if (a.comment) {
        content += `  审批意见：${a.comment}\n`
      }
    })
  }
  
  if (rejectedApprovers.length > 0) {
    content += '\n已拒绝：\n'
    rejectedApprovers.forEach(a => {
      const time = a.rejected_at ? formatDateTime(a.rejected_at) : ''
      content += `  ${a.approver_name} - ${time}\n`
      if (a.comment) {
        content += `  拒绝理由：${a.comment}\n`
      }
    })
  }
  
  return content
}

const handleApprove = (step: ApprovalStep) => {
  emit('approve', step)
}

const handleReject = (step: ApprovalStep) => {
  currentRejectStep.value = step
  rejectModalVisible.value = true
}

const confirmReject = () => {
  if (!rejectForm.value.reason.trim()) {
    ElMessage.warning('请输入拒绝原因')
    return
  }
  
  if (currentRejectStep.value) {
    emit('reject', currentRejectStep.value, rejectForm.value.reason)
  }
  rejectModalVisible.value = false
  rejectForm.value.reason = ''
  currentRejectStep.value = null
}

const formatDateTime = (dateStr: string | undefined) => {
  if (!dateStr) return '-'
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
.approval-timeline {
  width: 100%;
}

.timeline-card {
  border-radius: 8px;
}

.timeline-container {
  display: flex;
  align-items: stretch;
  gap: 0;
  padding: 24px 0;
}

.timeline-item {
  flex: 1;
  min-width: 220px;
  position: relative;
  display: flex;
  flex-direction: column;
}

.timeline-node {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
  border: 2px solid var(--el-border-color);
  transition: all 0.3s;
  cursor: default;
}

.timeline-node:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.timeline-item.completed .timeline-node {
  background: var(--el-color-success-light-9);
  border-color: var(--el-color-success);
}

.timeline-item.active .timeline-node {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 3px var(--el-color-primary-light-7);
}

.timeline-item.rejected .timeline-node {
  background: var(--el-color-danger-light-9);
  border-color: var(--el-color-danger);
}

.timeline-item.pending .timeline-node {
  background: var(--el-fill-color-light);
  border-color: var(--el-border-color);
  opacity: 0.7;
}

.timeline-icon {
  margin-bottom: 12px;
  display: flex;
  justify-content: center;
}

.timeline-item.completed .timeline-icon {
  color: var(--el-color-success);
}

.timeline-item.active .timeline-icon {
  color: var(--el-color-primary);
}

.timeline-item.rejected .timeline-icon {
  color: var(--el-color-danger);
}

.timeline-item.pending .timeline-icon {
  color: var(--el-text-color-placeholder);
}

.timeline-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.step-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.step-title {
  font-weight: 600;
  font-size: 14px;
  line-height: 1.4;
  flex: 1;
}

.step-badge {
  flex-shrink: 0;
}

.step-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
}

.detail-item {
  display: flex;
  gap: 4px;
  line-height: 1.5;
}

.detail-label {
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}

.detail-value {
  color: var(--el-text-color-regular);
  word-break: break-word;
}

.detail-value.highlight {
  color: var(--el-color-primary);
  font-weight: 500;
}

.detail-reject {
  margin-top: 4px;
  padding: 6px;
  background: rgba(var(--el-color-danger-rgb), 0.1);
  border-radius: 4px;
}

.detail-reject .detail-label {
  color: var(--el-color-danger);
  font-weight: 500;
}

.detail-reject .detail-value {
  color: var(--el-color-danger);
}

.step-actions {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
  display: flex;
  justify-content: center;
  gap: 8px;
}

.mr-1 {
  margin-right: 4px;
}

.timeline-line {
  position: absolute;
  top: 50%;
  right: -20px;
  width: 40px;
  height: 2px;
  background: var(--el-border-color);
  transform: translateY(-50%);
  z-index: 0;
}

.timeline-line .line-fill {
  width: 100%;
  height: 100%;
  background: var(--el-border-color);
  transition: all 0.3s;
}

.timeline-line .line-fill.completed {
  background: var(--el-color-success);
}

.timeline-tooltip {
  pointer-events: none;
}

@media (max-width: 768px) {
  .timeline-container {
    flex-direction: column;
    gap: 16px;
  }
  
  .timeline-line {
    display: none;
  }
  
  .timeline-item {
    min-width: auto;
    width: 100%;
  }
  
  .step-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
