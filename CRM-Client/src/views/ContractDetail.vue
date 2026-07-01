<template>
  <div class="contract-detail-page">
    <!-- 页面头部 -->
    <div class="page-header-bar">
      <div class="header-left">
        <el-button type="text" class="back-btn" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h1 class="wolf-page-title">{{ contractInfo?.contract_name || '合同详情' }}</h1>
      </div>
      <div class="header-right">
        <el-button v-if="canEditContract" type="primary" class="primary-btn" @click="handleEdit">
          编辑
        </el-button>
      </div>
    </div>

    <!-- 内容区 -->
    <div class="detail-content">
      <div v-loading="loading" class="content-wrapper">
        <el-card v-if="!contractInfo" shadow="never" class="info-card">
          <el-empty description="合同信息加载失败" />
        </el-card>

        <el-card v-else shadow="never" class="info-card">
          <!-- 基本信息 -->
          <div class="basic-info">
            <!-- 标题区 -->
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
                  <el-button v-if="canSubmitApproval" type="primary" class="primary-btn" @click="handleSubmitApproval" :loading="submitting">
                    提交审批
                  </el-button>
                  <el-button v-if="canWithdraw" class="default-btn" @click="handleWithdrawApproval" :loading="withdrawing">
                    撤回审批
                  </el-button>
                </div>
              </div>
            </div>

            <div class="info-divider"></div>

            <!-- 属性网格 -->
            <div class="info-bottom">
              <div class="attributes-grid">
                <div class="attribute-item">
                  <div class="attribute-header">
                    <el-icon class="attribute-icon"><Ticket /></el-icon>
                    <span class="attribute-label">合同编号</span>
                  </div>
                  <span class="attribute-value">{{ contractInfo?.contract_number || '-' }}</span>
                </div>
                <div class="attribute-item">
                  <div class="attribute-header">
                    <el-icon class="attribute-icon"><User /></el-icon>
                    <span class="attribute-label">关联客户</span>
                  </div>
                  <span class="attribute-value">{{ contractInfo?.customer_info?.account_name || '-' }}</span>
                </div>
                <div class="attribute-item">
                  <div class="attribute-header">
                    <el-icon class="attribute-icon"><TrendCharts /></el-icon>
                    <span class="attribute-label">关联商机</span>
                  </div>
                  <span class="attribute-value">{{ contractInfo?.opportunity_info?.opportunity_name || '-' }}</span>
                </div>
                <div class="attribute-item">
                  <div class="attribute-header">
                    <el-icon class="attribute-icon"><EditPen /></el-icon>
                    <span class="attribute-label">签约人</span>
                  </div>
                  <span class="attribute-value" :class="{ 'value-empty': !signingContactName || signingContactName === '-' }">{{ signingContactName }}</span>
                </div>
                <div class="attribute-item">
                  <div class="attribute-header">
                    <el-icon class="attribute-icon"><UserFilled /></el-icon>
                    <span class="attribute-label">采购用户数</span>
                  </div>
                  <span class="attribute-value">{{ contractInfo?.user_count || '-' }}</span>
                </div>
                <div class="attribute-item">
                  <div class="attribute-header">
                    <el-icon class="attribute-icon"><Coin /></el-icon>
                    <span class="attribute-label">标准单价</span>
                  </div>
                  <span class="attribute-value">¥{{ formatAmount(contractInfo?.standard_unit_price || '0') }}</span>
                </div>
                <div class="attribute-item">
                  <div class="attribute-header">
                    <el-icon class="attribute-icon"><Calendar /></el-icon>
                    <span class="attribute-label">订阅年限</span>
                  </div>
                  <span class="attribute-value">{{ contractInfo?.subscription_years ? contractInfo.subscription_years + '年' : '-' }}</span>
                </div>
                <div class="attribute-item">
                  <div class="attribute-header">
                    <el-icon class="attribute-icon"><UserFilled /></el-icon>
                    <span class="attribute-label">创建人</span>
                  </div>
                  <span class="attribute-value" :class="{ 'value-empty': !contractInfo?.creator_info?.name }">{{ contractInfo?.creator_info?.name || '-' }}</span>
                </div>
              </div>
            </div>
          </div>
        </el-card>

        <!-- 核心功能区 -->
        <div class="core-section">
          <div class="payment-section">
            <PaymentPlans
              v-if="contractInfo && ['SIGNED', 'EFFECTIVE', 'EXPIRED'].includes(contractInfo.status || '')"
              :contract-id="contractInfo.id"
              :contract-status="contractInfo.status"
              @plan-updated="handlePaymentPlanUpdated"
              ref="paymentPlansRef"
            />
            <el-card v-else shadow="never" class="placeholder-card">
              <el-empty description="回款计划仅在已签署、生效或已到期的合同中显示" />
            </el-card>
          </div>

          <div class="approval-section">
            <ApprovalProgressCompact
              v-if="approvalDetail"
              :approval-detail="approvalDetail"
              :can-approve="canApprove"
              @approve="handleApprove"
              @reject="handleReject"
            />
            <el-card v-else shadow="never" class="placeholder-card">
              <el-empty :description="getApprovalPlaceholderText()" />
            </el-card>
          </div>
        </div>
      </div>

      <!-- 拒绝审批弹窗 -->
      <el-dialog v-model="rejectModalVisible" title="拒绝审批" width="600px" :close-on-click-modal="false">
        <el-alert v-if="approvalDetail" type="warning" :show-icon="true" style="margin-bottom: 16px" :closable="false">
          您正在拒绝该合同的审批申请，此操作不可撤销。
        </el-alert>
        <el-form :model="rejectForm" label-position="top">
          <el-form-item label="拒绝原因" required>
            <el-input
              v-model="rejectForm.reason"
              type="textarea"
              :rows="4"
              placeholder="请输入拒绝原因"
              maxlength="500"
              show-word-limit
            />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button class="default-btn" @click="rejectModalVisible = false">取消</el-button>
          <el-button type="danger" class="danger-btn" @click="confirmReject" :loading="rejecting">确认拒绝</el-button>
        </template>
      </el-dialog>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { showError, showSuccess } from '@/utils/errorMessages'
