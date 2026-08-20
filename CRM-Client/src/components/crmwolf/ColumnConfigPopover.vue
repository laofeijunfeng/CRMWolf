<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Eye, EyeOff, GripVertical, Lock, Settings2, User, Users } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import TableToolbarButton from './TableToolbarButton.vue'
import TableToolbarBuilderPanel from './TableToolbarBuilderPanel.vue'
import type { ViewPreferenceScope } from '@/api/viewPreference'
import type { ColumnConfigOption } from './columnConfigTypes'

const props = withDefaults(defineProps<{
  columns: ColumnConfigOption[]
  active?: boolean
  activeCount?: number
  saving?: boolean
  loading?: boolean
  scope?: ViewPreferenceScope
  scopeEditable?: boolean
}>(), {
  active: false,
  activeCount: 0,
  saving: false,
  loading: false,
  scope: 'personal',
  scopeEditable: true
})

const emit = defineEmits<{
  change: [value: ColumnConfigOption[]]
  save: [scope: ViewPreferenceScope]
  reset: [scope: ViewPreferenceScope]
}>()

const open = ref(false)
const localColumns = ref<ColumnConfigOption[]>([])
const dragKey = ref<string | null>(null)
const selectedScope = ref<ViewPreferenceScope>(props.scope)
const normalizedActiveCount = computed(() => props.activeCount ?? 0)
const isActive = computed(() => props.active || normalizedActiveCount.value > 0)

function cloneColumns(columns: ColumnConfigOption[]): ColumnConfigOption[] {
  return columns.map((column) => ({ ...column }))
}

function publishChange(): void {
  emit('change', cloneColumns(localColumns.value))
}

function handleDragStart(column: ColumnConfigOption): void {
  if (column.configurable !== true) return
  dragKey.value = column.key
}

function handleDrop(targetKey: string): void {
  if (dragKey.value === null || dragKey.value === targetKey) return

  const targetColumn = localColumns.value.find((column) => column.key === targetKey)
  if (targetColumn == null || targetColumn.configurable !== true) return

  const fromIndex = localColumns.value.findIndex((column) => column.key === dragKey.value)
  const toIndex = localColumns.value.findIndex((column) => column.key === targetKey)
  if (fromIndex < 0 || toIndex < 0) return

  const nextColumns = [...localColumns.value]
  const [moved] = nextColumns.splice(fromIndex, 1)
  if (!moved) return
  nextColumns.splice(toIndex, 0, moved)

  localColumns.value = nextColumns
  dragKey.value = null
  publishChange()
}

function updateVisible(columnKey: string, visible: boolean): void {
  localColumns.value = localColumns.value.map((column) => (
    column.key === columnKey ? { ...column, visible } : column
  ))
  publishChange()
}

function handleSave(): void {
  emit('save', selectedScope.value)
}

watch(
  () => props.columns,
  (columns) => {
    localColumns.value = cloneColumns(columns)
  },
  { immediate: true, deep: true }
)

watch(() => props.scope, (scope) => {
  selectedScope.value = scope
})
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <TableToolbarButton :active="isActive" :count="normalizedActiveCount">
        <Settings2 class="w-4 h-4" aria-hidden="true" />
        <span>字段配置</span>
      </TableToolbarButton>
    </PopoverTrigger>

    <PopoverContent align="start" class="column-config-popover">
      <TableToolbarBuilderPanel
        title="字段配置"
        @close="open = false"
      >
        <div v-if="scopeEditable" class="column-config-scope" role="radiogroup" aria-label="保存范围">
          <Button
            type="button"
            size="sm"
            :variant="selectedScope === 'personal' ? 'default' : 'outline'"
            @click="selectedScope = 'personal'"
          >
            <User class="w-4 h-4" aria-hidden="true" />
            <span>仅自己</span>
          </Button>
          <Button
            type="button"
            size="sm"
            :variant="selectedScope === 'team' ? 'default' : 'outline'"
            @click="selectedScope = 'team'"
          >
            <Users class="w-4 h-4" aria-hidden="true" />
            <span>同步团队</span>
          </Button>
        </div>

        <ScrollArea class="column-config-list-scroll">
          <div v-if="loading" class="column-config-state">正在读取配置</div>
          <div v-else class="column-config-list">
            <div
              v-for="column in localColumns"
              :key="column.key"
              class="column-config-row"
              :class="{ 'is-locked': !column.configurable, 'is-hidden': !column.visible }"
              :draggable="column.configurable"
              @dragstart="handleDragStart(column)"
              @dragover.prevent
              @drop="handleDrop(column.key)"
              @dragend="dragKey = null"
            >
              <GripVertical v-if="column.configurable" class="column-config-drag-icon" aria-hidden="true" />
              <Lock v-else class="column-config-lock-icon" aria-hidden="true" />

              <span class="column-config-row-title">{{ column.title }}</span>

              <Button
                v-if="column.hideable"
                type="button"
                variant="ghost"
                size="icon-sm"
                class="column-config-visibility-button"
                :aria-pressed="column.visible"
                :aria-label="column.visible ? `隐藏${column.title}` : `显示${column.title}`"
                @click="updateVisible(column.key, !column.visible)"
              >
                <Eye v-if="column.visible" class="w-4 h-4" aria-hidden="true" />
                <EyeOff v-else class="w-4 h-4" aria-hidden="true" />
              </Button>
              <Lock v-else class="column-config-lock-icon" aria-hidden="true" />
            </div>
          </div>
        </ScrollArea>

        <template #footer>
          <Button type="button" variant="ghost" size="sm" @click="emit('reset', selectedScope)">
            恢复默认
          </Button>
          <Button type="button" size="sm" :disabled="saving" @click="handleSave">
            {{ saving ? '保存中' : '保存' }}
          </Button>
        </template>
      </TableToolbarBuilderPanel>
    </PopoverContent>
  </Popover>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

:global(.column-config-popover) {
  padding: 0;
}

.column-config-scope {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $wolf-space-sm-v2;
}

.column-config-list-scroll {
  height: 320px;
}

.column-config-state {
  padding: $wolf-space-xl-v2;
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-tertiary-v2;
  text-align: center;
}

.column-config-row {
  display: grid;
  grid-template-columns: $wolf-button-height-sm-v2 minmax(0, 1fr) $wolf-button-height-sm-v2;
  align-items: center;
  gap: $wolf-space-sm-v2;
  min-height: $wolf-touch-target-min-v2;
  padding: 0 $wolf-space-sm-v2;
  border-radius: $wolf-radius-v2;
  color: $wolf-text-primary-v2;
  cursor: grab;

  &:hover {
    background: $wolf-bg-muted-v2;
  }

  &.is-locked {
    cursor: default;
    color: $wolf-text-secondary-v2;
  }

  &.is-hidden {
    color: $wolf-text-tertiary-v2;
  }
}

.column-config-drag-icon,
.column-config-lock-icon {
  width: 16px;
  height: 16px;
  color: $wolf-text-tertiary-v2;
  justify-self: center;
}

.column-config-visibility-button {
  justify-self: center;
  color: $wolf-text-tertiary-v2;

  &:hover {
    color: $wolf-text-primary-v2;
  }
}

.column-config-row.is-hidden .column-config-visibility-button {
  color: $wolf-text-tertiary-v2;
}

.column-config-row-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: $wolf-font-size-body-v2;
}
</style>
