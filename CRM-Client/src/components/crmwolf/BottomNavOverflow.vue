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
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { More } from '@element-plus/icons-vue'
import { cn } from '@/lib/utils'
import type { Component } from 'vue'

interface NavItem {
  route: string
  icon: Component
  label: string
}

interface Props {
  /** Overflow navigation items */
  items: NavItem[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  navigate: [route: string]
}>()

const route = useRoute()
const popoverVisible = ref(false)

// Check if any overflow item is active
const isActive = computed((): boolean => {
  return props.items.some(item => route.path.startsWith(item.route))
})

function handleItemClick(itemRoute: string): void {
  emit('navigate', itemRoute)
  popoverVisible.value = false  // Close popover after navigation
}

function handleItemKeyDown(event: KeyboardEvent, itemRoute: string): void {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    handleItemClick(itemRoute)
  }
}

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
  <el-popover
    v-model:visible="popoverVisible"
    placement="top"
    :width="200"
    trigger="click"
    :show-arrow="false"
    :offset="8"
    popper-class="bottom-nav-overflow-popover"
  >
    <!-- Trigger Button -->
    <template #reference>
      <button
        :class="overflowButtonClasses"
        aria-label="更多"
        :aria-current="isActive ? 'page' : undefined"
        :aria-expanded="popoverVisible"
        aria-haspopup="menu"
        type="button"
      >
        <el-icon class="bottom-nav-icon text-wolf-icon-lg mb-wolf-xs">
          <More />
        </el-icon>
        <span class="bottom-nav-label text-wolf-caption">
          更多
        </span>
      </button>
    </template>

    <!-- Overflow Menu Content -->
    <div
      class="overflow-menu"
      role="menu"
      aria-label="次要导航"
    >
      <div
        v-for="item in items"
        :key="item.route"
        class="overflow-item"
        :class="{ 'overflow-item-active': route.path.startsWith(item.route) }"
        role="menuitem"
        tabindex="0"
        :aria-label="item.label"
        :aria-current="route.path.startsWith(item.route) ? 'page' : undefined"
        @click="handleItemClick(item.route)"
        @keydown="handleItemKeyDown($event, item.route)"
      >
        <el-icon class="overflow-icon">
          <component :is="item.icon" />
        </el-icon>
        <span class="overflow-label">{{ item.label }}</span>
      </div>
    </div>
  </el-popover>
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
  font-size: 18px;
  color: $wolf-text-tertiary-v2;
}

.overflow-label {
  font-size: $wolf-font-size-body-v2;  // 14px
}
</style>

<style lang="scss">
@use '@/styles/variables-v2.scss' as *;

/**
 * Global Popover Styles (scoped styles don't apply to el-popover)
 * Element Plus Popover is rendered outside component scope
 */
.bottom-nav-overflow-popover {
  background: $wolf-bg-card-v2 !important;
  border: 1px solid $wolf-border-default-v2 !important;
  border-radius: $wolf-radius-v2 !important;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1) !important;
  padding: 0 !important;
}
</style>