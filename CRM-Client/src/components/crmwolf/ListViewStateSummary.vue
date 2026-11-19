<script setup lang="ts">
import { computed } from 'vue'
import { X, RotateCw } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import type { FeedbackError } from '@/types/feedback'
import type { FilterSummaryItem, SortSummaryItem } from './listViewState'

const props = withDefaults(defineProps<{
  filters: FilterSummaryItem[]
  sorts: SortSummaryItem[]
  hiddenColumnCount: number
  applying?: boolean
  applyError?: FeedbackError | null
  saveViewEnabled?: boolean
  saveViewLoading?: boolean
  showSorts?: boolean
  showHiddenColumns?: boolean
  clearScope?: 'all' | 'filters' | 'filters-and-sorts'
}>(), {
  applying: false,
  applyError: null,
  saveViewEnabled: false,
  saveViewLoading: false,
  showSorts: true,
  showHiddenColumns: true,
  clearScope: 'all',
})

const showClear = computed(() => {
  if (props.clearScope === 'filters') return props.filters.length > 0
  if (props.clearScope === 'filters-and-sorts') return props.filters.length > 0 || props.sorts.length > 0
  return props.filters.length > 0 || props.sorts.length > 0 || props.hiddenColumnCount > 0
})

const showSave = computed(() =>
  props.saveViewEnabled && (props.filters.length > 0 || props.sorts.length > 0 || props.hiddenColumnCount > 0)
)

const emit = defineEmits<{
  'remove-filter': [id: string]
  'clear-filters': []
  'save-view': []
  'retry-view-apply': []
}>()

function getFilterSummaryTitle(filter: FilterSummaryItem): string {
  return filter.valueLabel !== null && filter.valueLabel !== ''
    ? `${filter.fieldLabel} ${filter.operatorLabel} “${filter.valueLabel}”`
    : `${filter.fieldLabel} ${filter.operatorLabel}`
}
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
          :title="getFilterSummaryTitle(filter)"
          :aria-label="getFilterSummaryTitle(filter)"
          role="group"
          tabindex="0"
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
      </div>

      <div class="list-view-state-summary-secondary">
        <span v-if="showSorts && sorts.length > 0" class="list-view-state-summary-meta">
          排序：{{ sorts[0]?.fieldLabel }} {{ sorts[0]?.direction === 'asc' ? '↑' : '↓' }}
          <span v-if="sorts.length > 1">+{{ sorts.length - 1 }}</span>
        </span>
        <span v-if="showHiddenColumns && hiddenColumnCount > 0" class="list-view-state-summary-meta">
          已隐藏 {{ hiddenColumnCount }} 列
        </span>
        <Button
          v-if="showClear"
          type="button"
          variant="ghost"
          size="sm"
          class="list-view-state-summary-clear"
          @click="emit('clear-filters')"
        >
          清除筛选
        </Button>
        <Button
          v-if="showSave"
          type="button"
          variant="ghost"
          size="sm"
          class="list-view-state-summary-save"
          :disabled="saveViewLoading"
          @click="emit('save-view')"
        >
          另存为视图
        </Button>
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
@use '@/styles/tokens.scss' as *;

.list-view-state-summary {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: $space-1;
  padding: 0 12px;
  border-bottom: 1px solid hsl(var(--border));
  background: hsl(var(--card));
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-body);
  flex-shrink: 0;
}

.list-view-state-summary-main {
  display: flex;
  min-width: 0;
  min-height: var(--touch-target);
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

.list-view-state-summary-filters {
  min-height: var(--touch-target);
}

.list-view-state-summary-muted {
  color: hsl(var(--muted-foreground));
}

.list-view-state-summary-filter {
  position: relative;
  display: inline-flex;
  min-height: var(--touch-target);
  max-width: min(360px, 100%);
  align-items: center;
  gap: 0;
  padding: 0 8px;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
}

.list-view-state-summary-filter::before {
  position: absolute;
  inset: 7px 0;
  border: 1px solid hsl(var(--border));
  border-radius: var(--radius-md);
  background: hsl(var(--muted));
  pointer-events: none;
  content: '';
}

.list-view-state-summary-filter > * {
  position: relative;
}

.list-view-state-summary-filter > span {
  overflow: hidden;
  text-overflow: ellipsis;
}

.list-view-state-summary-filter:focus-visible {
  outline: 2px solid hsl(var(--ring) / 0.5);
  outline-offset: 2px;
}

.list-view-state-summary-value {
  color: hsl(var(--foreground));
}

.list-view-state-summary-remove {
  position: absolute;
  top: 50%;
  right: 0;
  z-index: 1;
  display: inline-flex;
  width: var(--touch-target);
  height: var(--touch-target);
  min-width: var(--touch-target);
  min-height: var(--touch-target);
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: hsl(var(--muted-foreground));
  cursor: pointer;
  transition: none;
  opacity: 0;
  overflow: hidden;
  pointer-events: none;
  transform: translateY(-50%);
  visibility: visible;
}

.list-view-state-summary-filter:hover .list-view-state-summary-remove,
.list-view-state-summary-filter:focus-within .list-view-state-summary-remove {
  opacity: 1;
  pointer-events: auto;
  visibility: visible;
}

.list-view-state-summary-remove::before {
  position: absolute;
  inset: 7px 1px 7px 0;
  border-radius: 0 var(--radius-md) var(--radius-md) 0;
  background: hsl(var(--muted));
  content: '';
  pointer-events: none;
}

.list-view-state-summary-remove > * {
  position: relative;
  z-index: 1;
}

.list-view-state-summary-remove:hover,
.list-view-state-summary-remove:focus-visible {
  color: hsl(var(--foreground));
}

.list-view-state-summary-remove:hover::before,
.list-view-state-summary-remove:focus-visible::before {
  background: var(--wash-hover);
}

.list-view-state-summary-remove:focus-visible {
  outline: 2px solid hsl(var(--ring) / 0.5);
  outline-offset: 2px;
}

.list-view-state-summary-clear,
.list-view-state-summary-save {
  height: 28px;
  padding-inline: 6px;
  color: hsl(var(--brand));
}

.list-view-state-summary-secondary {
  color: hsl(var(--muted-foreground));
}

.list-view-state-summary-meta {
  white-space: nowrap;
}

.list-view-state-summary-feedback {
  color: hsl(var(--muted-foreground));
}

.list-view-state-summary-applying {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.list-view-state-summary-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid hsl(var(--border));
  border-top-color: hsl(var(--brand));
  border-radius: 50%;
  animation: list-view-state-summary-spin 700ms linear infinite;
}

.list-view-state-summary-error {
  width: 100%;
  justify-content: space-between;
  gap: $space-2;
  color: hsl(var(--status-danger));
}

@keyframes list-view-state-summary-spin {
  to { transform: rotate(360deg); }
}

@media (max-width: $bp-sm - 1) {
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

  .list-view-state-summary-filter .list-view-state-summary-remove {
    width: var(--touch-target);
    min-width: var(--touch-target);
    opacity: 1;
    pointer-events: auto;
    visibility: visible;
  }
}

@media (prefers-reduced-motion: reduce) {
  .list-view-state-summary-spinner {
    animation-duration: 0.01ms;
  }
}
</style>
