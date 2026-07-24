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
import { useRoute, useRouter } from 'vue-router'
import { computed } from 'vue'
import {
  Banknote,
  BarChart3,
  Bot,
  Building2,
  FileText,
  Flag,
  LogOut,
  ReceiptText,
  Settings,
  TrendingUp,
} from 'lucide-vue-next'
import BottomNavItem from './BottomNavItem.vue'
import BottomNavOverflow from './BottomNavOverflow.vue'
import type { Component } from 'vue'
import { usePermissionStore } from '@/stores/permissions'

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

const emit = defineEmits<{
  logout: []
}>()

const route = useRoute()
const router = useRouter()
const permissionStore = usePermissionStore()

// Primary navigation items (§9 bottom-nav-limit: max 5)
// Only top-level screens (§9 nav-hierarchy)
const mainNavItems: RouteNavItem[] = [
  { kind: 'route', route: '/agent', icon: Bot, label: 'Agent' },
  { kind: 'route', route: '/customers', icon: Building2, label: '客户' },
  { kind: 'route', route: '/opportunities', icon: TrendingUp, label: '商机' },
  { kind: 'route', route: '/contracts', icon: FileText, label: '合同' },
]

// Overflow navigation items (secondary workflows)
const baseOverflowItems: NavItem[] = [
  { kind: 'route', route: '/sales-dashboard', icon: BarChart3, label: '看板' },
  { kind: 'route', route: '/leads', icon: Flag, label: '线索' },
  { kind: 'route', route: '/payments', icon: Banknote, label: '回款' },
  { kind: 'route', route: '/invoices', icon: ReceiptText, label: '发票' },
  { kind: 'route', route: '/account', icon: Settings, label: '账户设置' },
  { kind: 'action', action: 'logout', icon: LogOut, label: '退出登录' },
]

const canViewSalesDashboard = computed(() => permissionStore.hasAnyPermission([
  'sales_dashboard:view:own',
  'sales_dashboard:view:team',
  'sales_dashboard:view:all'
]))

const overflowItems = computed<NavItem[]>(() => {
  return baseOverflowItems.filter(item => {
    if (item.kind === 'route' && item.route === '/sales-dashboard') {
      return canViewSalesDashboard.value
    }
    return true
  })
})

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
 * Handle an overflow navigation or action selection.
 */
function handleOverflowSelect(item: NavItem): void {
  if (item.kind === 'route') {
    router.push(item.route)
  } else {
    emit('logout')
  }
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
        @select="handleOverflowSelect"
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
