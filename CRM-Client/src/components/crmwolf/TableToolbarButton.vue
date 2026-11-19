<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { Button } from '@/components/ui/button'

const props = withDefaults(defineProps<{
  active?: boolean
  count?: number
  class?: HTMLAttributes['class']
}>(), {
  active: false,
  count: 0,
  class: undefined
})
</script>

<template>
  <Button
    v-bind="$attrs"
    type="button"
    variant="ghost"
    size="sm"
    :class="[
      'table-toolbar-button',
      { 'table-toolbar-button-active': active },
      props.class
    ]"
  >
    <slot />
    <span v-if="props.count > 0" class="table-toolbar-button-count">
      {{ props.count }}
    </span>
  </Button>
</template>

<style scoped lang="scss">

.table-toolbar-button {
  height: 30px;
  min-width: auto;
  padding: 0 8px;
  gap: 5px;
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-body);

  &:hover {
    background: var(--wash-hover);
    color: hsl(var(--foreground));
  }
}

.table-toolbar-button-active {
  background: var(--wash-hover);
  color: hsl(var(--brand));

  &:hover {
    background: var(--wash-selected);
    color: hsl(var(--brand));
  }
}

.table-toolbar-button-count {
  min-width: 16px;
  height: 16px;
  padding: 0 5px;
  border-radius: 999px;
  background: hsl(var(--brand));
  color: hsl(var(--primary-foreground));
  font-size: var(--font-size-caption);
  line-height: 16px;
  text-align: center;
}
</style>
