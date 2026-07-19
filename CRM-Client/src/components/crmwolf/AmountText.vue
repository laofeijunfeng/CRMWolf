<script setup lang="ts">
import { computed } from 'vue'
import { formatCurrency } from '@/utils/format'

type AmountTone = 'default' | 'primary' | 'success' | 'warning' | 'danger' | 'muted'
type AmountSize = 'sm' | 'md' | 'lg' | 'xl'

interface Props {
  value: number | string | null | undefined
  tone?: AmountTone
  size?: AmountSize
  placeholder?: string
}

const props = withDefaults(defineProps<Props>(), {
  tone: 'default',
  size: 'md',
  placeholder: '-'
})

const isEmpty = computed(() => props.value === null || props.value === undefined || props.value === '')
const displayValue = computed(() => (isEmpty.value ? props.placeholder : formatCurrency(props.value)))
</script>

<template>
  <span
    class="amount-text"
    :class="[
      `amount-text--${tone}`,
      `amount-text--${size}`,
      { 'amount-text--empty': isEmpty }
    ]"
  >
    {{ displayValue }}
  </span>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.amount-text {
  display: inline-flex;
  align-items: baseline;
  justify-content: flex-end;
  max-width: 100%;
  font-family: $wolf-font-mono-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  font-variant-numeric: tabular-nums;
  line-height: 1.35;
  white-space: nowrap;
}

.amount-text--sm {
  font-size: $wolf-font-size-caption-v2;
}

.amount-text--md {
  font-size: $wolf-font-size-body-v2;
}

.amount-text--lg {
  font-size: 18px;
}

.amount-text--xl {
  font-size: 24px;
}

.amount-text--default {
  color: $wolf-accent-v2;
}

.amount-text--primary {
  color: $wolf-primary-v2;
}

.amount-text--success {
  color: $wolf-success-text-v2;
}

.amount-text--warning {
  color: $wolf-warning-text-v2;
}

.amount-text--danger {
  color: $wolf-danger-text-v2;
}

.amount-text--muted,
.amount-text--empty {
  color: $wolf-text-tertiary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}
</style>
