<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
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
import { Button } from '@/components/ui/button'
import {
  DateField,
  InputField,
  SearchableSelectField,
  SelectField,
  TextareaField,
} from '@/components/crmwolf'
import contractApi, { type ContractListResponse } from '@/api/contract'
import customerApi, { type CustomerResponse } from '@/api/customer'
import paymentApi, {
  type PaymentPlanCreate,
  type PaymentPlanResponse,
  type PaymentPlanUpdate,
} from '@/api/payment'
import { handleApiError } from '@/utils/errorHandler'
import { formatCurrency } from '@/utils/format'
import { useDialogCloseGuard } from '@/composables/useDialogCloseGuard'
import { normalizePaginatedResponse } from '@/types/pagination'
import type { FormSuccessPayload } from '@/types/actionOutcome'

interface Props {
  open: boolean
  mode: 'create' | 'edit'
  plan?: PaymentPlanResponse | null
  fixedContract?: PaymentPlanContractOption | null
}

interface Emits {
  (event: 'update:open', value: boolean): void
  (event: 'success', payload?: FormSuccessPayload): void
}

interface PaymentPlanForm {
  customerId: string
  contractId: string
  stageName: string
  plannedAmount: string
  dueDate: string
  notes: string
}

interface PaymentPlanFormErrors {
  customerId: string
  contractId: string
  stageName: string
  plannedAmount: string
  dueDate: string
}

interface PaymentPlanContractOption {
  id: number
  contract_name: string
  total_amount: string | number
  customer_name?: string
}

const props = withDefaults(defineProps<Props>(), {
  plan: null,
  fixedContract: null,
})
const emit = defineEmits<Emits>()

const customers = ref<CustomerResponse[]>([])
const contracts = ref<ContractListResponse[]>([])
const customersLoading = ref(false)
const contractsLoading = ref(false)
const existingPlans = ref<PaymentPlanResponse[]>([])
const existingPlansLoading = ref(false)
const existingPlansFailed = ref(false)
const contractTotalOverride = ref<string | null>(null)
const contractTotalLoading = ref(false)
const contractTotalFailed = ref(false)
const submitting = ref(false)
const customerSearchKeyword = ref('')
let allocationLoadGeneration = 0

const initialForm = ref<PaymentPlanForm>({
  customerId: '',
  contractId: '',
  stageName: '',
  plannedAmount: '',
  dueDate: '',
  notes: '',
})

const form = reactive<PaymentPlanForm>({
  customerId: '',
  contractId: '',
  stageName: '',
  plannedAmount: '',
  dueDate: '',
  notes: '',
})

const errors = reactive<PaymentPlanFormErrors>({
  customerId: '',
  contractId: '',
  stageName: '',
  plannedAmount: '',
  dueDate: '',
})

const visible = computed({
  get: (): boolean => props.open,
  set: (value: boolean): void => emit('update:open', value),
})

const isCreateMode = computed<boolean>(() => props.mode === 'create')
const hasFixedContract = computed<boolean>(() => props.fixedContract !== null)
const hasFormChanges = computed<boolean>(() => {
  return Object.keys(form).some((key) => {
    const field = key as keyof PaymentPlanForm
    return form[field] !== initialForm.value[field]
  })
})
const closeGuard = useDialogCloseGuard({
  isDirty: hasFormChanges,
  submitting,
  emitOpen: (open) => emit('update:open', open),
})
const showConfirmDialog = closeGuard.showConfirmDialog
const title = computed<string>(() => isCreateMode.value ? '新建回款计划' : '编辑回款计划')
const description = computed<string>(() => {
  if (isCreateMode.value && hasFixedContract.value) {
    return '为当前合同填写计划金额、日期等信息。'
  }

  return isCreateMode.value
    ? '选择客户和合同，并填写计划金额、日期等信息。'
    : '调整当前回款计划的阶段、金额、日期或备注。'
})
const fixedContractLabel = computed<string>(() => {
  return props.fixedContract === null ? '' : contractOptionLabel(props.fixedContract)
})
const customerOptions = computed(() =>
  customers.value.map((customer) => ({
    value: customer.id,
    label: customerOptionLabel(customer),
  }))
)
const contractOptions = computed(() =>
  contracts.value.map((contract) => ({
    value: String(contract.id),
    label: contractOptionLabel(contract),
  }))
)

function clearErrors(): void {
  errors.customerId = ''
  errors.contractId = ''
  errors.stageName = ''
  errors.plannedAmount = ''
  errors.dueDate = ''
}

