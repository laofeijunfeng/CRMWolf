<script setup lang="ts">
/**
 * DesktopTableRowActions - 桌面 DataTable 行操作
 *
 * 桌面端只显示当前业务上下文下的 1～2 个主操作，其余操作统一收进
 * 可发现的“更多”菜单。右键菜单仍然保留，作为熟练用户的快捷入口。
 */
import { computed } from 'vue'
import { MoreHorizontal } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import type { ActionConfig } from './tableRowActionTypes'
import {
  getTableRowActionKey,
  getTableRowActionLabel,
  isDestructiveTableRowAction,
  getDesktopTableRowActions,
  shouldShowTableRowActionGroupLabels,
  type TableRowActionSet
} from './tableRowActionGroups'

defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<{
  row: Record<string, unknown>
  actions: TableRowActionSet | null | undefined
}>(), {})

const desktopActions = computed(() => getDesktopTableRowActions(props.actions))
const showGroupLabels = computed(() => shouldShowTableRowActionGroupLabels(desktopActions.value.groups))
const hasMenuActions = computed(() => desktopActions.value.menuGroups.length > 0)

function executeAction(event: Event, action: ActionConfig): void {
  // Stop at the action itself before running user code. The action cell lives
  // inside an interactive table row, so row-level navigation must never observe
  // this event, even when the handler changes reactive state synchronously.
  event.stopPropagation()
  if (action.disabled === true) return
  action.handler(props.row)
}
</script>

<template>
  <div
    v-if="desktopActions.primaryActions.length > 0 || hasMenuActions"
    class="desktop-table-row-actions"
    @click.stop
    @keydown.stop
  >
    <Button
      v-for="(action, actionIndex) in desktopActions.primaryActions"
      :key="getTableRowActionKey(action, actionIndex)"
      type="button"
      variant="ghost"
      size="sm"
      class="desktop-table-row-action"
      :disabled="action.disabled === true"
      :class="{ 'is-destructive': isDestructiveTableRowAction(action) }"
      :aria-label="getTableRowActionLabel(action)"
      :title="getTableRowActionLabel(action)"
      @click="executeAction($event, action)"
    >
      <component :is="action.icon" v-if="action.icon" class="desktop-table-row-action-icon" aria-hidden="true" />
      <span>{{ action.label }}</span>
    </Button>

    <DropdownMenu v-if="hasMenuActions">
      <DropdownMenuTrigger as-child>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          class="desktop-table-row-more"
          aria-label="更多操作"
          title="更多操作"
        >
          <MoreHorizontal class="desktop-table-row-more-icon" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" class="desktop-table-row-menu">
        <template v-for="(group, groupIndex) in desktopActions.menuGroups" :key="group.key">
          <DropdownMenuSeparator v-if="groupIndex > 0" />
          <DropdownMenuLabel v-if="showGroupLabels" class="desktop-table-row-menu-label">
            {{ group.label }}
          </DropdownMenuLabel>
          <DropdownMenuItem
            v-for="(action, actionIndex) in group.items"
            :key="`${group.key}-${getTableRowActionKey(action, actionIndex)}`"
            :disabled="action.disabled === true"
            :class="{ 'is-destructive': isDestructiveTableRowAction(action) }"
            :title="getTableRowActionLabel(action)"
            :aria-label="getTableRowActionLabel(action)"
            @select="executeAction($event, action)"
          >
            <component :is="action.icon" v-if="action.icon" class="desktop-table-row-menu-icon" aria-hidden="true" />
            {{ action.label }}
          </DropdownMenuItem>
        </template>
      </DropdownMenuContent>
    </DropdownMenu>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.desktop-table-row-actions {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: $wolf-space-xs-v2;
  max-width: 100%;
}

.desktop-table-row-action,
.desktop-table-row-more {
  min-height: $wolf-touch-target-min-v2;
  white-space: nowrap;
}

.desktop-table-row-action {
  max-width: 128px;
  padding-inline: $wolf-space-sm-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;

  &:hover:not(:disabled) {
    background: $wolf-bg-hover-v2;
    color: $wolf-text-primary-v2;
  }

  &:focus-visible,
  &:focus {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }

  &.is-destructive {
    color: $wolf-danger-text-v2;
  }
}

.desktop-table-row-action-icon,
.desktop-table-row-menu-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.desktop-table-row-action-icon {
  margin-right: 4px;
}

.desktop-table-row-more {
  width: $wolf-touch-target-min-v2;
  padding: 0;
  color: $wolf-text-secondary-v2;

  &:hover:not(:disabled) {
    background: $wolf-bg-hover-v2;
    color: $wolf-text-primary-v2;
  }

  &:focus-visible,
  &:focus {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }
}

.desktop-table-row-more-icon {
  width: 18px;
  height: 18px;
}

.desktop-table-row-menu {
  min-width: 180px;
}

.desktop-table-row-menu-label {
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.desktop-table-row-menu :deep([data-slot='dropdown-menu-item'].is-destructive) {
  color: $wolf-danger-text-v2;
}

@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .desktop-table-row-actions {
    display: none;
  }
}
</style>
