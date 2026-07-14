<script setup lang="ts">
/**
 * PaymentPlanDetailContent.vue - 回款计划详情内容组件
 *
 * 业务内容委托组件，包含：
 * - 计划信息展示
 * - 回款进度展示
 * - 回款记录列表
 * - 审批信息展示
 * - 关联发票展示
 * - 处理操作：编辑、登记回款、审批
 *
 * 设计规格参考：docs/superpowers/specs/2026-07-14-contract-payment-invoice-detail-sheet-design.md §7.2
 */
import { ref, computed, onMounted, watch, reactive } from 'vue'
import { toast } from 'vue-sonner'
import {
  FileText,
  Coins,
  RefreshCw,
  Info,
  AlertTriangle,
  CheckCircle,
  Plus,
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
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import paymentApi, {
  type PaymentPlanResponse,
  type PaymentRecordCreate,
  type PaymentRecordUpdate,
  type ApprovalStatus,
  type ApprovalNodeInfo
} from '@/api/payment'
import { useApprovalStore } from '@/stores/approval'
import { usePermissionStore } from '@/stores/permissions'
import { confirmDialog } from '@/utils/confirmDialog'
import { formatCurrency } from '@/utils/format'

// ==================== Props & Emits ====================
const props = defineProps<{
  recordId: number
}>()

const emit = defineEmits<{
  'refresh': []
  'deleted': []
}>()

// ==================== Stores ====================
const approvalStore = useApprovalStore()
const permissionStore = usePermissionStore()

// ==================== State ====================
const loading = ref(false)
const plan = ref<PaymentPlanResponse | null>(null)

// Payment dialog state
const paymentModalVisible = ref(false)
const paymentForm = ref<PaymentRecordCreate>({
  actual_amount: 0,
  payment_date: ''
})

// Approval submission loading state
const submittingApproval = ref(false)

// Edit and resubmit approval flow state
const showEditRecordDialog = ref(false)
const editRecordForm = ref<PaymentRecordUpdate>({
  actual_amount: 0,
  payment_date: '',
  proof_attachment: '',
  notes: ''
})
const resubmittingApproval = ref(false)

// Approve/Reject state
const approving = ref(false)
const rejecting = ref(false)
const rejectModalVisible = ref(false)
const rejectForm = reactive({
  reason: ''
})

// ==================== Computed ====================
const hasPendingRecord = computed((): boolean => {
  if (plan.value?.payment_records === undefined || plan.value.payment_records.length === 0) return false
  const latestRecord = plan.value.payment_records[plan.value.payment_records.length - 1]
  return latestRecord?.confirmation_status === 'PENDING'
})

const hasRejectedApproval = computed((): boolean => {
  return plan.value?.latest_approval?.status === 'REJECTED'
})

const hasApprovalPending = computed((): boolean => {
  return plan.value?.latest_approval?.status === 'PENDING'
})

const rejectionReason = computed((): string | null => {
  if (!hasRejectedApproval.value || plan.value?.latest_approval?.nodes === undefined) return null

  const rejectedNode = plan.value.latest_approval.nodes.find(node => node.status === 'REJECT' || node.status === 'REJECTED')
  return rejectedNode?.comment ?? '审批被驳回，请查看详情'
})

const currentApproverName = computed((): string | null => {
  if (!hasApprovalPending.value || plan.value?.latest_approval?.nodes === undefined) return null

  const pendingNode = plan.value.latest_approval.nodes.find(node => node.status === 'PENDING')
  return pendingNode?.approver_name ?? '待分配'
})

const isCompleted = computed((): boolean => {
  return plan.value?.status === 'COMPLETED'
})

const canRegisterPayment = computed((): boolean => {
  return !isCompleted.value && permissionStore.hasPermission('payment:record:create')
})

const canSubmitApproval = computed((): boolean => {
  return hasPendingRecord.value && plan.value?.latest_approval === undefined && permissionStore.hasPermission('payment:approval:submit')
})

const canApprove = computed((): boolean => {
  return hasApprovalPending.value && permissionStore.hasPermission('payment:approval:approve')
})

// ==================== Methods ====================
const fetchPlanDetail = async (): Promise<void> => {
  loading.value = true
  try {
    plan.value = await paymentApi.getPaymentPlanDetail(props.recordId)
  } catch (error) {
    toast.error('获取回款计划详情失败')
    plan.value = null
  } finally {
    loading.value = false
  }
}

const formatDate = (dateStr: string): string => {
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}

const formatDateTime = (dateTimeStr: string): string => {
  const date = new Date(dateTimeStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// ==================== Status Helpers ====================
const getApprovalStatusType = (status: ApprovalStatus): string => {
  const statusMap: Record<ApprovalStatus, string> = {
    'PENDING': 'warning',
    'APPROVED': 'success',
    'REJECTED': 'danger'
  }
  const result = statusMap[status]
  return result !== undefined ? result : 'info'
}

const getApprovalStatusLabel = (status: ApprovalStatus): string => {
  const statusMap: Record<ApprovalStatus, string> = {
    'PENDING': '审批中',
    'APPROVED': '已通过',
    'REJECTED': '已驳回'
  }
  const result = statusMap[status]
  return result !== undefined ? result : status
}

const getConfirmationStatusLabel = (status: string | undefined): string => {
  if (status === undefined) return '未知'
  const map: Record<string, string> = {
    'PENDING': '待确认',
    'CONFIRMED': '已确认',
    'DISPUTED': '有争议'
  }
  const result = map[status]
  return result !== undefined ? result : status
}

// ==================== Approval Node Helpers ====================
const getCurrentNodeOrder = (): number => {
  if (plan.value?.latest_approval?.nodes === undefined) return 0

  const pendingNode = plan.value.latest_approval.nodes.find(node => node.status === 'PENDING')
  return pendingNode?.node_order ?? plan.value.latest_approval.nodes.length
}

const getNodeDescription = (node: ApprovalNodeInfo): string => {
  if (node.status === 'PENDING') {
    return `等待 ${node.approve_role} 审批`
  } else if (node.status === 'APPROVE' || node.status === 'APPROVED') {
    return node.approver_name ?? '已通过'
  } else if (node.status === 'REJECT' || node.status === 'REJECTED') {
    return node.approver_name ?? '已驳回'
  } else if (node.status === 'SUBMIT') {
    return '已提交'
  }
  return node.approve_role ?? '审批中'
}

const getNodeStatus = (status: string): string => {
  if (status === 'APPROVE' || status === 'APPROVED') return 'success'
  if (status === 'REJECT' || status === 'REJECTED') return 'error'
  return 'process'
}

// ==================== Event Handlers ====================
const handleRegisterPayment = (): void => {
  const today = new Date()
  const year = today.getFullYear()
  const month = String(today.getMonth() + 1).padStart(2, '0')
  const day = String(today.getDate()).padStart(2, '0')
  const todayStr = `${year}-${month}-${day}`

  paymentForm.value = {
    actual_amount: plan.value?.remaining_amount ?? plan.value?.planned_amount ?? 0,
    payment_date: todayStr
  }
  paymentModalVisible.value = true
}

const handleCreatePayment = async (): Promise<void> => {
  if (paymentForm.value.actual_amount === null || paymentForm.value.actual_amount <= 0) {
    toast.warning('请输入有效的回款金额')
    return
  }

  if (paymentForm.value.payment_date.length === 0) {
    toast.warning('请选择回款日期')
    return
  }

  try {
    await paymentApi.createPaymentRecord(props.recordId, paymentForm.value)
    toast.success('回款登记成功')
    paymentModalVisible.value = false
    fetchPlanDetail()
    emit('refresh')
  } catch (error) {
    toast.error('登记回款失败')
  }
}

const handleSubmitApproval = async (): Promise<void> => {
  if (submittingApproval.value) return

  const confirmed = await confirmDialog(
    '确定要提交该回款记录进行审批吗？',
    '确认提交'
  )

  if (!confirmed) return

  submittingApproval.value = true

  try {
    const latestRecord = plan.value?.payment_records?.[plan.value.payment_records.length - 1]
    if (latestRecord === undefined) {
      toast.error('没有可提交审批的回款记录')
      return
    }

    const res = await approvalStore.submitEntity('PAYMENT', latestRecord.id)
    if (res.approval_id === 0) {
      toast.success('未配置审批流，已转为财务确认')
    } else {
      toast.success('已提交审批，等待审批人处理')
    }
    fetchPlanDetail()
    emit('refresh')
  } catch {
    toast.error('提交审批失败')
  } finally {
    submittingApproval.value = false
  }
}

const handleResubmitApproval = (): void => {
  if (plan.value?.latest_approval === undefined) return

  const latestRecord = plan.value.payment_records?.[plan.value.payment_records.length - 1]
  if (latestRecord !== undefined) {
    editRecordForm.value = {
      actual_amount: latestRecord.actual_amount,
      payment_date: latestRecord.payment_date,
      proof_attachment: latestRecord.proof_attachment ?? '',
      notes: latestRecord.notes ?? ''
    }
  }

  showEditRecordDialog.value = true
}

const handleEditAndResubmit = async (): Promise<void> => {
  if (plan.value?.latest_record_id === undefined || plan.value?.latest_record_id === null || plan.value?.latest_record_id === 0) {
    return
  }
  if (resubmittingApproval.value) return

  resubmittingApproval.value = true
  try {
    // 1. Update payment record
    await paymentApi.updatePaymentRecord(plan.value.latest_record_id, editRecordForm.value)

    // 2. Resubmit approval
    const res = await approvalStore.submitEntity('PAYMENT', plan.value.latest_record_id)
    if (res.approval_id === 0) {
      toast.success('未配置审批流，已转为财务确认')
    } else {
      toast.success('已重新提交审批')
    }

    // 3. Refresh detail
    fetchPlanDetail()
    showEditRecordDialog.value = false
    emit('refresh')
  } catch {
    toast.error('重新提交审批失败')
  } finally {
    resubmittingApproval.value = false
  }
}

const handleApprove = async (): Promise<void> => {
  const confirmed = await confirmDialog(
    '确定要同意该回款审批吗？',
    '确认同意'
  )

  if (!confirmed) return

  approving.value = true
  try {
    const latestRecord = plan.value?.payment_records?.[plan.value.payment_records.length - 1]
    if (latestRecord === undefined) {
      toast.error('没有可审批的回款记录')
      return
    }

    await approvalStore.approveEntity('PAYMENT', latestRecord.id, 'APPROVE', '')
    toast.success('审批已同意')
    fetchPlanDetail()
    emit('refresh')
  } catch {
    toast.error('审批失败')
  } finally {
    approving.value = false
  }
}

const handleReject = (): void => {
  rejectModalVisible.value = true
}

const confirmReject = async (): Promise<void> => {
  if (!rejectForm.reason.trim()) {
    toast.warning('请输入拒绝原因')
    return
  }

  rejecting.value = true
  try {
    const latestRecord = plan.value?.payment_records?.[plan.value.payment_records.length - 1]
    if (latestRecord === undefined) {
      toast.error('没有可拒绝的回款记录')
      return
    }

    await approvalStore.approveEntity('PAYMENT', latestRecord.id, 'REJECT', rejectForm.reason)
    toast.success('审批已拒绝')
    rejectModalVisible.value = false
    rejectForm.reason = ''
    fetchPlanDetail()
    emit('refresh')
  } catch {
    toast.error('拒绝审批失败')
  } finally {
    rejecting.value = false
  }
}

// ==================== Expose Methods ====================
defineExpose({
  refresh: fetchPlanDetail
})

// ==================== Lifecycle ====================
onMounted(() => {
  fetchPlanDetail()
})

// Watch recordId changes
watch(() => props.recordId, (newId): void => {
  if (newId !== undefined && newId !== null && newId > 0) {
    fetchPlanDetail()
  }
})
</script>

<template>
  <div class="payment-plan-detail-content">
    <!-- Loading Skeleton -->
    <div v-if="loading" class="space-y-4">
      <Skeleton class="h-32 w-full" />
      <Skeleton class="h-24 w-full" />
      <Skeleton class="h-48 w-full" />
    </div>

    <template v-else-if="plan">
      <!-- 回款进度 -->
      <Card class="progress-card">
        <CardHeader class="pb-4">
          <h3 class="text-sm font-semibold">回款进度</h3>
        </CardHeader>
        <CardContent>
          <div class="progress-grid">
            <div class="progress-item">
              <div class="progress-label">计划金额</div>
              <div class="progress-value mono-number">{{ formatCurrency(plan.planned_amount) }}</div>
            </div>
            <div class="progress-item">
              <div class="progress-label">已回款</div>
              <div class="progress-value mono-number text-wolf-success-text-v2">
                {{ formatCurrency(plan.paid_amount ?? 0) }}
              </div>
            </div>
            <div class="progress-item">
              <div class="progress-label">待回款</div>
              <div class="progress-value mono-number text-wolf-warning-text-v2">
                {{ formatCurrency(plan.remaining_amount ?? 0) }}
              </div>
            </div>
            <div class="progress-item">
              <div class="progress-label">计划日期</div>
              <div class="progress-value">{{ formatDate(plan.due_date) }}</div>
            </div>
          </div>

          <!-- Progress Bar -->
          <div class="progress-bar-container">
            <div class="progress-bar-bg">
              <div
                class="progress-bar-fill"
                :style="{
                  width: `${Math.min(100, ((plan.paid_amount ?? 0) / plan.planned_amount) * 100)}%`
                }"
              />
            </div>
            <div class="progress-text">
              {{ Math.round(((plan.paid_amount ?? 0) / plan.planned_amount) * 100) }}%
            </div>
          </div>
        </CardContent>
      </Card>

      <Separator />

      <!-- 回款记录 -->
      <Card class="records-card">
        <CardHeader class="pb-4 flex flex-row items-center justify-between">
          <CardTitle class="text-sm font-semibold">回款记录</CardTitle>
          <Button
            v-if="canRegisterPayment"
            size="sm"
            @click="handleRegisterPayment"
          >
            <Plus class="w-4 h-4 mr-1" />
            登记回款
          </Button>
        </CardHeader>
        <CardContent>
          <div v-if="plan.payment_records && plan.payment_records.length > 0" class="records-list">
            <div
              v-for="record in plan.payment_records"
              :key="record.id"
              class="record-item"
            >
              <div class="record-main">
                <div class="record-amount mono-number">
                  {{ formatCurrency(record.actual_amount) }}
                </div>
                <div class="record-info">
                  <div class="record-date">{{ formatDate(record.payment_date) }}</div>
                  <div class="record-creator">{{ record.creator_name || '未知' }}</div>
                </div>
              </div>
              <div class="record-status">
                <Badge
                  :variant="record.confirmation_status === 'CONFIRMED' ? 'default' : 'secondary'"
                  :class="[
                    'status-badge',
                    record.confirmation_status === 'CONFIRMED' ? 'status-confirmed' :
                    record.confirmation_status === 'PENDING' ? 'status-pending' : 'status-disputed'
                  ]"
                >
                  {{ getConfirmationStatusLabel(record.confirmation_status) }}
                </Badge>
                <div v-if="record.invoice_application_count && record.invoice_application_count > 0" class="invoice-count">
                  <FileText class="w-3 h-3" />
                  <span>{{ record.invoice_application_count }} 张发票</span>
                </div>
              </div>
              <div v-if="record.notes" class="record-notes">
                {{ record.notes }}
              </div>
            </div>
          </div>
          <div v-else class="empty-records">
            <Coins class="w-8 h-8 text-wolf-text-tertiary-v2 mb-2" />
            <p class="text-wolf-text-tertiary-v2 text-sm">暂无回款记录</p>
            <Button
              v-if="canRegisterPayment"
              variant="outline"
              size="sm"
              class="mt-3"
              @click="handleRegisterPayment"
            >
              <Plus class="w-4 h-4 mr-1" />
              登记回款
            </Button>
          </div>
        </CardContent>
      </Card>

      <Separator />

      <!-- 审批信息 -->
      <Card v-if="plan.latest_approval" class="approval-card">
        <CardHeader class="pb-4">
          <CardTitle class="text-sm font-semibold">审批进度</CardTitle>
        </CardHeader>
        <CardContent>
          <!-- Rejection Alert -->
          <Alert v-if="hasRejectedApproval" variant="destructive" class="rejection-alert">
            <AlertTriangle class="w-4 h-4" />
            <AlertTitle>审批被驳回</AlertTitle>
            <AlertDescription>
              {{ rejectionReason ?? '请查看驳回原因并修正后重新提交' }}
            </AlertDescription>
          </Alert>

          <!-- Approval Steps -->
          <div v-if="plan.latest_approval.nodes && plan.latest_approval.nodes.length > 0" class="approval-steps">
            <div
              v-for="(node, index) in plan.latest_approval.nodes"
              :key="node.id"
              class="approval-step"
              :class="{
                'step-active': index === getCurrentNodeOrder(),
                'step-completed': getNodeStatus(node.status) === 'success',
                'step-rejected': getNodeStatus(node.status) === 'error'
              }"
            >
              <div class="step-indicator">
                <CheckCircle v-if="getNodeStatus(node.status) === 'success'" class="w-4 h-4" />
                <WarningFilled v-else-if="getNodeStatus(node.status) === 'error'" class="w-4 h-4" />
                <div v-else class="step-dot" />
              </div>
              <div class="step-content">
                <div class="step-title">{{ node.node_name }}</div>
                <div class="step-description">{{ getNodeDescription(node) }}</div>
              </div>
            </div>
          </div>

          <!-- Approval Status -->
          <div class="approval-status">
            <div class="status-row">
              <span class="status-label">审批状态</span>
              <Badge
                :class="['status-badge', `status-${getApprovalStatusType(plan.latest_approval.status)}`]"
              >
                {{ getApprovalStatusLabel(plan.latest_approval.status) }}
              </Badge>
            </div>
            <div v-if="currentApproverName" class="status-row">
              <span class="status-label">当前审批人</span>
              <span class="status-value">{{ currentApproverName }}</span>
            </div>
            <div v-if="plan.latest_approval.created_time" class="status-row">
              <span class="status-label">提交时间</span>
              <span class="status-value">{{ formatDateTime(plan.latest_approval.created_time) }}</span>
            </div>
          </div>

          <!-- Approval Actions -->
          <div v-if="hasApprovalPending && canApprove" class="approval-actions">
            <Button
              @click="handleApprove"
              :disabled="approving"
            >
              <Loader2 v-if="approving" class="w-4 h-4 mr-2 animate-spin" />
              同意
            </Button>
            <Button
              variant="destructive"
              @click="handleReject"
              :disabled="rejecting"
            >
              <Loader2 v-if="rejecting" class="w-4 h-4 mr-2 animate-spin" />
              拒绝
            </Button>
          </div>

          <!-- Current Approver Hint -->
          <div v-if="hasApprovalPending" class="current-approver-hint">
            <Info class="w-4 h-4" />
            <span>审批通过后，回款状态将自动更新为"已确认"</span>
          </div>
        </CardContent>
      </Card>

      <!-- Approval Actions for Rejected Status -->
      <div v-if="hasRejectedApproval && !isCompleted" class="action-buttons">
        <Button
          variant="secondary"
          :disabled="resubmittingApproval"
          @click="handleResubmitApproval"
        >
          <RefreshCw class="w-4 h-4 mr-2" />
          重新提交审批
        </Button>
      </div>

      <!-- Submit Approval Button -->
      <div v-if="canSubmitApproval" class="action-buttons">
        <Button
          :disabled="submittingApproval"
          @click="handleSubmitApproval"
        >
          <Loader2 v-if="submittingApproval" class="w-4 h-4 mr-2 animate-spin" />
          提交审批
        </Button>
      </div>
    </template>

    <!-- Empty State -->
    <div v-else class="empty-state">
      <FileText class="w-10 h-10 text-wolf-text-tertiary-v2 mb-2" />
      <p class="text-wolf-text-tertiary-v2">回款计划信息加载失败</p>
    </div>

    <!-- Register Payment Dialog -->
    <Dialog v-model:open="paymentModalVisible">
      <DialogContent class="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>登记回款</DialogTitle>
          <DialogDescription>
            填写回款信息，提交后将进入审批流程。
          </DialogDescription>
        </DialogHeader>

        <div class="space-y-4">
          <div class="space-y-2">
            <Label for="payment-amount">回款金额 <span class="text-destructive">*</span></Label>
            <div class="relative">
              <span class="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">¥</span>
              <Input
                id="payment-amount"
                v-model.number="paymentForm.actual_amount"
                type="number"
                placeholder="请输入回款金额"
                class="pl-8"
              />
            </div>
            <div v-if="plan" class="form-hint mono-number">
              待回款：{{ formatCurrency(plan.remaining_amount ?? 0) }}
            </div>
          </div>

          <div class="space-y-2">
            <Label for="payment-date">回款日期 <span class="text-destructive">*</span></Label>
            <Input
              id="payment-date"
              v-model="paymentForm.payment_date"
              type="date"
            />
          </div>

          <div class="space-y-2">
            <Label for="proof-attachment">凭证附件</Label>
            <Input
              id="proof-attachment"
              v-model="paymentForm.proof_attachment"
              placeholder="附件URL（可选）"
            />
          </div>

          <div class="space-y-2">
            <Label for="payment-notes">备注</Label>
            <Textarea
              id="payment-notes"
              v-model="paymentForm.notes"
              placeholder="备注信息（可选）"
              :maxlength="200"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" @click="paymentModalVisible = false">取消</Button>
          <Button @click="handleCreatePayment">确定</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Edit Record Dialog -->
    <Dialog v-model:open="showEditRecordDialog">
      <DialogContent class="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>修改回款记录</DialogTitle>
          <DialogDescription>
            修改回款信息后重新提交审批。
          </DialogDescription>
        </DialogHeader>

        <Alert v-if="rejectionReason" variant="destructive" class="mb-4">
          <AlertTriangle class="w-4 h-4" />
          <AlertTitle>驳回原因</AlertTitle>
          <AlertDescription>{{ rejectionReason }}</AlertDescription>
        </Alert>

        <div class="space-y-4">
          <div class="space-y-2">
            <Label for="edit-amount">回款金额 <span class="text-destructive">*</span></Label>
            <div class="relative">
              <span class="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">¥</span>
              <Input
                id="edit-amount"
                v-model.number="editRecordForm.actual_amount"
                type="number"
                class="pl-8"
              />
            </div>
          </div>

          <div class="space-y-2">
            <Label for="edit-date">回款日期 <span class="text-destructive">*</span></Label>
            <Input
              id="edit-date"
              v-model="editRecordForm.payment_date"
              type="date"
            />
          </div>

          <div class="space-y-2">
            <Label for="edit-proof">凭证附件</Label>
            <Input
              id="edit-proof"
              v-model="editRecordForm.proof_attachment"
              placeholder="附件URL（可选）"
            />
          </div>

          <div class="space-y-2">
            <Label for="edit-notes">备注</Label>
            <Textarea
              id="edit-notes"
              v-model="editRecordForm.notes"
              placeholder="备注信息（可选）"
              :maxlength="200"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" @click="showEditRecordDialog = false">取消</Button>
          <Button
            :disabled="resubmittingApproval"
            @click="handleEditAndResubmit"
          >
            <Loader2 v-if="resubmittingApproval" class="w-4 h-4 mr-2 animate-spin" />
            修改并重新提交
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Reject Dialog -->
    <Dialog v-model:open="rejectModalVisible">
      <DialogContent class="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>拒绝审批</DialogTitle>
          <DialogDescription>
            您正在拒绝该回款的审批申请，此操作不可撤销。
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
          <Button
            variant="destructive"
            :disabled="rejecting"
            @click="confirmReject"
          >
            <Loader2 v-if="rejecting" class="w-4 h-4 mr-2 animate-spin" />
            确认拒绝
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.payment-plan-detail-content {
  padding: 0;
}

