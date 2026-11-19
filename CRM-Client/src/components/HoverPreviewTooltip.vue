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
@use '@/styles/tokens.scss' as *;

.hover-preview {
  display: inline-flex;
}

:global(.hover-preview-card) {
  width: auto;
  padding: $space-2;
}

.hover-preview-tooltip {
  max-width: 380px;
  font-size: 12px;
}

.tooltip-row {
  display: flex;
  gap: $space-2;
  padding: 2px 0;
}

.tooltip-label {
  color: hsl(var(--muted-foreground));
  font-weight: 500;
}

.tooltip-value {
  color: hsl(var(--foreground));
  white-space: normal;
  overflow-wrap: anywhere;
}
</style>
