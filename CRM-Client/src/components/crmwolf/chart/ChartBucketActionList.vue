<script lang="ts">
export interface ChartBucketAction {
  key: string
  label: string
  ariaLabel?: string
  disabled?: boolean
  value?: string | number
  class?: string
  color?: string
}
</script>

<script setup lang="ts" generic="T extends ChartBucketAction">
import type { VNode } from 'vue'
import { Button } from '@/components/ui/button'

withDefaults(defineProps<{
  actions: readonly T[]
  ariaLabel?: string
  testIdPrefix?: string
}>(), {
  ariaLabel: '图表分组',
  testIdPrefix: '',
})

const emit = defineEmits<{
  activate: [action: T]
}>()

defineSlots<{
  default?: (props: { action: T }) => VNode[]
}>()

function activate(action: T): void {
  if (action.disabled !== true) emit('activate', action)
}
</script>

<template>
  <div class="chart-bucket-actions" :aria-label="ariaLabel">
    <Button
      v-for="action in actions"
      :key="action.key"
      type="button"
      variant="ghost"
      class="chart-bucket-actions__action focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      :class="action.class"
      :data-testid="testIdPrefix ? `${testIdPrefix}-${action.key}` : undefined"
      :aria-label="action.ariaLabel ?? action.label"
      :disabled="action.disabled === true"
      @click="activate(action)"
    >
      <slot :action="action">
        <i v-if="action.color" class="chart-bucket-actions__color" :style="{ backgroundColor: action.color }" aria-hidden="true" />
        <span class="chart-bucket-actions__label">{{ action.label }}</span>
        <span v-if="action.value !== undefined" class="chart-bucket-actions__value">{{ action.value }}</span>
      </slot>
    </Button>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.chart-bucket-actions {
  display: grid;
  min-width: 0;
  gap: $wolf-space-sm-v2;
}

.chart-bucket-actions__action {
  width: 100%;
  height: auto;
  justify-content: flex-start;
  gap: $wolf-space-sm-v2;
  border-radius: $wolf-radius-control-v2;
  text-align: left;
  white-space: normal;
}

.chart-bucket-actions__action:not(:disabled):hover {
  background: $wolf-bg-muted-v2;
}

.chart-bucket-actions__color {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  border-radius: 50%;
}

@media (max-width: 600px) {
  .chart-bucket-actions__action {
    min-height: $wolf-touch-target-min-v2;
  }
}

.chart-bucket-actions__label {
  min-width: 0;
  flex: 1 1 auto;
  color: $wolf-text-primary-v2;
}

.chart-bucket-actions__value {
  color: $wolf-text-tertiary-v2;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
</style>
