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
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

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
        <div class="edit-record-dialog__field">
          <label class="edit-record-dialog__label" for="edit-record-amount">
            回款金额
            <span class="edit-record-dialog__required" aria-hidden="true">*</span>
          </label>
          <Input
            id="edit-record-amount"
            v-model="form.actualAmount"
            name="actual_amount"
            type="number"
            inputmode="decimal"
            min="0"
            step="0.01"
            placeholder="请输入回款金额"
            class="edit-record-dialog__control h-11 min-h-11"
            :disabled="isSubmitting || record === null"
            :aria-invalid="hasAmountError"
            aria-describedby="edit-record-amount-help edit-record-amount-error"
          />
          <p id="edit-record-amount-help" class="edit-record-dialog__help">
            金额需大于 0，可精确到分。
          </p>
          <p
            v-if="hasAmountError"
            id="edit-record-amount-error"
            class="edit-record-dialog__error"
            role="alert"
          >
            {{ errors.actualAmount }}
          </p>
        </div>

        <div class="edit-record-dialog__field">
          <label class="edit-record-dialog__label" for="edit-record-payer-name">
            实际付款方
            <span class="edit-record-dialog__required" aria-hidden="true">*</span>
          </label>
          <Input
            id="edit-record-payer-name"
            v-model="form.actualPayerName"
            name="actual_payer_name"
            type="text"
            maxlength="200"
            placeholder="请输入实际付款方"
            class="edit-record-dialog__control h-11 min-h-11"
            :disabled="isSubmitting || record === null"
            :aria-invalid="hasActualPayerNameError"
            aria-describedby="edit-record-payer-name-help edit-record-payer-name-error"
          />
          <p id="edit-record-payer-name-help" class="edit-record-dialog__help">
            可按实际付款公司抬头修改。
          </p>
          <p
            v-if="hasActualPayerNameError"
            id="edit-record-payer-name-error"
            class="edit-record-dialog__error"
            role="alert"
          >
            {{ errors.actualPayerName }}
          </p>
        </div>

        <div class="edit-record-dialog__field">
          <label class="edit-record-dialog__label" for="edit-record-date">
            回款日期
            <span class="edit-record-dialog__required" aria-hidden="true">*</span>
          </label>
          <Input
            id="edit-record-date"
            v-model="form.paymentDate"
            name="payment_date"
            type="date"
            class="edit-record-dialog__control h-11 min-h-11"
            :disabled="isSubmitting || record === null"
            :aria-invalid="hasPaymentDateError"
            aria-describedby="edit-record-date-help edit-record-date-error"
          />
          <p id="edit-record-date-help" class="edit-record-dialog__help">
            使用本地日期，格式为 YYYY-MM-DD。
          </p>
          <p
            v-if="hasPaymentDateError"
            id="edit-record-date-error"
            class="edit-record-dialog__error"
            role="alert"
          >
            {{ errors.paymentDate }}
          </p>
        </div>

        <div class="edit-record-dialog__field">
          <label class="edit-record-dialog__label" for="edit-record-proof">
            凭证附件 URL
          </label>
          <Input
            id="edit-record-proof"
            v-model="form.proofAttachment"
            name="proof_attachment"
            type="url"
            placeholder="请输入附件 URL（可选）"
            class="edit-record-dialog__control h-11 min-h-11"
            :disabled="isSubmitting || record === null"
          />
        </div>

        <div class="edit-record-dialog__field">
          <label class="edit-record-dialog__label" for="edit-record-notes">
            备注
          </label>
          <Textarea
            id="edit-record-notes"
            v-model="form.notes"
            name="notes"
            maxlength="200"
            placeholder="请输入备注信息（可选，最多 200 字）"
            class="edit-record-dialog__textarea min-h-20"
            :disabled="isSubmitting || record === null"
            :aria-invalid="hasNotesError"
            aria-describedby="edit-record-notes-help edit-record-notes-error"
          />
          <p id="edit-record-notes-help" class="edit-record-dialog__help">
            {{ form.notes.length }}/200
          </p>
          <p
            v-if="hasNotesError"
            id="edit-record-notes-error"
            class="edit-record-dialog__error"
            role="alert"
          >
            {{ errors.notes }}
          </p>
        </div>

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

.edit-record-dialog__label {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: $wolf-line-height-body-v2;
}

.edit-record-dialog__required {
  color: $wolf-danger-text-v2;
}

.edit-record-dialog__control,
.edit-record-dialog__textarea,
.edit-record-dialog__button {
  min-height: $wolf-touch-target-min-v2;
}

.edit-record-dialog__help,
.edit-record-dialog__error {
  margin: 0;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
}

.edit-record-dialog__help {
  color: $wolf-text-secondary-v2;
}

.edit-record-dialog__error {
  color: $wolf-danger-text-v2;
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
