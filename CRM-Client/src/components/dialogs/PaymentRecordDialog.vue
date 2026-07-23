<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { PaymentRecordCreate } from '@/api/payment'
import paymentApi from '@/api/payment'
import customerApi, { type CustomerMemberResponse } from '@/api/customer'
import { useUserStore } from '@/stores/user'
import { handleApiError } from '@/utils/errorHandler'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import {
  DateField,
  InputField,
  SelectField,
  TextareaField,
} from '@/components/crmwolf'

interface Props {
  open: boolean
  paymentPlanId?: number | null
  defaultAmount?: number | null
  defaultPayerName?: string | null
  submitting?: boolean
}

interface Emits {
  (event: 'update:open', value: boolean): void
  (event: 'submit', payload: PaymentRecordCreate): void
}

interface PaymentRecordForm {
  actualAmount: string
  actualPayerName: string
  paymentDate: string
  proofAttachment: string
  commissionMemberId: string
  notes: string
}

interface PaymentRecordErrors {
  actualAmount: string
  actualPayerName: string
  paymentDate: string
  commissionMemberId: string
  notes: string
}

const props = withDefaults(defineProps<Props>(), {
  paymentPlanId: null,
  defaultAmount: null,
  defaultPayerName: null,
  submitting: false,
})

const emit = defineEmits<Emits>()
const userStore = useUserStore()

interface CommissionMemberOption {
  id: string
  name: string
  source: 'self' | 'customer_member'
}

const form = reactive<PaymentRecordForm>({
  actualAmount: '',
  actualPayerName: '',
  paymentDate: '',
  proofAttachment: '',
  commissionMemberId: '',
  notes: '',
})

const errors = reactive<PaymentRecordErrors>({
  actualAmount: '',
  actualPayerName: '',
  paymentDate: '',
  commissionMemberId: '',
  notes: '',
})

const loadingCommissionMembers = ref(false)
const commissionMemberOptions = ref<CommissionMemberOption[]>([])
const commissionMemberSelectOptions = computed(() =>
  commissionMemberOptions.value.map((member) => ({
    value: member.id,
    label: `${member.name}${member.source === 'self' ? '（我）' : ''}`,
  }))
)

const visible = computed({
  get: (): boolean => props.open,
  set: (value: boolean): void => emit('update:open', value),
})

const isSubmitting = computed((): boolean => props.submitting === true)
const hasAmountError = computed((): boolean => errors.actualAmount.length > 0)
const hasActualPayerNameError = computed((): boolean => errors.actualPayerName.length > 0)
const hasPaymentDateError = computed((): boolean => errors.paymentDate.length > 0)
const hasCommissionMemberError = computed((): boolean => errors.commissionMemberId.length > 0)
const hasNotesError = computed((): boolean => errors.notes.length > 0)

function getLocalDateString(date: Date = new Date()): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function parseLocalDateString(value: string): Date | null {
  if (!isValidLocalDate(value)) return null

  const [year, month, day] = value.split('-').map(Number)
  if (year === undefined || month === undefined || day === undefined) return null
  return new Date(year, month - 1, day)
}

function handlePaymentDateChange(date: Date | null): void {
  form.paymentDate = date !== null ? getLocalDateString(date) : ''
}

function formatDefaultAmount(defaultAmount: number | null): string {
  if (defaultAmount === null) {
    return ''
  }
  return Number.isFinite(defaultAmount) ? String(defaultAmount) : ''
}

function clearErrors(): void {
  errors.actualAmount = ''
  errors.actualPayerName = ''
  errors.paymentDate = ''
  errors.commissionMemberId = ''
  errors.notes = ''
}

function resetForm(): void {
  form.actualAmount = formatDefaultAmount(props.defaultAmount)
  form.actualPayerName = props.defaultPayerName?.trim() ?? ''
  form.paymentDate = getLocalDateString()
  form.proofAttachment = ''
  form.commissionMemberId = String(userStore.userInfo?.id ?? '')
  form.notes = ''
  clearErrors()
}

