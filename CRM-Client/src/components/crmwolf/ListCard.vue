<script setup lang="ts" generic="T extends { id: string | number }">
/**
 * ListCard - 统一列表卡片组件
 *
 * 用于 Sheet、侧栏等受限空间的同类型列表项展示
 * 符合 list-card.md 规范 + accessibility.md 无障碍规范
 *
 * 技术栈：shadcn-vue + base.css 设计令牌
 * 无障碍：WCAG AA 级别（焦点、对比度、aria-label）
 */
import { Card } from '@/components/ui/card'

interface Props {
  /** 标题 */
  title: string
  /** 列表数据 */
  items: T[]
  /** 空状态提示文本 */
  emptyText?: string
  /** 加载状态 */
  loading?: boolean
  /** 行是否可点击 */
  rowInteractive?: boolean
  /** 需要高亮并可被外层恢复焦点的行 ID */
  highlightedItemId?: string | number | null | undefined
}

const props = withDefaults(defineProps<Props>(), {
  emptyText: '暂无数据',
  loading: false,
  rowInteractive: false,
  highlightedItemId: null
})

const emit = defineEmits<{
  'row-click': [item: T]
}>()

const handleRowClick = (event: MouseEvent, item: T): void => {
  if (isNestedInteractiveElement(event.target, event.currentTarget)) return
  if (props.rowInteractive) {
    emit('row-click', item)
  }
}

const isNestedInteractiveElement = (target: EventTarget | null, currentTarget: EventTarget | null): boolean => {
  if (!(target instanceof HTMLElement) || !(currentTarget instanceof HTMLElement)) return false
  if (target === currentTarget) return false
  const nestedInteractive = target.closest('button, a, input, select, textarea, [role="button"], [role="link"]')
  return nestedInteractive !== null && nestedInteractive !== currentTarget
}

const handleRowKeydown = (event: KeyboardEvent, item: T): void => {
  if (isNestedInteractiveElement(event.target, event.currentTarget)) return
  if (props.rowInteractive && (event.key === 'Enter' || event.key === ' ')) {
    event.preventDefault()
    emit('row-click', item)
  }
}
</script>

<template>
  <Card class="list-card" :aria-busy="loading">
    <!-- Header -->
    <div class="list-card-header">
      <h3 class="list-card-title">{{ title }}</h3>
      <div v-if="$slots['headerActions']" class="list-card-actions">
        <slot name="headerActions" />
      </div>
    </div>

    <!-- Content -->
    <div class="list-card-content">
      <!-- Loading State (Skeleton) -->
      <div v-if="loading" class="list-card-loading" aria-label="加载中">
        <div class="skeleton-header" />
        <div v-for="i in 3" :key="i" class="skeleton-item" />
      </div>

      <!-- Empty State -->
      <div v-else-if="items.length === 0" class="list-card-empty">
        <slot name="empty">
          <div class="list-card-empty-state" role="status">
            {{ emptyText }}
          </div>
        </slot>
      </div>

      <!-- List Items -->
      <div v-else class="list-card-list" role="list">
        <div
          v-for="item in items"
          :key="item.id"
          class="list-card-item"
          :class="{
            'is-interactive': rowInteractive,
            'is-highlighted': highlightedItemId === item.id
          }"
          :data-list-card-row-id="item.id"
          :data-highlighted="highlightedItemId === item.id ? 'true' : undefined"
          :role="rowInteractive ? 'button' : undefined"
          :tabindex="rowInteractive ? 0 : undefined"
          @click="handleRowClick($event, item)"
          @keydown="handleRowKeydown($event, item)"
        >
          <div class="list-card-item-main">
            <slot name="itemMain" :item="item" />
          </div>
          <div v-if="$slots['itemMeta']" class="list-card-item-meta">
            <slot name="itemMeta" :item="item" />
          </div>
          <div v-if="$slots['itemBadges']" class="list-card-item-badges">
            <slot name="itemBadges" :item="item" />
          </div>
          <div v-if="$slots['itemActions']" class="list-card-item-actions">
            <slot name="itemActions" :item="item" />
          </div>
        </div>
      </div>
    </div>
  </Card>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

