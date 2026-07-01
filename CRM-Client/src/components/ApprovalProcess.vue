<template>
  <el-card shadow="never" class="approval-process-card" v-loading="loading">
    <template #header>
      <div class="card-header">
        <span>审批流程</span>
        <div v-if="canSubmitApproval">
          <el-button type="primary" @click="handleSubmitApproval" :loading="submitting">
            提交审批
          </el-button>
        </div>
        <div v-else-if="canCancel">
          <el-button @click="handleCancel" :loading="cancelling">
            <el-icon><RefreshLeft /></el-icon>
            撤回审批
          </el-button>
        </div>
      </div>
    </template>

    <el-empty v-if="contractStatus === 'DRAFT'" description="此合同尚未提交审批">
      <template #image>
        <el-icon :size="60"><Document /></el-icon>
      </template>
    </el-empty>

    <div v-else-if="approvalDetail" class="approval-content">
      <ApprovalTimeline 
        :approval-detail="approvalDetail" 
        :show-history-only="isFinalStatus"
        @approve="handleTimelineApprove"
        @reject="handleTimelineReject"
      />
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { 
  RefreshLeft, 
  Document 
} from '@element-plus/icons-vue'
import ApprovalTimeline from './ApprovalTimeline.vue'
import approvalApi from '@/api/approval'
import { useUserStore } from '@/stores/user'

interface Props {
  contractId: number
  contractStatus: string
  contractOwnerId?: string
  contractCreatorId?: string
}

const props = defineProps<Props>()
const emit = defineEmits(['status-updated'])

const userStore = useUserStore()
const currentUserId = userStore.userInfo?.id ? String(userStore.userInfo.id) : ''

const loading = ref(false)
const submitting = ref(false)
const approving = ref(false)
const rejecting = ref(false)
const cancelling = ref(false)
const approvalDetail = ref<TransformedApprovalDetail | null>(null)

const handleTimelineApprove = async (_step: { id: number }) => {
  approving.value = true
  try {
    await approvalApi.approveContract(props.contractId, { action: 'APPROVE', comment: '' })
    ElMessage.success('审批通过')
    emit('status-updated')
    await fetchApprovalDetail()
  } catch (error: unknown) {
    console.error('审批失败', error)
    ElMessage.error(error.response?.data?.detail || '审批失败')
  } finally {
    approving.value = false
  }
}

const handleTimelineReject = async (_step: { id: number }, reason: string) => {
  rejecting.value = true
  try {
    await approvalApi.approveContract(props.contractId, { 
      action: 'REJECT',
      comment: reason 
    })
    ElMessage.success('已拒绝，合同已退回草稿状态')
    emit('status-updated', 'DRAFT')
    approvalDetail.value = null
  } catch (error: unknown) {
    console.error('拒绝审批失败', error)
    ElMessage.error(error.response?.data?.detail || '拒绝审批失败')
  } finally {
    rejecting.value = false
  }
}

interface ApproverInfo {
  approver_id: string
  approver_name: string
  approved_at?: string
  rejected_at?: string
  comment?: string
}

interface ApprovalStepInfo {
  step_order: number
  step_name: string
  node_code: string
  node_id: number
  approvers: ApproverInfo[]
  completed_at?: string
  comment?: string
}

interface ApprovalFlowInfo {
  id: number
  flow_name: string
  nodes: ApprovalNodeInfo[]
}

interface ApprovalNodeInfo {
  id: number
  node_order: number
  node_name: string
  node_code: string
}

interface ApprovalRecordInfo {
  id: number
  node_id: number
  approver_id: string
  approver_name: string
  action: string
  comment?: string
  created_time: string
}

interface TransformedApprovalDetail {
  current_step: number
  approval_steps: ApprovalStepInfo[]
  status: string
  flow: ApprovalFlowInfo
  records: ApprovalRecordInfo[]
}

const canSubmitApproval = computed(() => {
  return props.contractStatus === 'DRAFT'
})

const canCancel = computed(() => {
  return props.contractStatus === 'PENDING_REVIEW' && 
         props.contractCreatorId === currentUserId
})

const isFinalStatus = computed(() => {
  return ['SIGNED', 'EFFECTIVE', 'EXPIRED', 'TERMINATED'].includes(props.contractStatus)
})

