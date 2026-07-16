<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  AlertCircle,
  FileText,
  Loader2,
  ReceiptText,
  RefreshCw,
  Send,
  Undo2,
  WalletCards,
  X
} from 'lucide-vue-next'
import {
  Sheet,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle
} from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import StatusBadge, { type PaymentPlanStatus as PaymentPlanBadgeStatus } from '@/components/StatusBadge.vue'
import PaymentRecordList from '@/components/PaymentRecordList.vue'
import paymentApi, {
  type ApprovalInfo,
  type ApprovalNodeInfo,
  type ApprovalStatus,
  type PaymentPlanResponse,
  type PaymentPlanStatus,
  type PaymentRecordInfo
} from '@/api/payment'
import { handleApiError } from '@/utils/errorHandler'
import { formatCurrency, formatLocalDate } from '@/utils/format'

interface Props {
  planId: number | null
  visible: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  refresh: []
  'register-payment': [plan: PaymentPlanResponse]
  'record-click': [record: PaymentRecordInfo]
  'edit-record': [record: PaymentRecordInfo]
  'view-approval': [record: PaymentRecordInfo]
  'view-customer': [customerId: number, plan: PaymentPlanResponse]
  'view-contract': [contractId: number, plan: PaymentPlanResponse]
  'submit-approval': [plan: PaymentPlanResponse, recordId: number]
  'resubmit-approval': [plan: PaymentPlanResponse, recordId: number]
}>()

const loading = ref<boolean>(false)
const errorMessage = ref<string>('')
const paymentPlan = ref<PaymentPlanResponse | null>(null)
const activeRequestId = ref<number>(0)

const latestRecord = computed<PaymentRecordInfo | null>(() => {
  const records = paymentPlan.value?.payment_records ?? []
  return records.length === 0 ? null : records[records.length - 1] ?? null
})

const hasPendingRecord = computed<boolean>(() => latestRecord.value?.confirmation_status === 'PENDING')
const latestApproval = computed<ApprovalInfo | null>(() => paymentPlan.value?.latest_approval ?? null)
const hasRejectedApproval = computed<boolean>(() => latestApproval.value?.status === 'REJECTED')
const hasPendingApproval = computed<boolean>(() => latestApproval.value?.status === 'PENDING')
const hasApprovedApproval = computed<boolean>(() => latestApproval.value?.status === 'APPROVED')
const canRegisterPayment = computed<boolean>(() => paymentPlan.value !== null && paymentPlan.value.status !== 'COMPLETED')
const canSubmitApproval = computed<boolean>(() => {
  return paymentPlan.value !== null && canRegisterPayment.value && hasPendingRecord.value && latestApproval.value === null
})
const canResubmitApproval = computed<boolean>(() => {
  return paymentPlan.value !== null && canRegisterPayment.value && hasRejectedApproval.value
})

const rejectionReason = computed<string | null>(() => {
  const approval = latestApproval.value
  if (approval === null || approval.status !== 'REJECTED') return null
  if (approval.reject_reason !== undefined && approval.reject_reason.trim() !== '') return approval.reject_reason

  const rejectedNode = approval.nodes.find((node) => node.status === 'REJECT' || node.status === 'REJECTED')
  return rejectedNode?.comment ?? '审批被驳回，请查看详情'
})

const currentApproverName = computed<string>(() => {
  const approval = latestApproval.value
  if (approval === null || approval.status !== 'PENDING') return '-'

  const pendingNode = approval.nodes.find((node) => node.status === 'PENDING')
  return pendingNode?.approver_name ?? '待分配'
})

const paymentProgress = computed<number>(() => {
  const plan = paymentPlan.value
  if (plan === null || plan.planned_amount <= 0) return 0
  const paidAmount = plan.paid_amount ?? 0
  return Math.min(100, Math.round((paidAmount / plan.planned_amount) * 100))
})

