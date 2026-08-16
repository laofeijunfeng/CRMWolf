<template>
  <Sidebar collapsible="icon" variant="inset">
    <SidebarHeader>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton size="lg" class="cursor-default">
            <div class="flex aspect-square size-8 items-center justify-center overflow-hidden rounded-lg bg-wolf-bg-card">
              <img src="/logo.png" alt="CRMWolf Logo" class="size-8 object-contain" />
            </div>
            <div class="grid flex-1 text-left text-sm leading-tight">
              <span class="truncate font-semibold">CRMWolf</span>
              <span class="truncate text-xs text-muted-foreground">Sales CRM</span>
            </div>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarHeader>

    <SidebarContent>
      <NavMain :groups="navGroups" @navigate="handleMenuClick" />
    </SidebarContent>

    <SidebarFooter>
      <NavUser />
    </SidebarFooter>
    <SidebarRail />
  </Sidebar>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute, useRouter } from 'vue-router'
import {
  BarChart3,
  Bot,
  Building2,
  Columns3,
  FileText,
  Flag,
  ListChecks,
  Receipt,
  Stamp,
  TrendingUp,
  Wallet,
} from 'lucide-vue-next'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from '@/components/ui/sidebar'
import { usePermissionStore } from '@/stores/permissions'
import { useFollowUpConfirmationStore } from '@/stores/followUpConfirmation'
import { logger } from '@/utils/logger'
import NavMain, { type NavMainGroup } from './NavMain.vue'
import NavUser from './NavUser.vue'

const router = useRouter()
const route = useRoute()
const permissionStore = usePermissionStore()
const confirmationStore = useFollowUpConfirmationStore()
const { pendingCount: pendingConfirmationCount } = storeToRefs(confirmationStore)
const { fetchPendingCount } = confirmationStore

const pendingConfirmationBadge = computed<number | string | undefined>(() => {
  if (pendingConfirmationCount.value <= 0) return undefined
  return pendingConfirmationCount.value > 99 ? '99+' : pendingConfirmationCount.value
})

const confirmationRefreshIntervalMs = 45_000
let confirmationRefreshTimer: number | undefined
let confirmationRefreshInFlight = false

async function refreshPendingConfirmationCount(): Promise<void> {
  if (confirmationRefreshInFlight) return
  confirmationRefreshInFlight = true
  try {
    await fetchPendingCount()
  } catch (error) {
    logger.warn('[AppSidebar]', '待确认追踪数量加载失败', { error })
  } finally {
    confirmationRefreshInFlight = false
  }
}

function handleWindowFocus(): void {
  void refreshPendingConfirmationCount()
}

function handleVisibilityChange(): void {
  if (document.visibilityState === 'visible') {
    void refreshPendingConfirmationCount()
  }
}

const currentPath = computed(() => {
  const path = route.path
  if (path.startsWith('/leads/public')) return '/leads/public'
  if (path.startsWith('/leads/') && path.match(/\/leads\/\d+/)) return '/leads'
  if (path.startsWith('/opportunities/')) return '/opportunities'
  return path
})

const canViewSalesDashboard = computed(() => permissionStore.hasAnyPermission([
  'sales_dashboard:view:own',
  'sales_dashboard:view:team',
  'sales_dashboard:view:all',
]))

const shouldShowDashboardGroup = computed(() => {
  return !permissionStore.initialized || canViewSalesDashboard.value
})

const navGroups = computed<NavMainGroup[]>(() => [
  {
    label: '销售流程',
    items: [
      {
        label: 'AI Agent',
        path: '/agent',
        icon: Bot,
        active: currentPath.value.startsWith('/agent'),
      },
      {
        label: '线索管理',
        path: '/leads',
        icon: Flag,
        active: currentPath.value.startsWith('/leads'),
      },
      {
        label: '客户管理',
        path: '/customers',
        icon: Building2,
        active: currentPath.value.startsWith('/customers'),
      },
      {
        label: '客户追踪',
        path: '/customer-tracking',
        icon: ListChecks,
        active: currentPath.value.startsWith('/customer-tracking'),
        ...(pendingConfirmationBadge.value !== undefined
          ? {
              badge: pendingConfirmationBadge.value,
              badgeDescription: `待确认 ${pendingConfirmationBadge.value} 条`,
            }
          : {}),
      },
      {
        label: '商机管理',
        path: '/opportunities',
        icon: TrendingUp,
        active: currentPath.value === '/opportunities',
      },
      {
        label: '合同管理',
        path: '/contracts',
        icon: FileText,
        active: currentPath.value.startsWith('/contracts'),
      },
      {
        label: '回款计划',
        path: '/payments/plans',
        icon: Wallet,
        active: currentPath.value.startsWith('/payments/plans'),
      },
    ],
  },
  {
    label: '财务流程',
    items: [
      {
        label: '回款管理',
        path: '/payments/records',
        icon: Receipt,
        active: currentPath.value.startsWith('/payments/records'),
      },
      {
        label: '发票管理',
        path: '/invoices',
        icon: Stamp,
        active: currentPath.value.startsWith('/invoices'),
      },
    ],
  },
  ...(shouldShowDashboardGroup.value
    ? [{
        label: '数据看板',
        items: [
          {
            label: '销售看板',
            path: '/sales-dashboard',
            icon: BarChart3,
            active: currentPath.value.startsWith('/sales-dashboard'),
          },
          {
            label: '业务看板',
            path: '/business-journey-board',
            icon: Columns3,
            active: currentPath.value.startsWith('/business-journey-board'),
          },
        ],
      }]
    : []),
])

const handleMenuClick = (path: string): void => {
  router.push(path)
}

onMounted(() => {
  void refreshPendingConfirmationCount()
  confirmationRefreshTimer = window.setInterval(() => {
    void refreshPendingConfirmationCount()
  }, confirmationRefreshIntervalMs)
  window.addEventListener('focus', handleWindowFocus)
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onBeforeUnmount(() => {
  if (confirmationRefreshTimer !== undefined) {
    window.clearInterval(confirmationRefreshTimer)
  }
  window.removeEventListener('focus', handleWindowFocus)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
</script>
