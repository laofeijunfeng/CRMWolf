<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  ClipboardList,
  CreditCard,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
} from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import ListCard from '@/components/crmwolf/ListCard.vue'
import PaymentRecordList from '@/components/PaymentRecordList.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import PaymentNextStepDialog from '@/components/PaymentNextStepDialog.vue'
import EditRecordDialog from '@/components/dialogs/EditRecordDialog.vue'
import PaymentPlanFormDialog from '@/components/dialogs/PaymentPlanFormDialog.vue'
import PaymentRecordDialog from '@/components/dialogs/PaymentRecordDialog.vue'
import paymentApi, {
  type PaymentPlanResponse,
  type PaymentPlanStatus,
  type PaymentRecordCreate,
  type PaymentRecordInfo,
  type PaymentRecordResponse,
  type PaymentRecordUpdate,
} from '@/api/payment'
import { handleApiError } from '@/utils/errorHandler'
import { formatCurrency, formatLocalDate } from '@/utils/format'
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
const currentPlan = ref<PaymentPlanResponse | null>(null)
const editingPlan = ref<PaymentPlanResponse | null>(null)
const selectedRecord = ref<PaymentRecordInfo | PaymentRecordResponse | null>(null)
const recordToDelete = ref<PaymentRecordInfo | null>(null)
const planToDelete = ref<PaymentPlanResponse | null>(null)
const createdRecord = ref<PaymentRecordResponse | null>(null)

const planFormDialogOpen = ref<boolean>(false)
const planFormMode = ref<'create' | 'edit'>('create')
const recordDialogOpen = ref<boolean>(false)
const recordsDialogOpen = ref<boolean>(false)
const editRecordDialogOpen = ref<boolean>(false)
const nextStepDialogOpen = ref<boolean>(false)

const submittingRecord = ref<boolean>(false)
const editingRecord = ref<boolean>(false)
const deletingRecord = ref<boolean>(false)
const deletingPlan = ref<boolean>(false)

const fixedContractForPlanForm = computed(() => {
  const contractInfo = props.contractInfo
  if (contractInfo === undefined) return null

  const fixedContract = {
    id: props.contractId,
    contract_name: contractInfo.contract_name,
    total_amount: contractInfo.total_amount,
  }

  const customerName = contractInfo.customer_info?.account_name
  if (customerName === undefined) return fixedContract

  return {
    ...fixedContract,
    customer_name: customerName,
  }
})

const currentPlanDialogTitle = computed<string>(() => {
  return currentPlan.value === null ? '回款记录' : `${currentPlan.value.stage_name} - 回款记录`
})

const registerDefaultAmount = computed<number | null>(() => {
  const plan = currentPlan.value
  if (plan === null) return null
  return plan.remaining_amount ?? plan.planned_amount
})

function mapStatus(status: PaymentPlanStatus): 'pending' | 'overdue' | 'partial' | 'completed' {
  const statusMap: Record<PaymentPlanStatus, 'pending' | 'overdue' | 'partial' | 'completed'> = {
    PENDING: 'pending',
    OVERDUE: 'overdue',
    PARTIAL: 'partial',
    COMPLETED: 'completed',
  }
  return statusMap[status]
}

function getStatusToneClass(status: PaymentPlanStatus): string {
  const toneMap: Record<PaymentPlanStatus, string> = {
    PENDING: 'plan-status-pending',
    OVERDUE: 'plan-status-overdue',
    PARTIAL: 'plan-status-partial',
    COMPLETED: 'plan-status-completed',
  }
  return toneMap[status]
}

function formatDate(dateStr: string | undefined): string {
  if (dateStr === undefined || dateStr.trim() === '') return '-'
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return '-'
  return formatLocalDate(date)
}

function calculatePlanProgress(plan: PaymentPlanResponse): number {
  if (plan.planned_amount <= 0) return 0
  return Math.min(100, Math.round(((plan.paid_amount ?? 0) / plan.planned_amount) * 100))
}