const fetchPaymentPlanDetail = async (planId: number): Promise<void> => {
  const requestId = activeRequestId.value + 1
  activeRequestId.value = requestId
  loading.value = true
  errorMessage.value = ''
  paymentPlan.value = null

  try {
    const data = await paymentApi.getPaymentPlanDetail(planId)
    if (requestId !== activeRequestId.value) return
    paymentPlan.value = data
  } catch (error: unknown) {
    if (requestId !== activeRequestId.value) return
    errorMessage.value = '回款计划加载失败，请稍后重试'
    handleApiError(error, '获取回款计划详情')
  } finally {
    if (requestId === activeRequestId.value) {
      loading.value = false
    }
  }
}

const resetState = (): void => {
  activeRequestId.value += 1
  loading.value = false
  errorMessage.value = ''
  paymentPlan.value = null
}

const handleOpenChange = (open: boolean): void => {
  emit('update:visible', open)
}

const closeSheet = (): void => {
  emit('update:visible', false)
}

const handleRetry = (): void => {
  if (props.planId !== null) {
    void fetchPaymentPlanDetail(props.planId)
  }
}

const handleRegisterPayment = (): void => {
  if (paymentPlan.value === null || !canRegisterPayment.value) return
  emit('register-payment', paymentPlan.value)
}

const handleRecordClick = (record: PaymentRecordInfo): void => {
  emit('record-click', record)
}

const handleEditRecord = (record: PaymentRecordInfo): void => {
  emit('edit-record', record)
}

const handleViewApproval = (record: PaymentRecordInfo): void => {
  emit('view-approval', record)
}

const handleViewCustomer = (): void => {
  const plan = paymentPlan.value
  const customerId = plan?.customer_id
  if (plan === null || typeof customerId !== 'number') return
  emit('view-customer', customerId, plan)
}

const handleViewContract = (): void => {
  const plan = paymentPlan.value
  if (plan === null) return
  emit('view-contract', plan.contract_id, plan)
}

const handleSubmitApproval = (): void => {
  const plan = paymentPlan.value
  const record = latestRecord.value
  if (plan === null || record === null || !canSubmitApproval.value) return
  emit('submit-approval', plan, record.id)
}

const handleResubmitApproval = (): void => {
  const plan = paymentPlan.value
  const record = latestRecord.value
  if (plan === null || record === null || !canResubmitApproval.value) return
  emit('resubmit-approval', plan, record.id)
}

const mapPaymentPlanStatus = (status: PaymentPlanStatus): PaymentPlanBadgeStatus => {
  const statusMap: Record<PaymentPlanStatus, PaymentPlanBadgeStatus> = {
    PENDING: 'pending',
    OVERDUE: 'overdue',
    PARTIAL: 'partial',
    COMPLETED: 'completed'
  }
  return statusMap[status]
}

const getApprovalStatusLabel = (status: ApprovalStatus): string => {
  const statusMap: Record<ApprovalStatus, string> = {
    PENDING: '审批中',
    APPROVED: '已通过',
    REJECTED: '已驳回'
  }
  return statusMap[status]
}

const getApprovalBadgeClass = (status: ApprovalStatus): string => {
  const statusMap: Record<ApprovalStatus, string> = {
    PENDING: 'approval-status-warning',
    APPROVED: 'approval-status-success',
    REJECTED: 'approval-status-danger'
  }
  return statusMap[status]
}

const getApprovalNodeStatusText = (node: ApprovalNodeInfo): string => {
  if (node.status === 'SUBMIT') return '已提交'
  if (node.status === 'APPROVE' || node.status === 'APPROVED') return '已通过'
  if (node.status === 'REJECT' || node.status === 'REJECTED') return '已驳回'
  return '待审批'
}

const getApprovalNodeClass = (node: ApprovalNodeInfo): string => {
  if (node.status === 'APPROVE' || node.status === 'APPROVED' || node.status === 'SUBMIT') return 'node-approved'
  if (node.status === 'REJECT' || node.status === 'REJECTED') return 'node-rejected'
  return 'node-pending'
}

