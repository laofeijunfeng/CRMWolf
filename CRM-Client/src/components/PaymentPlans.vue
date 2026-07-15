<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  Calendar,
  CheckCircle2,
  ClipboardList,
  CreditCard,
  MoreHorizontal,
  Pencil,
  Plus,
  ReceiptText,
  Trash2,
  WalletCards
} from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle
} from '@/components/ui/alert-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { DatePicker } from '@/components/ui/date-picker'
import { Card, CardContent } from '@/components/ui/card'
import ListCard from '@/components/crmwolf/ListCard.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import PaymentRecords from './PaymentRecords.vue'
import PaymentPlanQuickCreate from './PaymentPlanQuickCreate.vue'
import PaymentNextStepDialog from './PaymentNextStepDialog.vue'
import paymentApi, {
  type PaymentPlanResponse,
  type PaymentPlanStatus,
  type PaymentRecordCreate,
  type PaymentRecordResponse
} from '@/api/payment'
import { formatCurrency, formatLocalDate, getTodayLocalDate } from '@/utils/format'
import { handleApiError } from '@/utils/errorHandler'
import { logger } from '@/utils/logger'

interface ContractInfo {
  contract_name: string
  contract_number: string
  total_amount: number
  customer_info?: { account_name: string }
  effective_date?: string
  signing_date?: string
}

interface Props {
  contractId: number
  contractStatus?: string | undefined
  contractInfo?: ContractInfo | undefined
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'plan-updated': []
}>()

const loading = ref<boolean>(false)
const plans = ref<PaymentPlanResponse[]>([])
const quickCreateVisible = ref<boolean>(false)

const paymentModalVisible = ref<boolean>(false)
interface PaymentFormState extends PaymentRecordCreate {
  actual_amount: number
  payment_date: string
  proof_attachment: string
  notes: string
}

interface EditPlanFormState {
  stage_name: string
  planned_amount: number
  due_date: string
  notes: string
}

const paymentForm = ref<PaymentFormState>({
  actual_amount: 0,
  payment_date: '',
  proof_attachment: '',
  notes: ''
})
const currentPlan = ref<PaymentPlanResponse | null>(null)
const submittingPayment = ref<boolean>(false)
const showPaymentDiscardDialog = ref<boolean>(false)

const recordsModalVisible = ref<boolean>(false)
const editModalVisible = ref<boolean>(false)
const editForm = ref<EditPlanFormState>({
  stage_name: '',
  planned_amount: 0,
  due_date: '',
  notes: ''
})
const editingPlan = ref<PaymentPlanResponse | null>(null)
const updatingPlan = ref<boolean>(false)

const planToDelete = ref<PaymentPlanResponse | null>(null)
const deletingPlan = ref<boolean>(false)

const showNextStepDialog = ref<boolean>(false)
const createdRecord = ref<PaymentRecordResponse | null>(null)

const completedCount = computed<number>(() => {
  return plans.value.filter((plan) => plan.status === 'COMPLETED').length
})

const plannedAmountTotal = computed<number>(() => {
  return plans.value.reduce((sum, plan) => sum + plan.planned_amount, 0)
})

const paidAmountTotal = computed<number>(() => {
  return plans.value.reduce((sum, plan) => sum + (plan.paid_amount ?? 0), 0)
})

const paymentProgress = computed<number>(() => {
  if (plannedAmountTotal.value <= 0) return 0
  return Math.min(100, Math.round((paidAmountTotal.value / plannedAmountTotal.value) * 100))
})

const hasUnsavedPaymentData = computed<boolean>(() => {
  return paymentForm.value.actual_amount > 0 ||
    paymentForm.value.payment_date !== '' ||
    (paymentForm.value.notes ?? '').length > 0 ||
    (paymentForm.value.proof_attachment ?? '').length > 0
})

const currentPlanDialogTitle = computed<string>(() => {
  return currentPlan.value === null ? '回款记录' : `${currentPlan.value.stage_name} - 回款记录`
})

