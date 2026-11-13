<script setup lang="ts">
import type { VNode } from 'vue'
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

const props = withDefaults(defineProps<{
  open: boolean
  title?: string
  description?: string
  loading?: boolean
  error?: string | null
  hasItems?: boolean
  hasMore?: boolean
  resetKey?: string | number | undefined
  testIdPrefix?: string
  class?: string | undefined
}>(), {
  title: '',
  description: '',
  resetKey: undefined,
  class: '',
  loading: false,
  error: null,
  hasItems: false,
  hasMore: false,
  testIdPrefix: 'chart-bucket',
})

const emit = defineEmits<{
  'update:open': [open: boolean]
  retry: []
  'load-more': []
}>()

defineSlots<{
  default?: () => VNode[]
  loading?: () => VNode[]
  error?: () => VNode[]
  empty?: () => VNode[]
  items?: () => VNode[]
  'load-more-label'?: () => VNode[]
  footer?: () => VNode[]
}>()

const bodyKey = computed(() => props.resetKey ?? 'chart-bucket-body')

function close(open: boolean): void {
  emit('update:open', open)
}
</script>

<template>
  <Dialog :open="open" @update:open="close">
    <DialogContent :class="['w-[calc(100vw-2rem)] max-w-2xl', props.class]">
      <DialogHeader v-if="title || description">
        <DialogTitle v-if="title">{{ title }}</DialogTitle>
        <DialogDescription v-if="description">{{ description }}</DialogDescription>
      </DialogHeader>
      <div :key="bodyKey" class="chart-bucket-dialog__body">
        <slot v-if="$slots['default']" />
        <template v-else>
          <div v-if="loading && !hasItems" class="chart-bucket-dialog__state" role="status">
            <slot name="loading">正在加载明细…</slot>
          </div>
          <div v-else-if="error && !hasItems" class="chart-bucket-dialog__state" role="alert">
            <slot name="error"><span>{{ error }}</span></slot>
            <Button
              type="button"
              variant="outline"
              size="sm"
              :data-testid="`${testIdPrefix}-retry`"
              class="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              @click="emit('retry')"
            >重试</Button>
          </div>
          <div v-else-if="!hasItems" class="chart-bucket-dialog__state">
            <slot name="empty">暂无明细</slot>
          </div>
          <template v-else>
            <div v-if="error" class="chart-bucket-dialog__inline-error" role="alert">
              <slot name="error"><span>{{ error }}</span></slot>
            </div>
            <div class="chart-bucket-dialog__items"><slot name="items" /></div>
            <Button
              v-if="hasMore"
              type="button"
              variant="outline"
              :loading="loading === true"
              :disabled="loading === true"
              :data-testid="`${testIdPrefix}-load-more`"
              class="chart-bucket-dialog__load-more focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              @click="emit('load-more')"
            >
              <slot name="load-more-label">{{ loading ? '正在读取…' : '查看更多' }}</slot>
            </Button>
          </template>
        </template>
      </div>
      <DialogFooter v-if="$slots['footer']"><slot name="footer" /></DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;


.chart-bucket-dialog__body {
  display: grid;
  min-width: 0;
  max-height: min(55vh, 440px);
  gap: $wolf-space-sm-v2;
  overflow-y: auto;
}

.chart-bucket-dialog__state {
  display: flex;
  min-height: 120px;
  align-items: center;
  justify-content: center;
  gap: $wolf-space-sm-v2;
  color: $wolf-text-tertiary-v2;
  text-align: center;
}

.chart-bucket-dialog__inline-error {
  color: $wolf-danger-text-v2;
}

.chart-bucket-dialog__items {
  min-width: 0;
  max-height: min(55vh, 440px);
  overflow-y: auto;
}

.chart-bucket-dialog__load-more {
  justify-self: center;
}
</style>
