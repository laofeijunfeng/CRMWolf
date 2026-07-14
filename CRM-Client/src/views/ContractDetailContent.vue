<template>
  <div class="contract-detail-content">
    <!-- Content Area -->
    <div class="detail-content">
      <div v-loading="loading" class="content-wrapper">
        <Card v-if="!contractInfo" class="info-card">
          <CardContent class="flex items-center justify-center min-h-[200px]">
            <div class="text-center text-muted-foreground">
              合同信息加载失败
            </div>
          </CardContent>
        </Card>

        <Card v-else class="info-card">
          <CardContent>
            <!-- Basic Info -->
            <div class="basic-info">
              <!-- Title Section -->
              <div class="info-top">
                <div class="info-left">
                  <div class="title-section">
                    <div class="contract-avatar">{{ contractInfo?.contract_name?.charAt(0) || '合' }}</div>
                    <div class="title-content">
                      <h2 class="contract-name">{{ contractInfo?.contract_name }}</h2>
                      <div class="status-tags">
                        <span :class="['status-tag', getStatusClass(contractInfo?.status || '')]">
                          {{ getStatusText(contractInfo?.status || '') }}
                        </span>
                        <span :class="['status-tag', contractInfo?.license_type === 'SUBSCRIPTION' ? 'status-subscription' : 'status-perpetual']">
                          {{ contractInfo?.license_type === 'SUBSCRIPTION' ? '订阅' : '买断' }}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="info-right">
                  <div class="amount-section">
                    <div class="amount-label">合同总金额</div>
                    <div class="amount-value">¥{{ formatAmount(contractInfo?.total_amount || '0') }}</div>
                  </div>
                  <div class="action-buttons">
                    <Button
                      v-if="canSubmitApproval"
                      @click="handleSubmitApproval"
                      :disabled="submitting"
                      class="w-full"
                    >
                      <Loader2 v-if="submitting" class="w-4 h-4 mr-2 animate-spin" />
                      提交审批
                    </Button>
                    <Button
                      v-if="canWithdraw"
                      variant="outline"
                      @click="handleWithdrawApproval"
                      :disabled="withdrawing"
                      class="w-full"
                    >
                      <Loader2 v-if="withdrawing" class="w-4 h-4 mr-2 animate-spin" />
                      撤回审批
                    </Button>
                  </div>
                </div>
              </div>

              <div class="info-divider"></div>

              <!-- Attributes Grid -->
              <div class="info-bottom">
                <div class="attributes-grid">
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <Ticket class="attribute-icon" />
                      <span class="attribute-label">合同编号</span>
                    </div>
                    <span class="attribute-value">{{ contractInfo?.contract_number || '-' }}</span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <User class="attribute-icon" />
                      <span class="attribute-label">关联客户</span>
                    </div>
                    <span class="attribute-value">{{ contractInfo?.customer_info?.account_name || '-' }}</span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <TrendingUp class="attribute-icon" />
                      <span class="attribute-label">关联商机</span>
                    </div>
                    <span class="attribute-value">{{ contractInfo?.opportunity_info?.opportunity_name || '-' }}</span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <PenLine class="attribute-icon" />
                      <span class="attribute-label">签约人</span>
                    </div>
                    <span class="attribute-value" :class="{ 'value-empty': !signingContactName || signingContactName === '-' }">{{ signingContactName }}</span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <Users class="attribute-icon" />
                      <span class="attribute-label">采购用户数</span>
                    </div>
                    <span class="attribute-value">{{ contractInfo?.user_count || '-' }}</span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <Coins class="attribute-icon" />
                      <span class="attribute-label">标准单价</span>
                    </div>
                    <span class="attribute-value">¥{{ formatAmount(contractInfo?.standard_unit_price || '0') }}</span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <Calendar class="attribute-icon" />
                      <span class="attribute-label">订阅年限</span>
                    </div>
                    <span class="attribute-value">{{ contractInfo?.subscription_years ? contractInfo.subscription_years + '年' : '-' }}</span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <Users class="attribute-icon" />
                      <span class="attribute-label">创建人</span>
                    </div>
                    <span class="attribute-value" :class="{ 'value-empty': !contractInfo?.creator_info?.name }">{{ contractInfo?.creator_info?.name || '-' }}</span>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <!-- Core Function Area -->
        <div class="core-section">
          <div class="payment-section">
            <PaymentPlans
              v-if="contractInfo && ['SIGNED', 'EFFECTIVE', 'EXPIRED'].includes(contractInfo.status || '')"
              :contract-id="contractInfo.id"
              :contract-status="contractInfo.status"
              :contract-info="contractInfo"
              @plan-updated="handlePaymentPlanUpdated"
              ref="paymentPlansRef"
            />
            <Card v-else class="placeholder-card">
              <CardContent class="flex items-center justify-center min-h-[200px]">
                <div class="text-center text-muted-foreground">
                  回款计划仅在已签署、生效或已到期的合同中显示
                </div>
              </CardContent>
            </Card>
          </div>

          <div class="approval-section">
            <ApprovalProgressCompact
              v-if="approvalDetail"
              :approval-detail="approvalDetail"
              :can-approve="canApprove"
              @approve="handleApprove"
              @reject="handleReject"
            />
            <Card v-else class="placeholder-card">
              <CardContent class="flex items-center justify-center min-h-[200px]">
                <div class="text-center text-muted-foreground">
                  {{ getApprovalPlaceholderText() }}
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      <!-- Reject Dialog -->
      <Dialog v-model:open="rejectModalVisible">
        <DialogContent class="sm:max-w-[600px]">
          <DialogHeader>
            <DialogTitle>拒绝审批</DialogTitle>
            <DialogDescription>
              您正在拒绝该合同的审批申请，此操作不可撤销。
            </DialogDescription>
          </DialogHeader>

          <div class="space-y-4">
            <div class="space-y-2">
              <Label for="reject-reason">拒绝原因 <span class="text-destructive">*</span></Label>
              <Textarea
                id="reject-reason"
                v-model="rejectForm.reason"
                placeholder="请输入拒绝原因"
                :maxlength="500"
                rows="4"
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" @click="rejectModalVisible = false">取消</Button>
            <Button variant="destructive" @click="confirmReject" :disabled="rejecting">
              <Loader2 v-if="rejecting" class="w-4 h-4 mr-2 animate-spin" />
              确认拒绝
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, reactive } from 'vue'
import { toast } from 'vue-sonner'
import {
  Ticket,
  User,
  TrendingUp,
  PenLine,
  Coins,
  Calendar,
  Users,
  Loader2
} from 'lucide-vue-next'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent } from '@/components/ui/card'
import contractApi, { type ContractResponse } from '@/api/contract'
import approvalApi from '@/api/approval'
import ApprovalProgressCompact from '@/components/ApprovalProgressCompact.vue'
import PaymentPlans from '@/components/PaymentPlans.vue'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'
import { confirmDialog } from '@/utils/confirmDialog'

