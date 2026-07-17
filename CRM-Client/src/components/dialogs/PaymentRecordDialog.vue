<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import type { PaymentRecordCreate } from '@/api/payment'
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
import { DatePicker } from '@/components/ui/date-picker'

interface Props {
  open: boolean
  defaultAmount?: number | null
  submitting?: boolean
}

interface Emits {
  (event: 'update:open', value: boolean): void
  (event: 'submit', payload: PaymentRecordCreate): void
}

interface PaymentRecordForm {
  actualAmount: string
  paymentDate: string
  proofAttachment: string
  notes: string
}

interface PaymentRecordErrors {
  actualAmount: string
  paymentDate: string
  notes: string
}

const props = withDefaults(defineProps<Props>(), {
  defaultAmount: null,
  submitting: false,
})

const emit = defineEmits<Emits>()

const form = reactive<PaymentRecordForm>({
  actualAmount: '',
  paymentDate: '',
  proofAttachment: '',
  notes: '',
})

const errors = reactive<PaymentRecordErrors>({
  actualAmount: '',
  paymentDate: '',
  notes: '',
})

const visible = computed({
  get: (): boolean => props.open,
  set: (value: boolean): void => emit('update:open', value),
})

const isSubmitting = computed((): boolean => props.submitting === true)
const hasAmountError = computed((): boolean => errors.actualAmount.length > 0)
const hasPaymentDateError = computed((): boolean => errors.paymentDate.length > 0)
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
  errors.paymentDate = ''
  errors.notes = ''
}

function resetForm(): void {
  form.actualAmount = formatDefaultAmount(props.defaultAmount)
  form.paymentDate = getLocalDateString()
  form.proofAttachment = ''
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

  const normalizedDate = form.paymentDate.trim()
  if (normalizedDate.length === 0 || !isValidLocalDate(normalizedDate)) {
    errors.paymentDate = '请选择回款日期'
  }

  if (form.notes.length > 200) {
    errors.notes = '备注不能超过 200 字'
  }

  return !hasAmountError.value && !hasPaymentDateError.value && !hasNotesError.value
}

function handleSubmit(): void {
  if (isSubmitting.value || !validateForm()) {
    return
  }

  const payload: PaymentRecordCreate = {
    actual_amount: Number(form.actualAmount.trim()),
    payment_date: form.paymentDate.trim(),
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

watch(
  () => [props.open, props.defaultAmount] as const,
  ([isOpen]) => {
    if (isOpen) {
      resetForm()
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
        <div class="payment-record-dialog__field">
          <label class="payment-record-dialog__label" for="payment-record-amount">
            回款金额
            <span class="payment-record-dialog__required" aria-hidden="true">*</span>
          </label>
          <Input
            id="payment-record-amount"
            v-model="form.actualAmount"
            name="actual_amount"
            type="number"
            inputmode="decimal"
            min="0"
            step="0.01"
            placeholder="请输入回款金额"
            class="payment-record-dialog__control h-11 min-h-11"
            :disabled="isSubmitting"
            :aria-invalid="hasAmountError"
            aria-describedby="payment-record-amount-help payment-record-amount-error"
          />
          <p id="payment-record-amount-help" class="payment-record-dialog__help">
            金额需大于 0，可精确到分。
          </p>
          <p
            v-if="hasAmountError"
            id="payment-record-amount-error"
            class="payment-record-dialog__error"
            role="alert"
          >
            {{ errors.actualAmount }}
          </p>
        </div>

        <div class="payment-record-dialog__field">
          <label class="payment-record-dialog__label" for="payment-record-date">
            回款日期
            <span class="payment-record-dialog__required" aria-hidden="true">*</span>
          </label>
          <DatePicker
            :model-value="parseLocalDateString(form.paymentDate)"
            placeholder="请选择回款日期"
            class="payment-record-dialog__control"
            :disabled="isSubmitting"
            @update:model-value="handlePaymentDateChange"
          />
          <p id="payment-record-date-help" class="payment-record-dialog__help">
            使用本地日期，格式为 YYYY-MM-DD。
          </p>
          <p
            v-if="hasPaymentDateError"
            id="payment-record-date-error"
            class="payment-record-dialog__error"
            role="alert"
          >
            {{ errors.paymentDate }}
          </p>
        </div>

        <div class="payment-record-dialog__field">
          <label class="payment-record-dialog__label" for="payment-record-proof">
            凭证附件 URL
          </label>
          <Input
            id="payment-record-proof"
            v-model="form.proofAttachment"
            name="proof_attachment"
            type="url"
            placeholder="请输入附件 URL（可选）"
            class="payment-record-dialog__control h-11 min-h-11"
            :disabled="isSubmitting"
          />
        </div>

        <div class="payment-record-dialog__field">
          <label class="payment-record-dialog__label" for="payment-record-notes">
            备注
          </label>
          <Textarea
            id="payment-record-notes"
            v-model="form.notes"
            name="notes"
            maxlength="200"
            placeholder="请输入备注信息（可选，最多 200 字）"
            class="payment-record-dialog__textarea min-h-20"
            :disabled="isSubmitting"
            :aria-invalid="hasNotesError"
            aria-describedby="payment-record-notes-help payment-record-notes-error"
          />
          <p id="payment-record-notes-help" class="payment-record-dialog__help">
            {{ form.notes.length }}/200
          </p>
          <p
            v-if="hasNotesError"
            id="payment-record-notes-error"
            class="payment-record-dialog__error"
            role="alert"
          >
            {{ errors.notes }}
          </p>
        </div>

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
            :disabled="isSubmitting"
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

.payment-record-dialog__label {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: $wolf-line-height-body-v2;
}

.payment-record-dialog__required {
  color: $wolf-danger-text-v2;
}

.payment-record-dialog__control,
.payment-record-dialog__textarea,
.payment-record-dialog__button {
  min-height: $wolf-touch-target-min-v2;
}

.payment-record-dialog__help,
.payment-record-dialog__error {
  margin: 0;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
}

.payment-record-dialog__help {
  color: $wolf-text-secondary-v2;
}

.payment-record-dialog__error {
  color: $wolf-danger-text-v2;
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
