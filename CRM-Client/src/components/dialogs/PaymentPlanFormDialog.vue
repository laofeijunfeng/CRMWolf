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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { DatePicker } from '@/components/ui/date-picker'
import contractApi, { type ContractListResponse } from '@/api/contract'
import paymentApi, {
  type PaymentPlanCreate,
  type PaymentPlanResponse,
  type PaymentPlanUpdate,
} from '@/api/payment'
import { handleApiError } from '@/utils/errorHandler'

interface Props {
  open: boolean
  mode: 'create' | 'edit'
  plan?: PaymentPlanResponse | null
  fixedContract?: PaymentPlanContractOption | null
}

interface Emits {
  (event: 'update:open', value: boolean): void
  (event: 'success'): void
}

interface PaymentPlanForm {
  contractId: string
  stageName: string
  plannedAmount: string
  dueDate: string
  notes: string
}

interface PaymentPlanFormErrors {
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

const contracts = ref<ContractListResponse[]>([])
const contractsLoading = ref(false)
const submitting = ref(false)

const form = reactive<PaymentPlanForm>({
  contractId: '',
  stageName: '',
  plannedAmount: '',
  dueDate: '',
  notes: '',
})

const errors = reactive<PaymentPlanFormErrors>({
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
const title = computed<string>(() => isCreateMode.value ? '新建回款计划' : '编辑回款计划')
const description = computed<string>(() => {
  if (isCreateMode.value && hasFixedContract.value) {
    return '为当前合同填写计划金额、日期等信息。'
  }

  return isCreateMode.value
    ? '选择合同并填写计划金额、日期等信息。'
    : '调整当前回款计划的阶段、金额、日期或备注。'
})
const fixedContractLabel = computed<string>(() => {
  return props.fixedContract === null ? '' : contractOptionLabel(props.fixedContract)
})

function clearErrors(): void {
  errors.contractId = ''
  errors.stageName = ''
  errors.plannedAmount = ''
  errors.dueDate = ''
}

function resetForm(): void {
  const plan = props.plan
  form.contractId = props.fixedContract !== null
    ? String(props.fixedContract.id)
    : plan?.contract_id !== undefined ? String(plan.contract_id) : ''
  form.stageName = plan?.stage_name ?? ''
  form.plannedAmount = plan?.planned_amount !== undefined
    ? String(plan.planned_amount)
    : getSelectedContractAmount()
  form.dueDate = plan?.due_date ?? ''
  form.notes = plan?.notes ?? ''
  clearErrors()
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

  if (isCreateMode.value && form.contractId.trim() === '') {
    errors.contractId = '请选择合同'
  }

  if (form.stageName.trim() === '') {
    errors.stageName = '请输入阶段名称'
  }

  const amount = Number(form.plannedAmount)
  if (form.plannedAmount.trim() === '' || !Number.isFinite(amount) || amount <= 0) {
    errors.plannedAmount = '请输入大于 0 的计划金额'
  }

  if (form.dueDate.trim() === '' || !isValidLocalDate(form.dueDate.trim())) {
    errors.dueDate = '请选择计划日期'
  }

  return errors.contractId === ''
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

async function fetchContracts(): Promise<void> {
  if (!isCreateMode.value || hasFixedContract.value || contracts.value.length > 0) return

  contractsLoading.value = true
  try {
    contracts.value = await contractApi.getContracts({
      limit: 100,
      order_by: 'created_time',
      order_dir: 'desc',
    })
  } catch (error: unknown) {
    handleApiError(error, '获取合同列表')
  } finally {
    contractsLoading.value = false
  }
}

async function handleSubmit(): Promise<void> {
  if (submitting.value || !validateForm()) return

  submitting.value = true
  try {
    if (isCreateMode.value) {
      await paymentApi.createPaymentPlans(Number(form.contractId), {
        plans: [buildCreatePayload()],
      })
      toast.success('回款计划创建成功')
    } else if (props.plan !== null) {
      await paymentApi.updatePaymentPlan(props.plan.id, buildUpdatePayload())
      toast.success('回款计划更新成功')
    }

    visible.value = false
    emit('success')
  } catch (error: unknown) {
    handleApiError(error, isCreateMode.value ? '创建回款计划' : '更新回款计划')
  } finally {
    submitting.value = false
  }
}

function handleCancel(): void {
  if (!submitting.value) {
    visible.value = false
  }
}

function contractOptionLabel(contract: PaymentPlanContractOption): string {
  return contract.contract_name
}

function getSelectedContractAmount(): string {
  if (!isCreateMode.value) return ''

  if (props.fixedContract !== null) {
    return String(props.fixedContract.total_amount)
  }

  const selectedContract = contracts.value.find((contract) => String(contract.id) === form.contractId)
  return selectedContract !== undefined ? String(selectedContract.total_amount) : ''
}

watch(
  () => [props.open, props.mode, props.plan?.id, props.fixedContract?.id] as const,
  ([open]) => {
    if (open) {
      resetForm()
      void fetchContracts()
    } else {
      clearErrors()
    }
  },
  { immediate: true }
)

watch(
  () => form.contractId,
  () => {
    if (!visible.value || !isCreateMode.value || hasFixedContract.value) return
    form.plannedAmount = getSelectedContractAmount()
  }
)
</script>

<template>
  <Dialog v-model:open="visible">
    <DialogContent class="payment-plan-form-dialog">
      <DialogHeader>
        <DialogTitle>{{ title }}</DialogTitle>
        <DialogDescription>{{ description }}</DialogDescription>
      </DialogHeader>

      <form class="payment-plan-form-dialog__form" novalidate @submit.prevent="handleSubmit">
        <div v-if="isCreateMode && hasFixedContract && fixedContract !== null" class="payment-plan-form-dialog__field">
          <label class="payment-plan-form-dialog__label" for="payment-plan-fixed-contract">
            所属合同
          </label>
          <Input
            id="payment-plan-fixed-contract"
            class="payment-plan-form-dialog__control h-11 min-h-11"
            :model-value="fixedContractLabel"
            disabled
          />
        </div>

        <div v-else-if="isCreateMode" class="payment-plan-form-dialog__field">
          <label class="payment-plan-form-dialog__label" for="payment-plan-contract">
            所属合同
            <span class="payment-plan-form-dialog__required" aria-hidden="true">*</span>
          </label>
          <Select v-model="form.contractId" :disabled="contractsLoading || submitting">
            <SelectTrigger
              id="payment-plan-contract"
              class="payment-plan-form-dialog__control h-11 min-h-11"
              :aria-invalid="errors.contractId !== ''"
              aria-describedby="payment-plan-contract-error"
            >
              <SelectValue :placeholder="contractsLoading ? '加载合同中...' : '请选择合同'" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem
                v-for="contract in contracts"
                :key="contract.id"
                :value="String(contract.id)"
              >
                {{ contractOptionLabel(contract) }}
              </SelectItem>
            </SelectContent>
          </Select>
          <p
            v-if="errors.contractId"
            id="payment-plan-contract-error"
            class="payment-plan-form-dialog__error"
            role="alert"
          >
            {{ errors.contractId }}
          </p>
        </div>

        <div class="payment-plan-form-dialog__grid">
          <div class="payment-plan-form-dialog__field">
            <label class="payment-plan-form-dialog__label" for="payment-plan-stage">
              阶段名称
              <span class="payment-plan-form-dialog__required" aria-hidden="true">*</span>
            </label>
            <Input
              id="payment-plan-stage"
              v-model="form.stageName"
              class="payment-plan-form-dialog__control h-11 min-h-11"
              placeholder="如：首付款、尾款"
              :disabled="submitting"
              :aria-invalid="errors.stageName !== ''"
              aria-describedby="payment-plan-stage-error"
            />
            <p
              v-if="errors.stageName"
              id="payment-plan-stage-error"
              class="payment-plan-form-dialog__error"
              role="alert"
            >
              {{ errors.stageName }}
            </p>
          </div>

          <div class="payment-plan-form-dialog__field">
            <label class="payment-plan-form-dialog__label" for="payment-plan-amount">
              计划金额
              <span class="payment-plan-form-dialog__required" aria-hidden="true">*</span>
            </label>
            <Input
              id="payment-plan-amount"
              v-model="form.plannedAmount"
              type="number"
              inputmode="decimal"
              min="0"
              step="0.01"
              class="payment-plan-form-dialog__control h-11 min-h-11"
              placeholder="请输入计划金额"
              :disabled="submitting"
              :aria-invalid="errors.plannedAmount !== ''"
              aria-describedby="payment-plan-amount-error"
            />
            <p
              v-if="errors.plannedAmount"
              id="payment-plan-amount-error"
              class="payment-plan-form-dialog__error"
              role="alert"
            >
              {{ errors.plannedAmount }}
            </p>
          </div>
        </div>

        <div class="payment-plan-form-dialog__field">
          <label class="payment-plan-form-dialog__label" for="payment-plan-due-date">
            计划日期
            <span class="payment-plan-form-dialog__required" aria-hidden="true">*</span>
          </label>
          <DatePicker
            :model-value="parseLocalDate(form.dueDate)"
            placeholder="请选择计划日期"
            class="payment-plan-form-dialog__control"
            :disabled="submitting"
            @update:model-value="handleDueDateChange"
          />
          <p
            v-if="errors.dueDate"
            id="payment-plan-due-date-error"
            class="payment-plan-form-dialog__error"
            role="alert"
          >
            {{ errors.dueDate }}
          </p>
        </div>

        <div class="payment-plan-form-dialog__field">
          <label class="payment-plan-form-dialog__label" for="payment-plan-notes">
            备注
          </label>
          <Textarea
            id="payment-plan-notes"
            v-model="form.notes"
            class="payment-plan-form-dialog__textarea"
            placeholder="请输入备注信息（可选）"
            :disabled="submitting"
          />
        </div>

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

.payment-plan-form-dialog__label {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.payment-plan-form-dialog__required,
.payment-plan-form-dialog__error {
  color: $wolf-danger-v2;
}

.payment-plan-form-dialog__control,
.payment-plan-form-dialog__textarea {
  width: 100%;
}

.payment-plan-form-dialog__textarea {
  min-height: 96px;
}

.payment-plan-form-dialog__error {
  margin: 0;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
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