// Props
const props = defineProps<{
  recordId: number
}>()

// Emits
const emit = defineEmits<{
  refresh: []
  deleted: []
}>()

// Stores
const userStore = useUserStore()
const permissionStore = usePermissionStore()
const currentUserId = userStore.userInfo?.id ? String(userStore.userInfo.id) : ''

// State
const contractInfo = ref<ContractResponse | null>(null)
const approvalDetail = ref<ApprovalDetail | null>(null)
const paymentPlansRef = ref<InstanceType<typeof PaymentPlans> | null>(null)
const loading = ref(false)
const submitting = ref(false)
const withdrawing = ref(false)
const approving = ref(false)
const rejecting = ref(false)
const rejectModalVisible = ref(false)
const rejectForm = reactive({
  reason: ''
})

// Computed
const signingContactName = computed(() => {
  return contractInfo.value?.contact_info?.name || '-'
})

const canEditContract = computed(() => {
  if (contractInfo.value?.status !== 'DRAFT') {
    return false
  }
  return permissionStore.canEditOwn('contract') || permissionStore.canEditAll('contract')
})

const canSubmitApproval = computed(() => {
  return permissionStore.canSubmitApproval('contract') && contractInfo.value?.status === 'DRAFT'
})

const canWithdraw = computed(() => {
  return permissionStore.canCancelApproval('contract') &&
    contractInfo.value?.status === 'PENDING_REVIEW' &&
    contractInfo.value.creator_id === currentUserId
})

