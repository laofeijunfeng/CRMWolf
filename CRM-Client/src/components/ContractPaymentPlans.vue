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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import ListCard from '@/components/crmwolf/ListCard.vue'
import AmountText from '@/components/crmwolf/AmountText.vue'
import PaymentRecordList from '@/components/PaymentRecordList.vue'
import StatusBadge from '@/components/crmwolf/StatusBadge.vue'
import { getStatusPresentation } from '@/utils/statusPresentation'
import PaymentNextStepDialog from '@/components/PaymentNextStepDialog.vue'
import EditRecordDialog from '@/components/dialogs/EditRecordDialog.vue'
import PaymentPlanFormDialog from '@/components/dialogs/PaymentPlanFormDialog.vue'
import PaymentRecordDialog from '@/components/dialogs/PaymentRecordDialog.vue'
import {
  createCommandRequestOptions,
  isNetworkOrTimeoutError,
  isPendingCommandResponse,
  operationIdFromError,
  pollCommandStatus,
  type CommandExecutionResponse,
  type CommandRequestOptions,
} from '@/api/command'
import paymentApi, {
  type PaymentPlanResponse,
  type PaymentPlanStatus,
  type PaymentRecordCreate,
  type PaymentRecordInfo,
  type PaymentRecordResponse,
  type PaymentRecordUpdate,
} from '@/api/payment'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'
import { handleApiError, handleOutcomeUnknown, isOutcomeUnknown } from '@/utils/errorHandler'
import { formatCurrency, formatLocalDate } from '@/utils/format'
import { logger } from '@/utils/logger'
import { confirmDelete } from '@/utils/confirmDialog'

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
  'view-plan': [plan: PaymentPlanResponse]
}>()
const permissionStore = usePermissionStore()
const userStore = useUserStore()

const loading = ref<boolean>(false)
const plans = ref<PaymentPlanResponse[]>([])
const currentPlan = ref<PaymentPlanResponse | null>(null)
const editingPlan = ref<PaymentPlanResponse | null>(null)
const selectedRecord = ref<PaymentRecordInfo | PaymentRecordResponse | null>(null)
const createdRecord = ref<PaymentRecordResponse | null>(null)

const planFormDialogOpen = ref<boolean>(false)
const planFormMode = ref<'create' | 'edit'>('create')
const recordDialogOpen = ref<boolean>(false)
const paymentRecordIdempotencyKey = ref<string | null>(null)
const paymentRecordCommandOptions = ref<CommandRequestOptions | null>(null)
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

const canEditAnyRecord = computed<boolean>(() => permissionStore.hasAnyPermission(['payment:record:edit', 'payment:edit']))
const canDeleteAnyRecord = computed<boolean>(() =>
  permissionStore.hasAnyPermission(['payment:record:delete', 'payment:delete'])
)

const canEditRecord = (record: PaymentRecordInfo): boolean => {
  if (record.approval?.status === 'PENDING') return false
  if (record.approval_phase !== 'draft' && record.approval_phase !== 'rejected') return false
  if (record.confirmation_status === 'CONFIRMED') return false
  if (canEditAnyRecord.value) return true
  return record.creator_id === String(userStore.userInfo?.id ?? '')
}

const canDeleteRecord = (record: PaymentRecordInfo): boolean => {
  if (!canDeleteAnyRecord.value) return false
  if (record.approval?.status === 'PENDING' || record.approval?.status === 'APPROVED') return false
  if (record.approval_phase === 'pending_review' || record.approval_phase === 'approved') return false
  if (record.confirmation_status === 'CONFIRMED') return false
  return true
}

const currentPlanDialogTitle = computed<string>(() => {
  return currentPlan.value === null ? '回款记录' : `${currentPlan.value.stage_name} - 回款记录`
})

const registerDefaultAmount = computed<number | null>(() => {
  const plan = currentPlan.value
  if (plan === null) return null
  return plan.remaining_amount ?? plan.planned_amount
})
const registerDefaultPayerName = computed<string>(() => {
  return currentPlan.value?.customer_name?.trim() ?? props.contractInfo?.customer_info?.account_name?.trim() ?? ''
})

