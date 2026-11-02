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

const check = computed(() => validatePaymentComposition(props.form, props.actualAmount))
const showStatus = computed(() => !check.value.empty && check.value.message.length > 0)

function fieldId(suffix: string): string {
  return `${props.idPrefix}-${suffix}`
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
          v-model="form.renewalHeadcount"
          name="renewal_headcount"
          type="number"
          inputmode="numeric"
          min="0"
          step="1"
          :disabled="props.disabled"
          aria-label="续购人数"
        />
      </div>
      <div>
        <Label class="sr-only" :for="fieldId('renewal-amount')">续购金额</Label>
        <InputField
          :id="fieldId('renewal-amount')"
          v-model="form.renewalAmount"
          name="renewal_amount"
          type="number"
          inputmode="decimal"
          min="0"
          step="0.01"
          :disabled="props.disabled"
          aria-label="续购金额"
        />
      </div>

      <span class="payment-composition__row" id="payment-composition-expansion-label">增购</span>
      <div>
        <Label class="sr-only" :for="fieldId('expansion-headcount')">增购人数</Label>
        <InputField
          :id="fieldId('expansion-headcount')"
          v-model="form.expansionHeadcount"
          name="expansion_headcount"
          type="number"
          inputmode="numeric"
          min="0"
          step="1"
          :disabled="props.disabled"
          aria-label="增购人数"
        />
      </div>
      <div>
        <Label class="sr-only" :for="fieldId('expansion-amount')">增购金额</Label>
        <InputField
          :id="fieldId('expansion-amount')"
          v-model="form.expansionAmount"
          name="expansion_amount"
          type="number"
          inputmode="decimal"
          min="0"
          step="0.01"
          :disabled="props.disabled"
          aria-label="增购金额"
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
@use '@/styles/variables-v2.scss' as *;

.payment-composition {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
  padding: $wolf-space-lg-v2;
  border: 1px solid $wolf-border-divider-v2;
  border-radius: $wolf-radius-lg-v2;
}

.payment-composition__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: $wolf-space-md-v2;
}

.payment-composition__title {
  margin: 0;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.payment-composition__hint,
.payment-composition__column,
.payment-composition__status {
  margin: 0;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
}

.payment-composition__table {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) minmax(0, 1fr);
  gap: $wolf-space-sm-v2 $wolf-space-md-v2;
  align-items: center;
}

.payment-composition__column {
  text-align: left;
}

.payment-composition__row {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.payment-composition__status--error {
  color: $wolf-danger-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

@media (max-width: $wolf-breakpoint-sm-v2) {
  .payment-composition__header {
    flex-direction: column;
  }
}
</style>
