<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'

withDefaults(defineProps<{
  title: string
  resetLabel?: string
}>(), {
  resetLabel: '清空'
})

const emit = defineEmits<{
  reset: []
}>()
</script>

<template>
  <div class="table-toolbar-builder">
    <div class="table-toolbar-builder-header">
      <span class="table-toolbar-builder-title">{{ title }}</span>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        class="table-toolbar-icon-button"
        :aria-label="resetLabel"
        @click="emit('reset')"
      >
        <X class="w-4 h-4" aria-hidden="true" />
      </Button>
    </div>

    <div class="table-toolbar-builder-body">
      <slot />
    </div>

    <div class="table-toolbar-builder-footer">
      <slot name="footer" />
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.table-toolbar-builder {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
}

.table-toolbar-builder-header,
.table-toolbar-builder-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.table-toolbar-builder-title {
  font-size: 14px;
  font-weight: 600;
  color: $wolf-text-primary-v2;
}

.table-toolbar-builder-body {
  min-width: 0;
}

.table-toolbar-icon-button {
  width: 32px;
  height: 32px;
  padding: 0;
}
</style>
