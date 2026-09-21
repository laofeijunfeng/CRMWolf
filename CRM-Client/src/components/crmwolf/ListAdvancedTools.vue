<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { Settings2 } from 'lucide-vue-next'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import TableToolbarButton from './TableToolbarButton.vue'
import ListSortPopover from './ListSortPopover.vue'
import ColumnConfigPopover from './ColumnConfigPopover.vue'
import type { ViewDisplayMode, ViewPreferenceScope } from '@/api/viewPreference'
import type { ColumnConfigOption } from './columnConfigTypes'
import type { ListSortCondition, ListSortField } from './listSortTypes'

const props = withDefaults(defineProps<{
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
  viewDisplayMode?: ViewDisplayMode | null
  viewDisplayModeEnabled?: boolean
  viewConfigTriggerLabel?: string
  viewConfigPanelTitle?: string
  canSaveCurrentView?: boolean
  viewSaveLoading?: boolean
}>(), {
  viewDisplayMode: null,
  viewDisplayModeEnabled: false,
  viewConfigTriggerLabel: '字段配置',
  viewConfigPanelTitle: '字段配置',
  canSaveCurrentView: false,
  viewSaveLoading: false,
})

const emit = defineEmits<{
  'update:sorts': [value: ListSortCondition[]]
  'update:view-display-mode': [value: ViewDisplayMode]
  'save-current-view': []
  'sort-apply': [value: ListSortCondition[]]
  'sort-reset': []
  'column-config-change': [value: ColumnConfigOption[]]
  'column-config-save': [value: ViewPreferenceScope]
  'column-config-reset': []
}>()

const isCompactToolbar = useMediaQuery('(width < 768px)')
const moreSettingsOpen = ref(false)
const sortOpen = ref(false)
const columnConfigOpen = ref(false)
const desktopToolsTarget = ref<HTMLElement | null>(null)
const compactToolsTarget = ref<HTMLElement | null>(null)
const parkedToolsTarget = ref<HTMLElement | null>(null)
const preserveChildOpenDuringMove = ref(false)
let toolMoveSequence = 0
const childToolOpen = computed(() => sortOpen.value || columnConfigOpen.value)
const normalizedViewDisplayMode = computed<ViewDisplayMode | null>(() => props.viewDisplayMode ?? null)
const normalizedViewDisplayModeEnabled = computed(() => props.viewDisplayModeEnabled ?? false)
const normalizedViewConfigTriggerLabel = computed(() => props.viewConfigTriggerLabel ?? '字段配置')
const normalizedViewConfigPanelTitle = computed(() => props.viewConfigPanelTitle ?? '字段配置')
const normalizedCanSaveCurrentView = computed(() => props.canSaveCurrentView ?? false)
const normalizedViewSaveLoading = computed(() => props.viewSaveLoading ?? false)
const toolsTarget = computed(() => {
  if (!isCompactToolbar.value) return desktopToolsTarget.value
  if (moreSettingsOpen.value && compactToolsTarget.value !== null) return compactToolsTarget.value
  return parkedToolsTarget.value
})

function handleMoreSettingsOpenChange(open: boolean): void {
  moreSettingsOpen.value = open
  if (!open && isCompactToolbar.value) {
    sortOpen.value = false
    columnConfigOpen.value = false
  }
}

function handleSortOpenChange(open: boolean): void {
  if (!open && preserveChildOpenDuringMove.value) return
  sortOpen.value = open
}

function handleColumnConfigOpenChange(open: boolean): void {
  if (!open && preserveChildOpenDuringMove.value) return
  columnConfigOpen.value = open
}

const advancedToolsAriaLabel = computed(() => {
  const parts: string[] = ['更多列表设置']
  if (props.sorts.length > 0) parts.push(`排序 ${props.sorts.length} 项`)
  if (props.columnConfigActiveCount > 0) parts.push(`已隐藏 ${props.columnConfigActiveCount} 列`)
  return parts.join('，')
})
watch(isCompactToolbar, async (compact) => {
  const sequence = ++toolMoveSequence
  const keepSortOpen = sortOpen.value
  const keepColumnConfigOpen = columnConfigOpen.value
  preserveChildOpenDuringMove.value = keepSortOpen || keepColumnConfigOpen
  moreSettingsOpen.value = compact && childToolOpen.value
  await nextTick()
  await nextTick()
  if (keepSortOpen) sortOpen.value = true
  if (keepColumnConfigOpen) columnConfigOpen.value = true
  setTimeout(() => {
    if (sequence === toolMoveSequence) preserveChildOpenDuringMove.value = false
  }, 0)
})
</script>

<template>
  <div
    ref="desktopToolsTarget"
    class="list-advanced-tools-desktop"
    :class="{ 'is-hidden': isCompactToolbar }"
  />
  <div ref="parkedToolsTarget" class="list-advanced-tools-parking" aria-hidden="true" />

  <Popover
    v-if="isCompactToolbar"
    :open="moreSettingsOpen"
    @update:open="handleMoreSettingsOpenChange"
  >
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
        <div ref="compactToolsTarget" class="list-advanced-tools-items" />
      </div>
    </PopoverContent>
  </Popover>

  <Teleport v-if="toolsTarget !== null" :to="toolsTarget">
    <ListSortPopover
      v-if="sortFields.length > 0"
      :open="sortOpen"
      :model-value="sorts"
      :fields="sortFields"
      @update:open="handleSortOpenChange"
      @update:model-value="emit('update:sorts', $event)"
      @apply="emit('sort-apply', $event)"
      @reset="emit('sort-reset')"
    />
    <ColumnConfigPopover
      v-if="columnConfigEnabled || viewDisplayModeEnabled || canSaveCurrentView"
      :open="columnConfigOpen"
      :columns="columns"
      :active="columnConfigActive"
      :active-count="columnConfigActiveCount"
      :scope="columnConfigScope"
      :scope-editable="columnPreferenceMode === 'default'"
      :loading="columnConfigLoading"
      :saving="columnConfigSaving"
      :view-display-mode="normalizedViewDisplayMode"
      :view-display-mode-enabled="normalizedViewDisplayModeEnabled"
      :view-config-trigger-label="normalizedViewConfigTriggerLabel"
      :view-config-panel-title="normalizedViewConfigPanelTitle"
      :can-save-current-view="normalizedCanSaveCurrentView"
      :view-save-loading="normalizedViewSaveLoading"
      @update:open="handleColumnConfigOpenChange"
      @change="emit('column-config-change', $event)"
      @save="emit('column-config-save', $event)"
      @reset="emit('column-config-reset')"
      @update:view-display-mode="emit('update:view-display-mode', $event)"
      @save-current-view="emit('save-current-view')"
    />
  </Teleport>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.list-advanced-tools-desktop {
  display: contents;
}

.list-advanced-tools-desktop.is-hidden,
.list-advanced-tools-parking {
  display: none;
}

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