// ==================== Card Container ====================
.list-card {
  display: flex;
  flex-direction: column;
  height: auto;
  background: hsl(var(--card));
  border-radius: var(--radius-lg);
  border: 1px solid hsl(var(--border));
}

// ==================== Header ====================
.list-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: $space-3 $space-4;
  border-bottom: 1px solid hsl(var(--border));
}

.list-card-title {
  font-size: var(--font-size-body);
  font-weight: 600;
  color: hsl(var(--foreground));
  margin: 0; // Reset default margin
}

.list-card-actions {
  display: flex;
  align-items: center;
  gap: $space-1;
}

// ==================== Content ====================
.list-card-content {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}

// ==================== Loading State ====================
.list-card-loading {
  padding: $space-3 $space-4;
}

.skeleton-header {
  height: 20px;
  background: linear-gradient(
    90deg,
    hsl(var(--muted)) 25%,
    var(--wash-hover) 50%,
    hsl(var(--muted)) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.5s ease-in-out infinite;
  border-radius: var(--radius-sm);
  margin-bottom: $space-3;
}

.skeleton-item {
  height: var(--touch-target); // 44px
  background: linear-gradient(
    90deg,
    hsl(var(--muted)) 25%,
    var(--wash-hover) 50%,
    hsl(var(--muted)) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.5s ease-in-out infinite;
  border-radius: var(--radius-sm);
  margin-bottom: $space-2;

  &:last-child {
    margin-bottom: 0;
  }
}

@keyframes skeleton-shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

// Reduced motion: disable skeleton animation
@media (prefers-reduced-motion: reduce) {
  .skeleton-header,
  .skeleton-item {
    animation: none;
    background: hsl(var(--muted));
  }
}

// ==================== Empty State ====================
.list-card-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 68px;
  padding: $space-3 $space-4;
}

.list-card-empty-state {
  width: 100%;
  font-size: var(--font-size-body);
  font-weight: 500;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

// ==================== List Items ====================
.list-card-list {
  display: flex;
  flex-direction: column;
}

.list-card-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto auto;
  align-items: center;
  gap: $space-3;
  min-height: 68px;
  padding: $space-3 $space-4;
  border-bottom: 1px solid hsl(var(--border));
  transition: background 150ms ease;

  &:last-child {
    border-bottom: none;
  }

  &:hover {
    background: var(--wash-hover);
  }

  // Keyboard focus state (accessibility.md requirement)
  &:focus-visible {
    outline: 2px solid hsl(var(--ring) / 0.5);
    outline-offset: 2px;
  }

  // Interactive row cursor
  &.is-interactive {
    cursor: pointer;
  }

  &.is-highlighted {
    background: var(--wash-hover);
  }
}

@media (prefers-reduced-motion: reduce) {
  .list-card-item {
    transition-duration: 0.01ms;
  }
}

.list-card-item-main {
  min-width: 0;
}

.list-card-item-meta {
  min-width: 0;
  font-size: var(--font-size-caption);
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.list-card-item-badges {
  display: flex;
  align-items: center;
  gap: $space-1;
  min-width: 0;
  flex-shrink: 0;
  white-space: nowrap;
}

.list-card-item-actions {
  display: flex;
  align-items: center;
  gap: $space-1; // Must be >=8px - touch spacing compliance
  flex-shrink: 0;

  // Ensure all buttons meet touch target size
  button {
    min-height: var(--touch-target);
    min-width: var(--touch-target);
  }
}

// ==================== Responsive ====================
@media (max-width: $bp-md - 1) {
  .list-card-header,
  .list-card-empty,
  .list-card-item {
    padding-left: $space-3;
    padding-right: $space-3;
  }

  .list-card-item {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .list-card-item-meta,
  .list-card-item-badges {
    grid-column: 1 / -1;
  }

  // Stack actions vertically on small screens if > 2 buttons
  .list-card-item-actions {
    @media (max-width: $bp-sm - 1) {
      flex-direction: column;
      gap: $space-1;
    }
  }
}

// ==================== Disabled State ====================
.list-card-item-actions button[disabled] {
  opacity: var(--disabled-opacity);
  cursor: not-allowed;
}
</style>