async function fetchPlans(): Promise<void> {
  loading.value = true
  const selectedPlanId = currentPlan.value?.id

  try {
    const nextPlans = await paymentApi.getPaymentPlans(props.contractId)
    plans.value = nextPlans

    if (selectedPlanId !== undefined) {
      currentPlan.value = nextPlans.find((plan) => plan.id === selectedPlanId) ?? null
    }
  } catch (error: unknown) {
    logger.error('[ContractPaymentPlans]', '获取回款计划失败', { error })
    handleApiError(error, '获取回款计划')
  } finally {
    loading.value = false
  }
}

function notifyUpdated(): void {
  emit('plan-updated')
}

function handleCreatePlan(): void {
  editingPlan.value = null
  planFormMode.value = 'create'
  planFormDialogOpen.value = true
}

function handleEditPlan(plan: PaymentPlanResponse): void {
  editingPlan.value = plan
  planFormMode.value = 'edit'
  planFormDialogOpen.value = true
}

async function handlePlanFormSuccess(): Promise<void> {
  await fetchPlans()
  notifyUpdated()
}

function showRecords(plan: PaymentPlanResponse): void {
  currentPlan.value = plan
  recordsDialogOpen.value = true
}

function showPaymentDialog(plan: PaymentPlanResponse): void {
  currentPlan.value = plan
  recordDialogOpen.value = true
}

async function handleCreateRecord(payload: PaymentRecordCreate): Promise<void> {
  const plan = currentPlan.value
  if (plan === null) return

  submittingRecord.value = true
  try {
    const record = await paymentApi.createPaymentRecord(plan.id, payload)
    toast.success('登记成功')
    createdRecord.value = record
    recordDialogOpen.value = false
    nextStepDialogOpen.value = true
    await fetchPlans()
    notifyUpdated()
  } catch (error: unknown) {
    logger.error('[ContractPaymentPlans]', '登记回款失败', { error })
    handleApiError(error, '登记回款')
  } finally {
    submittingRecord.value = false
  }
}

function handleEditRecord(record: PaymentRecordInfo): void {
  selectedRecord.value = record
  editRecordDialogOpen.value = true
}

async function handleEditRecordSubmit(recordId: number, payload: PaymentRecordUpdate): Promise<void> {
  editingRecord.value = true
  try {
    await paymentApi.updatePaymentRecord(recordId, payload)
    toast.success('回款记录已更新')
    editRecordDialogOpen.value = false
    selectedRecord.value = null
    await fetchPlans()
    notifyUpdated()
  } catch (error: unknown) {
    logger.error('[ContractPaymentPlans]', '更新回款记录失败', { error })
    handleApiError(error, '更新回款记录')
  } finally {
    editingRecord.value = false
  }
}

function requestDeleteRecord(record: PaymentRecordInfo): void {
  recordToDelete.value = record
}

async function handleDeleteRecord(): Promise<void> {
  const record = recordToDelete.value
  if (record === null) return

  deletingRecord.value = true
  try {
    await paymentApi.deletePaymentRecord(record.id)
    toast.success('回款记录已删除')
    recordToDelete.value = null
    await fetchPlans()
    notifyUpdated()
  } catch (error: unknown) {
    logger.error('[ContractPaymentPlans]', '删除回款记录失败', { error })
    handleApiError(error, '删除回款记录')
  } finally {
    deletingRecord.value = false
  }
}

function requestDeletePlan(plan: PaymentPlanResponse): void {
  if (plan.payment_records.length > 0) {
    toast.warning('存在回款记录的计划不能删除')
    return
  }

  planToDelete.value = plan
}

async function handleDeletePlan(): Promise<void> {
  const plan = planToDelete.value
  if (plan === null) return

  deletingPlan.value = true
  try {
    await paymentApi.deletePaymentPlan(plan.id)
    toast.success('回款计划已删除')
    planToDelete.value = null
    await fetchPlans()
    notifyUpdated()
  } catch (error: unknown) {
    logger.error('[ContractPaymentPlans]', '删除回款计划失败', { error })
    handleApiError(error, '删除回款计划')
  } finally {
    deletingPlan.value = false
  }
}

