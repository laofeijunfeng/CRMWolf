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
  /** Whether this skeleton owns the screen-reader loading announcement. */
  announce?: boolean
}

withDefaults(defineProps<Props>(), {
  rows: 3,
  type: 'list',
  showAvatar: false,
  announce: true,
})

const containerClasses = computed((): string =>
  cn(
    'loading-skeleton',
    'flex flex-col gap-3',
    'animate-pulse'  // Shimmer effect
  )
)
</script>

<template>
  <div
    :class="containerClasses"
    :role="announce ? 'status' : 'presentation'"
    :aria-label="announce ? '加载中' : undefined"
    :aria-live="announce ? 'polite' : undefined"
  >
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
@use '@/styles/tokens.scss' as *;

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
  gap: $space-3;
  padding: $space-3;
  background: hsl(var(--card));
  border-radius: var(--radius-md);
}

.skeleton-avatar {
  width: 40px;
  height: 40px;
  border-radius: 9999px;
  background: linear-gradient(
    90deg,
    var(--wash-hover) 25%,
    var(--wash-selected) 50%,
    var(--wash-hover) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}

.skeleton-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: $space-1;
}

.skeleton-line {
  background: linear-gradient(
    90deg,
    var(--wash-hover) 25%,
    var(--wash-selected) 50%,
    var(--wash-hover) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
  border-radius: var(--radius-sm);
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
  padding: $space-3;
  background: hsl(var(--card));
  border-radius: var(--radius-md);
  border: 1px solid hsl(var(--border));
}

.skeleton-card-header {
  margin-bottom: $space-3;
}

.skeleton-card-title {
  width: 50%;
  height: 18px;
}

.skeleton-card-body {
  display: flex;
  flex-direction: column;
  gap: $space-1;
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
  border-radius: var(--radius-md);
  overflow: hidden;
}

.skeleton-table-header,
.skeleton-table-row {
  display: flex;
  gap: $space-3;
  padding: $space-2 $space-3;
}

.skeleton-table-header {
  background: var(--wash-hover);
}

.skeleton-table-row {
  background: hsl(var(--card));
  border-bottom: 1px solid hsl(var(--border));

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
    background: var(--wash-hover);  // Static gray background
  }
}
</style>