function trimmedOptional(value: string): string | undefined {
  const trimmedValue = value.trim()
  return trimmedValue.length > 0 ? trimmedValue : undefined
}

function isValidLocalDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value)
}

function validateForm(): boolean {
  clearErrors()

  const normalizedAmount = form.actualAmount.trim()
  const amount = Number(normalizedAmount)
  if (normalizedAmount.length === 0 || !Number.isFinite(amount) || amount <= 0) {
    errors.actualAmount = '请输入大于 0 的回款金额'
  }

  const normalizedPayerName = form.actualPayerName.trim()
  if (normalizedPayerName.length === 0) {
    errors.actualPayerName = '请输入实际付款方'
  } else if (normalizedPayerName.length > 200) {
    errors.actualPayerName = '实际付款方不能超过 200 字'
  }

  const normalizedDate = form.paymentDate.trim()
  if (normalizedDate.length === 0 || !isValidLocalDate(normalizedDate)) {
    errors.paymentDate = '请选择回款日期'
  }

  if (form.commissionMemberId.trim().length === 0) {
    errors.commissionMemberId = '请选择提成协作成员'
  }

  if (form.notes.length > 200) {
    errors.notes = '备注不能超过 200 字'
  }

  return !hasAmountError.value
    && !hasActualPayerNameError.value
    && !hasPaymentDateError.value
    && !hasCommissionMemberError.value
    && !hasNotesError.value
}

function handleSubmit(): void {
  if (isSubmitting.value || loadingCommissionMembers.value || !validateForm()) {
    return
  }

  const payload: PaymentRecordCreate = {
    actual_amount: Number(form.actualAmount.trim()),
    actual_payer_name: form.actualPayerName.trim(),
    payment_date: form.paymentDate.trim(),
    commission_member_id: form.commissionMemberId.trim(),
  }

  const proofAttachment = trimmedOptional(form.proofAttachment)
  if (proofAttachment !== undefined) {
    payload.proof_attachment = proofAttachment
  }

  const notes = trimmedOptional(form.notes)
  if (notes !== undefined) {
    payload.notes = notes
  }

  emit('submit', payload)
}

function closeDialog(): void {
  if (!isSubmitting.value) {
    visible.value = false
  }
}

function mergeCommissionMemberOptions(members: CustomerMemberResponse[]): CommissionMemberOption[] {
  const options = new Map<string, CommissionMemberOption>()
  const currentUserId = String(userStore.userInfo?.id ?? '')
  if (currentUserId.length > 0) {
    options.set(currentUserId, {
      id: currentUserId,
      name: userStore.userInfo?.name ?? '我',
      source: 'self',
    })
  }

  for (const member of members) {
    const memberName = member.user_info?.name?.trim()
    options.set(member.user_id, {
      id: member.user_id,
      name: memberName !== undefined && memberName.length > 0 ? memberName : `用户 ${member.user_id}`,
      source: 'customer_member',
    })
  }
  return Array.from(options.values())
}

async function loadCommissionMembers(): Promise<void> {
  if (!props.open || props.paymentPlanId === null) {
    commissionMemberOptions.value = mergeCommissionMemberOptions([])
    return
  }

  loadingCommissionMembers.value = true
  try {
    const plan = await paymentApi.getPaymentPlanDetail(props.paymentPlanId)
    if (plan.customer_id === undefined || plan.customer_id === null) {
      commissionMemberOptions.value = mergeCommissionMemberOptions([])
      return
    }
    const members = await customerApi.getCustomerMembers(plan.customer_id)
    commissionMemberOptions.value = mergeCommissionMemberOptions(members)
  } catch (error) {
    commissionMemberOptions.value = mergeCommissionMemberOptions([])
    handleApiError(error, '加载提成协作成员')
  } finally {
    loadingCommissionMembers.value = false
  }
}

watch(
  () => [props.open, props.defaultAmount, props.defaultPayerName, props.paymentPlanId] as const,
  ([isOpen]) => {
    if (isOpen) {
      resetForm()
      void loadCommissionMembers()
    } else {
      clearErrors()
    }
  },
  { immediate: true }
)
</script>