const formatDate = (dateStr: string | undefined): string => {
  if (dateStr === undefined || dateStr.trim() === '') return '-'
  const date = new Date(dateStr)
  return Number.isNaN(date.getTime()) ? '-' : formatLocalDate(date)
}

const formatDateTime = (dateStr: string | undefined): string => {
  if (dateStr === undefined || dateStr.trim() === '') return '-'
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return '-'
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}`
}

const formatText = (value: string | number | boolean | undefined | null): string => {
  if (value === undefined || value === null || value === '') return '-'
  return String(value)
}

const formatInvoiceCount = (count: number | undefined): string => {
  return `${count ?? 0} 张`
}

watch(
  [(): boolean => props.visible, (): number | null => props.planId],
  ([visible, planId]): void => {
    if (!visible) {
      resetState()
    } else if (planId !== null) {
      void fetchPaymentPlanDetail(planId)
    } else {
      resetState()
    }
  },
  { immediate: true }
)
</script>

<template>
  <Sheet :open="visible" @update:open="handleOpenChange">
    <DetailSheetContent>
      <SheetHeader class="payment-sheet-header">
        <div class="payment-header-summary">
          <div v-if="paymentPlan" class="title-avatar" aria-hidden="true">
            {{ paymentPlan.stage_name.charAt(0) || '款' }}
          </div>

          <div class="header-title-block">
            <SheetTitle class="payment-sheet-title">
              {{ paymentPlan?.stage_name ?? '回款计划详情' }}
            </SheetTitle>
            <SheetDescription class="payment-sheet-description">
              <StatusBadge
                v-if="paymentPlan"
                :status="mapPaymentPlanStatus(paymentPlan.status)"
                type="paymentPlan"
              />
              <span v-else>{{ loading ? '正在加载回款计划' : '查看计划、记录与审批进度' }}</span>
            </SheetDescription>
          </div>

          <div v-if="paymentPlan" class="amount-summary" aria-label="回款金额概览">
            <div class="amount-summary-item">
              <span class="amount-summary-label">计划</span>
              <strong>{{ formatCurrency(paymentPlan.planned_amount) }}</strong>
            </div>
            <div class="amount-summary-item paid">
              <span class="amount-summary-label">已回款</span>
              <strong>{{ formatCurrency(paymentPlan.paid_amount ?? 0) }}</strong>
            </div>
            <div class="amount-summary-item remaining">
              <span class="amount-summary-label">待回款</span>
              <strong>{{ formatCurrency(paymentPlan.remaining_amount ?? 0) }}</strong>
            </div>
          </div>
        </div>
      </SheetHeader>

      <ScrollArea class="flex-1">
        <div class="sheet-body">
          <template v-if="loading">
            <div class="loading-stack" aria-live="polite" aria-busy="true">
              <Skeleton class="h-28 w-full" />
              <Skeleton class="h-48 w-full" />
              <Skeleton class="h-64 w-full" />
            </div>
          </template>

          <template v-else-if="errorMessage">
            <Card class="state-card">
              <CardContent class="state-card-content">
                <Empty>
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <AlertCircle aria-hidden="true" />
                    </EmptyMedia>
                    <EmptyTitle>{{ errorMessage }}</EmptyTitle>
                    <EmptyDescription>请检查网络连接后重试。</EmptyDescription>
                  </EmptyHeader>
                </Empty>
                <Button variant="outline" type="button" @click="handleRetry">
                  <RefreshCw data-icon="inline-start" aria-hidden="true" />
                  重新加载
                </Button>
              </CardContent>
            </Card>
          </template>

          <template v-else-if="paymentPlan">
            <Card class="info-card">
              <CardHeader class="section-heading">
                <CardTitle class="section-title">基本信息</CardTitle>
                <CardDescription>客户、合同、计划日期与发票汇总。</CardDescription>
              </CardHeader>
              <CardContent class="section-content">
                <div class="attributes-grid">
                  <div class="attribute-item">
                    <span class="attribute-label">客户名称</span>
                    <Button
                      v-if="typeof paymentPlan.customer_id === 'number'"
                      variant="link"
                      type="button"
                      class="attribute-link"
                      :aria-label="`查看客户 ${paymentPlan.customer_name ?? '未知客户'}`"
                      @click="handleViewCustomer"
                    >
                      {{ formatText(paymentPlan.customer_name) }}
                    </Button>
                    <span v-else class="attribute-value">{{ formatText(paymentPlan.customer_name) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">合同名称</span>
                    <Button
                      variant="link"
                      type="button"
                      class="attribute-link"
                      :aria-label="`查看合同 ${paymentPlan.contract_name ?? '未知合同'}`"
                      @click="handleViewContract"
                    >
                      {{ formatText(paymentPlan.contract_name) }}
                    </Button>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">计划日期</span>
                    <span class="attribute-value">{{ formatDate(paymentPlan.due_date) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">计划编号</span>
                    <span class="attribute-value mono-value">{{ formatText(paymentPlan.plan_number) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">待回款金额</span>
                    <span class="attribute-value mono-value amount-remaining">{{ formatCurrency(paymentPlan.remaining_amount ?? 0) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">已开票金额</span>
                    <span class="attribute-value mono-value">{{ formatCurrency(paymentPlan.invoiced_amount ?? 0) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">发票数量</span>
                    <span class="attribute-value mono-value">{{ formatInvoiceCount(paymentPlan.invoice_count) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">完成度</span>
                    <span class="attribute-value mono-value">{{ paymentProgress }}%</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <PaymentRecordList
              :records="paymentPlan.payment_records"
              :can-register="canRegisterPayment"
              @register="handleRegisterPayment"
              @record-click="handleRecordClick"
              @edit-record="handleEditRecord"
              @view-approval="handleViewApproval"
            />

            <Card v-if="latestApproval" class="approval-card">
              <CardHeader class="section-heading approval-heading">
                <div>
                  <CardTitle class="section-title">审批进度</CardTitle>
                  <CardDescription>最新回款记录的审批状态。</CardDescription>
                </div>
                <Badge :class="['approval-status-badge', getApprovalBadgeClass(latestApproval.status)]">
                  {{ getApprovalStatusLabel(latestApproval.status) }}
                </Badge>
              </CardHeader>
              <CardContent class="section-content approval-content">
                <Alert v-if="hasRejectedApproval" variant="destructive">
                  <AlertCircle aria-hidden="true" />
                  <AlertTitle>审批被驳回</AlertTitle>
                  <AlertDescription>{{ rejectionReason ?? '请查看驳回原因并修正后重新提交' }}</AlertDescription>
                </Alert>

                <div class="approval-summary-grid">
                  <div class="attribute-item">
                    <span class="attribute-label">审批人</span>
                    <span class="attribute-value">{{ currentApproverName }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">提交时间</span>
                    <span class="attribute-value mono-value">{{ formatDateTime(latestApproval.created_time) }}</span>
                  </div>
                </div>

                <ol v-if="latestApproval.nodes.length > 0" class="approval-node-list" aria-label="审批节点">
                  <li
                    v-for="node in latestApproval.nodes"
                    :key="node.id"
                    :class="['approval-node', getApprovalNodeClass(node)]"
                  >
                    <div class="node-marker" aria-hidden="true" />
                    <div class="node-content">
                      <div class="node-title-line">
                        <span class="node-name">{{ node.node_name }}</span>
                        <Badge variant="outline">{{ getApprovalNodeStatusText(node) }}</Badge>
                      </div>
                      <div class="node-meta">
                        <span>{{ node.approver_name ?? node.approve_role }}</span>
                        <span v-if="node.approved_time">{{ formatDateTime(node.approved_time) }}</span>
                      </div>
                      <p v-if="node.comment" class="node-comment">{{ node.comment }}</p>
                    </div>
                  </li>
                </ol>
              </CardContent>
            </Card>
          </template>

          <template v-else>
            <Card class="state-card">
              <CardContent class="state-card-content">
                <Empty>
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <FileText aria-hidden="true" />
                    </EmptyMedia>
                    <EmptyTitle>暂无回款计划信息</EmptyTitle>
                    <EmptyDescription>请选择一个回款计划查看详情。</EmptyDescription>
                  </EmptyHeader>
                </Empty>
              </CardContent>
            </Card>
          </template>
        </div>
      </ScrollArea>

      <SheetFooter class="payment-sheet-footer">
        <Button
          v-if="canResubmitApproval"
          variant="outline"
          type="button"
          @click="handleResubmitApproval"
        >
          <Undo2 data-icon="inline-start" aria-hidden="true" />
          重新提交审批
        </Button>
        <Button
          v-if="canSubmitApproval"
          type="button"
          @click="handleSubmitApproval"
        >
          <Send data-icon="inline-start" aria-hidden="true" />
          提交审批
        </Button>
        <Button
          v-if="hasPendingApproval"
          variant="secondary"
          type="button"
          disabled
        >
          <Loader2 data-icon="inline-start" aria-hidden="true" />
          审批中...
        </Button>
        <Button
          v-if="hasApprovedApproval"
          variant="secondary"
          type="button"
          disabled
        >
          <WalletCards data-icon="inline-start" aria-hidden="true" />
          已通过
        </Button>
        <Button
          v-if="canRegisterPayment"
          variant="outline"
          type="button"
          @click="handleRegisterPayment"
        >
          <ReceiptText data-icon="inline-start" aria-hidden="true" />
          登记回款
        </Button>
        <Button variant="outline" type="button" @click="closeSheet">
          <X data-icon="inline-start" aria-hidden="true" />
          关闭
        </Button>
      </SheetFooter>
    </DetailSheetContent>
  </Sheet>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

$payment-border-width: $wolf-focus-ring-width-subtle-v2;
$payment-title-avatar-size: calc($wolf-touch-target-min-v2 + $wolf-space-xs-v2);
$payment-header-mobile-indent: calc($payment-title-avatar-size + $wolf-space-md-v2);
$payment-sheet-min-height: ($wolf-touch-target-min-v2 * 12) + $wolf-space-2xl-v2;
$payment-empty-min-height: ($wolf-touch-target-min-v2 * 6) + $wolf-space-lg-v2;

.payment-sheet-header {
  padding: $wolf-space-xl-v2;
  padding-bottom: $wolf-space-lg-v2;
  border-bottom: $payment-border-width solid $wolf-border-default-v2;
}

.payment-header-summary {
  display: flex;
  align-items: center;
  gap: $wolf-space-md-v2;
  min-width: 0;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    align-items: flex-start;
    flex-wrap: wrap;
  }
}

.title-avatar {
  width: $payment-title-avatar-size;
  height: $payment-title-avatar-size;
  border-radius: $wolf-radius-full-v2;
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: $wolf-topbar-title-font-size-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  flex-shrink: 0;
}

.header-title-block {
  flex: 1;
  min-width: 0;
}

.payment-sheet-title {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  line-height: $wolf-line-height-title-v2;
}

.payment-sheet-description {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  min-height: $wolf-touch-target-min-v2;
  color: $wolf-text-tertiary-v2;
}

.amount-summary {
  display: grid;
  grid-template-columns: repeat(3, max-content);
  gap: $wolf-space-md-v2;
  align-items: center;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
    width: 100%;
    padding-left: $payment-header-mobile-indent;
  }
}

.amount-summary-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
  border: $payment-border-width solid $wolf-border-light-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-bg-muted-v2;

  strong {
    color: $wolf-text-primary-v2;
    font-family: $wolf-font-mono-v2;
    font-size: $wolf-font-size-body-v2;
    font-weight: $wolf-font-weight-semibold-v2;
    font-variant-numeric: tabular-nums;
  }

  &.paid strong {
    color: $wolf-success-text-v2;
  }

  &.remaining strong {
    color: $wolf-warning-text-v2;
  }
}

.amount-summary-label {
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
}

.sheet-body {
  padding: $wolf-space-xl-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xl-v2;
  min-height: $payment-sheet-min-height;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    padding: $wolf-space-md-v2;
    gap: $wolf-space-lg-v2;
  }
}

.loading-stack {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
}

.info-card,
.approval-card,
.state-card {
  background: $wolf-bg-card-v2;
  border: $payment-border-width solid $wolf-border-default-v2;
  border-radius: $wolf-radius-lg-v2;
  box-shadow: $wolf-shadow-card-v2;
}

.section-heading {
  padding: $wolf-space-md-v2 $wolf-space-lg-v2;
  border-bottom: $payment-border-width solid $wolf-border-light-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.section-title {
  margin: 0;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.section-content {
  padding: $wolf-space-lg-v2;
}

.attributes-grid,
.approval-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: $wolf-space-md-v2 $wolf-space-lg-v2;

  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
  }
}

.approval-summary-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
  }
}

.attribute-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  min-width: 0;
}

.attribute-label {
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.attribute-value,
.attribute-link {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: $wolf-line-height-body-v2;
  word-break: break-word;
}

.attribute-link {
  min-height: $wolf-touch-target-min-v2;
  justify-content: flex-start;
  padding: 0;
  color: $wolf-text-link-v2;
  text-align: left;

  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }
}

.mono-value {
  font-family: $wolf-font-mono-v2;
  font-variant-numeric: tabular-nums;
}

.amount-remaining {
  color: $wolf-warning-text-v2;
}

.approval-heading {
  flex-direction: row;
  align-items: flex-start;
  justify-content: space-between;
  gap: $wolf-space-md-v2;
}

.approval-content {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
}

.approval-status-badge,
.approval-node :deep([data-slot='badge']) {
  white-space: nowrap;
}

.approval-status-warning {
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
  border-color: transparent;
}

.approval-status-success {
  background: $wolf-success-bg-v2;
  color: $wolf-success-text-v2;
  border-color: transparent;
}

.approval-status-danger {
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-text-v2;
  border-color: transparent;
}

.approval-node-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
}

.approval-node {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: $wolf-space-md-v2;
  min-height: $wolf-touch-target-min-v2;
}

.node-marker {
  width: $wolf-space-md-v2;
  height: $wolf-space-md-v2;
  margin-top: $wolf-space-xs-v2;
  border-radius: $wolf-radius-full-v2;
  background: $wolf-border-default-v2;
}

.node-approved .node-marker {
  background: $wolf-success-v2;
}

.node-rejected .node-marker {
  background: $wolf-danger-v2;
}

.node-pending .node-marker {
  background: $wolf-warning-v2;
}

.node-content {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  min-width: 0;
}

.node-title-line {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  flex-wrap: wrap;
}

.node-name {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.node-meta,
.node-comment {
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
}

.node-meta {
  display: flex;
  gap: $wolf-space-sm-v2;
  flex-wrap: wrap;
}

.node-comment {
  margin: 0;
  color: $wolf-text-secondary-v2;
}

.state-card-content {
  min-height: $payment-empty-min-height;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: $wolf-space-md-v2;
  padding: $wolf-space-xl-v2;
}

.payment-sheet-footer {
  padding: $wolf-space-lg-v2;
  border-top: $payment-border-width solid $wolf-border-default-v2;
  display: flex;
  flex-direction: row;
  justify-content: flex-end;
  gap: $wolf-space-sm-v2;
  flex-wrap: wrap;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    :deep(button) {
      flex: 1 1 100%;
    }
  }
}

@media (prefers-reduced-motion: reduce) {
  .payment-header-summary,
  .approval-node {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>