const fetchPlans = async (): Promise<void> => {
  loading.value = true
  try {
    plans.value = await paymentApi.getPaymentPlans(props.contractId)
  } catch (error: unknown) {
    logger.error('[PaymentPlans]', '获取回款计划失败', { error })
    handleApiError(error, '获取回款计划')
  } finally {
    loading.value = false
  }
}

const mapStatus = (status: PaymentPlanStatus): 'pending' | 'overdue' | 'partial' | 'completed' => {
  const statusMap: Record<PaymentPlanStatus, 'pending' | 'overdue' | 'partial' | 'completed'> = {
    PENDING: 'pending',
    OVERDUE: 'overdue',
    PARTIAL: 'partial',
    COMPLETED: 'completed'
  }
  return statusMap[status]
}

const getStatusToneClass = (status: PaymentPlanStatus): string => {
  const toneMap: Record<PaymentPlanStatus, string> = {
    PENDING: 'plan-status-pending',
    OVERDUE: 'plan-status-overdue',
    PARTIAL: 'plan-status-partial',
    COMPLETED: 'plan-status-completed'
  }
  return toneMap[status]
}

const formatDate = (dateStr: string | undefined): string => {
  if (dateStr === undefined || dateStr === '') return '-'
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return '-'
  return formatLocalDate(date)
}

const toDateValue = (value: string | undefined): Date | null => {
  if (value === undefined || value === '') return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

const calculatePlanProgress = (plan: PaymentPlanResponse): number => {
  if (plan.planned_amount <= 0) return 0
  return Math.min(100, Math.round(((plan.paid_amount ?? 0) / plan.planned_amount) * 100))
}

const normalizeNumber = (value: string | number | undefined): number => {
  if (typeof value === 'number') return value
  if (typeof value === 'string') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : 0
  }
  return 0
}

const handleCreatePlan = (): void => {
  quickCreateVisible.value = true
}

const handleQuickCreateSuccess = (): void => {
  void fetchPlans()
  emit('plan-updated')
}

const showPaymentModal = (plan: PaymentPlanResponse): void => {
  currentPlan.value = plan
  paymentForm.value = {
    actual_amount: plan.remaining_amount ?? plan.planned_amount,
    payment_date: getTodayLocalDate(),
    proof_attachment: '',
    notes: ''
  }
  paymentModalVisible.value = true
}

const resetPaymentForm = (): void => {
  paymentForm.value = {
    actual_amount: 0,
    payment_date: '',
    proof_attachment: '',
    notes: ''
  }
}

const requestClosePaymentDialog = (open?: boolean): void => {
  if (open === true) return

  if (hasUnsavedPaymentData.value) {
    showPaymentDiscardDialog.value = true
    return
  }

  paymentModalVisible.value = false
  resetPaymentForm()
}

const confirmClosePaymentDialog = (): void => {
  showPaymentDiscardDialog.value = false
  paymentModalVisible.value = false
  resetPaymentForm()
}

const handleCreatePayment = async (): Promise<void> => {
  const plan = currentPlan.value
  if (plan === null) return

  const actualAmount = normalizeNumber(paymentForm.value.actual_amount)
  if (actualAmount <= 0) {
    toast.error('请输入有效的回款金额')
    return
  }

  if (paymentForm.value.payment_date === '') {
    toast.error('请选择回款日期')
    return
  }

  submittingPayment.value = true
  try {
    const record = await paymentApi.createPaymentRecord(plan.id, {
      ...paymentForm.value,
      actual_amount: actualAmount
    })
    toast.success('登记成功')
    createdRecord.value = record
    showNextStepDialog.value = true
    await fetchPlans()
    emit('plan-updated')
  } catch (error: unknown) {
    logger.error('[PaymentPlans]', '登记回款失败', { error })
    handleApiError(error, '登记回款')
  } finally {
    submittingPayment.value = false
  }
}

const showRecords = (plan: PaymentPlanResponse): void => {
  currentPlan.value = plan
  recordsModalVisible.value = true
}

const handleRecordUpdated = (): void => {
  void fetchPlans()
  emit('plan-updated')
}