import {
  ArrowLeft,
  Ticket,
  User,
  TrendCharts,
  EditPen,
  Coin,
  Calendar,
  UserFilled
} from '@element-plus/icons-vue'
import contractApi, { type ContractResponse } from '@/api/contract'
import approvalApi from '@/api/approval'
import ApprovalProgressCompact from '@/components/ApprovalProgressCompact.vue'
import PaymentPlans from '@/components/PaymentPlans.vue'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const permissionStore = usePermissionStore()
const currentUserId = userStore.userInfo?.id ? String(userStore.userInfo.id) : ''

const contractInfo = ref<ContractResponse | null>(null)
const approvalDetail = ref<any>(null)
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

const signingContactName = computed(() => {
  return contractInfo.value?.contact_info?.name || '-'
})

const getStatusText = (status: string) => {
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

const getStatusClass = (status: string) => {
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

const canEditContract = computed(() => {
  // 只有草稿状态的合同可以编辑
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

const formatAmount = (amount: number | string) => {
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const fetchContractInfo = async () => {
  loading.value = true
  try {
    const data = await contractApi.getContract(Number(route.params.id))
    contractInfo.value = data
    console.log('合同详情数据:', data)
  } catch (error: unknown) {
    console.error('获取合同详情失败', error)
    showError(error, '获取合同详情')
  } finally {
    loading.value = false
  }
}

const fetchApprovalDetail = async () => {
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

interface TransformedApprovalDetail {
  current_step: number
  approval_steps: {
    step_order: number
    step_name: string
    approver_role: string
    status: string
    approval_records: {
      approver_id: string
      approver_name?: string
      action: string
      created_time: string
      comment?: string
    }[]
  }[]
  status: string
  submitter_name?: string
  submitted_at?: string
  flow_name?: string
}

const transformApprovalData = (apiData: ApprovalDetailFromAPI): TransformedApprovalDetail | null => {
  if (!apiData) return null
  
  const nodes = apiData.flow?.nodes || []
  const nodeMap = new Map<number, any>()
  
  const submitRecord = apiData.records.find(r => r.action === 'SUBMIT')
  
  const submittedStep = {
    step_order: 0,
    step_name: '已提交',
    approver_role: '',
    status: 'APPROVED' as const,
    approval_records: submitRecord ? [{
      approver_id: submitRecord.approver_id,
      approver_name: submitRecord.approver_name,
      action: submitRecord.action,
      created_time: submitRecord.created_time,
      comment: submitRecord.comment
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
        comment: r.comment
      }))
    })
  })
  
  const isCompleted = ['APPROVED', 'REJECTED', 'CANCELLED'].includes(apiData.status)
  
  if (isCompleted) {
    const maxOrder = Math.max(...nodes.map(n => n.node_order), 0)
    const completedStep = {
      step_order: maxOrder + 1,
      step_name: '已完成',
      approver_role: '',
      status: apiData.status as 'APPROVED' | 'REJECTED' | 'CANCELLED',
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
  
  const transformed: TransformedApprovalDetail = {
    current_step: Math.max(0, currentStepIndex),
    approval_steps: stepsArray,
    status: apiData.status,
    submitter_name: apiData.submitter_name,
    submitted_at: apiData.created_time,
    flow_name: apiData.flow?.flow_name
  }
  
  return transformed
}

const handleBack = () => {
  router.back()
}

const handleEdit = () => {
  router.push(`/contracts/edit/${contractInfo.value?.id}`)
}

const handleSubmitApproval = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要提交合同"${contractInfo.value?.contract_name}"进行审批吗？`,
      '确认提交',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    submitting.value = true
    await approvalApi.submitContractApproval(contractInfo.value!.id)
    showSuccess('提交审批', '合同')
    await fetchContractInfo()
    await fetchApprovalDetail()
  } catch (error: unknown) {
    if (error !== 'cancel') {
      console.error('提交审批失败', error)
      showError(error, '提交审批')
    }
  } finally {
    submitting.value = false
  }
}

const handleWithdrawApproval = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要撤回合同"${contractInfo.value?.contract_name}"的审批申请吗？`,
      '确认撤回',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    withdrawing.value = true
    await approvalApi.cancelContractApproval(contractInfo.value!.id)
    showSuccess('撤回审批', '合同')
    await fetchContractInfo()
    approvalDetail.value = null
  } catch (error: unknown) {
    if (error !== 'cancel') {
      console.error('撤回失败', error)
      showError(error, '撤回审批')
    }
  } finally {
    withdrawing.value = false
  }
}

const handleApprove = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要同意合同"${contractInfo.value?.contract_name}"的审批申请吗？`,
      '确认同意',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'success'
      }
    )
    
    approving.value = true
    await approvalApi.approveContract(contractInfo.value!.id, { action: 'APPROVE' })
    showSuccess('同意审批', '合同')
    await fetchContractInfo()
    await fetchApprovalDetail()
  } catch (error: unknown) {
    if (error !== 'cancel') {
      console.error('审批失败', error)
      showError(error, '审批合同')
    }
  } finally {
    approving.value = false
  }
}

const handleReject = () => {
  rejectModalVisible.value = true
}

const confirmReject = async () => {
  if (!rejectForm.reason.trim()) {
    ElMessage.warning('请输入拒绝原因')
    return
  }
  
  try {
    rejecting.value = true
    await approvalApi.approveContract(contractInfo.value!.id, {
      action: 'REJECT',
      comment: rejectForm.reason
    })
    showSuccess('拒绝审批', '合同')
    rejectModalVisible.value = false
    rejectForm.reason = ''
    await fetchContractInfo()
    await fetchApprovalDetail()
  } catch (error: unknown) {
    console.error('拒绝失败', error)
    showError(error, '拒绝审批')
  } finally {
    rejecting.value = false
  }
}

const handleMarkEffective = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要将合同"${contractInfo.value?.contract_name}"标记为生效吗？`,
      '确认标记',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'success'
      }
    )
    
    await contractApi.updateContractStatus(contractInfo.value!.id, { status: 'EFFECTIVE' })
    showSuccess('标记生效', '合同')
    await fetchContractInfo()
  } catch (error: unknown) {
    if (error !== 'cancel') {
      console.error('标记失败', error)
      showError(error, '标记生效')
    }
  }
}

