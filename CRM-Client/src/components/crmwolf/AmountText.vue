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

.amount-text {
  display: inline-flex;
  align-items: baseline;
  justify-content: flex-end;
  max-width: 100%;
  font-family: var(--font-mono);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1.35;
  white-space: nowrap;
}

.amount-text--sm {
  font-size: 12px;
}

.amount-text--md {
  font-size: 14px;
}

.amount-text--lg {
  font-size: 18px;
}

.amount-text--xl {
  font-size: 24px;
}

.amount-text--default {
  color: hsl(var(--status-success));
}

.amount-text--primary {
  color: hsl(var(--brand));
}

.amount-text--success {
  color: hsl(var(--status-success));
}

.amount-text--warning {
  color: hsl(var(--status-warning));
}

.amount-text--danger {
  color: hsl(var(--status-danger));
}

.amount-text--muted,
.amount-text--empty {
  color: hsl(var(--muted-foreground));
  font-weight: 500;
}
</style>