function resetForm(): void {
  const plan = props.plan
  form.customerId = props.fixedContract !== null
    ? ''
    : plan?.customer_id !== null && plan?.customer_id !== undefined ? String(plan.customer_id) : ''
  form.contractId = props.fixedContract !== null
    ? String(props.fixedContract.id)
    : plan?.contract_id !== undefined ? String(plan.contract_id) : ''
  form.stageName = plan?.stage_name ?? ''
  form.plannedAmount = plan?.planned_amount !== undefined ? String(plan.planned_amount) : ''
  form.dueDate = plan?.due_date ?? ''
  form.notes = plan?.notes ?? ''
  clearErrors()
  initialForm.value = { ...form }
}

function isValidLocalDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value)
}

function formatLocalDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function parseLocalDate(value: string): Date | null {
  if (!isValidLocalDate(value)) return null

  const [year, month, day] = value.split('-').map(Number)
  if (year === undefined || month === undefined || day === undefined) return null
  return new Date(year, month - 1, day)
}

function handleDueDateChange(date: Date | null): void {
  form.dueDate = date !== null ? formatLocalDate(date) : ''
}

function validateForm(): boolean {
  clearErrors()

  if (isCreateMode.value && !hasFixedContract.value && form.customerId.trim() === '') {
    errors.customerId = '请选择客户'
  }

  if (isCreateMode.value && form.contractId.trim() === '') {
    errors.contractId = '请选择合同'
  }

  if (form.stageName.trim() === '') {
    errors.stageName = '请输入阶段名称'
  }

  validatePlannedAmount('submit')

  if (form.dueDate.trim() === '' || !isValidLocalDate(form.dueDate.trim())) {
    errors.dueDate = '请选择计划日期'
  }

  return errors.customerId === ''
    && errors.contractId === ''
    && errors.stageName === ''
    && errors.plannedAmount === ''
    && errors.dueDate === ''
}

function buildCreatePayload(): PaymentPlanCreate {
  const payload: PaymentPlanCreate = {
    stage_name: form.stageName.trim(),
    planned_amount: Number(form.plannedAmount),
    due_date: form.dueDate.trim(),
  }

  const notes = form.notes.trim()
  if (notes !== '') {
    payload.notes = notes
  }

  return payload
}

function buildUpdatePayload(): PaymentPlanUpdate {
  const payload: PaymentPlanUpdate = {
    stage_name: form.stageName.trim(),
    planned_amount: Number(form.plannedAmount),
    due_date: form.dueDate.trim(),
  }

  const notes = form.notes.trim()
  if (notes !== '') {
    payload.notes = notes
  }

  return payload
}

async function fetchCustomers(keyword?: string): Promise<void> {
  if (!isCreateMode.value || hasFixedContract.value) return

  customersLoading.value = true
  try {
    const params: { skip: number; limit: number; keyword?: string } = { skip: 0, limit: 50 }
    const normalizedKeyword = keyword?.trim()
    if (normalizedKeyword !== undefined && normalizedKeyword !== '') {
      params.keyword = normalizedKeyword
    }

    const response = await customerApi.getCustomers(params)
    customers.value = normalizePaginatedResponse(response).items
  } catch (error: unknown) {
    handleApiError(error, '获取客户列表')
  } finally {
    customersLoading.value = false
  }
}

async function handleCustomerSearch(keyword: string | number): Promise<void> {
  const normalizedKeyword = String(keyword).trim()
  customerSearchKeyword.value = normalizedKeyword
  await fetchCustomers(normalizedKeyword || undefined)
}

async function fetchContracts(customerId?: string): Promise<void> {
  if (!isCreateMode.value || hasFixedContract.value) return

  if (customerId === undefined || customerId.trim() === '') {
    contracts.value = []
    return
  }

  contractsLoading.value = true
  try {
    contracts.value = await contractApi.getCustomerContracts(customerId, { skip: 0, limit: 100 })
  } catch (error: unknown) {
    handleApiError(error, '获取合同列表')
  } finally {
    contractsLoading.value = false
  }
}

function normalizeSelectValue(value: unknown): string | null {
  if (typeof value === 'string') return value
  if (typeof value === 'number') return String(value)
  return null
}

function handleCustomerChange(value: unknown): void {
  const nextCustomerId = normalizeSelectValue(value)
  if (nextCustomerId === null || nextCustomerId === '') return
  if (nextCustomerId === form.customerId) return

  form.customerId = nextCustomerId
  form.contractId = ''
  form.plannedAmount = ''
  contracts.value = []

  const customerId = form.customerId.trim()
  if (customerId !== '') {
    void fetchContracts(customerId)
  }
}