<template>
  <Dialog v-model:open="visible">
    <DialogContent class="payment-record-dialog">
      <DialogHeader>
        <DialogTitle>登记回款</DialogTitle>
        <DialogDescription>
          填写实际到账金额、回款日期和可选凭证信息，用于创建回款记录。
        </DialogDescription>
      </DialogHeader>

      <form class="payment-record-dialog__form" novalidate @submit.prevent="handleSubmit">
        <InputField
          id="payment-record-amount"
          v-model="form.actualAmount"
          class="payment-record-dialog__field"
          label="回款金额"
          required
          name="actual_amount"
          type="number"
          inputmode="decimal"
          min="0"
          step="0.01"
          placeholder="请输入回款金额"
          :disabled="isSubmitting"
          helper-text="金额需大于 0，可精确到分。"
          :error="errors.actualAmount"
        />

        <InputField
          id="payment-record-payer-name"
          v-model="form.actualPayerName"
          class="payment-record-dialog__field"
          label="实际付款方"
          required
          name="actual_payer_name"
          type="text"
          maxlength="200"
          placeholder="请输入实际付款方"
          :disabled="isSubmitting"
          helper-text="默认使用客户名称，可按实际付款公司抬头修改。"
          :error="errors.actualPayerName"
        />

        <DateField
          id="payment-record-date"
          :model-value="parseLocalDateString(form.paymentDate)"
          class="payment-record-dialog__field"
          label="回款日期"
          required
          placeholder="请选择回款日期"
          :disabled="isSubmitting"
          helper-text="使用本地日期，格式为 YYYY-MM-DD。"
          :error="errors.paymentDate"
          @update:model-value="handlePaymentDateChange"
        />

        <SelectField
          id="payment-record-commission-member"
          v-model="form.commissionMemberId"
          class="payment-record-dialog__field"
          label="提成协作成员"
          required
          :options="commissionMemberSelectOptions"
          :placeholder="loadingCommissionMembers ? '加载成员中...' : '请选择提成协作成员'"
          :disabled="isSubmitting || loadingCommissionMembers"
          helper-text="可选择你自己，或当前客户团队成员中的一人。"
          :error="errors.commissionMemberId"
        />

        <InputField
          id="payment-record-proof"
          v-model="form.proofAttachment"
          class="payment-record-dialog__field"
          label="凭证附件 URL"
          name="proof_attachment"
          type="url"
          placeholder="请输入附件 URL（可选）"
          :disabled="isSubmitting"
        />

        <TextareaField
          id="payment-record-notes"
          v-model="form.notes"
          class="payment-record-dialog__field"
          label="备注"
          name="notes"
          maxlength="200"
          placeholder="请输入备注信息（可选，最多 200 字）"
          control-class="min-h-20"
          :disabled="isSubmitting"
          :helper-text="`${form.notes.length}/200`"
          :error="errors.notes"
        />

        <DialogFooter class="payment-record-dialog__footer">
          <Button
            type="button"
            variant="outline"
            class="payment-record-dialog__button min-h-11"
            :disabled="isSubmitting"
            @click="closeDialog"
          >
            取消
          </Button>
          <Button
            type="submit"
            class="payment-record-dialog__button min-h-11"
            :disabled="isSubmitting || loadingCommissionMembers"
          >
            {{ isSubmitting ? '提交中...' : '确定' }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.payment-record-dialog {
  max-height: $wolf-modal-height-mobile-v2;
  overflow-y: auto;
}

.payment-record-dialog__form {
  display: flex;
  flex-direction: column;
  gap: $wolf-form-item-gap-v2;
}

.payment-record-dialog__field {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm-v2;
}

.payment-record-dialog__button {
  min-height: $wolf-touch-target-min-v2;
}

.payment-record-dialog__footer {
  gap: $wolf-space-sm-v2;
  padding-top: $wolf-space-lg-v2;
  border-top: 1px solid $wolf-border-divider-v2;
}

@media (max-width: $wolf-breakpoint-sm-v2) {
  .payment-record-dialog__button {
    width: 100%;
  }
}
</style>
