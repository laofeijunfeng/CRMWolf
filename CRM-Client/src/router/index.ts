import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useTeamStore } from '@/stores/team'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/agent'
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/signup',
    name: 'Signup',
    component: () => import('@/views/Signup.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/invite/:code',
    name: 'InviteLogin',
    component: () => import('@/views/InviteLogin.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/auth/feishu/callback',
    name: 'FeishuCallback',
    component: () => import('@/views/FeishuCallback.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/onboarding',
    name: 'Onboarding',
    component: () => import('@/views/Onboarding.vue'),
    meta: { requiresAuth: true, requiresTeam: false }
  },
  {
    path: '/onboarding/create-team',
    name: 'TeamCreate',
    component: () => import('@/views/TeamCreate.vue'),
    meta: { requiresAuth: true, requiresTeam: false }
  },
  {
    path: '/onboarding/join-team',
    name: 'TeamJoin',
    component: () => import('@/views/TeamJoin.vue'),
    meta: { requiresAuth: true, requiresTeam: false }
  },
  {
    path: '/',
    component: () => import('@/AppLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: 'sales-dashboard',
        name: 'SalesDashboard',
        component: () => import('@/views/SalesDashboard.vue'),
        meta: { requiresAuth: true, title: '销售看板' }
      },
      {
        path: 'business-journey-board',
        name: 'BusinessJourneyBoard',
        component: () => import('@/views/BusinessJourneyBoard.vue'),
        meta: { requiresAuth: true, title: '业务看板' }
      },
      {
        path: 'agent',
        name: 'AgentChat',
        component: () => import('@/views/AgentChat.vue'),
        meta: { requiresAuth: true, title: 'AI Agent', keepAlive: true }
      },
      {
        path: 'follow-up-confirmations',
        redirect: '/customer-tracking'
      },
      {
        path: 'leads',
        name: 'Leads',
        component: () => import('@/views/Leads.vue'),
        meta: { requiresAuth: true, title: '线索管理' }
      },
      {
        path: 'customers',
        name: 'Customers',
        component: () => import('@/views/Customers.vue'),
        meta: { requiresAuth: true, title: '客户管理' }
      },
      {
        path: 'customer-tracking',
        name: 'CustomerTracking',
        component: () => import('@/views/CustomerTracking.vue'),
        meta: { requiresAuth: true, title: '客户追踪' }
      },
      {
        path: 'customers/create',
        name: 'CustomerCreate',
        component: () => import('@/views/CustomerEdit.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'customers/:id/edit',
        name: 'CustomerEdit',
        component: () => import('@/views/CustomerEdit.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'public-customers',
        name: 'PublicCustomers',
        redirect: '/customers'
      },
      {
        path: 'opportunities',
        name: 'Opportunities',
        component: () => import('@/views/Opportunities.vue'),
        meta: { requiresAuth: true, title: '商机管理' }
      },
      {
        path: 'contracts',
        name: 'Contracts',
        component: () => import('@/views/Contracts.vue'),
        meta: { requiresAuth: true, title: '合同管理' }
      },
      {
        path: 'contracts/:contractId/payment-plans/create',
        name: 'PaymentPlanCreate',
        redirect: '/contracts'
      },
      {
        path: 'sales-funnel',
        name: 'SalesFunnel',
        redirect: '/opportunities'
      },
      {
        path: 'roles',
        name: 'Roles',
        redirect: '/settings/roles'
      },
      {
        path: 'approval-flows',
        name: 'ApprovalFlows',
        redirect: '/settings/approval-flows'
      },
      {
        path: 'approval-flows/create',
        name: 'ApprovalFlowCreate',
        redirect: '/settings/approval-flows?action=create'
      },
      {
        path: 'approval-flows/:id/edit',
        name: 'ApprovalFlowEdit',
        redirect: to => ({
          path: '/settings/approval-flows',
          query: { action: 'edit', id: String(to.params['id']) }
        })
      },
      {
        path: 'payments',
        redirect: '/payments/plans'
      },
      {
        path: 'payments/plans',
        name: 'PaymentPlans',
        component: () => import('@/views/PaymentPlans.vue'),
        meta: { requiresAuth: true, title: '回款计划' }
      },
      {
        path: 'payments/records',
        name: 'PaymentRecords',
        component: () => import('@/views/PaymentRecords.vue'),
        meta: { requiresAuth: true, title: '回款管理' }
      },
      {
        path: 'payments/plans/:id',
        name: 'PaymentPlanDetail',
        redirect: to => ({
          path: '/payments/plans',
          query: { planId: String(to.params['id']) }
        })
      },
      {
        path: 'invoices',
        name: 'Invoices',
        component: () => import('@/views/Invoices.vue'),
        meta: { requiresAuth: true, title: '发票管理' }
      },
      {
        path: 'procurement-methods',
        name: 'ProcurementMethods',
        redirect: '/settings/procurement-methods'
      },
      {
        path: 'procurement-methods/create',
        name: 'ProcurementMethodCreate',
        redirect: '/settings/procurement-methods?action=create'
      },
      {
        path: 'procurement-methods/:id/edit',
        name: 'ProcurementMethodEdit',
        redirect: to => ({
          path: '/settings/procurement-methods',
          query: { action: 'edit', id: String(to.params['id']) }
        })
      },
      {
        path: 'procurement-methods/:methodId/stages',
        name: 'ProcurementStageTemplates',
        redirect: to => ({
          path: '/settings/procurement-methods',
          query: { methodId: String(to.params['methodId']) }
        })
      },
      {
        path: 'settings',
        name: 'Settings',
        redirect: '/settings/account'
      },
      {
        path: 'settings/account',
        name: 'SettingsAccount',
        component: () => import('@/views/AccountSettings.vue'),
        meta: { requiresAuth: true, title: '账户设置' }
      },
      {
        path: 'settings/team',
        name: 'SettingsTeam',
        component: () => import('@/views/TeamSettings.vue'),
        meta: { requiresAuth: true, title: '团队信息与安全', settingsKey: 'team' }
      },
      {
        path: 'settings/procurement-methods',
        name: 'SettingsProcurementMethods',
        component: () => import('@/views/SettingsModulePage.vue'),
        meta: { requiresAuth: true, title: '采购方式管理', settingsKey: 'procurement' },
        props: { module: 'procurement' }
      },
      {
        path: 'settings/procurement-methods/:methodId/stages',
        name: 'SettingsProcurementStages',
        component: () => import('@/views/ProcurementStagesSettings.vue'),
        meta: { requiresAuth: true, title: '采购阶段模板', settingsKey: 'procurement' }
      },
      {
        path: 'settings/procurement',
        name: 'SettingsProcurementLegacy',
        redirect: '/settings/procurement-methods'
      },
      {
        path: 'settings/procurement/stages/:methodId',
        name: 'SettingsProcurementStagesLegacy',
        redirect: to => ({
          path: `/settings/procurement-methods/${String(to.params['methodId'])}/stages`
        })
      },
      {
        path: 'settings/:module',
        name: 'SettingsModule',
        component: () => import('@/views/SettingsModulePage.vue'),
        meta: { requiresAuth: true, title: '系统设置' }
      },
      {
        path: 'system-config',
        name: 'SystemConfig',
        redirect: '/settings/account'
      },
      {
        path: 'account',
        name: 'AccountSettings',
        redirect: '/settings/account'
      },
      {
        path: 'ai-config',
        name: 'AIConfig',
        redirect: '/settings/ai'
      },
      {
        path: 'notification-config',
        name: 'NotificationConfig',
        redirect: '/settings/notifications'
      },
      {
        path: 'team-members',
        name: 'TeamMembers',
        redirect: '/settings/members'
      },
      // 审批中心（Phase C / Task C3）：取代自写按钮的
      // FinanceInvoiceApprovals / FinancePaymentConfirmations，INVOICE 与 PAYMENT
      // 合一指向 ApprovalCenter，business_type 筛选分流。
      //
      // 审批入口优化（2026-07-03）：路由改为 /approvals（不是 /finance/approvals）
      {
        path: 'approvals',
        name: 'ApprovalCenter',
        component: () => import('@/views/ApprovalCenter.vue'),
        meta: { requiresAuth: true, title: '审批中心' }
      },
      // 向后兼容旧深链：finance/invoice-approvals、finance/payment-confirmations
      // 重定向到统一审批中心。
      {
        path: 'finance/approvals',
        redirect: '/approvals'
      },
      {
        path: 'finance/invoice-approvals',
        redirect: '/approvals'
      },
      {
        path: 'finance/payment-confirmations',
        redirect: '/approvals'
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to, _from, next) => {
  const userStore = useUserStore()
  const teamStore = useTeamStore()
  const requiresAuth = to.meta['requiresAuth'] !== false
  const requiresTeam = to.meta['requiresTeam'] !== false

  if (requiresAuth && !userStore.isLoggedIn()) {
    next('/login')
  } else if (to.path === '/login' && userStore.isLoggedIn()) {
    next('/leads')
  } else if (requiresAuth && requiresTeam && userStore.isLoggedIn()) {
    if (!teamStore.hasTeam()) {
      try {
        await teamStore.fetchUserTeams()
        if (!teamStore.hasTeam()) {
          next('/onboarding')
          return
        }
      } catch {
        next('/onboarding')
        return
      }
    }
    next()
  } else {
    next()
  }
})

export default router