const handleCreateInvoice = () => {
  router.push(`/invoices/create?contract_id=${contractInfo.value?.id}`)
}

const handlePaymentPlanUpdated = () => {
  if (paymentPlansRef.value) {
    paymentPlansRef.value.refresh()
  }
}

const getApprovalPlaceholderText = () => {
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

onMounted(async () => {
  await fetchContractInfo()
  await fetchApprovalDetail()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.contract-detail-page {
  padding: 0;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

// 页面头部
.page-header-bar {
  position: sticky;
  top: 0;
  z-index: 100;
  background: $wolf-bg-card;
  border-bottom: 1px solid $wolf-border-color;
  height: $wolf-header-height;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 $wolf-page-padding;
}

.header-left,
.header-right {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.header-left {
  flex: 1;
  min-width: 0;
}

.header-right {
  flex-shrink: 0;
}


.header-title {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.back-btn {
  width: 32px !important;
  height: 32px !important;
  padding: 0 !important;
  border-radius: $wolf-radius-md !important;
  color: $wolf-text-tertiary;

  &:hover {
    background: $wolf-bg-hover !important;
    color: $wolf-text-secondary;
  }
}

.primary-btn {
  background: $wolf-primary;
  color: $wolf-text-inverse;
  border-radius: $wolf-radius-sm;

  &:hover {
    background: $wolf-primary-hover;
  }
}

.default-btn {
  background: $wolf-bg-card;
  color: $wolf-text-secondary;
  border: 1px solid $wolf-border-color;
  border-radius: $wolf-radius-sm;

  &:hover {
    background: $wolf-bg-hover;
    border-color: $wolf-border-hover;
  }
}

.danger-btn {
  background: $wolf-danger;
  color: $wolf-text-inverse;
  border-radius: $wolf-radius-sm;

  &:hover {
    background: $wolf-danger-hover;
  }
}

// 内容区
.detail-content {
  padding: $wolf-page-padding;
}

.content-wrapper {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-lg;
}

.info-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
}

.info-card :deep(.el-card__body) {
  padding: $wolf-space-lg;
}

// 基本信息
.basic-info {
  padding: 0;
}

.info-top {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: $wolf-space-lg;
}

.info-left {
  .title-section {
    display: flex;
    gap: $wolf-space-md;
    align-items: flex-start;
  }

  .contract-avatar {
    width: 48px;
    height: 48px;
    border-radius: $wolf-radius-full;
    background: $wolf-primary-light;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    font-weight: $wolf-font-weight-semibold;
    color: $wolf-primary;
    flex-shrink: 0;
  }

  .title-content {
    flex: 1;

    .contract-name {
      margin: 0 0 $wolf-space-sm 0;
      font-size: $wolf-font-size-card-title;
      font-weight: $wolf-font-weight-semibold;
      color: $wolf-text-primary;
      line-height: $wolf-line-height-tight;
    }

    .status-tags {
      display: flex;
      gap: $wolf-space-xs;
      flex-wrap: wrap;
    }
  }
}

.info-divider {
  height: 1px;
  background: $wolf-border-light;
  margin: $wolf-space-lg 0;
}

.info-bottom {
  .attributes-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: $wolf-space-md $wolf-space-lg;
  }

  .attribute-item {
    display: flex;
    flex-direction: column;
    gap: $wolf-space-xs;
  }

  .attribute-header {
    display: flex;
    align-items: center;
    gap: $wolf-space-xs;
  }

  .attribute-icon {
    font-size: 14px;
    color: $wolf-text-tertiary;
    flex-shrink: 0;
  }

  .attribute-label {
    font-size: $wolf-font-size-auxiliary;
    color: $wolf-text-tertiary;
    font-weight: $wolf-font-weight-normal;
  }

  .attribute-value {
    font-size: $wolf-font-size-body;
    color: $wolf-text-primary;
    font-weight: $wolf-font-weight-medium;
    line-height: $wolf-line-height-normal;

    &.value-empty {
      color: $wolf-text-placeholder;
    }
  }
}

.info-right {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-end;
  gap: $wolf-space-md;

  .amount-section {
    text-align: right;

    .amount-label {
      font-size: $wolf-font-size-auxiliary;
      color: $wolf-text-tertiary;
      margin-bottom: $wolf-space-xs;
    }

    .amount-value {
      font-size: 24px;
      font-weight: $wolf-font-weight-semibold;
      color: $wolf-primary;
      line-height: $wolf-line-height-tight;
    }
  }

  .action-buttons {
    display: flex;
    flex-direction: column;
    gap: $wolf-space-xs;
    width: 100%;

    .el-button {
      width: 100%;
      justify-content: center;
    }
  }
}

// 状态标签（中性色系）
.status-tag {
  display: inline-flex;
  padding: 4px 8px;
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-normal;
  border-radius: $wolf-radius-sm;
}

.status-draft {
  background: $wolf-bg-hover;
  color: $wolf-text-tertiary;
}

.status-pending {
  background: $wolf-warning-bg;
  color: $wolf-warning-text;
}

.status-signed {
  background: $wolf-bg-hover;
  color: $wolf-text-secondary;
}

.status-effective {
  background: $wolf-success-bg;
  color: $wolf-success-text;
}

.status-expired {
  background: $wolf-danger-bg;
  color: $wolf-danger-text;
}

.status-terminated {
  background: $wolf-bg-hover;
  color: $wolf-text-placeholder;
}

.status-subscription {
  background: $wolf-bg-hover;
  color: $wolf-text-tertiary;
}

.status-perpetual {
  background: $wolf-bg-hover;
  color: $wolf-text-secondary;
}

// 核心功能区
.core-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $wolf-space-lg;
}

.payment-section,
.approval-section {
  min-height: 400px;

  .el-card {
    height: 100%;
  }
}

.placeholder-card {
  height: 100%;
  min-height: 400px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;

  :deep(.el-card__body) {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
  }
}

// 响应式
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
  .page-header-bar {
    padding: $wolf-space-sm $wolf-page-padding;
  }

  .header-title {
    font-size: $wolf-font-size-card-title;
  }

  .info-bottom {
    .attributes-grid {
      grid-template-columns: 1fr;
    }
  }

  .detail-content {
    padding: $wolf-space-md;
  }
}
</style>
