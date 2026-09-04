<script setup lang="ts">
import { computed, type HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'
import ErrorState from '@/components/ErrorState.vue'
import { Button } from '@/components/ui/button'
import LoadingSkeleton from './LoadingSkeleton.vue'
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from '@/components/ui/empty'

export type DataViewState = 'loading' | 'error' | 'empty' | 'ready'

interface Props {
  /** 当前读取状态；ready 状态渲染默认 slot。 */
  state: DataViewState
  /** 外层样式，不能覆盖页面的滚动容器。 */
  class?: HTMLAttributes['class']
  /** 默认加载骨架的类型。 */
  loadingType?: 'list' | 'card' | 'table'
  loadingRows?: number
  errorTitle?: string
  errorDescription?: string
  emptyTitle?: string
  emptyDescription?: string
}

const props = withDefaults(defineProps<Props>(), {
  class: undefined,
  loadingType: 'card',
  loadingRows: 3,
  errorTitle: '加载失败',
  errorDescription: '请检查网络连接后重试。',
  emptyTitle: '暂无数据',
  emptyDescription: '',
})

const loadingType = computed(() => props.loadingType ?? 'card')
const loadingRows = computed(() => props.loadingRows ?? 3)
const errorTitle = computed(() => props.errorTitle ?? '加载失败')
const errorDescription = computed(() => props.errorDescription ?? '请检查网络连接后重试。')
const emptyTitle = computed(() => props.emptyTitle ?? '暂无数据')
const emptyDescription = computed(() => props.emptyDescription ?? '')

const emit = defineEmits<{
  retry: []
}>()
</script>

<template>
  <div :class="cn('data-view-state-panel', props.class)">
    <div
      v-if="state === 'loading'"
      class="data-view-state-panel__loading"
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label="加载中"
    >
      <slot name="loading">
        <LoadingSkeleton :type="loadingType" :rows="loadingRows" :announce="false" aria-hidden="true" />
      </slot>
    </div>

    <ErrorState
      v-else-if="state === 'error'"
      :title="errorTitle"
      :description="errorDescription"
    >
      <template #action>
        <slot name="error-action">
          <Button type="button" variant="outline" @click="emit('retry')">
            重新加载
          </Button>
        </slot>
      </template>
    </ErrorState>

    <Empty
      v-else-if="state === 'empty'"
      class="data-view-state-panel__empty"
      role="status"
      aria-live="polite"
    >
      <EmptyHeader>
        <EmptyTitle>{{ emptyTitle }}</EmptyTitle>
        <EmptyDescription v-if="emptyDescription">
          {{ emptyDescription }}
        </EmptyDescription>
      </EmptyHeader>
      <div v-if="$slots['empty-action']" class="flex items-center justify-center gap-2">
        <slot name="empty-action" />
      </div>
    </Empty>

    <slot v-else />
  </div>
</template>

<style scoped>
.data-view-state-panel {
  min-width: 0;
}

.data-view-state-panel__loading {
  min-width: 0;
}

</style>
