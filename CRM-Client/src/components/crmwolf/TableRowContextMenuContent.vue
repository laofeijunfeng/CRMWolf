<script setup lang="ts">
import { computed } from 'vue'
import {
  ContextMenuItem,
  ContextMenuLabel,
  ContextMenuSeparator
} from '@/components/ui/context-menu'
import type { ActionConfig } from './tableRowActionTypes'
import {
  groupTableRowActions,
  shouldShowTableRowActionGroupLabels,
  type TableRowActionSet
} from './tableRowActionGroups'

const props = defineProps<{
  row: Record<string, unknown>
  actions: TableRowActionSet
}>()

const groups = computed(() => groupTableRowActions(props.actions))
const showGroupLabels = computed(() => shouldShowTableRowActionGroupLabels(groups.value))

function getActionLabel(action: ActionConfig): string {
  if (action.disabledReason === undefined || action.disabledReason.trim() === '') return action.label
  return `${action.label}（${action.disabledReason}）`
}

function executeAction(action: ActionConfig): void {
  if (action.disabled === true) return
  action.handler(props.row)
}
</script>

<template>
  <template v-for="(group, groupIndex) in groups" :key="group.key">
    <ContextMenuSeparator v-if="groupIndex > 0" />
    <ContextMenuLabel v-if="showGroupLabels" class="table-row-context-menu-label">
      {{ group.label }}
    </ContextMenuLabel>
    <ContextMenuItem
      v-for="(action, actionIndex) in group.items"
      :key="`${group.key}-${action.label}-${actionIndex}`"
      :disabled="action.disabled === true"
      :class="['table-row-context-menu-item', { 'is-destructive': action.destructive === true }]"
      :title="getActionLabel(action)"
      :aria-label="getActionLabel(action)"
      @select="executeAction(action)"
    >
      <component :is="action.icon" v-if="action.icon" class="table-row-context-menu-icon" aria-hidden="true" />
      {{ action.label }}
    </ContextMenuItem>
  </template>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.table-row-context-menu-label {
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  color: $wolf-text-tertiary-v2;
}

.table-row-context-menu-item {
  gap: $wolf-space-sm-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  color: $wolf-text-primary-v2;
  cursor: pointer;

  &.is-destructive {
    color: $wolf-danger-text-v2;
  }
}

.table-row-context-menu-icon {
  width: 16px;
  height: 16px;
}
</style>
