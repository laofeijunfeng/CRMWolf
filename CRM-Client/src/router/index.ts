import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useTeamStore } from '@/stores/team'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/leads'
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
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
        path: 'leads',
        name: 'Leads',
        component: () => import('@/views/Leads.vue'),
        meta: { requiresAuth: true, title: '线索管理' }
      },
      {
        path: 'leads/reminder',
        name: 'FollowUpReminder',
        redirect: '/leads'
      },
      {
        path: 'customers',
        name: 'Customers',
        component: () => import('@/views/Customers.vue'),
        meta: { requiresAuth: true, title: '客户管理' }
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
        path: 'users',
        name: 'Users',
        component: () => import('@/views/Users.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'roles',
        name: 'Roles',
        redirect: '/system-config'
      },
      {
        path: 'approval-flows',
        name: 'ApprovalFlows',
        component: () => import('@/views/ApprovalFlows.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'approval-flows/create',
        name: 'ApprovalFlowCreate',
        redirect: '/system-config'
      },
      {
        path: 'approval-flows/:id/edit',
        name: 'ApprovalFlowEdit',
        redirect: '/system-config'
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
        component: () => import('@/views/ProcurementMethods.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'procurement-methods/create',
        name: 'ProcurementMethodCreate',
        component: () => import('@/views/ProcurementMethodForm.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'procurement-methods/:id/edit',
        name: 'ProcurementMethodEdit',
        component: () => import('@/views/ProcurementMethodForm.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'procurement-methods/:methodId/stages',
        name: 'ProcurementStageTemplates',
        component: () => import('@/views/ProcurementStageTemplates.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'settings',
        name: 'Settings',
        redirect: '/system-config'
      },
      {
        path: 'system-config',
        name: 'SystemConfig',
        component: () => import(
          /* webpackChunkName: "system-config" */
          '@/views/SystemConfig.vue'
        ),
        meta: { requiresAuth: true, title: '系统配置' }
      },
      {
        path: 'account',
        name: 'AccountSettings',
        component: () => import('@/views/AccountSettings.vue'),
        meta: { requiresAuth: true, title: '账户设置' }
      },
      {
        path: 'ai-config',
        name: 'AIConfig',
        redirect: '/system-config'
      },
      {
        path: 'notification-config',
        name: 'NotificationConfig',
        redirect: '/system-config'
      },
      {
        path: 'team-members',
        name: 'TeamMembers',
        component: () => import('@/views/TeamMembers.vue'),
        meta: { requiresAuth: true }
      },
      // 审批中心（Phase C / Task C3）：取代自写按钮的
      // FinanceInvoiceApprovals / FinancePaymentConfirmations，INVOICE 与 PAYMENT
      // 合一指向 ApprovalCenter，business_type 筛选分流。
      //
      // 审批入口优化（2026-07-03）：路由改为 /approvals（不是 /finance/approvals）
      // 详见：.claude/plans/jolly-frolicking-shell.md
      {
        path: 'approvals',
        name: 'ApprovalCenter',
        component: () => import('@/views/ApprovalCenter.vue'),
        meta: { requiresAuth: true, title: '财务审批' }
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
