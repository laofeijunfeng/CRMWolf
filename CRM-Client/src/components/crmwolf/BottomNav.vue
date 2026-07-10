<script setup lang="ts">
/**
 * BottomNav - Mobile Bottom Navigation
 * UI/UX Pro Max Compliant:
 * - §9 HIGH: Bottom nav ≤5 items (4 main + 1 overflow)
 * - §9 HIGH: nav-label-icon (icon + text for each item)
 * - §9 HIGH: nav-state-active (active route highlighted)
 * - §9 HIGH: nav-hierarchy (primary nav for top-level screens only)
 * - §9 HIGH: gesture-nav-support (doesn't block system gestures)
 * - §9 HIGH: adaptive-navigation (mobile: bottom nav, desktop: sidebar)
 * - §2 CRITICAL: Touch targets 44×44px
 * - §5 HIGH: Safe area handling (iOS notch / Android gesture bar)
 * - §1 CRITICAL: aria-label, aria-current
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  OfficeBuilding,
  TrendCharts,
  Document,
  Flag,
  Money,
  Tickets,
  Bell,
  Setting,
} from '@element-plus/icons-vue'
import BottomNavItem from './BottomNavItem.vue'
import BottomNavOverflow from './BottomNavOverflow.vue'
import type { Component } from 'vue'

interface NavItem {
  route: string
  icon: Component
  label: string
}

const route = useRoute()
const router = useRouter()

// Primary navigation items (§9 bottom-nav-limit: max 5)
// Only top-level screens (§9 nav-hierarchy)
const mainNavItems: NavItem[] = [
  { route: '/payments', icon: Money, label: '回款' },
  { route: '/customers', icon: OfficeBuilding, label: '客户' },
  { route: '/opportunities', icon: TrendCharts, label: '商机' },
  { route: '/contracts', icon: Document, label: '合同' },
]

// Overflow navigation items (secondary workflows)
const overflowItems: NavItem[] = [
  { route: '/leads', icon: Flag, label: '线索' },
  { route: '/invoices', icon: Tickets, label: '发票' },
  { route: '/approvals', icon: Bell, label: '审批' },
  { route: '/settings', icon: Setting, label: '设置' },
]

/**
 * Check if a route is currently active
 * Handles nested routes (e.g., /customers/:id should highlight /customers)
 */
function isRouteActive(itemRoute: string): boolean {
  // Special handling for routes with sub-paths
  if (itemRoute === '/leads') {
    // Leads has multiple sub-routes: /leads/public, /leads/my, /leads/:id
    return route.path.startsWith('/leads')
  }

  // Default: check if current path starts with item route
  return route.path.startsWith(itemRoute)
}

/**
 * Handle navigation item click
 */
function handleNavClick(itemRoute: string): void {
  router.push(itemRoute)
}

/**
 * Handle overflow menu navigation
 */
function handleOverflowNavigate(itemRoute: string): void {
  router.push(itemRoute)
}
</script>

<template>
  <nav
    class="bottom-nav"
    role="navigation"
    aria-label="主导航"
  >
    <div class="bottom-nav-container">
      <!-- Main Navigation Items (4 items) -->
      <BottomNavItem
        v-for="item in mainNavItems"
        :key="item.route"
        :item="item"
        :active="isRouteActive(item.route)"
        @click="handleNavClick(item.route)"
      />

      <!-- Overflow Menu ("更多") -->
      <BottomNavOverflow
        :items="overflowItems"
        @navigate="handleOverflowNavigate"
      />
    </div>
  </nav>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.bottom-nav {
  // Fixed positioning at bottom
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 100;  // §5 z-index-management

  // Background & border
  background: $wolf-bg-card-v2;
  border-top: 1px solid $wolf-border-default-v2;

  // §5 safe-area-awareness: iOS notch / Android gesture bar
  padding-bottom: env(safe-area-inset-bottom, 0px);

  // §9 gesture-nav-support: Don't block system gestures
  pointer-events: auto;  // Allow touch events to pass through
  touch-action: pan-y;   // Allow vertical scroll and gestures
}

.bottom-nav-container {
  display: flex;
  align-items: center;
  justify-content: space-around;  // Evenly distribute items
  max-width: 100%;
  height: $wolf-bottom-nav-height-v2;  // 56px
  padding: 0 $wolf-space-sm-v2;  // 8px horizontal padding
}

// §9 adaptive-navigation: Hide on desktop (≥768px)
@media (min-width: $wolf-breakpoint-sm-v2) {  // 768px
  .bottom-nav {
    display: none;
  }
}

// §7 reduced-motion: Respect user preference for reduced motion
@media (prefers-reduced-motion: reduce) {
  .bottom-nav {
    * {
      transition: opacity 150ms ease-out !important;
      transform: none !important;
    }
  }
}
</style>