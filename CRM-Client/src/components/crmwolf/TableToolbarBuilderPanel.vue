<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'

defineProps<{
  title: string
  subtitle?: string
}>()

const emit = defineEmits<{
  close: []
}>()
</script>

<template>
  <div class="table-toolbar-builder">
    <div class="table-toolbar-builder-header">
      <div class="table-toolbar-builder-heading">
        <span class="table-toolbar-builder-title">{{ title }}</span>
        <span v-if="subtitle" class="table-toolbar-builder-subtitle">{{ subtitle }}</span>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label="关闭"
        @click="emit('close')"
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
  gap: $wolf-space-md-v2;
  padding: $wolf-space-md-v2;
}

.table-toolbar-builder-header,
.table-toolbar-builder-footer {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: $wolf-space-sm-v2;
}

.table-toolbar-builder-footer {
  align-items: center;
}

.table-toolbar-builder-heading {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.table-toolbar-builder-title {
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
}

.table-toolbar-builder-subtitle {
  margin-top: 2px;
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
}

.table-toolbar-builder-body {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: $wolf-space-md-v2;
}
</style>
