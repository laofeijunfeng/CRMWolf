<script setup lang="ts">
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
  <div class="hover-preview">
    <slot />  <!-- 触发元素 -->

    <div
      class="hover-preview-tooltip"
      :style="{ minWidth: `${minWidth}px` }"
    >
      <div v-for="row in rows" :key="row.label" class="tooltip-row">
        <span class="tooltip-label">{{ row.label }}:</span>
        <span class="tooltip-value">{{ row.value }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.hover-preview {
  position: relative;
}

.hover-preview-tooltip {
  position: absolute;
  left: 0;
  top: 100%;
  margin-top: 4px;
  background: white;
  border: 1px solid #E5E5E5;
  border-radius: 8px;
  padding: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  font-size: 12px;
  z-index: 100;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.15s, visibility 0.15s;
  white-space: nowrap;
}

.hover-preview:hover .hover-preview-tooltip {
  opacity: 1;
  visibility: visible;
}

.tooltip-row {
  display: flex;
  gap: 8px;
  padding: 2px 0;
}

.tooltip-label {
  color: #636363;
  font-weight: 500;
}

.tooltip-value {
  color: #1C1C1C;
}

// 无障碍：减少动画
@media (prefers-reduced-motion: reduce) {
  .hover-preview-tooltip {
    transition: none;
  }
}
</style>