const canApprove = computed(() => {
  if (contractInfo.value?.status !== 'PENDING_REVIEW' || !approvalDetail.value) {
    return false
  }

  const isOwner = contractInfo.value.creator_id === currentUserId
  const hasApproveOwnPermission = permissionStore.canApproveOwn('contract')
  const hasApproveAllPermission = permissionStore.canApproveAll('contract')

  if (!hasApproveOwnPermission && !hasApproveAllPermission) {
    return false
  }

  if (isOwner && !hasApproveOwnPermission) {
    return false
  }

  const currentStep = approvalDetail.value.current_step
  const currentStepInfo = approvalDetail.value.approval_steps?.[currentStep]

  if (!currentStepInfo) {
    return false
  }

  const userRoles = userStore.userInfo?.roles || []

  if (!Array.isArray(userRoles) || userRoles.length === 0) {
    return false
  }

  const roleCodes = userRoles.map(r => r.code)

  if (roleCodes.includes('SYSTEM_ADMIN')) {
    return true
  }

  if (hasApproveAllPermission) {
    return true
  }

  const nodeRole = currentStepInfo.approver_role

  if (!nodeRole) {
    return false
  }

  return roleCodes.includes(nodeRole)
})

// Methods
const getStatusText = (status: string): string => {
  const map: Record<string, string> = {
    DRAFT: '草稿',
    PENDING_REVIEW: '审批中',
    SIGNED: '已签署',
    EFFECTIVE: '生效中',
    EXPIRED: '已到期',
    TERMINATED: '已终止'
  }
  return map[status] || '未知'
}

const getStatusClass = (status: string): string => {
  const map: Record<string, string> = {
    DRAFT: 'status-draft',
    PENDING_REVIEW: 'status-pending',
    SIGNED: 'status-signed',
    EFFECTIVE: 'status-effective',
    EXPIRED: 'status-expired',
    TERMINATED: 'status-terminated'
  }
  return map[status] || 'status-draft'
}

