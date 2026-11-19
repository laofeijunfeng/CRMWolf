<script setup lang="ts">
import { computed } from 'vue'
import {
  ContextMenuItem,
  ContextMenuLabel,
  ContextMenuSeparator
} from '@/components/ui/context-menu'
import type { ActionConfig } from './tableRowActionTypes'
import {
  getTableRowActionKey,
  getTableRowActionLabel,
  isDestructiveTableRowAction,
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
      :key="`${group.key}-${getTableRowActionKey(action, actionIndex)}`"
      :disabled="action.disabled === true"
      :class="['table-row-context-menu-item', { 'is-destructive': isDestructiveTableRowAction(action) }]"
      :title="getTableRowActionLabel(action)"
      :aria-label="getTableRowActionLabel(action)"
      @select="executeAction(action)"
    >
      <component :is="action.icon" v-if="action.icon" class="table-row-context-menu-icon" aria-hidden="true" />
      {{ action.label }}
    </ContextMenuItem>
  </template>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.table-row-context-menu-label {
  font-size: 12px;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
}

.table-row-context-menu-item {
  gap: $space-2;
  font-size: 14px;
  font-weight: 500;
  color: hsl(var(--foreground));
  cursor: pointer;

  &.is-destructive {
    color: hsl(var(--status-danger));
  }
}

.table-row-context-menu-icon {
  width: 16px;
  height: 16px;
}
</style>
