<script setup lang="ts">
/**
 * LoadingSkeleton - Skeleton Screen Component
 * UI/UX Pro Max Compliant:
 * - §3 HIGH: Skeleton screens for >300ms loading
 * - §7 MEDIUM: Animation duration 150ms
 * - §7 MEDIUM: Reduced motion support (disable animation)
 */
import { computed } from 'vue'
import { cn } from '@/lib/utils'

interface Props {
  /** Number of skeleton rows */
  rows?: number
  /** Skeleton type */
  type?: 'list' | 'card' | 'table'
  /** Show avatar placeholder */
  showAvatar?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  rows: 3,
  type: 'list',
  showAvatar: false,
})

const containerClasses = computed((): string =>
  cn(
    'loading-skeleton',
    'flex flex-col gap-wolf-md',
    'animate-pulse'  // Shimmer effect
  )
)
</script>

<template>
  <div :class="containerClasses" role="status" aria-label="加载中" aria-live="polite">
    <!-- List skeleton -->
    <template v-if="type === 'list'">
      <div
        v-for="i in rows"
        :key="i"
        class="skeleton-item"
      >
        <div v-if="showAvatar" class="skeleton-avatar"></div>
        <div class="skeleton-content">
          <div class="skeleton-line skeleton-title"></div>
          <div class="skeleton-line skeleton-text"></div>
        </div>
      </div>
    </template>

    <!-- Card skeleton -->
    <template v-else-if="type === 'card'">
      <div
        v-for="i in rows"
        :key="i"
        class="skeleton-card"
      >
        <div class="skeleton-card-header">
          <div class="skeleton-line skeleton-card-title"></div>
        </div>
        <div class="skeleton-card-body">
          <div class="skeleton-line skeleton-card-text"></div>
          <div class="skeleton-line skeleton-card-text-short"></div>
        </div>
      </div>
    </template>

    <!-- Table skeleton -->
    <template v-else-if="type === 'table'">
      <div class="skeleton-table">
        <div class="skeleton-table-header">
          <div class="skeleton-line skeleton-th"></div>
          <div class="skeleton-line skeleton-th"></div>
          <div class="skeleton-line skeleton-th"></div>
        </div>
        <div
          v-for="i in rows"
          :key="i"
          class="skeleton-table-row"
        >
          <div class="skeleton-line skeleton-td"></div>
          <div class="skeleton-line skeleton-td"></div>
          <div class="skeleton-line skeleton-td"></div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

// Base skeleton animation
@keyframes shimmer {
  0% {
    background-position: -200% 0;
  }
  100% {
    background-position: 200% 0;
  }
}

.loading-skeleton {
  width: 100%;
}

.skeleton-item {
  display: flex;
  align-items: center;
  gap: $wolf-space-md-v2;
  padding: $wolf-space-md-v2;
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-v2;
}

.skeleton-avatar {
  width: 40px;
  height: 40px;
  border-radius: $wolf-radius-full-v2;
  background: linear-gradient(
    90deg,
    $wolf-bg-hover-v2 25%,
    $wolf-bg-active-v2 50%,
    $wolf-bg-hover-v2 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}

.skeleton-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.skeleton-line {
  background: linear-gradient(
    90deg,
    $wolf-bg-hover-v2 25%,
    $wolf-bg-active-v2 50%,
    $wolf-bg-hover-v2 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
  border-radius: $wolf-radius-sm-v2;
}

.skeleton-title {
  width: 60%;
  height: 16px;
}

.skeleton-text {
  width: 80%;
  height: 12px;
}

// Card skeleton
.skeleton-card {
  padding: $wolf-space-md-v2;
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-v2;
  border: 1px solid $wolf-border-default-v2;
}

.skeleton-card-header {
  margin-bottom: $wolf-space-md-v2;
}

.skeleton-card-title {
  width: 50%;
  height: 18px;
}

.skeleton-card-body {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.skeleton-card-text {
  width: 100%;
  height: 12px;
}

.skeleton-card-text-short {
  width: 60%;
  height: 12px;
}

// Table skeleton
.skeleton-table {
  width: 100%;
  border-radius: $wolf-radius-v2;
  overflow: hidden;
}

.skeleton-table-header,
.skeleton-table-row {
  display: flex;
  gap: $wolf-space-md-v2;
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
}

.skeleton-table-header {
  background: $wolf-bg-hover-v2;
}

.skeleton-table-row {
  background: $wolf-bg-card-v2;
  border-bottom: 1px solid $wolf-border-default-v2;

  &:last-child {
    border-bottom: none;
  }
}

.skeleton-th {
  flex: 1;
  height: 14px;
}

.skeleton-td {
  flex: 1;
  height: 12px;
}

// §7 reduced-motion: Disable animation for users who prefer reduced motion
@media (prefers-reduced-motion: reduce) {
  .loading-skeleton,
  .skeleton-line,
  .skeleton-avatar {
    animation: none !important;
    background: $wolf-bg-hover-v2;  // Static gray background
  }
}
</style>