const formatAmount = (amount: number | string): string => {
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const fetchContractInfo = async (): Promise<void> => {
  loading.value = true
  try {
    const data = await contractApi.getContract(props.recordId)
    contractInfo.value = data
    console.log('合同详情数据:', data)
  } catch (error: unknown) {
    console.error('获取合同详情失败', error)
    toast.error('获取合同详情失败')
  } finally {
    loading.value = false
  }
}

const fetchApprovalDetail = async (): Promise<void> => {
  const statusesWithApproval = ['PENDING_REVIEW', 'SIGNED', 'EFFECTIVE', 'EXPIRED', 'TERMINATED']

  if (!contractInfo.value || !statusesWithApproval.includes(contractInfo.value.status)) {
    approvalDetail.value = null
    return
  }

  try {
    const response = await approvalApi.getContractApprovalDetail(contractInfo.value.id)
    const data = response.data || response
    approvalDetail.value = transformApprovalData(data as ApprovalDetailFromAPI)
  } catch (error: unknown) {
    if (error.response?.status !== 404) {
      console.error('获取审批详情失败', error)
    }
    approvalDetail.value = null
  }
}

// Approval Data Types
interface ApprovalRecordFromAPI {
  record_id: number
  node_name: string
  approver_id: string
  approver_name: string
  action: string
  comment?: string
  created_at?: string
}

interface ApprovalDetailFromAPI {
  approval_id: number
  contract_id: number
  status: string
  submitter_id: string
  submitter_name: string
  created_time: string
  flow: {
    id: number
    flow_name: string
    flow_code: string
    nodes: {
      id: number
      flow_id: number
      node_name: string
      node_code: string
      node_order: number
      description: string
      approve_role: string
      is_required: number
    }[]
  }
  current_node_id: number
  records: {
    id: number
    approval_id: number
    node_id: number
    node_name: string | null
    approver_id: string
    approver_name: string
    action: string
    comment: string | null
    created_time: string
  }[]
}

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
  status: 'PENDING' | 'APPROVED' | 'REJECTED'
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

const transformApprovalData = (apiData: ApprovalDetailFromAPI): ApprovalDetail | null => {
  if (!apiData) return null

  const nodes = apiData.flow?.nodes || []
  const nodeMap = new Map<number, ApprovalStep>()

  const submitRecord = apiData.records.find(r => r.action === 'SUBMIT')

  const submittedStep: ApprovalStep = {
    step_order: 0,
    step_name: '已提交',
    approver_role: '',
    status: 'APPROVED',
    approval_records: submitRecord ? [{
      approver_id: submitRecord.approver_id,
      approver_name: submitRecord.approver_name,
      action: submitRecord.action,
      created_time: submitRecord.created_time,
      comment: submitRecord.comment ?? undefined
    }] : []
  }

  nodeMap.set(-1, submittedStep)

  nodes.forEach(node => {
    const nodeRecords = apiData.records.filter(r => r.node_id === node.id)
    let stepStatus: 'PENDING' | 'APPROVED' | 'REJECTED' = 'PENDING'

    if (nodeRecords.some(r => r.action === 'APPROVE')) {
      stepStatus = 'APPROVED'
    } else if (nodeRecords.some(r => r.action === 'REJECT')) {
      stepStatus = 'REJECTED'
    }

    nodeMap.set(node.id, {
      step_order: node.node_order,
      step_name: node.node_name,
      approver_role: node.approve_role,
      status: stepStatus,
      approval_records: nodeRecords.map(r => ({
        approver_id: r.approver_id,
        approver_name: r.approver_name,
        action: r.action,
        created_time: r.created_time,
        comment: r.comment ?? undefined
      }))
    })
  })

  const isCompleted = ['APPROVED', 'REJECTED', 'CANCELLED'].includes(apiData.status)

  if (isCompleted) {
    const maxOrder = Math.max(...nodes.map(n => n.node_order), 0)
    const completedStep: ApprovalStep = {
      step_order: maxOrder + 1,
      step_name: '已完成',
      approver_role: '',
      status: apiData.status as 'APPROVED' | 'REJECTED',
      approval_records: []
    }
    nodeMap.set(-2, completedStep)
  }

  const stepsArray = Array.from(nodeMap.values())
    .sort((a, b) => a.step_order - b.step_order)

  const currentNodeId = apiData.current_node_id
  let currentStepIndex = 0

  if (currentNodeId) {
    currentStepIndex = stepsArray.findIndex(s => {
      const node = nodes.find(n => n.id === currentNodeId)
      return s.step_name === node?.node_name
    })
  }

  if (currentStepIndex === -1) {
    currentStepIndex = 0
  }

  const transformed: ApprovalDetail = {
    current_step: Math.max(0, currentStepIndex),
    approval_steps: stepsArray,
    status: apiData.status,
    submitter_name: apiData.submitter_name,
    submitted_at: apiData.created_time,
    flow_name: apiData.flow?.flow_name
  }

  return transformed
}

// Event Handlers
const handleSubmitApproval = async (): Promise<void> => {
  if (!contractInfo.value) return

  const confirmed = await confirmDialog(
    `确定要提交合同"${contractInfo.value.contract_name}"进行审批吗？`,
    '确认提交'
  )

  if (!confirmed) return

  try {
    submitting.value = true
    await approvalApi.submitContractApproval(contractInfo.value.id)
    toast.success('合同已提交审批')
    await fetchContractInfo()
    await fetchApprovalDetail()
    emit('refresh')
  } catch (error: unknown) {
    console.error('提交审批失败', error)
    toast.error('提交审批失败')
  } finally {
    submitting.value = false
  }
}

const handleWithdrawApproval = async (): Promise<void> => {
  if (!contractInfo.value) return

  const confirmed = await confirmDialog(
    `确定要撤回合同"${contractInfo.value.contract_name}"的审批申请吗？`,
    '确认撤回'
  )

  if (!confirmed) return

  try {
    withdrawing.value = true
    await approvalApi.cancelContractApproval(contractInfo.value.id)
    toast.success('审批已撤回')
    await fetchContractInfo()
    approvalDetail.value = null
    emit('refresh')
  } catch (error: unknown) {
    console.error('撤回失败', error)
    toast.error('撤回审批失败')
  } finally {
    withdrawing.value = false
  }
}

const handleApprove = async (): Promise<void> => {
  if (!contractInfo.value) return

  const confirmed = await confirmDialog(
    `确定要同意合同"${contractInfo.value.contract_name}"的审批申请吗？`,
    '确认同意'
  )

  if (!confirmed) return

  try {
    approving.value = true
    await approvalApi.approveContract(contractInfo.value.id, { action: 'APPROVE' })
    toast.success('审批已同意')
    await fetchContractInfo()
    await fetchApprovalDetail()
    emit('refresh')
  } catch (error: unknown) {
    console.error('审批失败', error)
    toast.error('审批失败')
  } finally {
    approving.value = false
  }
}

const handleReject = (): void => {
  rejectModalVisible.value = true
}

const confirmReject = async (): Promise<void> => {
  if (!contractInfo.value) return
  if (!rejectForm.reason.trim()) {
    toast.warning('请输入拒绝原因')
    return
  }

  try {
    rejecting.value = true
    await approvalApi.approveContract(contractInfo.value.id, {
      action: 'REJECT',
      comment: rejectForm.reason
    })
    toast.success('审批已拒绝')
    rejectModalVisible.value = false
    rejectForm.reason = ''
    await fetchContractInfo()
    await fetchApprovalDetail()
    emit('refresh')
  } catch (error: unknown) {
    console.error('拒绝失败', error)
    toast.error('拒绝审批失败')
  } finally {
    rejecting.value = false
  }
}

const handlePaymentPlanUpdated = (): void => {
  if (paymentPlansRef.value) {
    paymentPlansRef.value.refresh()
  }
}

const getApprovalPlaceholderText = (): string => {
  if (!contractInfo.value) return '暂无审批信息'

  const statusTextMap: Record<string, string> = {
    'DRAFT': '草稿状态的合同尚未提交审批',
    'PENDING_REVIEW': '加载审批信息中...',
    'SIGNED': '已签署合同的审批记录',
    'EFFECTIVE': '生效中合同的审批记录',
    'EXPIRED': '已到期合同的审批记录',
    'TERMINATED': '已终止合同的审批记录'
  }

  return statusTextMap[contractInfo.value.status] || '暂无审批信息'
}

// Expose methods for parent component
defineExpose({
  refresh: fetchContractInfo,
  canEdit: canEditContract
})

// Lifecycle
onMounted(async () => {
  await fetchContractInfo()
  await fetchApprovalDetail()
})

// Watch recordId changes
watch(() => props.recordId, async (newId) => {
  if (newId) {
    await fetchContractInfo()
    await fetchApprovalDetail()
  }
})
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.contract-detail-content {
  padding: 0;
  background: $wolf-bg-page-v2;
  min-height: 0;
  flex: 1;
}

.detail-content {
  padding: $wolf-page-padding-v2;
}

.content-wrapper {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
}

.info-card {
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-v2;
  box-shadow: $wolf-shadow-card-v2;
}

.basic-info {
  padding: 0;
}

.info-top {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: $wolf-space-lg-v2;
}

.info-left {
  .title-section {
    display: flex;
    gap: $wolf-space-md-v2;
    align-items: flex-start;
  }

  .contract-avatar {
    width: 48px;
    height: 48px;
    border-radius: $wolf-radius-full-v2;
    background: $wolf-primary-light-v2;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    font-weight: $wolf-font-weight-semibold-v2;
    color: $wolf-primary-v2;
    flex-shrink: 0;
  }

  .title-content {
    flex: 1;

    .contract-name {
      margin: 0 0 $wolf-space-sm-v2 0;
      font-size: $wolf-font-size-title-v2;
      font-weight: $wolf-font-weight-semibold-v2;
      color: $wolf-text-primary-v2;
      line-height: $wolf-line-height-title-v2;
    }

    .status-tags {
      display: flex;
      gap: $wolf-space-xs-v2;
      flex-wrap: wrap;
    }
  }
}

.info-divider {
  height: 1px;
  background: $wolf-border-light-v2;
  margin: $wolf-space-lg-v2 0;
}

.info-bottom {
  .attributes-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: $wolf-space-md-v2 $wolf-space-lg-v2;
  }

  .attribute-item {
    display: flex;
    flex-direction: column;
    gap: $wolf-space-xs-v2;
  }

  .attribute-header {
    display: flex;
    align-items: center;
    gap: $wolf-space-xs-v2;
  }

  .attribute-icon {
    width: 14px;
    height: 14px;
    color: $wolf-text-tertiary-v2;
    flex-shrink: 0;
  }

  .attribute-label {
    font-size: $wolf-font-size-auxiliary-v2;
    color: $wolf-text-tertiary-v2;
    font-weight: $wolf-font-weight-normal-v2;
  }

  .attribute-value {
    font-size: $wolf-font-size-body-v2;
    color: $wolf-text-primary-v2;
    font-weight: $wolf-font-weight-medium-v2;
    line-height: $wolf-line-height-body-v2;

    &.value-empty {
      color: $wolf-text-placeholder-v2;
    }
  }
}

