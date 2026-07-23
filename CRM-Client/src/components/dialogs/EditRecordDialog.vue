<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import type { PaymentRecordInfo, PaymentRecordResponse, PaymentRecordUpdate } from '@/api/payment'
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
  TextareaField,
} from '@/components/crmwolf'

type EditablePaymentRecord = PaymentRecordInfo | PaymentRecordResponse

interface Props {
  open: boolean
  record: EditablePaymentRecord | null
  submitting?: boolean
}

interface Emits {
  (event: 'update:open', value: boolean): void
  (event: 'submit', recordId: number, data: PaymentRecordUpdate): void
}

interface EditRecordForm {
  actualAmount: string
  actualPayerName: string
  paymentDate: string
  proofAttachment: string
  notes: string
}

interface EditRecordErrors {
  actualAmount: string
  actualPayerName: string
  paymentDate: string
  notes: string
}

const props = withDefaults(defineProps<Props>(), {
  submitting: false,
})

const emit = defineEmits<Emits>()

const form = reactive<EditRecordForm>({
  actualAmount: '',
  actualPayerName: '',
  paymentDate: '',
  proofAttachment: '',
  notes: '',
})

const errors = reactive<EditRecordErrors>({
  actualAmount: '',
  actualPayerName: '',
  paymentDate: '',
  notes: '',
})

const visible = computed({
  get: (): boolean => props.open,
  set: (value: boolean): void => emit('update:open', value),
})

const isSubmitting = computed((): boolean => props.submitting === true)
const hasAmountError = computed((): boolean => errors.actualAmount.length > 0)
const hasActualPayerNameError = computed((): boolean => errors.actualPayerName.length > 0)
const hasPaymentDateError = computed((): boolean => errors.paymentDate.length > 0)
const hasNotesError = computed((): boolean => errors.notes.length > 0)

function clearErrors(): void {
  errors.actualAmount = ''
  errors.actualPayerName = ''
  errors.paymentDate = ''
  errors.notes = ''
}

function normalizeDateString(value: string): string {
  const timeSeparatorIndex = value.indexOf('T')
  return timeSeparatorIndex >= 0 ? value.slice(0, timeSeparatorIndex) : value
}

function resetForm(): void {
  form.actualAmount = ''
  form.actualPayerName = ''
  form.paymentDate = ''
  form.proofAttachment = ''
  form.notes = ''
  clearErrors()
}

function populateForm(record: EditablePaymentRecord): void {
  form.actualAmount = Number.isFinite(record.actual_amount) ? String(record.actual_amount) : ''
  form.actualPayerName = record.actual_payer_name ?? ''
  form.paymentDate = normalizeDateString(record.payment_date)
  form.proofAttachment = record.proof_attachment ?? ''
  form.notes = record.notes ?? ''
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

function handlePaymentDateChange(date: Date | null): void {
  form.paymentDate = date !== null ? formatLocalDate(date) : ''
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

  if (form.notes.length > 200) {
    errors.notes = '备注不能超过 200 字'
  }

  return !hasAmountError.value && !hasActualPayerNameError.value && !hasPaymentDateError.value && !hasNotesError.value
}

function handleSubmit(): void {
  if (isSubmitting.value || props.record === null || !validateForm()) {
    return
  }

  const payload: PaymentRecordUpdate = {
    actual_amount: Number(form.actualAmount.trim()),
    actual_payer_name: form.actualPayerName.trim(),
    payment_date: form.paymentDate.trim(),
    proof_attachment: form.proofAttachment.trim(),
    notes: form.notes.trim(),
  }

  emit('submit', props.record.id, payload)
}

function closeDialog(): void {
  if (!isSubmitting.value) {
    visible.value = false
  }
}

watch(
  () => [props.open, props.record] as const,
  ([isOpen, record]) => {
    if (!isOpen || record === null) {
      resetForm()
      return
    }

    populateForm(record)
  },
  { immediate: true }
)
</script>

<template>
  <Dialog v-model:open="visible">
    <DialogContent class="edit-record-dialog">
      <DialogHeader>
        <DialogTitle>修改回款记录</DialogTitle>
        <DialogDescription>
          修改已登记的回款金额、日期和凭证备注，保存后由上层流程继续处理审批。
        </DialogDescription>
      </DialogHeader>

      <form class="edit-record-dialog__form" novalidate @submit.prevent="handleSubmit">
        <InputField
          id="edit-record-amount"
          v-model="form.actualAmount"
          class="edit-record-dialog__field"
          label="回款金额"
          required
          name="actual_amount"
          type="number"
          inputmode="decimal"
          min="0"
          step="0.01"
          placeholder="请输入回款金额"
          :disabled="isSubmitting || record === null"
          helper-text="金额需大于 0，可精确到分。"
          :error="errors.actualAmount"
        />

        <InputField
          id="edit-record-payer-name"
          v-model="form.actualPayerName"
          class="edit-record-dialog__field"
          label="实际付款方"
          required
          name="actual_payer_name"
          type="text"
          maxlength="200"
          placeholder="请输入实际付款方"
          :disabled="isSubmitting || record === null"
          helper-text="可按实际付款公司抬头修改。"
          :error="errors.actualPayerName"
        />

        <DateField
          id="edit-record-date"
          :model-value="parseLocalDate(form.paymentDate)"
          class="edit-record-dialog__field"
          label="回款日期"
          required
          placeholder="请选择回款日期"
          :disabled="isSubmitting || record === null"
          helper-text="使用本地日期，格式为 YYYY-MM-DD。"
          :error="errors.paymentDate"
          @update:model-value="handlePaymentDateChange"
        />

        <InputField
          id="edit-record-proof"
          v-model="form.proofAttachment"
          class="edit-record-dialog__field"
          label="凭证附件 URL"
          name="proof_attachment"
          type="url"
          placeholder="请输入附件 URL（可选）"
          :disabled="isSubmitting || record === null"
        />

        <TextareaField
          id="edit-record-notes"
          v-model="form.notes"
          class="edit-record-dialog__field"
          label="备注"
          name="notes"
          maxlength="200"
          placeholder="请输入备注信息（可选，最多 200 字）"
          control-class="min-h-20"
          :disabled="isSubmitting || record === null"
          :helper-text="`${form.notes.length}/200`"
          :error="errors.notes"
        />

        <DialogFooter class="edit-record-dialog__footer">
          <Button
            type="button"
            variant="outline"
            class="edit-record-dialog__button min-h-11"
            :disabled="isSubmitting"
            @click="closeDialog"
          >
            取消
          </Button>
          <Button
            type="submit"
            class="edit-record-dialog__button min-h-11"
            :disabled="isSubmitting || record === null"
          >
            {{ isSubmitting ? '提交中...' : '保存修改' }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.edit-record-dialog {
  max-height: $wolf-modal-height-mobile-v2;
  overflow-y: auto;
}

.edit-record-dialog__form {
  display: flex;
  flex-direction: column;
  gap: $wolf-form-item-gap-v2;
}

.edit-record-dialog__field {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm-v2;
}

.edit-record-dialog__button {
  min-height: $wolf-touch-target-min-v2;
}

.edit-record-dialog__footer {
  gap: $wolf-space-sm-v2;
  padding-top: $wolf-space-lg-v2;
  border-top: 1px solid $wolf-border-divider-v2;
}

@media (max-width: $wolf-breakpoint-sm-v2) {
  .edit-record-dialog__button {
    width: 100%;
  }
}
</style>
