<script setup lang="ts">
/**
 * TableRowActions.vue - 窄视口卡片行操作
 *
 * 桌面 DataTable 行操作改走右键 Context Menu，不再用本组件把高频操作放在表格行外。
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
 * 过滤可见的操作
 */
const visiblePrimaryActions = computed(() =>
  props.primaryActions.filter(action => action.visible !== false)
)

const visibleSecondaryActions = computed(() =>
  props.secondaryActions.filter(action => action.visible !== false)
)

/**
 * 是否显示 DropdownMenu（有 secondaryActions 时才显示）
 */
const showDropdownMenu = computed(() => visibleSecondaryActions.value.length > 0)

/**
 * 执行操作（阻止事件冒泡）
 */
const executeAction = (action: ActionConfig): void => {
  if (action.disabled === true) return
  action.handler(props.row)
}
</script>

<template>
  <div class="table-row-actions">
    <!-- 高频操作按钮（行外） -->
    <Button
      v-for="action in visiblePrimaryActions"
      :key="action.label"
      :size="size"
      variant="ghost"
      :disabled="action.disabled === true"
      :class="['action-button', { 'action-destructive': action.destructive }]"
      @click.stop="executeAction(action)"
      :aria-label="action.label"
    >
      <component :is="action.icon" v-if="action.icon" class="action-icon" aria-hidden="true" />
      {{ action.label }}
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
        <template v-for="action in visibleSecondaryActions" :key="action.label">
          <!-- 分隔线 -->
          <DropdownMenuSeparator v-if="action.separator" />

          <!-- 操作项 -->
          <DropdownMenuItem
            :disabled="action.disabled === true"
            :class="['dropdown-item', { 'dropdown-item-destructive': action.destructive }]"
            @click.stop="executeAction(action)"
          >
            <component :is="action.icon" v-if="action.icon" class="dropdown-icon" aria-hidden="true" />
            {{ action.label }}
          </DropdownMenuItem>
        </template>
      </DropdownMenuContent>
    </DropdownMenu>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.table-row-actions {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
  justify-content: center;
}

// 操作按钮
.action-button {
  // Touch target size 扩展（UI/UX Pro Max §2）
  // shadcn-vue Button sm: 36px，需要扩展到 ≥44px
  min-height: $wolf-touch-target-min-v2;
  min-width: $wolf-touch-target-min-v2;
  padding: 0 $wolf-space-sm-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  transition: all $wolf-transition-v2;

  &:hover:not(:disabled) {
    background: $wolf-bg-hover-v2;
  }

  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-primary-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
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
  color: $wolf-danger-text-v2;

  &:hover:not(:disabled) {
    background: $wolf-danger-bg-v2;
  }
}

// More 按钮（无文字，只有图标）
.action-more {
  padding: 0 8px;

  .action-icon {
    margin-right: 0;
  }
}

// DropdownMenu 内容样式
.dropdown-content {
  min-width: 160px;
  background: $wolf-bg-card-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-popover-v2;
  padding: $wolf-space-xs-v2;
  box-shadow: $wolf-shadow-modal-v2;
}

// DropdownMenu 项样式
.dropdown-item {
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  color: $wolf-text-primary-v2;
  border-radius: $wolf-radius-v2;
  cursor: pointer;
  transition: background $wolf-transition-v2;

  &:hover:not([data-disabled]) {
    background: $wolf-bg-hover-v2;
  }

  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-primary-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }
}

// DropdownMenu 危险操作项
.dropdown-item-destructive {
  color: $wolf-danger-text-v2;

  &:hover:not([data-disabled]) {
    background: $wolf-danger-bg-v2;
  }
}

// DropdownMenu 图标
.dropdown-icon {
  width: 16px;
  height: 16px;
  margin-right: $wolf-space-xs-v2;
}

// Reduced motion 支持（UI/UX Pro Max §7）
@media (prefers-reduced-motion: reduce) {
  .action-button,
  .dropdown-item {
    transition: none;
  }
}
</style>