const editPlan = (plan: PaymentPlanResponse): void => {
  editingPlan.value = plan
  editForm.value = {
    stage_name: plan.stage_name,
    planned_amount: plan.planned_amount,
    due_date: plan.due_date,
    notes: plan.notes ?? ''
  }
  editModalVisible.value = true
}

const handleUpdatePlan = async (): Promise<void> => {
  const plan = editingPlan.value
  if (plan === null) return

  const stageName = editForm.value.stage_name ?? ''
  const plannedAmount = normalizeNumber(editForm.value.planned_amount)
  const dueDate = editForm.value.due_date ?? ''

  if (stageName.trim() === '' || plannedAmount <= 0 || dueDate === '') {
    toast.error('请填写完整的计划信息')
    return
  }

  updatingPlan.value = true
  try {
    await paymentApi.updatePaymentPlan(plan.id, {
      stage_name: stageName.trim(),
      planned_amount: plannedAmount,
      due_date: dueDate,
      notes: editForm.value.notes
    })
    toast.success('回款计划已更新')
    editModalVisible.value = false
    await fetchPlans()
    emit('plan-updated')
  } catch (error: unknown) {
    logger.error('[PaymentPlans]', '更新回款计划失败', { error })
    handleApiError(error, '更新回款计划')
  } finally {
    updatingPlan.value = false
  }
}

const requestDeletePlan = (plan: PaymentPlanResponse): void => {
  if (plan.payment_records.length > 0) {
    toast.warning('存在回款记录的计划不能删除')
    return
  }
  planToDelete.value = plan
}

const handleDeletePlan = async (): Promise<void> => {
  const plan = planToDelete.value
  if (plan === null) return

  deletingPlan.value = true
  try {
    await paymentApi.deletePaymentPlan(plan.id)
    toast.success('回款计划已删除')
    planToDelete.value = null
    await fetchPlans()
    emit('plan-updated')
  } catch (error: unknown) {
    logger.error('[PaymentPlans]', '删除回款计划失败', { error })
    handleApiError(error, '删除回款计划')
  } finally {
    deletingPlan.value = false
  }
}

const closeDeleteDialog = (open: boolean): void => {
  if (!open) {
    planToDelete.value = null
  }
}

const handleNextStepClose = (visible: boolean): void => {
  showNextStepDialog.value = visible
  if (!visible) {
    paymentModalVisible.value = false
    createdRecord.value = null
    resetPaymentForm()
  }
}

const handleNextStepSubmitted = (): void => {
  void fetchPlans()
  emit('plan-updated')
}

const refresh = (): void => {
  void fetchPlans()
}

defineExpose({
  refresh
})

watch(
  () => props.contractId,
  () => {
    void fetchPlans()
  },
  { immediate: true }
)
</script>