.info-right {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-end;
  gap: $wolf-space-md-v2;

  .amount-section {
    text-align: right;

    .amount-label {
      font-size: $wolf-font-size-auxiliary-v2;
      color: $wolf-text-tertiary-v2;
      margin-bottom: $wolf-space-xs-v2;
    }

    .amount-value {
      font-size: 24px;
      font-weight: $wolf-font-weight-semibold-v2;
      color: $wolf-primary-v2;
      line-height: $wolf-line-height-title-v2;
    }
  }

  .action-buttons {
    display: flex;
    flex-direction: column;
    gap: $wolf-space-xs-v2;
    width: 100%;
  }
}

.status-tag {
  display: inline-flex;
  padding: 4px 8px;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-normal-v2;
  border-radius: $wolf-radius-sm-v2;
}

.status-draft {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-tertiary-v2;
}

.status-pending {
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
}

.status-signed {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-secondary-v2;
}

.status-effective {
  background: $wolf-success-bg-v2;
  color: $wolf-success-text-v2;
}

.status-expired {
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-text-v2;
}

.status-terminated {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-placeholder-v2;
}

.status-subscription {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-tertiary-v2;
}

.status-perpetual {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-secondary-v2;
}

.core-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $wolf-space-lg-v2;
}

.payment-section,
.approval-section {
  min-height: 400px;
}

.placeholder-card {
  height: 100%;
  min-height: 400px;
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-v2;
  box-shadow: $wolf-shadow-card-v2;
}

// Responsive
@media (max-width: 1200px) {
  .info-top {
    grid-template-columns: 1fr;
  }

  .info-left {
    .title-section {
      flex-direction: column;
      text-align: center;
    }
  }

  .info-right {
    align-items: center;

    .amount-section {
      text-align: center;
    }

    .action-buttons {
      flex-direction: row;
      flex-wrap: wrap;
      justify-content: center;
    }
  }

  .info-bottom {
    .attributes-grid {
      grid-template-columns: repeat(2, 1fr);
    }
  }

  .core-section {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .info-bottom {
    .attributes-grid {
      grid-template-columns: 1fr;
    }
  }

  .detail-content {
    padding: $wolf-space-md-v2;
  }
}
</style>