.progress-card,
.records-card,
.approval-card {
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-v2;
  box-shadow: $wolf-shadow-card-v2;
}

.progress-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: $wolf-space-md-v2;

  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    grid-template-columns: repeat(2, 1fr);
  }

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
  }
}

.progress-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.progress-label {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.progress-value {
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-primary-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.mono-number {
  font-family: $wolf-font-mono-v2;
  font-variant-numeric: tabular-nums lining-nums;
}

.progress-bar-container {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  margin-top: $wolf-space-md-v2;
}

.progress-bar-bg {
  flex: 1;
  height: 8px;
  background: $wolf-bg-hover-v2;
  border-radius: $wolf-radius-full-v2;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: $wolf-primary-v2;
  border-radius: $wolf-radius-full-v2;
  transition: width 0.3s ease;
}

.progress-text {
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  color: $wolf-text-secondary-v2;
  min-width: 40px;
  text-align: right;
}

// Records List
.records-list {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm-v2;
}

.record-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  padding: $wolf-space-sm-v2;
  background: $wolf-bg-page-v2;
  border-radius: $wolf-radius-sm-v2;
}

.record-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.record-amount {
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
}

.record-info {
  display: flex;
  gap: $wolf-space-md-v2;
}

.record-date,
.record-creator {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
}

.record-status {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
}

.invoice-count {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
}

.record-notes {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-secondary-v2;
  padding-top: $wolf-space-xs-v2;
}

// Status Badges
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  border-radius: $wolf-radius-full-v2;
  white-space: nowrap;
}

