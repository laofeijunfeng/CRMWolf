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
        meta: { requiresAuth: true }
      },
      {
        path: 'leads/create',
        name: 'LeadCreate',
        component: () => import('@/views/LeadForm.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'leads/:id/edit',
        name: 'LeadEdit',
        component: () => import('@/views/LeadForm.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'leads/:id',
        name: 'LeadDetail',
        component: () => import('@/views/LeadDetail.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'leads/public',
        name: 'PublicLeads',
        component: () => import('@/views/PublicLeads.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'leads/my',
        name: 'MyLeads',
        component: () => import('@/views/MyLeads.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'leads/reminder',
        name: 'FollowUpReminder',
        component: () => import('@/views/FollowUpReminder.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'leads/:id/convert',
        name: 'LeadConvert',
        component: () => import('@/views/LeadConvert.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'leads/convert',
        name: 'LeadConvertFromList',
        component: () => import('@/views/LeadConvert.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'customers',
        name: 'Customers',
        component: () => import('@/views/Customers.vue'),
        meta: { requiresAuth: true }
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
        path: 'customers/:id',
        name: 'CustomerDetail',
        component: () => import('@/views/CustomerDetail.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'public-customers',
        name: 'PublicCustomers',
        component: () => import('@/views/PublicCustomers.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'opportunities',
        name: 'Opportunities',
        component: () => import('@/views/Opportunities.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'opportunities/create',
        name: 'OpportunityCreate',
        component: () => import('@/views/OpportunityEdit.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'opportunities/:id/edit',
        name: 'OpportunityEdit',
        component: () => import('@/views/OpportunityEdit.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'customers/:customerId/opportunities/create',
        name: 'CustomerOpportunityCreate',
        component: () => import('@/views/OpportunityEdit.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'opportunities/:id',
        name: 'OpportunityDetail',
        component: () => import('@/views/OpportunityDetail.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'contracts',
        name: 'Contracts',
        component: () => import('@/views/Contracts.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'contracts/create',
        name: 'ContractCreate',
        component: () => import('@/views/ContractCreate.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'contracts/:id',
        name: 'ContractDetail',
        component: () => import('@/views/ContractDetail.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'contracts/edit/:id',
        name: 'ContractEdit',
        component: () => import('@/views/ContractCreate.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'contracts/:contractId/payment-plans/create',
        name: 'PaymentPlanCreate',
        component: () => import('@/views/PaymentPlanCreate.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'sales-funnel',
        name: 'SalesFunnel',
        component: () => import('@/views/SalesFunnel.vue'),
        meta: { requiresAuth: true }
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
        component: () => import('@/views/Roles.vue'),
        meta: { requiresAuth: true }
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
        component: () => import('@/views/ApprovalFlowForm.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'approval-flows/:id/edit',
        name: 'ApprovalFlowEdit',
        component: () => import('@/views/ApprovalFlowForm.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'payments',
        name: 'Payments',
        component: () => import('@/views/Payments.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'invoices',
        name: 'Invoices',
        component: () => import('@/views/Invoices.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'invoices/create',
        name: 'InvoiceCreate',
        component: () => import('@/views/InvoiceForm.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'invoices/edit/:id',
        name: 'InvoiceEdit',
        component: () => import('@/views/InvoiceForm.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'invoices/:id',
        name: 'InvoiceDetail',
        component: () => import('@/views/InvoiceDetail.vue'),
        meta: { requiresAuth: true }
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
        component: () => import('@/views/Settings.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'ai-config',
        name: 'AIConfig',
        component: () => import('@/views/AIConfig.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'notification-config',
        name: 'NotificationConfig',
        component: () => import('@/views/NotificationConfig.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'team-members',
        name: 'TeamMembers',
        component: () => import('@/views/TeamMembers.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'calendar',
        name: 'Calendar',
        component: () => import('@/views/Calendar.vue'),
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
        meta: { requiresAuth: true }
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
      },
      // TODO: 财务管理模块 - 等待后端接口实现后启用
      // {
      //   path: 'finance/dashboard',
      //   name: 'FinanceDashboard',
      //   component: () => import('@/views/FinanceDashboard.vue'),
      //   meta: { requiresAuth: true }
      // },
      // {
      //   path: 'finance/reports',
      //   name: 'FinanceReports',
      //   component: () => import('@/views/FinanceReports.vue'),
      //   meta: { requiresAuth: true }
      // },
      {
        path: 'ai-assistant',
        name: 'AIAssistant',
        component: () => import('@/views/AIAssistant.vue'),
        meta: { requiresAuth: true }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to, from, next) => {
  const userStore = useUserStore()
  const teamStore = useTeamStore()
  const requiresAuth = to.meta.requiresAuth !== false
  const requiresTeam = to.meta.requiresTeam !== false

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