function handleContractChange(value: unknown): void {
  const nextContractId = normalizeSelectValue(value)
  if (nextContractId === null || nextContractId === '') return

  form.contractId = nextContractId
}

async function handleSubmit(): Promise<void> {
  if (submitting.value || !validateForm()) return

  submitting.value = true
  try {
    let entityId: number
    let operation: FormSuccessPayload['operation']
    if (isCreateMode.value) {
      const createdPlans = await paymentApi.createPaymentPlans(Number(form.contractId), {
        plans: [buildCreatePayload()],
      })
      const createdPlan = createdPlans[0]
      if (createdPlan === undefined) {
        throw new Error('回款计划创建结果为空')
      }
      entityId = createdPlan.id
      operation = 'create'
      toast.success('回款计划创建成功')
    } else if (props.plan !== null) {
      const updatedPlan = await paymentApi.updatePaymentPlan(props.plan.id, buildUpdatePayload())
      entityId = updatedPlan.id
      operation = 'update'
      toast.success('回款计划更新成功')
    } else {
      throw new Error('缺少待更新的回款计划')
    }

    closeGuard.approveClose()
    visible.value = false
    emit('success', {
      entityType: 'payment-plan',
      entityId,
      operation,
      outcome: 'success',
      stateSyncRequested: true,
    })
  } catch (error: unknown) {
    handleApiError(error, isCreateMode.value ? '创建回款计划' : '更新回款计划')
  } finally {
    submitting.value = false
  }
}

function handleOpenChange(open: boolean): void {
  closeGuard.handleOpenChange(open)
}

function handleCancel(): void {
  closeGuard.requestClose()
}

function continueEditing(): void {
  closeGuard.continueEditing()
}

function confirmCancel(): void {
  closeGuard.confirmDiscard()
}

function contractOptionLabel(contract: PaymentPlanContractOption): string {
  return contract.contract_name
}

function customerOptionLabel(customer: CustomerResponse): string {
  return customer.account_name
}

function toCents(value: string | number): number | null {
  const amount = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(amount)) return null
  return Math.round(amount * 100)
}

function centsToAmountString(cents: number): string {
  return (cents / 100).toString()
}

const resolvedContractId = computed<number | null>(() => {
  const raw = form.contractId.trim()
  if (raw === '') return null
  const id = Number(raw)
  return Number.isInteger(id) && id > 0 ? id : null
})

const contractTotalCents = computed<number | null>(() => {
  if (props.fixedContract !== null) {
    return toCents(props.fixedContract.total_amount)
  }
  if (!isCreateMode.value) {
    if (contractTotalFailed.value) return null
    if (contractTotalOverride.value !== null) {
      return toCents(contractTotalOverride.value)
    }
  }
  const selected = contracts.value.find((contract) => String(contract.id) === form.contractId)
  return selected === undefined ? null : toCents(selected.total_amount)
})

const allocatedCents = computed<number>(() => {
  const currentId = props.plan?.id
  return existingPlans.value.reduce((total, plan) => {
    if (currentId !== undefined && plan.id === currentId) return total
    const cents = toCents(plan.planned_amount)
    return cents === null ? total : total + cents
  }, 0)
})

const remainingCents = computed<number | null>(() => {
  if (existingPlansFailed.value || contractTotalCents.value === null) return null
  if (existingPlansLoading.value || contractTotalLoading.value) return null
  return Math.max(0, contractTotalCents.value - allocatedCents.value)
})

const amountHelperText = computed<string>(() => {
  if (errors.plannedAmount !== '') return ''
  if (remainingCents.value === null) return ''
  return `还可分配 ${formatCurrency(remainingCents.value / 100)}`
})

function plannedAmountOverCapMessage(amountCents: number): string {
  if (remainingCents.value === null || contractTotalCents.value === null) return ''
  if (isCreateMode.value) {
    if (amountCents > remainingCents.value) {
      return `回款计划合计不能超过合同金额 ${formatCurrency(contractTotalCents.value / 100)}，当前还可分配 ${formatCurrency(remainingCents.value / 100)}`
    }
    return ''
  }
  const originalCents = toCents(props.plan?.planned_amount ?? 0) ?? 0
  const oldTotal = allocatedCents.value + originalCents
  const newTotal = allocatedCents.value + amountCents
  if (newTotal > oldTotal && newTotal > contractTotalCents.value) {
    return `回款计划合计不能超过合同金额 ${formatCurrency(contractTotalCents.value / 100)}，当前还可分配 ${formatCurrency(remainingCents.value / 100)}`
  }
  return ''
}

