<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import {
  ListFilterPopover,
  TableToolbarButton
} from '@/components/crmwolf'
import JourneySearch from '@/components/crmwolf/DataTableSearch.vue'
import ListAdvancedTools from '@/components/crmwolf/ListAdvancedTools.vue'
import { projectListFieldCatalog } from '@/components/crmwolf/listFieldCatalog'
import type { ViewDisplayMode, ViewPreferenceConfig } from '@/api/viewPreference'
import type { ListFieldDefinition } from '@/components/crmwolf/listFieldCatalog'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'
import type { ColumnConfigOption } from '@/components/crmwolf/columnConfigTypes'


interface Props {
  fields: ListFieldDefinition[]
  filters: ListFilterCondition[]
  sorts: ListSortCondition[]
  columns: ViewPreferenceConfig['columns']
  search: string
  displayMode: ViewDisplayMode
  loading?: boolean
  saving?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  saving: false
})

const emit = defineEmits<{
  'update:search': [value: string]
  'search-apply': [value: string]
  'search-clear': []
  'update:filters': [value: ListFilterCondition[]]
  'filter-apply': [value: ListFilterCondition[]]
  'filter-reset': []
  'filter-save-view': [value: ListFilterCondition[]]
  'update:sorts': [value: ListSortCondition[]]
  'sort-apply': [value: ListSortCondition[]]
  'sort-reset': []
  'column-config-save': [value: ViewPreferenceConfig]
  'column-config-reset': []
  'update:view-display-mode': [value: ViewDisplayMode]
  'save-current-view': []
  refresh: []
}>()

const projected = computed(() => projectListFieldCatalog(props.fields))
const draftColumns = ref<ColumnConfigOption[]>([])

watch([projected, (): ViewPreferenceConfig['columns'] => props.columns], ([value, preferences]): void => {
  const preferenceByKey = new Map(preferences.map(preference => [preference.key, preference]))
  draftColumns.value = value.columns
    .map((column, index) => {
      const preference = preferenceByKey.get(column.key)
      return {
        ...column,
        order: preference?.order ?? index,
        visible: preference?.visible ?? column.visible !== false,
        fixed: preference?.fixed ?? column.fixed,
        configurable: column.configurable !== false,
        hideable: column.hideable !== false
      }
    })
    .sort((left, right) => (left.order ?? 0) - (right.order ?? 0))
}, { immediate: true })

function handleColumnConfigSave(): void {
  emit('column-config-save', {
    version: 1,
    columns: draftColumns.value.map((column, index) => ({
      key: column.key,
      order: index * 10,
      visible: column.visible
    }))
  })
}
</script>

<template>
  <div class="business-journey-list-tools" aria-label="业务旅程列表工具栏">
    <JourneySearch
      :model-value="search"
      placeholder="搜索旅程、客户或商机"
      :loading="loading ?? false"
      @update:model-value="emit('update:search', $event)"
      @search="emit('search-apply', $event)"
      @clear="emit('search-clear')"
    />
    <ListFilterPopover
      :model-value="filters"
      :fields="projected.filterFields"
      save-view-enabled
      :save-view-loading="saving ?? false"
      @update:model-value="emit('update:filters', $event)"
      @apply="emit('filter-apply', $event)"
      @reset="emit('filter-reset')"
      @save-view="emit('filter-save-view', $event)"
    />
    <ListAdvancedTools
      :sorts="sorts"
      :sort-fields="projected.sortFields"
      :columns="draftColumns"
      column-config-enabled
      :column-config-loading="false"
      :column-config-saving="false"
      :column-config-active="columns.length > 0"
      :column-config-active-count="columns.filter(column => column.visible === false).length"
      column-config-scope="personal"
      column-preference-mode="custom"
      :view-display-mode="displayMode"
      view-display-mode-enabled
      view-config-trigger-label="视图配置"
      view-config-panel-title="视图配置"
      can-save-current-view
      :view-save-loading="saving ?? false"
      @update:sorts="emit('update:sorts', $event)"
      @sort-apply="emit('sort-apply', $event)"
      @sort-reset="emit('sort-reset')"
      @column-config-change="draftColumns = $event"
      @column-config-save="handleColumnConfigSave"
      @column-config-reset="emit('column-config-reset')"
      @update:view-display-mode="emit('update:view-display-mode', $event)"
      @save-current-view="emit('save-current-view')"
    />
    <TableToolbarButton :disabled="loading" aria-label="刷新业务旅程" @click="emit('refresh')">
      <RefreshCw class="refresh-icon" :class="{ spinning: loading }" aria-hidden="true" />
      刷新
    </TableToolbarButton>
  </div>
</template>

<style scoped>
.business-journey-list-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.refresh-icon {
  width: 14px;
  height: 14px;
}

.spinning {
  animation: business-journey-spin 0.8s linear infinite;
}

@keyframes business-journey-spin {
  to { transform: rotate(360deg); }
}
</style>
