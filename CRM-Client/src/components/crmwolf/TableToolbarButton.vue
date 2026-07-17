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
@use '@/styles/variables-v2.scss' as *;

.table-toolbar-button {
  height: 30px;
  min-width: auto;
  padding: 0 8px;
  gap: 5px;
  border: 0;
  border-radius: $wolf-radius-sm-v2;
  background: transparent;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-auxiliary-v2;

  &:hover {
    background: #F1F5FD;
    color: $wolf-text-primary-v2;
  }
}

.table-toolbar-button-active {
  background: #EAF2FF;
  color: #1F5FBF;

  &:hover {
    background: #DFEAFF;
    color: #1F5FBF;
  }
}

.table-toolbar-button-count {
  min-width: 16px;
  height: 16px;
  padding: 0 5px;
  border-radius: 999px;
  background: #1F5FBF;
  color: #FFFFFF;
  font-size: 11px;
  line-height: 16px;
  text-align: center;
}
</style>