function validatePlannedAmount(trigger: 'input' | 'submit'): void {
  const raw = form.plannedAmount.trim()
  if (raw === '') {
    errors.plannedAmount = trigger === 'submit' ? '请输入大于 0 的计划金额' : ''
    return
  }
  const amount = Number(raw)
  if (!Number.isFinite(amount) || amount <= 0) {
    errors.plannedAmount = '请输入大于 0 的计划金额'
    return
  }
  const amountCents = toCents(raw)
  if (amountCents === null) {
    errors.plannedAmount = '请输入大于 0 的计划金额'
    return
  }
  errors.plannedAmount = plannedAmountOverCapMessage(amountCents)
}

function resetAllocationState(): void {
  allocationLoadGeneration += 1
  existingPlans.value = []
  existingPlansLoading.value = false
  existingPlansFailed.value = false
  contractTotalOverride.value = null
  contractTotalLoading.value = false
  contractTotalFailed.value = false
}

async function loadExistingPlans(contractId: number, generation: number): Promise<void> {
  existingPlansLoading.value = true
  existingPlansFailed.value = false
  try {
    const plans = await paymentApi.getPaymentPlans(contractId)
    if (generation !== allocationLoadGeneration) return
    existingPlans.value = plans
  } catch (error: unknown) {
    if (generation !== allocationLoadGeneration) return
    existingPlans.value = []
    existingPlansFailed.value = true
    handleApiError(error, '获取回款计划')
  } finally {
    if (generation === allocationLoadGeneration) {
      existingPlansLoading.value = false
    }
  }
}

async function loadContractTotalForEdit(contractId: number, generation: number): Promise<void> {
  if (props.fixedContract !== null || isCreateMode.value) return
  contractTotalLoading.value = true
  contractTotalFailed.value = false
  try {
    const contract = await contractApi.getContract(contractId)
    if (generation !== allocationLoadGeneration) return
    contractTotalOverride.value = String(contract.total_amount)
  } catch (error: unknown) {
    if (generation !== allocationLoadGeneration) return
    contractTotalOverride.value = null
    contractTotalFailed.value = true
    handleApiError(error, '获取合同金额')
  } finally {
    if (generation === allocationLoadGeneration) {
      contractTotalLoading.value = false
    }
  }
}

async function refreshAllocation(contractId: number): Promise<void> {
  const generation = allocationLoadGeneration + 1
  allocationLoadGeneration = generation
  await Promise.all([
    loadExistingPlans(contractId, generation),
    loadContractTotalForEdit(contractId, generation),
  ])
  if (generation !== allocationLoadGeneration) return
  applyCreatePrefill()
  validatePlannedAmount('input')
}

function applyCreatePrefill(): void {
  if (!isCreateMode.value) return
  if (remainingCents.value === null) {
    form.plannedAmount = ''
    return
  }
  form.plannedAmount = remainingCents.value > 0 ? centsToAmountString(remainingCents.value) : ''
  initialForm.value = { ...form }
}

watch(
  () => [props.open, props.mode, props.plan?.id, props.fixedContract?.id] as const,
  ([open]) => {
    if (open) {
      closeGuard.reset()
      customerSearchKeyword.value = ''
      resetForm()
      resetAllocationState()
      void fetchCustomers(customerSearchKeyword.value)
      const customerId = form.customerId.trim()
      if (customerId !== '') {
        void fetchContracts(customerId)
      }
      const contractId = resolvedContractId.value
      if (contractId !== null) {
        void refreshAllocation(contractId)
      }
    } else {
      resetAllocationState()
      if (closeGuard.handleParentClose()) return
      clearErrors()
      customerSearchKeyword.value = ''
    }
  },
  { immediate: true }
)

watch(
  () => form.plannedAmount,
  () => {
    if (!visible.value) return
    validatePlannedAmount('input')
  },
)

watch(
  () => resolvedContractId.value,
  (contractId) => {
    if (!visible.value) return
    if (contractId === null) {
      resetAllocationState()
      return
    }
    void refreshAllocation(contractId)
  },
)
</script>

