<script setup lang="ts">
import { HoverInfo } from '@/components/crmwolf'

interface TooltipRow {
  label: string
  value: string
}

interface Props {
  rows: TooltipRow[]
  minWidth?: number
}

const props = withDefaults(defineProps<Props>(), {
  minWidth: 200
})
</script>

<template>
  <HoverInfo side="bottom" align="start" content-class="hover-preview-card">
    <template #trigger>
      <span class="hover-preview">
        <slot />
      </span>
    </template>
    <div
      class="hover-preview-tooltip"
      :style="{ minWidth: `${props.minWidth}px` }"
    >
      <div v-for="row in rows" :key="row.label" class="tooltip-row">
        <span class="tooltip-label">{{ row.label }}:</span>
        <span class="tooltip-value">{{ row.value }}</span>
      </div>
    </div>
  </HoverInfo>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.hover-preview {
  display: inline-flex;
}

:global(.hover-preview-card) {
  width: auto;
  padding: $wolf-space-sm-v2;
}

.hover-preview-tooltip {
  font-size: $wolf-font-size-caption-v2;
  white-space: nowrap;
}

.tooltip-row {
  display: flex;
  gap: $wolf-space-sm-v2;
  padding: 2px 0;
}

.tooltip-label {
  color: $wolf-text-tertiary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.tooltip-value {
  color: $wolf-text-primary-v2;
}
</style>
