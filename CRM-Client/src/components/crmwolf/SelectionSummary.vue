<script setup lang="ts">
import { computed } from 'vue'
import { ChevronDown } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Skeleton } from '@/components/ui/skeleton'

export interface SummaryItem {
  key?: string
  label: string
  value: string | number | null | undefined
}

interface Props {
  items: SummaryItem[]
  details?: SummaryItem[]
  variant?: 'default' | 'compact'
  detailsLabel?: string
  placeholder?: string
  loading?: boolean
  loadingCount?: number
  loadingDetails?: boolean
  loadingLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  details: () => [],
  variant: 'default',
  detailsLabel: '详情',
  placeholder: '-',
  loading: false,
  loadingCount: 0,
  loadingDetails: false,
  loadingLabel: '加载中',
})

const normalizedDetails = computed(() => props.details.filter(item =>
  item.value !== null && item.value !== undefined && String(item.value).trim() !== '',
))
const skeletonCount = computed(() => Math.max(
  1,
  props.loadingCount > 0 ? props.loadingCount : props.items.length,
))
</script>

<template>
  <div
    class="selection-summary"
    :class="variant === 'compact' ? 'selection-summary--compact' : undefined"
    :role="loading ? 'status' : undefined"
    :aria-live="loading ? 'polite' : undefined"
    :aria-busy="loading ? 'true' : undefined"
    :aria-label="loading ? loadingLabel : undefined"
  >
    <div v-if="loading" class="selection-summary__items" aria-hidden="true">
      <div
        v-for="i in skeletonCount"
        :key="`skeleton-${i}`"
        class="selection-summary__item"
      >
        <Skeleton class="selection-summary__skeleton-label" />
        <Skeleton class="selection-summary__skeleton-value" />
      </div>
    </div>

    <Skeleton
      v-if="loading && loadingDetails"
      class="selection-summary__skeleton-details"
      aria-hidden="true"
    />

    <template v-if="!loading">
      <div class="selection-summary__items">
        <div
          v-for="item in items"
          :key="item.key ?? item.label"
          class="selection-summary__item"
        >
          <span>{{ item.label }}</span>
          <strong>
            <slot
              :name="`value-${item.key ?? item.label}`"
              :item="item"
            >
              {{ item.value ?? placeholder }}
            </slot>
          </strong>
        </div>
      </div>

      <Collapsible
        v-if="normalizedDetails.length > 0"
        class="selection-summary__details"
      >
        <CollapsibleTrigger as-child>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            class="selection-summary__details-trigger"
          >
            {{ detailsLabel }}
            <ChevronDown class="selection-summary__details-icon" aria-hidden="true" />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div class="selection-summary__detail-items">
            <div
              v-for="item in normalizedDetails"
              :key="item.key ?? item.label"
              class="selection-summary__item"
            >
              <span>{{ item.label }}</span>
              <strong>
                <slot
                  :name="`value-${item.key ?? item.label}`"
                  :item="item"
                >
                  {{ item.value ?? placeholder }}
                </slot>
              </strong>
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </template>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.selection-summary {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  padding: $wolf-space-md-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-bg-muted-v2;
}

.selection-summary__items,
.selection-summary__detail-items {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $wolf-space-xs-v2 $wolf-space-md-v2;
}

.selection-summary__item {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 2px;

  span {
    color: $wolf-text-tertiary-v2;
    font-size: $wolf-font-size-caption-v2;
  }

  strong {
    overflow: hidden;
    color: $wolf-text-primary-v2;
    font-size: $wolf-font-size-body-v2;
    font-weight: $wolf-font-weight-medium-v2;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.selection-summary--compact {
  gap: $wolf-space-xs-v2;
  padding: $wolf-space-md-v2;

  .selection-summary__items {
    gap: $wolf-space-sm-v2 $wolf-form-item-gap-v2;
  }

  .selection-summary__item {
    gap: $wolf-space-xs-v2;

    span {
      font-size: $wolf-font-size-caption-v2;
      line-height: $wolf-line-height-body-v2;
    }

    strong {
      font-size: $wolf-font-size-body-v2;
      line-height: $wolf-line-height-body-v2;
    }
  }
}

.selection-summary__skeleton-label,
.selection-summary__skeleton-value,
.selection-summary__skeleton-details {
  background-clip: content-box;
}

.selection-summary__skeleton-label {
  width: 42%;
  height: 18px;
  padding-block: 3px;
}

.selection-summary__skeleton-value {
  width: 72%;
  height: 21px;
  padding-block: 3px 4px;
}

.selection-summary__skeleton-details {
  width: 72px;
  height: 36px;
  padding-block: 12px;
}

.selection-summary__details {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.selection-summary__details-trigger {
  align-self: flex-start;
  min-height: 36px;
  padding: 0 $wolf-space-xs-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
}

.selection-summary__details-icon {
  width: 14px;
  height: 14px;
  transition: transform 150ms ease;
}

.selection-summary__details-trigger[aria-expanded='true'] .selection-summary__details-icon {
  transform: rotate(180deg);
}

.selection-summary__detail-items {
  padding-top: $wolf-space-xs-v2;
  border-top: 1px solid $wolf-border-divider-v2;
}

@media (max-width: $wolf-breakpoint-sm-v2) {
  .selection-summary__items,
  .selection-summary__detail-items {
    grid-template-columns: 1fr;
  }
}
</style>