<template>
  <ListCard
    title="回款计划"
    :items="plans"
    :loading="loading"
    empty-text="暂无回款计划"
  >
    <template #headerActions>
      <Button size="sm" @click="handleCreatePlan">
        <Plus class="w-4 h-4" aria-hidden="true" />
        新建计划
      </Button>
    </template>

    <template #itemMain="{ item }">
      <div class="plan-row" :class="getStatusToneClass(item.status)">
        <div class="plan-row-header">
          <div class="plan-title-block">
            <div class="plan-title-line">
              <span class="stage-name">{{ item.stage_name }}</span>
              <StatusBadge
                :status="mapStatus(item.status)"
                type="paymentPlan"
                size="small"
              />
            </div>
            <div class="plan-subtitle">
              <Calendar class="plan-subtitle-icon" aria-hidden="true" />
              计划回款日：{{ formatDate(item.due_date) }}
            </div>
          </div>

          <div class="plan-amount">
            <span class="amount-label">计划金额</span>
            <span class="amount-value">{{ formatCurrency(item.planned_amount) }}</span>
          </div>
        </div>

        <div class="plan-metrics" aria-label="回款计划金额概览">
          <div class="metric-item">
            <WalletCards class="metric-icon" aria-hidden="true" />
            <span class="metric-label">已回款</span>
            <span class="metric-value">{{ formatCurrency(item.paid_amount ?? 0) }}</span>
          </div>
          <div class="metric-item">
            <ReceiptText class="metric-icon" aria-hidden="true" />
            <span class="metric-label">待回款</span>
            <span class="metric-value">{{ formatCurrency(item.remaining_amount ?? 0) }}</span>
          </div>
          <div class="metric-item">
            <CheckCircle2 class="metric-icon" aria-hidden="true" />
            <span class="metric-label">完成度</span>
            <span class="metric-value">{{ calculatePlanProgress(item) }}%</span>
          </div>
        </div>

        <Progress
          :model-value="calculatePlanProgress(item)"
          class="plan-progress"
          :aria-label="`${item.stage_name} 回款进度 ${calculatePlanProgress(item)}%`"
        />

        <p v-if="item.notes" class="plan-notes">
          {{ item.notes }}
        </p>
      </div>
    </template>

    <template #itemActions="{ item }">
      <Button
        variant="outline"
        size="sm"
        :aria-label="`查看 ${item.stage_name} 的回款记录`"
        @click.stop="showRecords(item)"
      >
        <ClipboardList class="w-4 h-4" aria-hidden="true" />
        回款记录
      </Button>

      <Button
        v-if="item.status !== 'COMPLETED'"
        size="sm"
        :aria-label="`为 ${item.stage_name} 登记回款`"
        @click.stop="showPaymentModal(item)"
      >
        <CreditCard class="w-4 h-4" aria-hidden="true" />
        登记回款
      </Button>

      <DropdownMenu v-if="item.status !== 'COMPLETED'">
        <DropdownMenuTrigger as-child>
          <Button
            variant="ghost"
            size="icon"
            :aria-label="`${item.stage_name} 更多操作`"
            @click.stop
          >
            <MoreHorizontal class="w-4 h-4" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem @click.stop="editPlan(item)">
            <Pencil class="w-4 h-4 mr-2" aria-hidden="true" />
            编辑
          </DropdownMenuItem>
          <DropdownMenuItem
            :disabled="item.payment_records.length > 0"
            @click.stop="requestDeletePlan(item)"
          >
            <Trash2 class="w-4 h-4 mr-2 text-wolf-danger-text-v2" aria-hidden="true" />
            删除
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </template>
  </ListCard>

  <Card v-if="plans.length > 0" class="payment-summary-card" aria-label="回款计划汇总">
    <CardContent class="payment-summary-content">
      <div class="summary-copy">
        <span class="summary-eyebrow">合同回款编排</span>
        <strong>{{ completedCount }} / {{ plans.length }} 个阶段已完成</strong>
      </div>
      <div class="summary-progress-block">
        <span>{{ formatCurrency(paidAmountTotal) }} / {{ formatCurrency(plannedAmountTotal) }}</span>
        <Progress
          :model-value="paymentProgress"
          class="summary-progress"
          :aria-label="`合同回款总进度 ${paymentProgress}%`"
        />
      </div>
    </CardContent>
  </Card>

  <Teleport to="body">
    <Dialog :open="paymentModalVisible" @update:open="requestClosePaymentDialog">
    <DialogContent class="max-h-[90vh] overflow-y-auto sm:max-w-[520px]">
      <DialogHeader>
        <DialogTitle>登记回款</DialogTitle>
        <DialogDescription>
          记录 {{ currentPlan?.stage_name ?? '当前阶段' }} 的实际回款信息。
        </DialogDescription>
      </DialogHeader>

      <div class="dialog-form-grid">
        <div class="form-field">
          <Label for="payment-amount">回款金额 <span class="required-mark">*</span></Label>
          <Input
            id="payment-amount"
            v-model="paymentForm.actual_amount"
            type="number"
            min="0"
            step="0.01"
            placeholder="请输入回款金额"
            aria-label="回款金额"
          />
          <p v-if="currentPlan" class="field-hint">
            待回款：{{ formatCurrency(currentPlan.remaining_amount ?? 0) }}
          </p>
        </div>

        <div class="form-field">
          <Label>回款日期 <span class="required-mark">*</span></Label>
          <DatePicker
            :model-value="toDateValue(paymentForm.payment_date)"
            placeholder="请选择回款日期"
            @update:model-value="(date: Date | null) => { paymentForm.payment_date = date === null ? '' : formatLocalDate(date) }"
          />
        </div>

        <div class="form-field">
          <Label for="payment-proof">凭证附件</Label>
          <Input
            id="payment-proof"
            v-model="paymentForm.proof_attachment"
            placeholder="附件 URL（可选）"
            aria-label="凭证附件"
          />
        </div>

        <div class="form-field">
          <Label for="payment-notes">备注</Label>
          <Textarea
            id="payment-notes"
            v-model="paymentForm.notes"
            maxlength="200"
            placeholder="备注信息（可选）"
            aria-label="回款备注"
          />
        </div>
      </div>

      <DialogFooter>
        <Button variant="outline" type="button" @click="requestClosePaymentDialog()">
          取消
        </Button>
        <Button type="button" :disabled="submittingPayment" @click="handleCreatePayment">
          {{ submittingPayment ? '登记中...' : '确定' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <Dialog v-model:open="recordsModalVisible">
    <DialogContent class="max-h-[90vh] overflow-y-auto sm:max-w-[800px]">
      <DialogHeader>
        <DialogTitle>{{ currentPlanDialogTitle }}</DialogTitle>
        <DialogDescription>查看该阶段的回款登记历史。</DialogDescription>
      </DialogHeader>
      <PaymentRecords
        v-if="currentPlan"
        :plan-id="currentPlan.id"
        @record-updated="handleRecordUpdated"
      />
    </DialogContent>
  </Dialog>

  <Dialog v-model:open="editModalVisible">
    <DialogContent class="max-h-[90vh] overflow-y-auto sm:max-w-[520px]">
      <DialogHeader>
        <DialogTitle>编辑回款计划</DialogTitle>
        <DialogDescription>调整阶段名称、金额和计划回款日期。</DialogDescription>
      </DialogHeader>

      <div class="dialog-form-grid">
        <div class="form-field">
          <Label for="plan-stage-name">阶段名称 <span class="required-mark">*</span></Label>
          <Input
            id="plan-stage-name"
            v-model="editForm.stage_name"
            placeholder="阶段名称"
            aria-label="阶段名称"
          />
        </div>

        <div class="form-field">
          <Label for="plan-amount">计划金额 <span class="required-mark">*</span></Label>
          <Input
            id="plan-amount"
            v-model="editForm.planned_amount"
            type="number"
            min="0"
            step="0.01"
            placeholder="计划金额"
            aria-label="计划金额"
          />
        </div>

        <div class="form-field">
          <Label>计划日期 <span class="required-mark">*</span></Label>
          <DatePicker
            :model-value="toDateValue(editForm.due_date)"
            placeholder="计划回款日期"
            @update:model-value="(date: Date | null) => { editForm.due_date = date === null ? '' : formatLocalDate(date) }"
          />
        </div>

        <div class="form-field">
          <Label for="plan-notes">备注</Label>
          <Textarea
            id="plan-notes"
            v-model="editForm.notes"
            maxlength="200"
            placeholder="备注（可选）"
            aria-label="计划备注"
          />
        </div>
      </div>

      <DialogFooter>
        <Button variant="outline" type="button" @click="editModalVisible = false">
          取消
        </Button>
        <Button type="button" :disabled="updatingPlan" @click="handleUpdatePlan">
          {{ updatingPlan ? '保存中...' : '保存' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <AlertDialog :open="planToDelete !== null" @update:open="closeDeleteDialog">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>删除回款计划？</AlertDialogTitle>
        <AlertDialogDescription>
          确定要删除回款计划“{{ planToDelete?.stage_name }}”吗？此操作不可恢复。
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel>取消</AlertDialogCancel>
        <AlertDialogAction :disabled="deletingPlan" @click="handleDeletePlan">
          {{ deletingPlan ? '删除中...' : '删除' }}
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>

  <AlertDialog v-model:open="showPaymentDiscardDialog">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>放弃登记内容？</AlertDialogTitle>
        <AlertDialogDescription>
          已填写的回款信息将丢失，确定要关闭吗？
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel>继续填写</AlertDialogCancel>
        <AlertDialogAction @click="confirmClosePaymentDialog">
          放弃更改
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>

  <PaymentPlanQuickCreate
    v-if="contractInfo !== undefined"
    :visible="quickCreateVisible"
    :contract-id="contractId"
    :contract-info="contractInfo"
    :existing-plans="plans"
    @close="quickCreateVisible = false"
    @success="handleQuickCreateSuccess"
  />
  <PaymentPlanQuickCreate
    v-else
    :visible="quickCreateVisible"
    :contract-id="contractId"
    :existing-plans="plans"
    @close="quickCreateVisible = false"
    @success="handleQuickCreateSuccess"
  />

  <PaymentNextStepDialog
    :visible="showNextStepDialog"
    :record="createdRecord"
    @update:visible="handleNextStepClose"
    @submitted="handleNextStepSubmitted"
  />
  </Teleport>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.plan-row {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
  width: 100%;
  padding-left: $wolf-space-md-v2;

  &::before {
    content: '';
    position: absolute;
    top: $wolf-space-xs-v2;
    bottom: $wolf-space-xs-v2;
    left: 0;
    width: 3px;
    border-radius: $wolf-radius-full-v2;
    background: $wolf-border-default-v2;
  }
}

.plan-status-pending::before,
.plan-status-partial::before {
  background: $wolf-warning-v2;
}

.plan-status-overdue::before {
  background: $wolf-danger-v2;
}

.plan-status-completed::before {
  background: $wolf-success-v2;
}

.plan-row-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: $wolf-space-md-v2;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    flex-direction: column;
  }
}

.plan-title-block {
  min-width: 0;
}

.plan-title-line {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  flex-wrap: wrap;
}

.stage-name {
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
}

.plan-subtitle {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
  margin-top: $wolf-space-xs-v2;
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
}

.plan-subtitle-icon,
.metric-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.plan-amount {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: $wolf-space-xs-v2;
  white-space: nowrap;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    align-items: flex-start;
  }
}

.amount-label,
.metric-label,
.summary-eyebrow,
.field-hint {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
}

.amount-value {
  font-family: $wolf-font-mono-v2;
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
  font-variant-numeric: tabular-nums;
}

.plan-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: $wolf-space-sm-v2;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
  }
}