<template>
  <Dialog :open="props.open" @update:open="handleOpenChange">
    <DialogContent class="payment-plan-form-dialog w-[calc(100vw-2rem)] max-h-[min(90vh,90dvh)] overflow-y-auto overscroll-contain [scroll-padding-bottom:calc(5rem+env(safe-area-inset-bottom,0px))]">
      <DialogHeader>
        <DialogTitle>{{ title }}</DialogTitle>
        <DialogDescription>{{ description }}</DialogDescription>
      </DialogHeader>

      <form class="payment-plan-form-dialog__form" novalidate @submit.prevent="handleSubmit">
        <InputField
          v-if="isCreateMode && hasFixedContract && fixedContract !== null"
          id="payment-plan-fixed-contract"
          class="payment-plan-form-dialog__field"
          label="所属合同"
          :model-value="fixedContractLabel"
          disabled
        />

        <template v-else-if="isCreateMode">
          <SearchableSelectField
            id="payment-plan-customer"
            :model-value="form.customerId"
            class="payment-plan-form-dialog__field"
            label="所属客户"
            required
            :options="customerOptions"
            :search-value="customerSearchKeyword"
            placeholder="请选择客户"
            search-placeholder="搜索客户名称"
            :loading="customersLoading"
            loading-text="加载客户中..."
            empty-text="暂无客户"
            :disabled="submitting"
            :error="errors.customerId"
            @update:model-value="handleCustomerChange"
            @update:open="(open: boolean) => { if (open) fetchCustomers(customerSearchKeyword) }"
            @update:search-value="handleCustomerSearch"
          />

          <SelectField
            id="payment-plan-contract"
            :model-value="form.contractId"
            class="payment-plan-form-dialog__field"
            label="所属合同"
            required
            :options="contractOptions"
            :placeholder="form.customerId === '' ? '请先选择客户' : contractsLoading ? '加载合同中...' : '请选择合同'"
            :disabled="contractsLoading || submitting || form.customerId === ''"
            :error="errors.contractId"
            @update:model-value="handleContractChange"
          />
        </template>

        <div class="payment-plan-form-dialog__grid">
          <InputField
            id="payment-plan-stage"
            v-model="form.stageName"
            class="payment-plan-form-dialog__field"
            label="阶段名称"
            required
            placeholder="如：首付款、尾款"
            :disabled="submitting"
            :error="errors.stageName"
          />

          <InputField
            id="payment-plan-amount"
            v-model="form.plannedAmount"
            class="payment-plan-form-dialog__field"
            label="计划金额"
            required
            type="number"
            inputmode="decimal"
            min="0"
            step="0.01"
            placeholder="请输入计划金额"
            :disabled="submitting"
            :error="errors.plannedAmount"
            :helper-text="amountHelperText"
          />
        </div>

        <DateField
          id="payment-plan-due-date"
          :model-value="parseLocalDate(form.dueDate)"
          class="payment-plan-form-dialog__field"
          label="计划日期"
          required
          placeholder="请选择计划日期"
          :disabled="submitting"
          :error="errors.dueDate"
          @update:model-value="handleDueDateChange"
        />

        <TextareaField
          id="payment-plan-notes"
          v-model="form.notes"
          class="payment-plan-form-dialog__field"
          label="备注"
          placeholder="请输入备注信息（可选）"
          :disabled="submitting"
        />

        <DialogFooter class="payment-plan-form-dialog__footer">
          <Button type="button" variant="outline" :disabled="submitting" @click="handleCancel">
            取消
          </Button>
          <Button type="submit" :disabled="submitting">
            {{ submitting ? '保存中...' : '保存' }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
  <AlertDialog :open="showConfirmDialog" @update:open="closeGuard.handleConfirmOpenChange">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>放弃填写回款计划？</AlertDialogTitle>
        <AlertDialogDescription>
          当前已填写或调整回款计划内容，关闭后这些未保存内容会丢失。
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel @click="continueEditing">继续编辑</AlertDialogCancel>
        <AlertDialogAction @click="confirmCancel">放弃填写</AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.payment-plan-form-dialog {
  max-width: 640px;
}

.payment-plan-form-dialog__form {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
}

.payment-plan-form-dialog__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $wolf-space-md-v2;
}

.payment-plan-form-dialog__field {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  min-width: 0;
}

.payment-plan-form-dialog__footer {
  padding-top: $wolf-space-sm-v2;
}

@media (max-width: $wolf-breakpoint-sm-v2) {
  .payment-plan-form-dialog__grid {
    grid-template-columns: 1fr;
  }
}
</style>
