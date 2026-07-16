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
import { useRoute } from 'vue-router'
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
  select: [item: NavItem]
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
    'px-wolf-sm py-wolf-xs',
    'rounded-wolf',
    'transition-all duration-150 ease-out',
    'touch-manipulation',
    'cursor-pointer',
    'bg-transparent',
    'border-none',
    'outline-none',
    'text-wolf-text-tertiary',
    // Active state
    isActive.value && [
      'text-wolf-primary',
      'font-wolf-medium',
      '[&_.bottom-nav-icon]:text-wolf-primary',
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
        <MoreHorizontal class="bottom-nav-icon text-wolf-icon-lg mb-wolf-xs" />
        <span class="bottom-nav-label text-wolf-caption">
          更多
        </span>
      </button>
    </DropdownMenuTrigger>

    <DropdownMenuContent side="top" align="end" :side-offset="8" class="overflow-menu">
      <div role="group" aria-label="次要导航">
        <DropdownMenuItem
          v-for="item in items"
          :key="item.label"
          class="overflow-item"
          :class="{ 'overflow-item-active': isItemActive(item) }"
          :aria-label="item.label"
          :aria-current="isItemActive(item) ? 'page' : undefined"
          @select="emit('select', item)"
        >
          <component :is="item.icon" class="overflow-icon" />
          <span class="overflow-label">{{ item.label }}</span>
        </DropdownMenuItem>
      </div>
    </DropdownMenuContent>
  </DropdownMenu>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.bottom-nav-item {
  // §2 press-feedback
  &:active {
    transform: scale(0.95);
    opacity: 0.7;
    background: $wolf-bg-hover-v2;
  }

  // §1 focus-states
  &:focus-visible {
    outline: 2px solid $wolf-primary-v2;
    outline-offset: 2px;
  }

  &:hover:not(:active) {
    background: $wolf-bg-hover-v2;
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
  font-size: $wolf-font-size-caption-v2;  // 12px
  line-height: 1.2;
}

.overflow-menu {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;  // 4px
  padding: $wolf-space-sm-v2;  // 8px
}

.overflow-item {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;  // 8px
  padding: $wolf-space-md-v2 $wolf-space-sm-v2;  // 12px 8px
  min-height: 44px;  // §2: Touch target
  cursor: pointer;
  border-radius: $wolf-radius-sm-v2;  // 4px
  transition: all 150ms ease-out;  // §7: duration
  color: $wolf-text-primary-v2;

  &:hover {
    background: $wolf-bg-hover-v2;
  }

  &:active {
    transform: scale(0.98);
    opacity: 0.7;
  }

  &:focus-visible {
    outline: 2px solid $wolf-primary-v2;
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
    color: $wolf-primary-v2;
    font-weight: $wolf-font-weight-medium-v2;

    .overflow-icon {
      color: $wolf-primary-v2;
    }
  }
}

.overflow-icon {
  width: 18px;
  height: 18px;
  color: $wolf-text-tertiary-v2;
}

.overflow-label {
  font-size: $wolf-font-size-body-v2;  // 14px
}
</style>
