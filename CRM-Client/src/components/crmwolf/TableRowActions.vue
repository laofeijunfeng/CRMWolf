<script setup lang="ts">
/**
 * TableRowActions.vue - 窄视口卡片行操作
 *
 * 桌面 DataTable 行操作采用主操作 + 更多菜单；本组件只服务移动端卡片。
 * 本组件只服务 `#mobile-actions`：主按钮常显，低频操作收入 DropdownMenu。
 *
 * 设计规范强制要求：
 * - 使用 shadcn-vue DropdownMenu + Button（组合组件，不重复造轮子）
 * - Touch target size ≥44px（UI/UX Pro Max §2）
 * - Destructive actions 使用红色 + 确认对话框（UI/UX Pro Max §8）
 */
import { computed } from 'vue'
import { MoreHorizontal } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator
} from '@/components/ui/dropdown-menu'
import type { ActionConfig } from './tableRowActionTypes'
import {
  getMobileTableRowActions,
  getTableRowActionKey,
  getTableRowActionLabel,
  isDestructiveTableRowAction
} from './tableRowActionGroups'

export type { ActionConfig }

interface TableRowActionsProps {
  /** 当前行数据 */
  row: Record<string, unknown>
  /** 高频操作（窄视口卡片常显按钮） */
  primaryActions?: ActionConfig[]
  /** 低频操作（窄视口收入 DropdownMenu） */
  secondaryActions?: ActionConfig[]
  /** 按钮尺寸 */
  size?: 'default' | 'sm' | 'lg'
}

const props = withDefaults(defineProps<TableRowActionsProps>(), {
  primaryActions: () => [],
  secondaryActions: () => [],
  size: 'sm'
})

/**
 * 过滤详情入口，并确保危险动作不会绕过“更多”层级直接平铺。
 */
const mobileActions = computed(() => getMobileTableRowActions({
  primaryActions: props.primaryActions,
  secondaryActions: props.secondaryActions
}))

const visiblePrimaryActions = computed(() => mobileActions.value.primaryActions)
const visibleSecondaryActions = computed(() => mobileActions.value.secondaryActions)

/**
 * 是否显示 DropdownMenu（有 secondaryActions 时才显示）
 */
const showDropdownMenu = computed(() => visibleSecondaryActions.value.length > 0)

/**
 * 执行操作（阻止事件冒泡）
 */
const executeAction = (event: Event, action: ActionConfig): void => {
  event.stopPropagation()
  if (action.disabled === true) {
    event.preventDefault()
    return
  }
  action.handler(props.row)
}

const hasDisabledReason = (action: ActionConfig): boolean =>
  action.disabled === true && Boolean(action.disabledReason?.trim())
</script>

<template>
  <div class="table-row-actions">
    <!-- 高频操作按钮（行外） -->
    <Button
      v-for="(action, actionIndex) in visiblePrimaryActions"
      :key="getTableRowActionKey(action, actionIndex)"
      :size="size"
      variant="ghost"
      :disabled="action.disabled === true && !hasDisabledReason(action)"
      :aria-disabled="action.disabled === true ? 'true' : undefined"
      :class="['action-button', { 'action-destructive': isDestructiveTableRowAction(action), 'action-has-disabled-reason': hasDisabledReason(action) }]"
      @click="executeAction($event, action)"
      :aria-label="getTableRowActionLabel(action)"
      :title="getTableRowActionLabel(action)"
    >
      <component :is="action.icon" v-if="action.icon" class="action-icon" aria-hidden="true" />
      <span class="action-copy">
        <span>{{ action.label }}</span>
        <span v-if="hasDisabledReason(action)" class="action-reason">{{ action.disabledReason }}</span>
      </span>
    </Button>

    <!-- 低频操作下拉菜单 -->
    <DropdownMenu v-if="showDropdownMenu">
      <DropdownMenuTrigger as-child>
        <Button
          :size="size"
          variant="ghost"
          class="action-button action-more"
          aria-label="更多操作"
          @click.stop
        >
          <MoreHorizontal class="action-icon" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" class="dropdown-content">
        <template v-for="(action, actionIndex) in visibleSecondaryActions" :key="getTableRowActionKey(action, actionIndex)">
          <!-- 分隔线 -->
          <DropdownMenuSeparator v-if="action.separator" />

          <!-- 操作项 -->
          <DropdownMenuItem
            as-child
            :disabled="action.disabled === true && !hasDisabledReason(action)"
            @select="executeAction($event, action)"
          >
            <div
              role="menuitem"
              :aria-disabled="action.disabled === true ? 'true' : undefined"
              :class="['dropdown-item', { 'dropdown-item-destructive': isDestructiveTableRowAction(action), 'dropdown-item-has-disabled-reason': hasDisabledReason(action) }]"
              :title="getTableRowActionLabel(action)"
              :aria-label="getTableRowActionLabel(action)"
            >
              <component :is="action.icon" v-if="action.icon" aria-hidden="true" />
              <span class="action-copy">
                <span>{{ action.label }}</span>
                <span v-if="hasDisabledReason(action)" class="action-reason">{{ action.disabledReason }}</span>
              </span>
            </div>
          </DropdownMenuItem>
        </template>
      </DropdownMenuContent>
    </DropdownMenu>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.table-row-actions {
  display: flex;
  align-items: center;
  gap: $space-1;
  justify-content: center;
}

.action-copy {
  display: inline-flex;
  min-width: 0;
  flex-direction: column;
  align-items: flex-start;
  text-align: left;
}

.action-reason {
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-caption);
  font-weight: 400;
  line-height: 1.25;
  white-space: normal;
}

.dropdown-item-has-disabled-reason {
  cursor: help;
}

// 操作按钮
.action-button {
  // Touch target size 扩展（UI/UX Pro Max §2）
  // shadcn-vue Button sm: 36px，需要扩展到 ≥44px
  min-height: var(--touch-target);
  min-width: var(--touch-target);
  padding: 0 $space-2;
  font-size: var(--font-size-caption);
  font-weight: 500;
  transition: all all var(--duration-base) var(--ease-standard);

  &:hover:not(:disabled) {
    background: var(--wash-hover);
  }

  &:focus-visible {
    outline: 2px solid hsl(var(--brand));
    outline-offset: 2px;
  }
}

// 图标
.action-icon {
  width: 16px;
  height: 16px;
  margin-right: 4px;
}

// 危险操作（红色）
.action-destructive {
  color: hsl(var(--status-danger));

  &:hover:not(:disabled) {
    background: color-mix(in srgb, hsl(var(--status-danger)) var(--status-bg-mix), transparent);
  }
}

// More 按钮（无文字，只有图标）
.action-more {
  padding: 0 8px;

  .action-icon {
    margin-right: 0;
  }
}

// DropdownMenu 项样式
.dropdown-item {
  cursor: pointer;
}

// DropdownMenu 危险操作项
.dropdown-item-destructive {
  color: hsl(var(--status-danger));

  &:hover:not([data-disabled]) {
    background: color-mix(in srgb, hsl(var(--status-danger)) var(--status-bg-mix), transparent);
  }
}

// Reduced motion 支持（UI/UX Pro Max §7）
@media (prefers-reduced-motion: reduce) {
  .action-button,
  .dropdown-item {
    transition: none;
  }
}
</style>