.status-confirmed {
  background: $wolf-success-bg-v2;
  color: $wolf-success-text-v2;
}

.status-pending {
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
}

.status-disputed {
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-text-v2;
}

.status-success {
  background: $wolf-success-bg-v2;
  color: $wolf-success-text-v2;
}

.status-warning {
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
}

.status-danger {
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-text-v2;
}

// Empty Records
.empty-records {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: $wolf-space-xl-v2;
  background: $wolf-bg-muted-v2;
  border-radius: $wolf-radius-sm-v2;
}

// Approval Steps
.approval-steps {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm-v2;
  margin-bottom: $wolf-space-md-v2;
}

.approval-step {
  display: flex;
  align-items: flex-start;
  gap: $wolf-space-sm-v2;
  padding: $wolf-space-sm-v2;
  border-radius: $wolf-radius-sm-v2;
  background: $wolf-bg-page-v2;

  &.step-active {
    background: $wolf-primary-light-v2;
  }

  &.step-completed {
    background: $wolf-success-bg-v2;
  }

  &.step-rejected {
    background: $wolf-danger-bg-v2;
  }
}

.step-indicator {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.step-dot {
  width: 8px;
  height: 8px;
  border-radius: $wolf-radius-full-v2;
  background: $wolf-text-tertiary-v2;
}

.step-content {
  flex: 1;
}

.step-title {
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  color: $wolf-text-primary-v2;
}

.step-description {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
  margin-top: 2px;
}

// Approval Status
.approval-status {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm-v2;
  padding: $wolf-space-sm-v2;
  background: $wolf-bg-page-v2;
  border-radius: $wolf-radius-sm-v2;
}

.status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.status-label {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
}

.status-value {
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-primary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

// Approval Actions
.approval-actions {
  display: flex;
  gap: $wolf-space-sm-v2;
  margin-top: $wolf-space-md-v2;
}

// Current Approver Hint
.current-approver-hint {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  margin-top: $wolf-space-md-v2;
  padding: $wolf-space-sm-v2;
  background: $wolf-bg-elevated-v2;
  border-radius: $wolf-radius-sm-v2;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
}

// Action Buttons
.action-buttons {
  display: flex;
  gap: $wolf-space-sm-v2;
  margin-top: $wolf-space-md-v2;
}

// Form Hint
.form-hint {
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
}

// Rejection Alert
.rejection-alert {
  margin-bottom: $wolf-space-md-v2;
}

// Empty State
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

// Reduced Motion 支持
@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>