.metric-item {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: $wolf-space-xs-v2 $wolf-space-sm-v2;
  align-items: center;
  padding: $wolf-space-sm-v2;
  border: 1px solid $wolf-border-light-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-bg-muted-v2;
}

.metric-icon {
  color: $wolf-text-tertiary-v2;
}

.metric-value {
  grid-column: 2;
  font-family: $wolf-font-mono-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  color: $wolf-text-secondary-v2;
  font-variant-numeric: tabular-nums;
}

.plan-progress,
.summary-progress {
  height: 6px;
}

.plan-notes {
  margin: 0;
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-bg-hover-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-auxiliary-v2;
  line-height: $wolf-line-height-body-v2;
}

.payment-summary-card {
  margin-top: $wolf-space-md-v2;
  border: 1px solid $wolf-border-default-v2;
  background: $wolf-bg-card-v2;
  box-shadow: $wolf-shadow-card-v2;
}

.payment-summary-content {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(240px, 0.8fr);
  gap: $wolf-space-lg-v2;
  align-items: center;
  padding: $wolf-space-lg-v2;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
  }
}

.summary-copy {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;

  strong {
    color: $wolf-text-primary-v2;
    font-size: $wolf-font-size-body-v2;
    font-weight: $wolf-font-weight-semibold-v2;
  }
}

.summary-progress-block {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  color: $wolf-text-secondary-v2;
  font-family: $wolf-font-mono-v2;
  font-size: $wolf-font-size-caption-v2;
  font-variant-numeric: tabular-nums;
}

.dialog-form-grid {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.required-mark {
  color: $wolf-danger-text-v2;
}

@media (prefers-reduced-motion: reduce) {
  .plan-row,
  .metric-item {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>
