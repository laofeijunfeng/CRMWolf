<script setup lang="ts">
import { computed } from 'vue'
import { Settings2 } from 'lucide-vue-next'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import TableToolbarButton from './TableToolbarButton.vue'
import ListSortPopover from './ListSortPopover.vue'
import ColumnConfigPopover from './ColumnConfigPopover.vue'
import type { ViewPreferenceScope } from '@/api/viewPreference'
import type { ColumnConfigOption } from './columnConfigTypes'
import type { ListSortCondition, ListSortField } from './listSortTypes'

const props = defineProps<{
  sorts: ListSortCondition[]
  sortFields: ListSortField[]
  columns: ColumnConfigOption[]
  columnConfigEnabled: boolean
  columnConfigActive: boolean
  columnConfigActiveCount: number
  columnConfigScope: ViewPreferenceScope
  columnPreferenceMode: 'default' | 'custom'
  columnConfigLoading: boolean
  columnConfigSaving: boolean
}>()

const emit = defineEmits<{
  'update:sorts': [value: ListSortCondition[]]
  'sort-apply': [value: ListSortCondition[]]
  'sort-reset': []
  'column-config-change': [value: ColumnConfigOption[]]
  'column-config-save': [value: ViewPreferenceScope]
  'column-config-reset': []
}>()

const advancedToolsAriaLabel = computed(() => {
  const parts: string[] = ['更多列表设置']
  if (props.sorts.length > 0) parts.push(`排序 ${props.sorts.length} 项`)
  if (props.columnConfigActiveCount > 0) parts.push(`已隐藏 ${props.columnConfigActiveCount} 列`)
  return parts.join('，')
})
</script>

<template>
  <Popover>
    <PopoverTrigger as-child>
      <TableToolbarButton
        :active="sorts.length > 0 || columnConfigActive || columnConfigActiveCount > 0"
        :count="sorts.length + columnConfigActiveCount"
        :aria-label="advancedToolsAriaLabel"
      >
        <Settings2 class="h-4 w-4" aria-hidden="true" />
        <span>更多设置</span>
      </TableToolbarButton>
    </PopoverTrigger>
    <PopoverContent align="start" class="list-advanced-tools-popover">
      <div class="list-advanced-tools-panel">
        <div class="list-advanced-tools-heading">列表设置</div>
        <div class="list-advanced-tools-items">
          <ListSortPopover
            v-if="sortFields.length > 0"
            :model-value="sorts"
            :fields="sortFields"
            @update:model-value="emit('update:sorts', $event)"
            @apply="emit('sort-apply', $event)"
            @reset="emit('sort-reset')"
          />
          <ColumnConfigPopover
            v-if="columnConfigEnabled"
            :columns="columns"
            :active="columnConfigActive"
            :active-count="columnConfigActiveCount"
            :scope="columnConfigScope"
            :scope-editable="columnPreferenceMode === 'default'"
            :loading="columnConfigLoading"
            :saving="columnConfigSaving"
            @change="emit('column-config-change', $event)"
            @save="emit('column-config-save', $event)"
            @reset="emit('column-config-reset')"
          />
        </div>
      </div>
    </PopoverContent>
  </Popover>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.list-advanced-tools-popover {
  width: auto;
  min-width: 180px;
  padding: 8px;
}

.list-advanced-tools-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.list-advanced-tools-heading {
  padding: 4px 8px;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
}

.list-advanced-tools-items {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.list-advanced-tools-items :deep(.table-toolbar-button) {
  width: 100%;
  justify-content: flex-start;
}
</style>