function handleRecordClick(record: PaymentRecordInfo): void {
  selectedRecord.value = record
  editRecordDialogOpen.value = true
}

function handleViewApproval(): void {
  toast.info('请在审批中心查看回款审批进度')
}

function handleNextStepClose(open: boolean): void {
  nextStepDialogOpen.value = open
  if (!open) {
    createdRecord.value = null
  }
}

async function handleNextStepSubmitted(): Promise<void> {
  await fetchPlans()
  notifyUpdated()
}

function closeEditRecordDialog(open: boolean): void {
  editRecordDialogOpen.value = open
  if (!open) {
    selectedRecord.value = null
  }
}

function closeDeletePlanDialog(open: boolean): void {
  if (!open && !deletingPlan.value) {
    planToDelete.value = null
  }
}

function closeDeleteRecordDialog(open: boolean): void {
  if (!open && !deletingRecord.value) {
    recordToDelete.value = null
  }
}

function refresh(): void {
  void fetchPlans()
}

defineExpose({
  refresh,
})

watch(
  () => props.contractId,
  () => {
    currentPlan.value = null
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
      <Button size="sm" type="button" @click="handleCreatePlan">
        <Plus data-icon="inline-start" aria-hidden="true" />
        新建计划
      </Button>
    </template>

    <template #itemMain="{ item }">
      <div class="plan-row" :class="getStatusToneClass(item.status)">
        <div class="plan-row-main">
          <div class="plan-copy">
            <div class="plan-title-line">
              <span class="stage-name">{{ item.stage_name }}</span>
              <StatusBadge
                :status="mapStatus(item.status)"
                type="paymentPlan"
                size="small"
              />
            </div>
            <div class="plan-subtitle">
              到期：{{ formatDate(item.due_date) }}
              <span v-if="item.notes" class="plan-note-inline"> · {{ item.notes }}</span>
            </div>
          </div>

          <div class="plan-amount">
            <span class="amount-value">{{ formatCurrency(item.planned_amount) }}</span>
            <span v-if="item.status !== 'PENDING'" class="amount-subtitle">
              已回款：{{ formatCurrency(item.paid_amount ?? 0) }}
            </span>
          </div>
        </div>

        <Progress
          v-if="item.status !== 'PENDING'"
          :model-value="calculatePlanProgress(item)"
          class="plan-progress"
          :aria-label="`${item.stage_name} 回款进度 ${calculatePlanProgress(item)}%`"
        />
      </div>
    </template>

    <template #itemActions="{ item }">
      <Button
        variant="outline"
        size="sm"
        type="button"
        :aria-label="`查看 ${item.stage_name} 的回款记录`"
        @click.stop="showRecords(item)"
      >
        <ClipboardList data-icon="inline-start" aria-hidden="true" />
        回款记录
      </Button>

      <Button
        v-if="item.status !== 'COMPLETED'"
        size="sm"
        type="button"
        :aria-label="`为 ${item.stage_name} 登记回款`"
        @click.stop="showPaymentDialog(item)"
      >
        <CreditCard data-icon="inline-start" aria-hidden="true" />
        登记回款
      </Button>

      <DropdownMenu v-if="item.status !== 'COMPLETED'">
        <DropdownMenuTrigger as-child>
          <Button
            variant="ghost"
            size="icon"
            type="button"
            :aria-label="`${item.stage_name} 更多操作`"
            @click.stop
          >
            <MoreHorizontal aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem class="min-h-11" @click.stop="handleEditPlan(item)">
            <Pencil class="mr-2 h-4 w-4" aria-hidden="true" />
            编辑
          </DropdownMenuItem>
          <DropdownMenuItem
            class="min-h-11"
            :disabled="item.payment_records.length > 0"
            @click.stop="requestDeletePlan(item)"
          >
            <Trash2 class="mr-2 h-4 w-4 text-wolf-danger-text" aria-hidden="true" />
            删除
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </template>
  </ListCard>

  <Teleport to="body">
    <Dialog v-model:open="recordsDialogOpen">
      <DialogContent class="contract-payment-records-dialog">
        <DialogHeader>
          <DialogTitle>{{ currentPlanDialogTitle }}</DialogTitle>
          <DialogDescription>查看、修改或删除该阶段的回款登记历史。</DialogDescription>
        </DialogHeader>
        <PaymentRecordList
          v-if="currentPlan"
          :records="currentPlan.payment_records"
          :can-register="currentPlan.status !== 'COMPLETED'"
          can-delete
          @register="showPaymentDialog(currentPlan)"
          @record-click="handleRecordClick"
          @edit-record="handleEditRecord"
          @delete-record="requestDeleteRecord"
          @view-approval="handleViewApproval"
        />
      </DialogContent>
    </Dialog>

    <PaymentRecordDialog
      :open="recordDialogOpen"
      :default-amount="registerDefaultAmount"
      :submitting="submittingRecord"
      @update:open="recordDialogOpen = $event"
      @submit="handleCreateRecord"
    />

    <EditRecordDialog
      :open="editRecordDialogOpen"
      :record="selectedRecord"
      :submitting="editingRecord"
      @update:open="closeEditRecordDialog"
      @submit="handleEditRecordSubmit"
    />

    <PaymentPlanFormDialog
      :open="planFormDialogOpen"
      :mode="planFormMode"
      :plan="editingPlan"
      :fixed-contract="fixedContractForPlanForm"
      @update:open="planFormDialogOpen = $event"
      @success="handlePlanFormSuccess"
    />

    <AlertDialog :open="planToDelete !== null" @update:open="closeDeletePlanDialog">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>删除回款计划？</AlertDialogTitle>
          <AlertDialogDescription>
            确定要删除回款计划“{{ planToDelete?.stage_name }}”吗？此操作不可恢复。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel :disabled="deletingPlan">取消</AlertDialogCancel>
          <AlertDialogAction :disabled="deletingPlan" @click="handleDeletePlan">
            {{ deletingPlan ? '删除中...' : '删除' }}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <AlertDialog :open="recordToDelete !== null" @update:open="closeDeleteRecordDialog">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>删除回款记录？</AlertDialogTitle>
          <AlertDialogDescription>
            确定要删除这条回款记录吗？金额：{{ formatCurrency(recordToDelete?.actual_amount ?? 0) }}。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel :disabled="deletingRecord">取消</AlertDialogCancel>
          <AlertDialogAction :disabled="deletingRecord" @click="handleDeleteRecord">
            {{ deletingRecord ? '删除中...' : '删除' }}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <PaymentNextStepDialog
      :visible="nextStepDialogOpen"
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
  gap: $wolf-space-sm-v2;
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

.plan-row-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $wolf-space-md-v2;
  min-width: 0;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    flex-direction: column;
    align-items: flex-start;
  }
}

.plan-copy {
  min-width: 0;
}

.plan-title-line {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  flex-wrap: wrap;
}

.stage-name {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  line-height: $wolf-line-height-body-v2;
  word-break: break-word;
}

.plan-subtitle,
.plan-note-inline {
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
  word-break: break-word;
}

.plan-amount {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: $wolf-space-xs-v2;
  flex-shrink: 0;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    align-items: flex-start;
  }
}

.amount-value {
  color: $wolf-text-primary-v2;
  font-family: $wolf-font-mono-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  font-variant-numeric: tabular-nums;
}

.amount-subtitle {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
}

.plan-progress {
  height: 6px;
}

.contract-payment-records-dialog {
  max-height: $wolf-modal-height-mobile-v2;
  overflow-y: auto;

  @media (min-width: $wolf-breakpoint-sm-v2) {
    max-width: 800px;
  }
}
</style>
