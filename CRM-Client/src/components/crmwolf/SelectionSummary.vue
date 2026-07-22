<script setup lang="ts">
interface SummaryItem {
  label: string
  value: string | number | null | undefined
}

interface Props {
  items: SummaryItem[]
  placeholder?: string
}

withDefaults(defineProps<Props>(), {
  placeholder: '-',
})
</script>

<template>
  <div class="selection-summary">
    <div
      v-for="item in items"
      :key="item.label"
      class="selection-summary__item"
    >
      <span>{{ item.label }}</span>
      <strong>{{ item.value ?? placeholder }}</strong>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.selection-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $wolf-space-sm-v2 $wolf-space-md-v2;
  padding: $wolf-space-md-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-bg-muted-v2;
}

.selection-summary__item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  min-width: 0;

  span {
    color: $wolf-text-tertiary-v2;
    font-size: $wolf-font-size-caption-v2;
  }

  strong {
    color: $wolf-text-primary-v2;
    font-size: $wolf-font-size-body-v2;
    font-weight: $wolf-font-weight-medium-v2;
    overflow-wrap: anywhere;
  }
}

@media (max-width: $wolf-breakpoint-sm-v2) {
  .selection-summary {
    grid-template-columns: 1fr;
  }
}
</style>
