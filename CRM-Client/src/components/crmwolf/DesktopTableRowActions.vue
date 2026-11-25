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
  if (action.disabled === true) {
    event.preventDefault()
    return
  }
  action.handler(props.row)
}

function hasDisabledReason(action: ActionConfig): boolean {
  return action.disabled === true && Boolean(action.disabledReason?.trim())
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
      :disabled="action.disabled === true && !hasDisabledReason(action)"
      :class="{ 'is-destructive': isDestructiveTableRowAction(action), 'has-disabled-reason': hasDisabledReason(action) }"
      :aria-disabled="action.disabled === true ? 'true' : undefined"
      :aria-label="getTableRowActionLabel(action)"
      :title="getTableRowActionLabel(action)"
      @click="executeAction($event, action)"
    >
      <component :is="action.icon" v-if="action.icon" class="desktop-table-row-action-icon" aria-hidden="true" />
      <span class="desktop-table-row-action-copy">
        <span>{{ action.label }}</span>
        <span v-if="hasDisabledReason(action)" class="desktop-table-row-action-reason">{{ action.disabledReason }}</span>
      </span>
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
          <DropdownMenuLabel v-if="showGroupLabels">
            {{ group.label }}
          </DropdownMenuLabel>
          <template v-for="action in group.items" :key="`${group.key}-${getTableRowActionKey(action, group.items.indexOf(action))}`">
            <DropdownMenuItem
              as-child
              :disabled="action.disabled === true && !hasDisabledReason(action)"
              @select="executeAction($event, action)"
            >
              <div
                role="menuitem"
                :aria-disabled="action.disabled === true ? 'true' : undefined"
                :class="{ 'is-destructive': isDestructiveTableRowAction(action), 'has-disabled-reason': hasDisabledReason(action) }"
                :title="getTableRowActionLabel(action)"
                :aria-label="getTableRowActionLabel(action)"
              >
                <component :is="action.icon" v-if="action.icon" aria-hidden="true" />
                <span class="desktop-table-row-menu-copy">
                  <span>{{ action.label }}</span>
                  <span v-if="hasDisabledReason(action)" class="desktop-table-row-menu-reason">{{ action.disabledReason }}</span>
                </span>
              </div>
            </DropdownMenuItem>
          </template>
        </template>
      </DropdownMenuContent>
    </DropdownMenu>

  </div>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.desktop-table-row-actions {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: $space-1;
  max-width: 100%;
}


.desktop-table-row-action,
.desktop-table-row-more {
  min-height: var(--touch-target);
  white-space: nowrap;
}
.desktop-table-row-action-copy,
.desktop-table-row-menu-copy {
  display: inline-flex;
  min-width: 0;
  flex-direction: column;
  align-items: flex-start;
  text-align: left;
}

.desktop-table-row-action-reason,
.desktop-table-row-menu-reason {
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-caption);
  font-weight: 400;
  line-height: 1.25;
  white-space: normal;
}

.desktop-table-row-menu :deep([data-slot='dropdown-menu-item'].has-disabled-reason) {
  cursor: help;
}

.desktop-table-row-action {
  max-width: 128px;
  padding-inline: $space-2;
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-caption);
  font-weight: 500;

  &:hover:not(:disabled) {
    background: var(--wash-hover);
    color: hsl(var(--foreground));
  }

  &:focus-visible,
  &:focus {
    outline: 2px solid hsl(var(--ring) / 0.5);
    outline-offset: 2px;
  }

  &.is-destructive {
    color: hsl(var(--status-danger));
  }
}

.desktop-table-row-action-icon {
  width: var(--icon-sm);
  height: var(--icon-sm);
  flex-shrink: 0;
  margin-right: var(--control-gap-sm);
}

.desktop-table-row-more {
  width: var(--touch-target);
  padding: 0;
  color: hsl(var(--muted-foreground));

  &:hover:not(:disabled) {
    background: var(--wash-hover);
    color: hsl(var(--foreground));
  }

  &:focus-visible,
  &:focus {
    outline: 2px solid hsl(var(--ring) / 0.5);
    outline-offset: 2px;
  }
}

.desktop-table-row-more-icon {
  width: var(--icon-lg);
  height: var(--icon-lg);
}

.desktop-table-row-menu :deep([data-slot='dropdown-menu-item'].is-destructive) {
  color: hsl(var(--status-danger));
}

@media (max-width: $bp-sm - 1) {
  .desktop-table-row-actions {
    display: none;
  }
}
</style>
