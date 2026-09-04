<script setup lang="ts">
import { X, RotateCw } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import type { FeedbackError } from '@/types/feedback'
import type { FilterSummaryItem, SortSummaryItem } from './listViewState'

withDefaults(defineProps<{
  filters: FilterSummaryItem[]
  sorts: SortSummaryItem[]
  hiddenColumnCount: number
  applying?: boolean
  applyError?: FeedbackError | null
}>(), {
  applying: false,
  applyError: null,
})

const emit = defineEmits<{
  'remove-filter': [id: string]
  'clear-filters': []
  'retry-view-apply': []
}>()
</script>

<template>
  <section class="list-view-state-summary" aria-label="当前列表状态">
    <div class="list-view-state-summary-main">
      <div class="list-view-state-summary-filters" aria-live="polite">
        <span v-if="filters.length === 0" class="list-view-state-summary-muted">
          无额外筛选
        </span>
        <span
          v-for="filter in filters"
          :key="filter.id"
          class="list-view-state-summary-filter"
        >
          <span>{{ filter.fieldLabel }} {{ filter.operatorLabel }}</span>
          <span v-if="filter.valueLabel" class="list-view-state-summary-value">“{{ filter.valueLabel }}”</span>
          <button
            v-if="filter.removable"
            type="button"
            class="list-view-state-summary-remove"
            :aria-label="`移除筛选：${filter.fieldLabel}`"
            @click="emit('remove-filter', filter.id)"
          >
            <X class="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </span>
        <Button
          v-if="filters.length > 0"
          type="button"
          variant="ghost"
          size="sm"
          class="list-view-state-summary-clear"
          @click="emit('clear-filters')"
        >
          清除筛选
        </Button>
      </div>

      <div class="list-view-state-summary-secondary">
        <span v-if="sorts.length > 0" class="list-view-state-summary-meta">
          排序：{{ sorts[0]?.fieldLabel }} {{ sorts[0]?.direction === 'asc' ? '↑' : '↓' }}
          <span v-if="sorts.length > 1">+{{ sorts.length - 1 }}</span>
        </span>
        <span v-if="hiddenColumnCount > 0" class="list-view-state-summary-meta">
          已隐藏 {{ hiddenColumnCount }} 列
        </span>
      </div>
    </div>

    <div v-if="applying || applyError" class="list-view-state-summary-feedback">
      <span v-if="applying" class="list-view-state-summary-applying" aria-live="polite">
        <span class="list-view-state-summary-spinner" aria-hidden="true" />
        正在应用视图…
      </span>
      <div v-else-if="applyError" class="list-view-state-summary-error" role="alert">
        <span>{{ applyError.description || applyError.title || '视图应用失败' }}</span>
        <Button
          v-if="applyError.retryable !== false"
          type="button"
          variant="outline"
          size="sm"
          @click="emit('retry-view-apply')"
        >
          <RotateCw class="h-3.5 w-3.5" aria-hidden="true" />
          重试
        </Button>
      </div>
    </div>
  </section>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.list-view-state-summary {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  padding: 8px 12px;
  border-bottom: 1px solid $wolf-border-light-v2;
  background: $wolf-bg-card-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-auxiliary-v2;
  flex-shrink: 0;
}

.list-view-state-summary-main {
  display: flex;
  min-width: 0;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 12px;
}

.list-view-state-summary-filters,
.list-view-state-summary-secondary,
.list-view-state-summary-feedback,
.list-view-state-summary-error {
  display: flex;
  min-width: 0;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}


.list-view-state-summary-muted {
  color: $wolf-text-tertiary-v2;
}


.list-view-state-summary-filter {
  display: inline-flex;
  max-width: min(360px, 100%);
  align-items: center;
  gap: 4px;
  padding: 3px 5px 3px 8px;
  border: 1px solid $wolf-border-light-v2;
  border-radius: $wolf-radius-control-v2;
  background: $wolf-bg-muted-v2;
  color: $wolf-text-secondary-v2;
  white-space: nowrap;
}

.list-view-state-summary-filter > span {
  overflow: hidden;
  text-overflow: ellipsis;
}

.list-view-state-summary-value {
  color: $wolf-text-primary-v2;
}

.list-view-state-summary-remove {
  display: inline-flex;
  min-width: 22px;
  min-height: 22px;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: $wolf-text-tertiary-v2;
  cursor: pointer;
}

.list-view-state-summary-remove:hover,
.list-view-state-summary-remove:focus-visible {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-primary-v2;
}

.list-view-state-summary-remove:focus-visible {
  outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
  outline-offset: $wolf-focus-ring-offset-v2;
}

.list-view-state-summary-clear {
  height: 28px;
  padding-inline: 6px;
  color: $wolf-primary-v2;
}

.list-view-state-summary-secondary {
  color: $wolf-text-tertiary-v2;
}

.list-view-state-summary-meta {
  white-space: nowrap;
}

.list-view-state-summary-feedback {
  color: $wolf-text-tertiary-v2;
}

.list-view-state-summary-applying {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.list-view-state-summary-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid $wolf-border-light-v2;
  border-top-color: $wolf-primary-v2;
  border-radius: 50%;
  animation: list-view-state-summary-spin 700ms linear infinite;
}

.list-view-state-summary-error {
  width: 100%;
  justify-content: space-between;
  gap: $wolf-space-sm-v2;
  color: $wolf-danger-v2;
}

@keyframes list-view-state-summary-spin {
  to { transform: rotate(360deg); }
}

@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .list-view-state-summary {
    padding-inline: 0;
  }

  .list-view-state-summary-main {
    align-items: flex-start;
    flex-direction: column;
    gap: 6px;
  }

  .list-view-state-summary-filters {
    width: 100%;
  }

  .list-view-state-summary-filter {
    max-width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .list-view-state-summary-spinner {
    animation-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>