const transformApprovalData = (apiData: unknown): TransformedApprovalDetail | null => {
  if (!apiData) return null

  const data = apiData as { status?: string; flow?: ApprovalFlowInfo; records?: ApprovalRecordInfo[] }

  const transformed: TransformedApprovalDetail = {
    current_step: 0,
    approval_steps: [],
    status: data.status || '',
    flow: data.flow || { id: 0, flow_name: '', nodes: [] },
    records: data.records || []
  }

  if (data.flow && data.flow.nodes) {
    transformed.approval_steps = data.flow.nodes.map((node: ApprovalNodeInfo): ApprovalStepInfo => ({
      step_order: node.node_order,
      step_name: node.node_name,
      node_code: node.node_code,
      node_id: node.id,
      approvers: [],
      comment: undefined
    }))
    
    if (apiData.current_node_id) {
      const currentNodeIndex = transformed.approval_steps.findIndex(
        (step) => step.node_id === apiData.current_node_id
      )
      if (currentNodeIndex >= 0) {
        transformed.current_step = currentNodeIndex
      }
    }
  }
  
  if (data.records) {
    data.records.forEach((record: ApprovalRecordInfo) => {
      const stepIndex = transformed.approval_steps.findIndex(
        (step) => step.node_id === record.node_id
      )
      
      if (stepIndex >= 0) {
        const step = transformed.approval_steps[stepIndex]
        
        if (record.action === 'SUBMIT') {
          if (stepIndex < transformed.current_step) {
            step.completed_at = record.created_time
          }
        } else if (record.action === 'APPROVE') {
          const approver: ApproverInfo = {
            approver_id: record.approver_id,
            approver_name: record.approver_name,
            approved_at: record.created_time,
            comment: record.comment
          }
          
          const existingApprover = step.approvers.find(
            (a) => a.approver_id === record.approver_id
          )
          
          if (existingApprover) {
            Object.assign(existingApprover, approver)
          } else {
            step.approvers.push(approver)
          }
          
          step.completed_at = record.created_time
        } else if (record.action === 'REJECT') {
          const approver: ApproverInfo = {
            approver_id: record.approver_id,
            approver_name: record.approver_name,
            rejected_at: record.created_time,
            comment: record.comment
          }
          
          const existingApprover = step.approvers.find(
            (a) => a.approver_id === record.approver_id
          )
          
          if (existingApprover) {
            Object.assign(existingApprover, approver)
          } else {
            step.approvers.push(approver)
          }
        }
      }
    })
  }
  
  return transformed
}

const fetchApprovalDetail = async () => {
  if (props.contractStatus === 'DRAFT') {
    approvalDetail.value = null
    return
  }

  loading.value = true
  try {
    const data = await approvalApi.getContractApprovalDetail(props.contractId)
    approvalDetail.value = transformApprovalData(data)
  } catch (error: unknown) {
    const axiosError = error as { response?: { status?: number } }
    console.log('审批详情:', axiosError.response?.status)
    if (axiosError.response?.status === 404) {
      approvalDetail.value = null
    } else {
      console.error('获取审批详情失败', error)
    }
  } finally {
    loading.value = false
  }
}

const handleSubmitApproval = async () => {
  submitting.value = true
  try {
    await approvalApi.submitContractApproval(props.contractId, { comment: '' })
    ElMessage.success('提交成功，已进入审批流程')
    emit('status-updated', 'PENDING_REVIEW')
  } catch (error: unknown) {
    console.error('提交审批失败', error)
    const axiosError = error as { response?: { data?: { errors?: { msg?: string; message?: string }[]; detail?: string } } }
    if (axiosError.response?.data?.errors) {
      const validationErrors = axiosError.response.data.errors
      const errorMessages = validationErrors.map(e => e.msg || e.message).join('; ')
      ElMessage.error(`提交审批失败: ${errorMessages}`)
    } else {
      ElMessage.error(axiosError.response?.data?.detail || '提交审批失败')
    }
  } finally {
    submitting.value = false
  }
}

const handleCancel = () => {
  ElMessageBox.confirm(
    '确定要撤回审批吗？撤回后合同将退回草稿状态。',
    '确认撤回',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    cancelling.value = true
    try {
      await approvalApi.cancelContractApproval(props.contractId)
      ElMessage.success('已撤回审批')
      emit('status-updated', 'DRAFT')
      approvalDetail.value = null
    } catch (error: unknown) {
      console.error('撤回审批失败', error)
      ElMessage.error(error.response?.data?.detail || '撤回审批失败')
    } finally {
      cancelling.value = false
    }
  }).catch(() => {
  })
}

watch(() => props.contractStatus, () => {
  fetchApprovalDetail()
}, { immediate: true })

onMounted(() => {
  fetchApprovalDetail()
})
</script>

<style scoped>
.approval-process-card {
  margin-top: 16px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.approval-content {
  padding: 16px 0;
}

.approval-history {
  padding: 16px 0;
}
</style>