function mapStatus(status: PaymentPlanStatus): string {
  const statusMap: Record<PaymentPlanStatus, 'pending' | 'overdue' | 'partial' | 'completed'> = {
    PENDING: 'pending',
    OVERDUE: 'overdue',
    PARTIAL: 'partial',
    COMPLETED: 'completed',
  }
  return Object.prototype.hasOwnProperty.call(statusMap, status) ? statusMap[status] : status
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

async function fetchPlans(): Promise<boolean> {
  loading.value = true
  const selectedPlanId = currentPlan.value?.id

  try {
    const nextPlans = await paymentApi.getPaymentPlans(props.contractId)
    plans.value = nextPlans

    if (selectedPlanId !== undefined) {
      currentPlan.value = nextPlans.find((plan) => plan.id === selectedPlanId) ?? null
    }
    return true
  } catch (error: unknown) {
    logger.error('[ContractPaymentPlans]', '获取回款计划失败', { error })
    handleApiError(error, '获取回款计划')
    return false
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
  const refreshed = await fetchPlans()
  notifyUpdated()
  if (!refreshed) {
    toast.warning('回款计划已保存，但详情中的计划列表刷新失败，请稍后重试。')
  }
}

function showRecords(plan: PaymentPlanResponse): void {
  currentPlan.value = plan
  recordsDialogOpen.value = true
}

function showPaymentDialog(plan: PaymentPlanResponse): void {
  currentPlan.value = plan
  recordDialogOpen.value = true
  const commandOptions = createCommandRequestOptions()
  paymentRecordCommandOptions.value = commandOptions
  paymentRecordIdempotencyKey.value = commandOptions.idempotencyKey ?? null
}

function handleRecordDialogOpenChange(open: boolean): void {
  recordDialogOpen.value = open
  if (!open && !submittingRecord.value) {
    paymentRecordIdempotencyKey.value = null
    paymentRecordCommandOptions.value = null
  }
}

function paymentRecordFromCommand(result: CommandExecutionResponse): PaymentRecordResponse | null {
  if (result.status !== 'SUCCEEDED') return null
  const data = result.data
  if (typeof data !== 'object' || data === null) return null
  if (!('id' in data) || typeof data.id !== 'number') return null
  return data as PaymentRecordResponse
}

async function recoverPaymentRecord(options: CommandRequestOptions): Promise<PaymentRecordResponse | null> {
  try {
    const result = await pollCommandStatus(options.operationId ?? '', { attempts: 8, intervalMs: 500 })
    const response = paymentRecordFromCommand(result)
    if (response !== null) return response
    if (result.status === 'PENDING' || result.status === 'UNKNOWN') {
      handleOutcomeUnknown('回款登记')
      return null
    }
    toast.error('回款登记失败', { description: result.error?.message ?? '请稍后重试' })
    return null
  } catch {
    const idempotencyKey = options.idempotencyKey
    if (idempotencyKey === undefined || idempotencyKey === null || idempotencyKey.length === 0) {
      handleOutcomeUnknown('回款登记')
      return null
    }
    try {
      return await paymentApi.resolvePaymentRecordWithRetry(idempotencyKey)
    } catch {
      handleOutcomeUnknown('回款登记')
      return null
    }
  }
}

async function handleCreateRecord(payload: PaymentRecordCreate): Promise<void> {
  const plan = currentPlan.value
  if (plan === null) return

  submittingRecord.value = true
  try {
    const commandOptions = paymentRecordCommandOptions.value ?? createCommandRequestOptions()
    paymentRecordCommandOptions.value = commandOptions
    paymentRecordIdempotencyKey.value = commandOptions.idempotencyKey ?? null
    let record: PaymentRecordResponse | null = null
    try {
      const result = await paymentApi.createPaymentRecord(plan.id, payload, commandOptions)
      record = isPendingCommandResponse(result)
        ? await recoverPaymentRecord(commandOptions)
        : result
    } catch (error: unknown) {
      const operationId = operationIdFromError(error)
      if (isNetworkOrTimeoutError(error) || operationId !== null || isOutcomeUnknown(error)) {
        record = await recoverPaymentRecord(
          operationId === null ? commandOptions : { ...commandOptions, operationId },
        )
      } else {
        throw error
      }
    }
    if (record === null) return
    createdRecord.value = record
    recordDialogOpen.value = false
    paymentRecordIdempotencyKey.value = null
    paymentRecordCommandOptions.value = null
    nextStepDialogOpen.value = true
    const refreshed = await fetchPlans()
    notifyUpdated()
    toast.success('登记成功', {
      description: refreshed
        ? '回款计划和当前合同详情已同步。'
        : '回款已登记，但详情中的计划列表刷新失败，请稍后重试。',
    })
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
    editRecordDialogOpen.value = false
    selectedRecord.value = null
    const refreshed = await fetchPlans()
    notifyUpdated()
    toast.success('回款记录已更新', {
      description: refreshed
        ? '回款计划和当前合同详情已同步。'
        : '回款记录已更新，但详情中的计划列表刷新失败，请稍后重试。',
    })
  } catch (error: unknown) {
    logger.error('[ContractPaymentPlans]', '更新回款记录失败', { error })
    handleApiError(error, '更新回款记录')
  } finally {
    editingRecord.value = false
  }
}

async function requestDeleteRecord(record: PaymentRecordInfo): Promise<void> {
  if (deletingRecord.value) return
  if (!(await confirmDelete(`这条回款记录（金额：${formatCurrency(record.actual_amount ?? 0)}）`))) return

  deletingRecord.value = true
  try {
    await paymentApi.deletePaymentRecord(record.id)
    const refreshed = await fetchPlans()
    notifyUpdated()
    toast.success('回款记录已删除', refreshed ? undefined : {
      description: '回款记录已删除，但详情中的计划列表刷新失败，请稍后重试。',
    })
  } catch (error: unknown) {
    logger.error('[ContractPaymentPlans]', '删除回款记录失败', { error })
    handleApiError(error, '删除回款记录')
  } finally {
    deletingRecord.value = false
  }
}

async function requestDeletePlan(plan: PaymentPlanResponse): Promise<void> {
  if (plan.payment_records.length > 0) {
    toast.warning('存在回款记录的计划不能删除')
    return
  }

  if (deletingPlan.value) return
  if (!(await confirmDelete(`回款计划“${plan.stage_name}”`))) return

  deletingPlan.value = true
  try {
    await paymentApi.deletePaymentPlan(plan.id)
    const refreshed = await fetchPlans()
    notifyUpdated()
    toast.success('回款计划已删除', refreshed ? undefined : {
      description: '回款计划已删除，但详情中的计划列表刷新失败，请稍后重试。',
    })
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
  const refreshed = await fetchPlans()
  notifyUpdated()
  if (!refreshed) {
    toast.warning('下一步操作已完成，但详情中的计划列表刷新失败，请稍后重试。')
  }
}

function closeEditRecordDialog(open: boolean): void {
  editRecordDialogOpen.value = open
  if (!open) {
    selectedRecord.value = null
  }
}

async function refresh(): Promise<boolean> {
  return fetchPlans()
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
    row-interactive
    @row-click="(plan) => emit('view-plan', plan)"
  >
    <template #headerActions>
      <Button size="sm" type="button" @click="handleCreatePlan">
        <Plus data-icon="inline-start" aria-hidden="true" />
        新建计划
      </Button>
    </template>

    <template #itemMain="{ item }">
      <div class="plan-row">
        <span
          class="plan-row-stripe"
          :data-tone="getStatusPresentation('paymentPlan', mapStatus(item.status)).tone"
          aria-hidden="true"
        ></span>
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
            <AmountText :value="item.planned_amount" tone="warning" />
            <span v-if="item.status !== 'PENDING'" class="amount-subtitle">
              已回款：<AmountText :value="item.paid_amount ?? 0" size="sm" />
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
          <DropdownMenuItem class="min-h-touch-target" @click.stop="handleEditPlan(item)">
            <Pencil aria-hidden="true" />
            编辑
          </DropdownMenuItem>
          <DropdownMenuItem
            class="min-h-touch-target"
            :disabled="item.payment_records.length > 0"
            @click.stop="requestDeletePlan(item)"
          >
            <Trash2 class="text-danger" aria-hidden="true" />
            删除
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </template>
  </ListCard>

  <Teleport to="body">
    <Dialog v-model:open="recordsDialogOpen">
      <DialogContent size="xl" class="contract-payment-records-dialog">
        <DialogHeader>
          <DialogTitle>{{ currentPlanDialogTitle }}</DialogTitle>
          <DialogDescription>查看、修改或删除该阶段的回款登记历史。</DialogDescription>
        </DialogHeader>
        <PaymentRecordList
          v-if="currentPlan"
          :records="currentPlan.payment_records"
          :can-register="currentPlan.status !== 'COMPLETED'"
          :can-edit-record="canEditRecord"
          :can-delete="canDeleteRecord"
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
      :payment-plan-id="currentPlan?.id ?? null"
      :default-amount="registerDefaultAmount"
      :default-payer-name="registerDefaultPayerName"
      :submitting="submittingRecord"
      @update:open="handleRecordDialogOpenChange"
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


    <PaymentNextStepDialog
      :visible="nextStepDialogOpen"
      :record="createdRecord"
      @update:visible="handleNextStepClose"
      @submitted="handleNextStepSubmitted"
    />
  </Teleport>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.plan-row {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: $space-2;
  width: 100%;
  padding-left: $space-3;
}

.plan-row-stripe {
  position: absolute;
  top: $space-1;
  bottom: $space-1;
  left: 0;
  width: 3px;
  border-radius: 9999px;
  background: hsl(var(--tone));
}

.plan-row-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $space-3;
  min-width: 0;

  @media (max-width: $bp-sm - 1) {
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
  gap: $space-2;
  flex-wrap: wrap;
}

.stage-name {
  color: hsl(var(--foreground));
  font-size: var(--font-size-body);
  font-weight: 600;
  line-height: 20px;
  word-break: break-word;
}

.plan-subtitle,
.plan-note-inline {
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-caption);
  line-height: 20px;
  word-break: break-word;
}

.plan-amount {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: $space-1;
  flex-shrink: 0;

  @media (max-width: $bp-sm - 1) {
    align-items: flex-start;
  }
}

.amount-subtitle {
  display: inline-flex;
  align-items: baseline;
  gap: $space-1;
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-caption);
}

.plan-progress {
  height: 6px;
}

.contract-payment-records-dialog {
  max-height: min(90vh, 90dvh);
  overflow-y: auto;
}
</style>
