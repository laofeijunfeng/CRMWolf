<script setup lang="ts">
/**
 * BottomNavOverflow - Overflow Menu for Secondary Navigation
 * UI/UX Pro Max Compliant:
 * - §9 HIGH: Overflow menu (when actions exceed 5 items)
 * - §2 CRITICAL: Touch targets ≥44px
 * - §1 CRITICAL: aria-label for menu and items
 * - §7 MEDIUM: Animation duration 150ms
 * - §7 MEDIUM: Reduced motion support
 */
import { computed, type Component } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { MoreHorizontal } from 'lucide-vue-next'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'

interface RouteNavItem {
  kind: 'route'
  route: string
  icon: Component
  label: string
}

interface ActionNavItem {
  kind: 'action'
  action: 'logout'
  icon: Component
  label: string
}

type NavItem = RouteNavItem | ActionNavItem

interface Props {
  /** Overflow navigation and action items */
  items: NavItem[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  select: [item: ActionNavItem]
}>()

const route = useRoute()

function isItemActive(item: NavItem): boolean {
  return item.kind === 'route' && route.path.startsWith(item.route)
}

// Check if any overflow route item is active
const isActive = computed((): boolean => props.items.some(isItemActive))

const overflowButtonClasses = computed((): string =>
  cn(
    'bottom-nav-item',
    'flex flex-col items-center justify-center',
    'min-w-touch-target min-h-touch-target',  // §2: 44px
    'px-2 py-1',
    'rounded-md',
    'transition-all duration-150 ease-out',
    'touch-manipulation',
    'cursor-pointer',
    'bg-transparent',
    'border-none',
    'outline-none',
    'text-muted-foreground',
    // Active state
    isActive.value && [
      'text-brand',
      'font-medium',
      '[&_.bottom-nav-icon]:text-brand',
    ]
  )
)
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <button
        :class="overflowButtonClasses"
        aria-label="更多"
        :aria-current="isActive ? 'page' : undefined"
        type="button"
      >
        <MoreHorizontal class="bottom-nav-icon mb-1" />
        <span class="bottom-nav-label text-caption">
          更多
        </span>
      </button>
    </DropdownMenuTrigger>

    <DropdownMenuContent side="top" align="end" :side-offset="8" class="overflow-menu">
      <div role="group" aria-label="次要导航">
        <template v-for="item in items" :key="item.label">
          <DropdownMenuItem
            v-if="item.kind === 'route'"
            as-child
            class="overflow-item"
            :class="{ 'overflow-item-active': isItemActive(item) }"
          >
            <RouterLink
              :to="item.route"
              :aria-label="item.label"
              :aria-current="isItemActive(item) ? 'page' : undefined"
            >
              <component :is="item.icon" class="overflow-icon" aria-hidden="true" />
              <span class="overflow-label">{{ item.label }}</span>
            </RouterLink>
          </DropdownMenuItem>
          <DropdownMenuItem
            v-else
            class="overflow-item"
            :aria-label="item.label"
            @select="emit('select', item)"
          >
            <component :is="item.icon" class="overflow-icon" aria-hidden="true" />
            <span class="overflow-label">{{ item.label }}</span>
          </DropdownMenuItem>
        </template>
      </div>
    </DropdownMenuContent>
  </DropdownMenu>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.bottom-nav-item {
  // §2 press-feedback
  &:active {
    transform: scale(0.95);
    opacity: 0.7;
    background: var(--wash-hover);
  }

  // §1 focus-states
  &:focus-visible {
    outline: 2px solid hsl(var(--brand));
    outline-offset: 2px;
  }

  &:hover:not(:active) {
    background: var(--wash-hover);
  }

  // §7 reduced-motion
  @media (prefers-reduced-motion: reduce) {
    transition: opacity 150ms ease-out;

    &:active {
      transform: none;
      opacity: 0.7;
    }
  }
}

.bottom-nav-icon {
  font-size: 20px;
  width: 20px;
  height: 20px;
}

.bottom-nav-label {
  font-size: var(--font-size-caption);  // 12px
  line-height: 1.2;
}

.overflow-menu {
  display: flex;
  flex-direction: column;
  gap: $space-1;  // 4px
  padding: $space-2;  // 8px
}

.overflow-item {
  display: flex;
  align-items: center;
  gap: $space-2;  // 8px
  padding: $space-3 $space-2;  // 12px 8px
  min-height: 44px;  // §2: Touch target
  cursor: pointer;
  border-radius: var(--radius-sm);  // 4px
  transition: all 150ms ease-out;  // §7: duration
  color: hsl(var(--foreground));

  &:hover {
    background: var(--wash-hover);
  }

  &:active {
    transform: scale(0.98);
    opacity: 0.7;
  }

  &:focus-visible {
    outline: 2px solid hsl(var(--brand));
    outline-offset: 2px;
  }

  // §7 reduced-motion
  @media (prefers-reduced-motion: reduce) {
    transition: opacity 150ms ease-out;

    &:active {
      transform: none;
      opacity: 0.7;
    }
  }

  &.overflow-item-active {
    color: hsl(var(--brand));
    font-weight: 500;

    .overflow-icon {
      color: hsl(var(--brand));
    }
  }
}

.overflow-icon {
  width: 18px;
  height: 18px;
  color: hsl(var(--muted-foreground));
}

.overflow-label {
  font-size: var(--font-size-body);  // 14px
}
</style>
