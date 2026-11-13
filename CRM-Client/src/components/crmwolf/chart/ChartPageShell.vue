<script setup lang="ts">
import type { VNode } from 'vue'

export type ChartPageState = 'loading' | 'error' | 'empty' | 'ready'

defineProps<{
  state: ChartPageState
  ariaLabel?: string
}>()

defineSlots<{
  loading?: (props: { state: ChartPageState }) => VNode[]
  error?: (props: { state: ChartPageState }) => VNode[]
  empty?: (props: { state: ChartPageState }) => VNode[]
  summary?: () => VNode[]
  refreshing?: () => VNode[]
  'inline-error'?: () => VNode[]
  ready?: () => VNode[]
  default?: () => VNode[]
  overlays?: () => VNode[]
}>()
</script>

<template>
  <section class="chart-page-shell" :aria-label="ariaLabel">
    <slot v-if="state === 'loading'" name="loading" :state="state" />
    <slot v-else-if="state === 'error'" name="error" :state="state" />
    <slot v-else-if="state === 'empty'" name="empty" :state="state" />
    <template v-else>
      <slot name="summary" />
      <slot name="refreshing" />
      <slot name="inline-error" />
      <slot name="ready"><slot /></slot>
    </template>
    <slot name="overlays" />
  </section>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.chart-page-shell {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  gap: $wolf-space-md-v2;
  overflow: auto;
  padding: $wolf-space-md-v2;
}
</style>
