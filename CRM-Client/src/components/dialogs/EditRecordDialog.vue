<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
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
import { confirmDialog } from '@/utils/confirmDialog'
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

const initialForm = ref<EditRecordForm | null>(null)
const closeGuardPending = ref(false)

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
const validationErrorMessages = computed((): string[] => [
  errors.actualAmount,
  errors.actualPayerName,
  errors.paymentDate,
  errors.notes,
].filter((message): message is string => message.length > 0))

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
  initialForm.value = null
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
  initialForm.value = { ...form }
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

async function focusFirstError(): Promise<void> {
  await nextTick()
  const fieldIds: [keyof EditRecordErrors, string][] = [
    ['actualAmount', 'edit-record-amount'],
    ['actualPayerName', 'edit-record-payer-name'],
    ['paymentDate', 'edit-record-date'],
    ['notes', 'edit-record-notes'],
  ]

  for (const [field, id] of fieldIds) {
    if (errors[field].length === 0) continue
    const element = document.getElementById(id)
    if (element instanceof HTMLElement) {
      element.focus()
      return
    }
  }
}

function handleSubmit(): void {
  if (isSubmitting.value || props.record === null) {
    return
  }

  if (!validateForm()) {
    void focusFirstError()
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

const hasFormChanges = computed(() => {
  const initial = initialForm.value
  if (initial === null) return false

  return form.actualAmount.trim() !== initial.actualAmount.trim()
    || form.actualPayerName.trim() !== initial.actualPayerName.trim()
    || form.paymentDate !== initial.paymentDate
    || form.proofAttachment.trim() !== initial.proofAttachment.trim()
    || form.notes.trim() !== initial.notes.trim()
})

async function handleOpenChange(open: boolean): Promise<void> {
  if (open) {
    visible.value = true
    return
  }

  if (isSubmitting.value || closeGuardPending.value) return

  if (!hasFormChanges.value) {
    visible.value = false
    return
  }

  closeGuardPending.value = true
  try {
    const confirmed = await confirmDialog(
      '已修改回款记录，关闭后这些修改不会保存。确定关闭吗？',
      '放弃本次修改？',
      { variant: 'destructive', confirmText: '放弃并关闭' },
    )
    if (confirmed) visible.value = false
  } finally {
    closeGuardPending.value = false
  }
}

function closeDialog(): void {
  void handleOpenChange(false)
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
  <Dialog :open="props.open" @update:open="handleOpenChange">
    <DialogContent class="edit-record-dialog">
      <DialogHeader>
        <DialogTitle>修改回款记录</DialogTitle>
        <DialogDescription>
          修改已登记的回款金额、日期和凭证备注，保存后由上层流程继续处理审批。
        </DialogDescription>
      </DialogHeader>

      <div
        v-if="validationErrorMessages.length > 0"
        class="edit-record-dialog__error-summary"
        role="alert"
        aria-live="assertive"
      >
        <strong>请先修正以下字段：</strong>
        <ul>
          <li v-for="message in validationErrorMessages" :key="message">{{ message }}</li>
        </ul>
      </div>

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
            :disabled="isSubmitting || closeGuardPending"
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
  overscroll-behavior: contain;
  scroll-padding-bottom: calc($wolf-space-xl-v2 + $wolf-safe-area-bottom-v2);
}

.edit-record-dialog__form {
  display: flex;
  flex-direction: column;
  gap: $wolf-form-item-gap-v2;
}

.edit-record-dialog__error-summary {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  padding: $wolf-space-md-v2;
  border: 1px solid $wolf-danger-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-danger-bg-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
}

.edit-record-dialog__error-summary strong {
  color: $wolf-text-primary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.edit-record-dialog__error-summary ul {
  margin: 0;
  padding-left: $wolf-space-lg-v2;
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
