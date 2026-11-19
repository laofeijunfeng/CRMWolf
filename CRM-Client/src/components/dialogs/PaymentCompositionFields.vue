<script setup lang="ts">
import { computed } from 'vue'
import { InputField } from '@/components/crmwolf'
import { Label } from '@/components/ui/label'
import {
  validatePaymentComposition,
  type PaymentCompositionForm,
} from '@/components/dialogs/paymentComposition'

interface Props {
  idPrefix: string
  form: PaymentCompositionForm
  actualAmount: string
  disabled: boolean
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
})

const emit = defineEmits<{
  'update:form': [value: PaymentCompositionForm]
}>()

const check = computed(() => validatePaymentComposition(props.form, props.actualAmount))
const showStatus = computed(() => !check.value.empty && check.value.message.length > 0)

function fieldId(suffix: string): string {
  return `${props.idPrefix}-${suffix}`
}

function updateField(field: keyof PaymentCompositionForm, value: string | number): void {
  emit('update:form', { ...props.form, [field]: String(value) })
}
</script>

<template>
  <section class="payment-composition" aria-label="构成">
    <div class="payment-composition__header">
      <h3 class="payment-composition__title">构成</h3>
      <p class="payment-composition__hint">点开补充信息之后才填。</p>
    </div>
    <div class="payment-composition__table">
      <span />
      <span class="payment-composition__column">人数</span>
      <span class="payment-composition__column">金额</span>

      <span class="payment-composition__row" id="payment-composition-renewal-label">续购</span>
      <div>
        <Label class="sr-only" :for="fieldId('renewal-headcount')">续购人数</Label>
        <InputField
          :id="fieldId('renewal-headcount')"
          :model-value="form.renewalHeadcount"
          name="renewal_headcount"
          type="number"
          inputmode="numeric"
          min="0"
          step="1"
          :disabled="props.disabled"
          aria-label="续购人数"
          @update:model-value="updateField('renewalHeadcount', $event)"
        />
      </div>
      <div>
        <Label class="sr-only" :for="fieldId('renewal-amount')">续购金额</Label>
        <InputField
          :id="fieldId('renewal-amount')"
          :model-value="form.renewalAmount"
          name="renewal_amount"
          type="number"
          inputmode="decimal"
          min="0"
          step="0.01"
          :disabled="props.disabled"
          aria-label="续购金额"
          @update:model-value="updateField('renewalAmount', $event)"
        />
      </div>

      <span class="payment-composition__row" id="payment-composition-expansion-label">增购</span>
      <div>
        <Label class="sr-only" :for="fieldId('expansion-headcount')">增购人数</Label>
        <InputField
          :id="fieldId('expansion-headcount')"
          :model-value="form.expansionHeadcount"
          name="expansion_headcount"
          type="number"
          inputmode="numeric"
          min="0"
          step="1"
          :disabled="props.disabled"
          aria-label="增购人数"
          @update:model-value="updateField('expansionHeadcount', $event)"
        />
      </div>
      <div>
        <Label class="sr-only" :for="fieldId('expansion-amount')">增购金额</Label>
        <InputField
          :id="fieldId('expansion-amount')"
          :model-value="form.expansionAmount"
          name="expansion_amount"
          type="number"
          inputmode="decimal"
          min="0"
          step="0.01"
          :disabled="props.disabled"
          aria-label="增购金额"
          @update:model-value="updateField('expansionAmount', $event)"
        />
      </div>
    </div>
    <p
      v-if="showStatus"
      :id="fieldId('composition-status')"
      class="payment-composition__status"
      :class="{ 'payment-composition__status--error': !check.valid }"
      :role="check.valid ? undefined : 'alert'"
    >
      {{ check.message }}
    </p>
  </section>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.payment-composition {
  display: flex;
  flex-direction: column;
  gap: $space-3;
  padding: $space-4;
  border: 1px solid hsl(var(--border));
  border-radius: var(--radius-lg);
}

.payment-composition__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: $space-3;
}

.payment-composition__title {
  margin: 0;
  color: hsl(var(--foreground));
  font-size: var(--font-size-body);
  font-weight: 500;
}

.payment-composition__hint,
.payment-composition__column,
.payment-composition__status {
  margin: 0;
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-caption);
}

.payment-composition__table {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) minmax(0, 1fr);
  gap: $space-2 $space-3;
  align-items: center;
}

.payment-composition__column {
  text-align: left;
}

.payment-composition__row {
  color: hsl(var(--foreground));
  font-size: var(--font-size-body);
  font-weight: 500;
}

.payment-composition__status--error {
  color: hsl(var(--status-danger));
  font-weight: 500;
}

@media (max-width: $bp-sm) {
  .payment-composition__header {
    flex-direction: column;
  }
}
</style>
