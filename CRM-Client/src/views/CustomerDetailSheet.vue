<script setup lang="ts">
/**
 * CustomerDetailSheet.vue - 客户详情抽屉组件
 *
 * 技术栈：shadcn-vue + variables-v2.scss
 * 宽度：75%（w-3/4 Tailwind 内置 class）
 *
 * 导航：使用 ContextTabs（Segmented Control 模式）放在 Header
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  Sheet,
  SheetHeader,
  SheetFooter
} from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import ErrorState from '@/components/ErrorState.vue'
import { ContextTabs } from '@/components/crmwolf'
import DetailContextHost from '@/components/crmwolf/DetailContextHost.vue'

// Panels
import FollowUpPanel from '@/components/panels/FollowUpPanel.vue'
import ContactsPanel from '@/components/panels/ContactsPanel.vue'
import ContractsPanel from '@/components/panels/ContractsPanel.vue'
import OpportunitiesPanel from '@/components/panels/OpportunitiesPanel.vue'
import InvoicesPanel from '@/components/panels/InvoicesPanel.vue'
import LicensePanel from '@/components/panels/LicensePanel.vue'
import CustomerMembersPanel from '@/components/panels/CustomerMembersPanel.vue'
import OpportunityDetailContent from '@/components/panels/OpportunityDetailContent.vue'
import ContractDetailContent from '@/components/panels/ContractDetailContent.vue'
import PaymentPlanDetailContent from '@/components/panels/PaymentPlanDetailContent.vue'
import PaymentRecordDetailContent from '@/components/panels/PaymentRecordDetailContent.vue'
import CustomerProfileContent from '@/components/panels/CustomerProfileContent.vue'

// Dialogs
import FollowUpFormDialog from '@/components/dialogs/FollowUpFormDialog.vue'
import CustomerFormDialog from '@/components/dialogs/CustomerFormDialog.vue'
import ContactFormDialog from '@/components/dialogs/ContactFormDialog.vue'
import OpportunityFormDialog from '@/components/dialogs/OpportunityFormDialog.vue'
import ContractFormDialog from '@/components/dialogs/ContractFormDialog.vue'
import InvoiceTitleFormDialog from '@/components/dialogs/InvoiceTitleFormDialog.vue'
import DeploymentInfoFormDialog from '@/components/dialogs/DeploymentInfoFormDialog.vue'
import EditRecordDialog from '@/components/dialogs/EditRecordDialog.vue'

import { Plus, Pencil } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { handleApiError } from '@/utils/errorHandler'
import customerApi, { type CustomerDetailResponse, type ContactResponse, type CustomerMemberResponse } from '@/api/customer'
import customerProfileApi from '@/api/customerProfile'
import type { CustomerProfileEvidence, CustomerProfileResponse } from '@/schemas/customerProfile'
import { getAcquisitionSourceDisplayName } from '@/schemas/acquisition-source'
import customerActivityApi, { type CustomerActivityResponse } from '@/api/customerActivity'
import { opportunityApi, type OpportunityListResponse } from '@/api/opportunity'
import contractApi, { type ContractListResponse, type ContractResponse } from '@/api/contract'
import type { PaymentPlanResponse, PaymentRecordInfo, ApprovalInfo, ApprovalInfoLite, PaymentRecordUpdate } from '@/api/payment'
import paymentApi from '@/api/payment'
import invoiceApi, { type InvoiceTitleResponse } from '@/api/invoice'
import deploymentApi, { type DeploymentInfoResponse } from '@/api/deployment'
import { normalizePaginatedResponse } from '@/types/pagination'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'
import { useApprovalStore } from '@/stores/approval'
import approvalGenericApi from '@/api/approvalGeneric'
import { confirmDelete } from '@/utils/confirmDialog'
import { toFeedbackError, type FeedbackError } from '@/types/feedback'
import type { DetailContextNode, DetailObjectType } from '@/types/detailContext'
import { useDetailContextStack } from '@/composables/useDetailContextStack'

// ==================== Props & Emits ====================
type CustomerDetailPanel = 'customer-profile' | 'customer-info' | 'followup' | 'opportunities'

interface Props {
  customerId: string | null
  targetOpportunityId?: string | null
  targetPanel?: CustomerDetailPanel | null
  visible: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:visible': [value: boolean]
  'refresh': []
  'view-customer': [customerId: string]
}>()

const userStore = useUserStore()
const permissionStore = usePermissionStore()
const approvalStore = useApprovalStore()
const detailContextStack = useDetailContextStack()
const detailContextNodes = computed(() => detailContextStack.nodes.value)
const detailContextCanGoBack = computed(() => detailContextStack.canGoBack.value)
const hasNestedDetail = computed(() => {
  const current = detailContextStack.current.value
  return current !== null && current.type !== 'customer'
})

// ==================== State ====================
const loading = ref(false)  // TODO: Task 3 - 加载客户详情数据时使用
const detailError = ref<FeedbackError | null>(null)
const activePanel = ref('customer-profile')  // Sidebar 导航切换
const refreshingCustomerProfile = ref(false)

// ==================== Dialog States ====================
const followUpDialogOpen = ref(false)
const customerEditDialogOpen = ref(false)
const contactDialogOpen = ref(false)
const opportunityDialogOpen = ref(false)
const contractDialogOpen = ref(false)
const invoiceTitleDialogOpen = ref(false)
const deploymentDialogOpen = ref(false)

// ==================== Edit States ====================
const editingContact = ref<ContactResponse | null>(null)
const editingContract = ref<ContractResponse | null>(null)
const editingInvoiceTitle = ref<InvoiceTitleResponse | null>(null)

// ==================== Detail Sheet States (Task 6) ====================
const selectedContractId = ref<number | null>(null)
const selectedPlanId = ref<number | null>(null)
const selectedRecord = ref<{ record: PaymentRecordInfo; stageName: string; approval: ApprovalInfo | ApprovalInfoLite | null; planId: number | null } | null>(null)
const recordEditDialogOpen = ref(false)
const recordEditSubmitting = ref(false)
const isRecordResubmitMode = ref(false)
const selectedOpportunityId = ref<string | null>(null)
const highlightedOpportunityId = ref<string | null>(null)
const restoreFocusOpportunityId = ref<string | null>(null)

interface ContractOpportunityContext {
  id: string
  opportunity_name: string
  customer_id: string
  customer_name?: string
  total_amount: number
  user_count: number
  license_type: string
  subscription_years: number | null
}

interface CreateContractPayload {
  opportunityId: string
  customerId: string
  customerName: string
  opportunityName: string
  totalAmount: number
  userCount: number
  licenseType: string
  subscriptionYears: number | null
}

interface OpportunityDetailContentExpose {
  refresh: () => Promise<void>
}

const fixedContractOpportunity = ref<ContractOpportunityContext | null>(null)
const opportunityDetailContentRef = ref<OpportunityDetailContentExpose | null>(null)

// ==================== Data Loading State ====================
const customer = ref<CustomerDetailResponse | null>(null)
const customerProfile = ref<CustomerProfileResponse | null>(null)
const customerProfileEvidence = ref<CustomerProfileEvidence[]>([])
const followUps = ref<CustomerActivityResponse[]>([])
const opportunities = ref<OpportunityListResponse[]>([])
const contracts = ref<ContractListResponse[]>([])
const paymentPlans = ref<PaymentPlanResponse[]>([])
const invoiceTitles = ref<InvoiceTitleResponse[]>([])
const deployments = ref<DeploymentInfoResponse[]>([])
const customerMembers = ref<CustomerMemberResponse[]>([])
type CustomerDetailPanelKey =
  | 'followUps'
  | 'opportunities'
  | 'contracts'
  | 'invoiceTitles'
  | 'deployments'
  | 'customerMembers'
  | 'customerProfile'
  | 'customerProfileEvidence'
  | 'paymentPlans'
const panelErrors = ref<Partial<Record<CustomerDetailPanelKey, FeedbackError | undefined>>>({})
const panelLoading = ref<Record<CustomerDetailPanelKey, boolean>>({
  followUps: false,
  opportunities: false,
  contracts: false,
  invoiceTitles: false,
  deployments: false,
  customerMembers: false,
  customerProfile: false,
  customerProfileEvidence: false,
  paymentPlans: false,
})
const CUSTOMER_DETAIL_PANELS: CustomerDetailPanelKey[] = [
  'followUps',
  'opportunities',
  'contracts',
  'invoiceTitles',
  'deployments',
  'customerMembers',
  'customerProfile',
  'customerProfileEvidence',
  'paymentPlans',
]
const panelRequestIds: Record<CustomerDetailPanelKey, number> = {
  followUps: 0,
  opportunities: 0,
  contracts: 0,
  invoiceTitles: 0,
  deployments: 0,
  customerMembers: 0,
  customerProfile: 0,
  customerProfileEvidence: 0,
  paymentPlans: 0,
}
let latestLoadRequestId = 0
let profileRefreshPollGeneration = 0

const PROFILE_REFRESH_POLL_INTERVAL_MS = 2000
const PROFILE_REFRESH_POLL_TIMEOUT_MS = 120000

// ==================== Navigation Tabs ====================
interface NavTabItem {
  key: string
  label: string
}

const navTabs: NavTabItem[] = [
  { key: 'customer-profile', label: '客户档案' },
  { key: 'customer-info', label: '客户信息' },
  { key: 'followup', label: '客户活动' },
  { key: 'opportunities', label: '项目旅程' }
]

// ==================== Methods ====================
const handleCreateContractForCustomer = (): void => {
  if (!canCreateContractForCustomer.value) {
    toast.error('你没有在该客户下新建合同的权限')
    return
  }
  editingContract.value = null
  fixedContractOpportunity.value = null
  contractDialogOpen.value = true
}

const handleCreateOpportunity = (): void => {
  if (!canCreateOpportunityForCustomer.value) {
    toast.error('你没有在该客户下新建商机的权限')
    return
  }
  opportunityDialogOpen.value = true
}

const handleCreateContact = (): void => {
  if (!canCreateContact.value) {
    toast.error('你没有在该客户下新建联系人的权限')
    return
  }
  contactDialogOpen.value = true
}

const handleCreateInvoiceTitle = (): void => {
  if (!canCreateInvoiceTitle.value) {
    toast.error('你没有在该客户下新建发票抬头的权限')
    return
  }
  invoiceTitleDialogOpen.value = true
}

const handleCreateFollowUp = (): void => {
  if (!canCreateActivity.value) {
    toast.error('你没有在该客户下添加跟进的权限')
    return
  }
  followUpDialogOpen.value = true
}

const handleEdit = (): void => {
  if (!canEditCurrentCustomer.value) {
    toast.error('你没有编辑该客户的权限')
    return
  }
  customerEditDialogOpen.value = true
}

const createCustomerContextNode = (customerId: string): DetailContextNode => {
  const customerName = customer.value?.account_name?.trim()
  return {
    type: 'customer',
    id: customerId,
    label: customerName !== undefined && customerName.length > 0 ? customerName : '客户详情',
    source: 'customer-detail'
  }
}

const createOpportunityContextNode = (opportunityId: string): DetailContextNode => {
  const opportunity = opportunities.value.find(item => item.id === opportunityId)
  const opportunityName = opportunity?.opportunity_name?.trim()
  const node: DetailContextNode = {
    type: 'opportunity',
    id: opportunityId,
    label: opportunityName !== undefined && opportunityName.length > 0 ? opportunityName : '商机详情',
    parentType: 'customer',
    source: 'related-object'
  }
  if (props.customerId !== null) node.parentId = props.customerId
  return node
}

const createContractContextNode = (contractId: number): DetailContextNode => {
  const contract = contracts.value.find(item => item.id === contractId)
  const contractName = contract?.contract_name?.trim()
  const node: DetailContextNode = {
    type: 'contract',
    id: String(contractId),
    label: contractName !== undefined && contractName.length > 0 ? contractName : '合同详情',
    parentType: 'customer',
    source: 'related-object'
  }
  if (props.customerId !== null) node.parentId = props.customerId
  return node
}

const createPaymentPlanContextNode = (
  planId: number,
  parentType: DetailContextNode['type'] = 'customer',
  parentId?: string
): DetailContextNode => {
  const plan = paymentPlans.value.find(item => item.id === planId)
  const planLabel = plan?.plan_number?.trim() ?? plan?.stage_name?.trim()
  const node: DetailContextNode = {
    type: 'payment-plan',
    id: String(planId),
    label: planLabel !== undefined && planLabel.length > 0 ? planLabel : '回款计划详情',
    parentType,
    source: 'related-object'
  }
  if (parentId !== undefined) node.parentId = parentId
  return node
}

const createPaymentRecordContextNode = (record: PaymentRecordInfo, planId: number): DetailContextNode => ({
  type: 'payment-record',
  id: String(record.id),
  label: `回款记录 #${record.id}`,
  parentType: 'payment-plan',
  parentId: String(planId),
  source: 'related-object'
})

const resetDetailContext = (): void => {
  if (props.customerId === null) {
    detailContextStack.closeRoot()
    return
  }
  detailContextStack.reset([createCustomerContextNode(props.customerId)])
}

const resetLocalNavigation = (): void => {
  activePanel.value = 'customer-profile'
  selectedOpportunityId.value = null
  selectedContractId.value = null
  selectedPlanId.value = null
  selectedRecord.value = null
  highlightedOpportunityId.value = null
  restoreFocusOpportunityId.value = null
  resetDetailContext()
}

const setActivePanel = (panel: string): void => {
  activePanel.value = panel
  selectedOpportunityId.value = null
  selectedContractId.value = null
  selectedPlanId.value = null
  selectedRecord.value = null
  highlightedOpportunityId.value = null
  restoreFocusOpportunityId.value = null
  resetDetailContext()
}

// ==================== Helper Functions ====================
const formatDate = (dateStr: string | null | undefined): string => {
  if (dateStr === undefined || dateStr === null || dateStr.trim() === '') return '-'
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return '-'
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const isDateBeforeToday = (dateStr: string | null | undefined): boolean => {
  if (dateStr === undefined || dateStr === null || dateStr.trim() === '') return false
  const date = new Date(`${dateStr.slice(0, 10)}T00:00:00`)
  if (Number.isNaN(date.getTime())) return false
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return date < today
}

const getLicenseStatusLabel = (licenseType: string | null | undefined, expiryDate: string | null | undefined): string => {
  if (expiryDate === undefined || expiryDate === null || expiryDate.trim() === '') return '未授权'
  if (isDateBeforeToday(expiryDate)) return '已过期'
  if (licenseType === 'TRIAL') return '试用'
  if (licenseType === 'OFFICIAL') return '正式'
  return '已授权'
}

const getLicenseStatusClass = (licenseType: string | null | undefined, expiryDate: string | null | undefined): string => {
  if (expiryDate === undefined || expiryDate === null || expiryDate.trim() === '') return 'license-badge--none'
  if (isDateBeforeToday(expiryDate)) return 'license-badge--expired'
  if (licenseType === 'TRIAL') return 'license-badge--trial'
  return 'license-badge--official'
}

const canManageCustomerMembers = computed(() => {
  if (!customer.value) return false
  if (customer.value.owner_id === String(userStore.userInfo?.id)) return true
  if (userStore.userInfo?.roles?.some(role => role.code === 'TEAM_ADMIN') === true) return true
  return permissionStore.hasAnyPermission(['customer:assign', 'customer:edit:all'])
})

const currentCustomerMember = computed(() => {
  const currentUserId = String(userStore.userInfo?.id ?? '')
  if (currentUserId === '') return undefined
  return customerMembers.value.find(member => member.user_id === currentUserId)
})

const canEditCurrentCustomer = computed(() => {
  if (!customer.value) return false
  if (permissionStore.hasPermission('customer:edit:all')) return true
  if (currentCustomerMember.value?.access_level === 'EDIT') return true
  return customer.value.owner_id === String(userStore.userInfo?.id) && permissionStore.hasPermission('customer:edit:own')
})

const canCreateActivity = computed(() => {
  if (!customer.value) return false
  if (permissionStore.hasPermission('customer:edit:all')) return true
  if (['FOLLOW_UP', 'EDIT'].includes(currentCustomerMember.value?.access_level ?? '')) return true
  return customer.value.owner_id === String(userStore.userInfo?.id)
    && permissionStore.hasAnyPermission(['customer:activity:create', 'customer:follow_up:create', 'customer:edit:own'])
})

const canCreateContact = computed(() => canEditCurrentCustomer.value)
const canEditContact = computed(() => canEditCurrentCustomer.value)
const canDeleteContact = computed(() => canEditCurrentCustomer.value)
const canSetPrimaryContact = computed(() => canEditCurrentCustomer.value)
const canCreateInvoiceTitle = computed(() =>
  canEditCurrentCustomer.value && permissionStore.hasPermission('invoice:title:create')
)
const canEditInvoiceTitle = computed(() =>
  canEditCurrentCustomer.value && permissionStore.hasPermission('invoice:title:edit')
)
const canDeleteInvoiceTitle = computed(() =>
  canEditCurrentCustomer.value && permissionStore.hasPermission('invoice:title:delete')
)
const canSetDefaultInvoiceTitle = computed(() =>
  canEditCurrentCustomer.value && permissionStore.hasPermission('invoice:title:set_default')
)
const canCreateDeployment = computed(() => canEditCurrentCustomer.value)
const canDeleteDeployment = computed(() => canEditCurrentCustomer.value)
const canCreateOpportunityForCustomer = computed(() => (
  permissionStore.hasPermission('opportunity:create') && canEditCurrentCustomer.value
))

const canCreateContractForCustomer = computed(() => (
  permissionStore.hasPermission('contract:create') && canEditCurrentCustomer.value
))

const canEditContractRow = (contract: ContractListResponse): boolean => {
  if (contract.status !== 'DRAFT') return false
  if (permissionStore.hasPermission('contract:edit:all')) return true
  return permissionStore.hasPermission('contract:edit:own')
    && contract.owner_id === String(userStore.userInfo?.id ?? '')
}

const canSubmitContractApprovalRow = (contract: ContractListResponse): boolean => (
  contract.status === 'DRAFT'
)

const canWithdrawContractApprovalRow = (contract: ContractListResponse): boolean => (
  contract.approval_phase === 'pending_review'
)

const canDeleteContractRow = (contract: ContractListResponse): boolean => {
  if (contract.approval_phase === 'pending_review' || contract.approval_phase === 'approved') return false
  if (contract.status !== 'DRAFT') return false
  if (permissionStore.hasPermission('contract:delete:all')) return true
  return permissionStore.hasPermission('contract:delete:own')
    && contract.owner_id === String(userStore.userInfo?.id ?? '')
}

// ==================== Data Loading ====================
const setPanelError = (panel: CustomerDetailPanelKey, error: FeedbackError | null): void => {
  const nextErrors = { ...panelErrors.value }
  if (error === null) {
    nextErrors[panel] = undefined
  } else {
    nextErrors[panel] = error
  }
  panelErrors.value = nextErrors
}

const setPanelLoading = (panel: CustomerDetailPanelKey, value: boolean): void => {
  panelLoading.value = { ...panelLoading.value, [panel]: value }
}

const runPanelRequest = async <T>(
  panel: CustomerDetailPanelKey,
  context: string,
  request: () => Promise<T>,
  apply: (value: T) => void,
): Promise<void> => {
  const requestId = panelRequestIds[panel] + 1
  panelRequestIds[panel] = requestId
  setPanelLoading(panel, true)
  setPanelError(panel, null)

  try {
    const value = await request()
    if (requestId !== panelRequestIds[panel]) return
    apply(value)
  } catch (error) {
    if (requestId !== panelRequestIds[panel]) return
    setPanelError(panel, toFeedbackError(error, context))
  } finally {
    if (requestId === panelRequestIds[panel]) {
      setPanelLoading(panel, false)
    }
  }
}

const loadPaymentPlansForContracts = async (
  contractList: ContractListResponse[],
): Promise<void> => {
  if (contractList.length === 0) {
    paymentPlans.value = []
    setPanelError('paymentPlans', null)
    setPanelLoading('paymentPlans', false)
    return
  }

  await runPanelRequest(
    'paymentPlans',
    '回款计划',
    async () => {
      const results = await Promise.allSettled(
        contractList.map((contract) => paymentApi.getPaymentPlans(contract.id))
      )
      const failedResult = results.find((result): result is PromiseRejectedResult => result.status === 'rejected')
      if (failedResult !== undefined) throw failedResult.reason
      return results.flatMap((result) => result.status === 'fulfilled' ? result.value : [])
    },
    (plans) => {
      paymentPlans.value = plans
    },
  )
}

const loadAllData = async (customerId: string): Promise<void> => {
  const loadRequestId = latestLoadRequestId + 1
  latestLoadRequestId = loadRequestId
  panelErrors.value = {}
  detailError.value = null
  loading.value = true
  const panelLoadSnapshot = { ...panelRequestIds }
  CUSTOMER_DETAIL_PANELS.forEach((panel) => {
    panelRequestIds[panel] += 1
    panelLoadSnapshot[panel] = panelRequestIds[panel]
    setPanelLoading(panel, true)
  })
  const isCurrentPanelLoad = (panel: CustomerDetailPanelKey): boolean =>
    panelRequestIds[panel] === panelLoadSnapshot[panel]

  try {
    const readPanel = <T>(
      result: PromiseSettledResult<T>,
      panel: CustomerDetailPanelKey,
      context: string,
      fallback: T,
    ): T => {
      if (!isCurrentPanelLoad(panel)) return fallback
      if (result.status === 'fulfilled') return result.value
      setPanelError(panel, toFeedbackError(result.reason, context))
      return fallback
    }

    const [
      customerDetailResult,
      followUpsResult,
      opportunitiesResult,
      contractsResult,
      invoiceTitlesResult,
      deploymentsResult,
      customerMembersResult,
      customerProfileResult,
      customerProfileEvidenceResult
    ] = await Promise.allSettled([
      customerApi.getCustomerDetail(customerId),
      customerActivityApi.getActivities(customerId),
      opportunityApi.getOpportunities({ customer_id: customerId }),
      contractApi.getCustomerContracts(customerId),
      invoiceApi.getInvoiceTitles(customerId),
      deploymentApi.list(customerId),
      customerApi.getCustomerMembers(customerId),
      customerProfileApi.getProfile(customerId),
      customerProfileApi.getEvidence(customerId),
    ])

    if (customerDetailResult.status === 'rejected') {
      throw customerDetailResult.reason
    }

    if (loadRequestId !== latestLoadRequestId) return

    customer.value = customerDetailResult.value
    const followUpsData = readPanel(followUpsResult, 'followUps', '客户活动', followUps.value)
    const opportunitiesData = readPanel(opportunitiesResult, 'opportunities', '商机', opportunities.value)
    const contractsData = readPanel(contractsResult, 'contracts', '合同', contracts.value)
    const invoiceTitlesData = readPanel(invoiceTitlesResult, 'invoiceTitles', '发票抬头', { invoice_titles: invoiceTitles.value })
    const deploymentsData = readPanel(deploymentsResult, 'deployments', '部署信息', deployments.value)
    const customerMembersData = readPanel(customerMembersResult, 'customerMembers', '客户团队', customerMembers.value)
    const profileData = readPanel(customerProfileResult, 'customerProfile', '客户档案', customerProfile.value)
    const profileEvidenceData = readPanel(customerProfileEvidenceResult, 'customerProfileEvidence', '客户档案证据', customerProfileEvidence.value)
    if (isCurrentPanelLoad('followUps')) followUps.value = followUpsData
    if (isCurrentPanelLoad('opportunities')) opportunities.value = normalizePaginatedResponse(opportunitiesData).items
    if (isCurrentPanelLoad('contracts')) contracts.value = contractsData
    if (isCurrentPanelLoad('invoiceTitles')) invoiceTitles.value = invoiceTitlesData.invoice_titles ?? []
    if (isCurrentPanelLoad('deployments')) deployments.value = deploymentsData
    if (isCurrentPanelLoad('customerMembers')) customerMembers.value = customerMembersData
    if (isCurrentPanelLoad('customerProfile')) customerProfile.value = profileData
    if (isCurrentPanelLoad('customerProfileEvidence')) customerProfileEvidence.value = profileEvidenceData

    CUSTOMER_DETAIL_PANELS.forEach((panel) => {
      if (panel !== 'paymentPlans' && isCurrentPanelLoad(panel)) setPanelLoading(panel, false)
    })

    if (contractsResult.status === 'fulfilled' && isCurrentPanelLoad('contracts')) {
      await loadPaymentPlansForContracts(contractsData)
    } else if (contractsResult.status === 'rejected' && isCurrentPanelLoad('contracts')) {
      // 合同请求失败时，回款计划无法可靠读取，避免把旧数据误显示成当前客户数据。
      paymentPlans.value = []
      setPanelError('paymentPlans', toFeedbackError(contractsResult.reason, '回款计划'))
      setPanelLoading('paymentPlans', false)
    }
  } catch (error) {
    if (loadRequestId !== latestLoadRequestId) return
    detailError.value = toFeedbackError(error, '客户详情')
  } finally {
    if (loadRequestId === latestLoadRequestId) {
      loading.value = false
      CUSTOMER_DETAIL_PANELS.forEach((panel) => {
        if (isCurrentPanelLoad(panel) && panelLoading.value[panel]) setPanelLoading(panel, false)
      })
    }
  }
}

const retryPanel = async (panel: CustomerDetailPanelKey): Promise<void> => {
  if (props.customerId === null) return
  activePanel.value = panel === 'followUps' ? 'followup'
    : panel === 'opportunities' ? 'opportunities'
      : panel === 'customerProfile' || panel === 'customerProfileEvidence' ? 'customer-profile'
        : 'customer-info'

  const customerId = props.customerId
  switch (panel) {
    case 'followUps':
      await runPanelRequest(panel, '客户活动', () => customerActivityApi.getActivities(customerId), (data) => { followUps.value = data })
      return
    case 'opportunities':
      await runPanelRequest(panel, '商机', () => opportunityApi.getOpportunities({ customer_id: customerId }), (data) => {
        opportunities.value = normalizePaginatedResponse(data).items
      })
      return
    case 'contracts':
      await runPanelRequest(panel, '合同', () => contractApi.getCustomerContracts(customerId), (data) => { contracts.value = data })
      if (!panelErrors.value.contracts) await loadPaymentPlansForContracts(contracts.value)
      return
    case 'invoiceTitles':
      await runPanelRequest(panel, '发票抬头', () => invoiceApi.getInvoiceTitles(customerId), (data) => { invoiceTitles.value = data.invoice_titles ?? [] })
      return
    case 'deployments':
      await runPanelRequest(panel, '部署信息', () => deploymentApi.list(customerId), (data) => { deployments.value = data })
      return
    case 'customerMembers':
      await runPanelRequest(panel, '客户团队', () => customerApi.getCustomerMembers(customerId), (data) => { customerMembers.value = data })
      return
    case 'customerProfile':
      await runPanelRequest(panel, '客户档案', () => customerProfileApi.getProfile(customerId), (data) => { customerProfile.value = data })
      return
    case 'customerProfileEvidence':
      await runPanelRequest(panel, '客户档案证据', () => customerProfileApi.getEvidence(customerId), (data) => { customerProfileEvidence.value = data })
      return
    case 'paymentPlans':
      await loadPaymentPlansForContracts(contracts.value)
      return
  }
}

const refreshCustomerMembers = async (): Promise<void> => {
  await retryPanel('customerMembers')
}

const waitForCustomerProfileRefresh = async (
  customerId: string,
  pollGeneration: number
): Promise<CustomerProfileResponse['profile_status'] | null> => {
  const deadline = Date.now() + PROFILE_REFRESH_POLL_TIMEOUT_MS

  while (Date.now() < deadline) {
    await new Promise<void>((resolve) => {
      window.setTimeout(resolve, PROFILE_REFRESH_POLL_INTERVAL_MS)
    })

    if (
      pollGeneration !== profileRefreshPollGeneration
      || !props.visible
      || props.customerId !== customerId
    ) {
      return null
    }

    try {
      const [profileData, evidenceData] = await Promise.all([
        customerProfileApi.getProfile(customerId),
        customerProfileApi.getEvidence(customerId)
      ])
      customerProfile.value = profileData
      customerProfileEvidence.value = evidenceData

      if (['READY', 'PARTIAL', 'FAILED'].includes(profileData.profile_status)) {
        return profileData.profile_status
      }
    } catch {
      // 后台任务运行期间接口可能短暂不可用，继续下一轮轮询。
    }
  }

  return null
}

const handleRefreshCustomerProfile = async (): Promise<void> => {
  if (props.customerId === null) return
  const customerId = props.customerId
  const pollGeneration = ++profileRefreshPollGeneration
  refreshingCustomerProfile.value = true
  try {
    await customerProfileApi.refresh(customerId, { scope: 'full', reason: 'manual_refresh' })
    toast.info('客户档案正在更新，完成后会自动展示最新内容')
    await loadAllData(customerId)
    const status = await waitForCustomerProfileRefresh(customerId, pollGeneration)

    if (status === 'READY' || status === 'PARTIAL') {
      toast.success('客户档案已更新')
    } else if (status === 'FAILED') {
      toast.error('客户档案更新失败，请稍后重试')
    } else if (pollGeneration === profileRefreshPollGeneration && props.visible && props.customerId === customerId) {
      toast.info('客户档案仍在后台更新，请稍后重新查看')
    }
  } catch (error) {
    handleApiError(error, '刷新客户智能档案')
  } finally {
    if (pollGeneration === profileRefreshPollGeneration) {
      refreshingCustomerProfile.value = false
    }
  }
}

// ==================== Dialog Handlers ====================
const handleCustomerEditSuccess = (): void => {
  customerEditDialogOpen.value = false
  if (props.customerId !== null) {
    void loadAllData(props.customerId)
  }
  emit('refresh')
}

// FollowUp handlers
const handleFollowUpSuccess = (): void => {
  followUpDialogOpen.value = false
  if (props.customerId !== null) {
    loadAllData(props.customerId)
    window.setTimeout(() => {
      if (props.visible && props.customerId !== null) {
        loadAllData(props.customerId)
      }
    }, 3000)
  }
}

const handleFollowUpDelete = async (followUp: { id: number }): Promise<void> => {
  try {
    await customerActivityApi.deleteActivity(followUp.id)
    toast.success('客户活动已删除')
    if (props.customerId !== null) {
      await loadAllData(props.customerId)
    }
  } catch (error) {
    handleApiError(error, '删除客户活动')
  }
}

// Contact handlers
const handleEditContact = (contact: ContactResponse): void => {
  if (!canEditContact.value) {
    toast.error('你没有编辑该客户联系人的权限')
    return
  }
  editingContact.value = contact
  contactDialogOpen.value = true
}

const handleContactDialogClose = (open: boolean): void => {
  contactDialogOpen.value = open
  if (!open) {
    editingContact.value = null
  }
}

const handleContactSuccess = (): void => {
  contactDialogOpen.value = false
  editingContact.value = null
  if (props.customerId !== null) {
    loadAllData(props.customerId)
  }
}

const handleDeleteContact = async (contactId: number): Promise<void> => {
  if (!canDeleteContact.value) {
    toast.error('你没有删除该客户联系人的权限')
    return
  }
  try {
    await customerApi.deleteContact(contactId)
    toast.success('联系人已删除')
    if (props.customerId !== null) {
      loadAllData(props.customerId)
    }
  } catch (error) {
    handleApiError(error, '删除联系人')
  }
}

const handleSetPrimaryContact = async (contactId: number): Promise<void> => {
  if (!canSetPrimaryContact.value) {
    toast.error('你没有设置主要联系人的权限')
    return
  }
  try {
    await customerApi.setPrimaryContact(contactId)
    toast.success('已设为主要联系人')
    if (props.customerId !== null) {
      loadAllData(props.customerId)
    }
  } catch (error) {
    handleApiError(error, '设置主要联系人')
  }
}

// Opportunity handlers
const handleOpportunitySuccess = (): void => {
  opportunityDialogOpen.value = false
  if (props.customerId !== null) {
    loadAllData(props.customerId)
  }
}

const handleViewOpportunity = (opportunityId: string): void => {
  activePanel.value = 'opportunities'
  if (props.customerId !== null) {
    const currentRoot = detailContextStack.nodes.value[0]
    if (currentRoot?.type !== 'customer' || currentRoot.id !== props.customerId) {
      detailContextStack.reset([createCustomerContextNode(props.customerId)])
    }
    detailContextStack.push(createOpportunityContextNode(opportunityId))
  }
  selectedContractId.value = null
  selectedPlanId.value = null
  selectedRecord.value = null
  selectedOpportunityId.value = opportunityId
  highlightedOpportunityId.value = null
  restoreFocusOpportunityId.value = null
}

const applyNavigationTarget = (): void => {
  if (props.targetOpportunityId !== undefined && props.targetOpportunityId !== null) {
    handleViewOpportunity(props.targetOpportunityId)
    return
  }

  if (props.targetPanel !== undefined && props.targetPanel !== null) {
    activePanel.value = props.targetPanel
  }
}

const syncNavigationFromContext = (): void => {
  const current = detailContextStack.current.value
  selectedOpportunityId.value = current?.type === 'opportunity' ? current.id : null
  selectedContractId.value = current?.type === 'contract' ? Number(current.id) : null
  selectedPlanId.value = current?.type === 'payment-plan'
    ? Number(current.id)
    : current?.type === 'payment-record'
      ? Number(current.parentId)
      : null

  if (current?.type === 'payment-record') {
    const recordId = Number(current.id)
    const planId = Number(current.parentId)
    const plan = paymentPlans.value.find(item => item.id === planId)
    const record = plan?.payment_records.find(item => item.id === recordId)
    if (record !== undefined && plan !== undefined) {
      selectedRecord.value = {
        record,
        stageName: plan.stage_name,
        approval: record.approval ?? (plan.latest_record_id === record.id ? plan.latest_approval : null) ?? null,
        planId
      }
    }
  } else {
    selectedRecord.value = null
  }
}

const handleBackFromOpportunity = (): void => {
  const previousOpportunityId = selectedOpportunityId.value
  detailContextStack.pop()
  syncNavigationFromContext()
  if (previousOpportunityId !== null && detailContextStack.current.value?.type === 'customer') {
    highlightedOpportunityId.value = previousOpportunityId
    restoreFocusOpportunityId.value = previousOpportunityId
  }
}

const handleBackFromContract = (): void => {
  detailContextStack.pop()
  syncNavigationFromContext()
}

const handleContextBack = (): void => {
  const currentType = detailContextStack.current.value?.type
  if (currentType === 'opportunity') {
    handleBackFromOpportunity()
    return
  }
  detailContextStack.pop()
  syncNavigationFromContext()
}

const handleContextNavigate = (index: number): void => {
  while (detailContextStack.depth.value > index + 1 && detailContextStack.canGoBack.value) {
    detailContextStack.pop()
  }
  syncNavigationFromContext()
}

const handleContextClose = (): void => {
  detailContextStack.closeRoot()
  selectedOpportunityId.value = null
  selectedContractId.value = null
  selectedPlanId.value = null
  selectedRecord.value = null
  emit('update:visible', false)
}

const handleOpportunityDetailRefresh = (): void => {
  if (props.customerId !== null) {
    void loadAllData(props.customerId)
  }
}

const handleOpportunityDetailCreateContract = (payload: CreateContractPayload): void => {
  fixedContractOpportunity.value = {
    id: payload.opportunityId,
    opportunity_name: payload.opportunityName,
    customer_id: payload.customerId,
    customer_name: payload.customerName,
    total_amount: payload.totalAmount,
    user_count: payload.userCount,
    license_type: payload.licenseType,
    subscription_years: payload.subscriptionYears
  }
  contractDialogOpen.value = true
}

const handleContractDialogClose = (open: boolean): void => {
  contractDialogOpen.value = open
  if (!open) {
    editingContract.value = null
    fixedContractOpportunity.value = null
  }
}

const handleContractSuccess = (): void => {
  contractDialogOpen.value = false
  editingContract.value = null
  fixedContractOpportunity.value = null
  void opportunityDetailContentRef.value?.refresh()
  void retryPanel('contracts')
}

const refreshContractRelations = (): void => {
  void opportunityDetailContentRef.value?.refresh()
  void retryPanel('contracts')
}

const handleEditContract = async (contract: ContractListResponse): Promise<void> => {
  try {
    editingContract.value = await contractApi.getContract(contract.id)
    contractDialogOpen.value = true
  } catch (error) {
    handleApiError(error, '获取合同详情')
  }
}

const handleDeleteContract = async (contract: ContractListResponse): Promise<void> => {
  const confirmed = await confirmDelete(`合同 "${contract.contract_name}"`)
  if (!confirmed) return

  try {
    await contractApi.deleteContract(contract.id)
    toast.success('合同删除成功')
    refreshContractRelations()
  } catch (error) {
    handleApiError(error, '删除合同')
  }
}

const handleSubmitContractApproval = async (contract: ContractListResponse): Promise<void> => {
  try {
    await approvalGenericApi.submitApproval('CONTRACT', contract.id)
    toast.success('合同已提交审批')
    refreshContractRelations()
  } catch (error) {
    handleApiError(error, '提交审批')
  }
}

const handleWithdrawContractApproval = async (contract: ContractListResponse): Promise<void> => {
  try {
    await approvalGenericApi.cancelApproval('CONTRACT', contract.id)
    toast.success('合同审批已撤回')
    refreshContractRelations()
  } catch (error) {
    handleApiError(error, '撤回审批')
  }
}

// Invoice Title handlers
const handleEditInvoiceTitle = (invoiceTitle: InvoiceTitleResponse): void => {
  if (!canEditInvoiceTitle.value) {
    toast.error('你没有编辑该客户发票抬头的权限')
    return
  }
  editingInvoiceTitle.value = invoiceTitle
  invoiceTitleDialogOpen.value = true
}

const handleInvoiceTitleDialogClose = (open: boolean): void => {
  invoiceTitleDialogOpen.value = open
  if (!open) {
    editingInvoiceTitle.value = null
  }
}

const handleInvoiceTitleSuccess = (): void => {
  invoiceTitleDialogOpen.value = false
  editingInvoiceTitle.value = null
  void retryPanel('invoiceTitles')
}

const handleDeleteInvoiceTitle = async (titleId: number): Promise<void> => {
  if (!canDeleteInvoiceTitle.value) {
    toast.error('你没有删除该客户发票抬头的权限')
    return
  }
  try {
    await invoiceApi.deleteInvoiceTitle(titleId)
    toast.success('发票抬头已删除')
    void retryPanel('invoiceTitles')
  } catch (error) {
    handleApiError(error, '删除发票抬头')
  }
}

const handleSetDefaultInvoiceTitle = async (titleId: number): Promise<void> => {
  if (!canSetDefaultInvoiceTitle.value) {
    toast.error('你没有设置默认发票抬头的权限')
    return
  }
  try {
    await invoiceApi.setDefaultInvoiceTitle(titleId)
    toast.success('已设为默认发票抬头')
    void retryPanel('invoiceTitles')
  } catch (error) {
    handleApiError(error, '设置默认发票抬头')
  }
}

// License handlers
const handleCreateDeployment = (): void => {
  if (!canCreateDeployment.value) {
    toast.error('你没有在该客户下新建部署信息的权限')
    return
  }
  deploymentDialogOpen.value = true
}

const handleDeploymentSuccess = (): void => {
  deploymentDialogOpen.value = false
  void retryPanel('deployments')
}

const handleDeleteDeployment = async (deploymentId: number): Promise<void> => {
  if (!canDeleteDeployment.value) {
    toast.error('你没有删除该客户部署信息的权限')
    return
  }
  try {
    await deploymentApi.deleteDeployment(deploymentId)
    toast.success('部署信息已删除')
    void retryPanel('deployments')
  } catch (error) {
    handleApiError(error, '删除部署信息')
  }
}

// Contract and payment-plan detail navigation.
const handleViewContract = (contractId: number): void => {
  if (props.customerId !== null) {
    const currentRoot = detailContextStack.nodes.value[0]
    if (currentRoot?.type !== 'customer' || currentRoot.id !== props.customerId) {
      detailContextStack.reset([createCustomerContextNode(props.customerId)])
    }
    detailContextStack.push(createContractContextNode(contractId))
  }
  selectedOpportunityId.value = null
  selectedContractId.value = contractId
  selectedPlanId.value = null
  selectedRecord.value = null
}

const handleViewContractFromOpportunity = (contractId: number): void => {
  const opportunityId = selectedOpportunityId.value
  if (opportunityId !== null && props.customerId !== null) {
    const currentRoot = detailContextStack.nodes.value[0]
    if (currentRoot?.type !== 'customer' || currentRoot.id !== props.customerId) {
      detailContextStack.reset([createCustomerContextNode(props.customerId)])
    }
    detailContextStack.push(createOpportunityContextNode(opportunityId))
    detailContextStack.push({
      ...createContractContextNode(contractId),
      parentType: 'opportunity',
      parentId: opportunityId
    })
  }
  selectedOpportunityId.value = null
  selectedContractId.value = contractId
  selectedPlanId.value = null
  selectedRecord.value = null
}

const handleViewPaymentPlan = (planId: number, plan?: PaymentPlanResponse): void => {
  if (props.customerId === null) return
  const root = detailContextStack.nodes.value[0]
  if (root?.type !== 'customer' || root.id !== props.customerId) {
    detailContextStack.reset([createCustomerContextNode(props.customerId)])
  }
  const parent = detailContextStack.current.value
  const parentType = parent?.type === 'opportunity' || parent?.type === 'contract'
    ? parent.type
    : 'customer'
  const parentId = parentType === 'customer' ? props.customerId : parent?.id
  detailContextStack.push(createPaymentPlanContextNode(planId, parentType, parentId))
  selectedOpportunityId.value = null
  selectedContractId.value = null
  selectedPlanId.value = planId
  selectedRecord.value = null
  if (plan !== undefined) {
    // Keep the list response available for immediate record navigation; the content
    // component still reloads server-authoritative detail by ID.
    paymentPlans.value = paymentPlans.value.some(item => item.id === plan.id)
      ? paymentPlans.value
      : [...paymentPlans.value, plan]
  }
}

const handleViewPaymentPlanFromOpportunity = (planId: number, plan: PaymentPlanResponse): void => {
  handleViewPaymentPlan(planId, plan)
}

const handleViewPaymentPlanFromContract = (plan: PaymentPlanResponse): void => {
  handleViewPaymentPlan(plan.id, plan)
}

const handleContractSheetRefresh = (): void => {
  void retryPanel('contracts')
}

const handlePlanDetailRefresh = async (): Promise<void> => {
  await retryPanel('paymentPlans')
  syncSelectedPaymentRecord()
}

// Payment record detail navigation.
const handleRecordClick = (record: PaymentRecordInfo): void => {
  const selectedPlanIdValue = selectedPlanId.value
  const plan = paymentPlans.value.find(item =>
    item.payment_records?.some(itemRecord => itemRecord.id === record.id)
  )
  const planId = plan?.id ?? selectedPlanIdValue
  if (planId === null) return

  const current = detailContextStack.current.value
  if (current?.type !== 'payment-plan' || current.id !== String(planId)) {
    handleViewPaymentPlan(planId, plan)
  }

  const activePlan = paymentPlans.value.find(item => item.id === planId) ?? plan
  const approval = record.approval ?? (activePlan?.latest_record_id === record.id ? activePlan.latest_approval : null) ?? null
  selectedRecord.value = {
    record,
    stageName: activePlan?.stage_name ?? '',
    approval,
    planId
  }
  detailContextStack.push(createPaymentRecordContextNode(record, planId))
}

const syncSelectedPaymentRecord = (): void => {
  const selected = selectedRecord.value
  if (selected === null) return
  const plan = paymentPlans.value.find(item =>
    item.payment_records?.some(record => record.id === selected.record.id)
  )
  const updatedRecord = plan?.payment_records?.find(record => record.id === selected.record.id)
  if (updatedRecord === undefined) return
  selectedRecord.value = {
    record: updatedRecord,
    stageName: plan?.stage_name ?? selected.stageName,
    approval: updatedRecord.approval ?? (plan?.latest_record_id === updatedRecord.id ? plan.latest_approval : null) ?? null,
    planId: plan?.id ?? selected.planId
  }
}

const handleRecordResubmit = (): void => {
  if (selectedRecord.value === null) return
  isRecordResubmitMode.value = true
  recordEditDialogOpen.value = true
}

const handleRecordEdit = (): void => {
  if (selectedRecord.value === null) return
  isRecordResubmitMode.value = false
  recordEditDialogOpen.value = true
}

const handleRecordEditDialogOpenChange = (open: boolean): void => {
  recordEditDialogOpen.value = open
  if (!open) {
    isRecordResubmitMode.value = false
  }
}

const handleRecordEditSubmit = async (recordId: number, payload: PaymentRecordUpdate): Promise<void> => {
  recordEditSubmitting.value = true
  try {
    await paymentApi.updatePaymentRecord(recordId, payload)
    if (isRecordResubmitMode.value) {
      const res = await approvalStore.submitEntity('PAYMENT', recordId)
      toast.success(res.approval_id === 0 ? '未配置审批流，已转为财务确认' : '已重新提交审批')
    } else {
      toast.success('回款记录更新成功')
    }
    recordEditDialogOpen.value = false
    isRecordResubmitMode.value = false
    await handlePlanDetailRefresh()
  } catch (error: unknown) {
    handleApiError(error, isRecordResubmitMode.value ? '重新提交审批' : '更新回款记录')
  } finally {
    recordEditSubmitting.value = false
  }
}

// Contract detail approval handlers (Task 6 fix)
const handleContractApprove = (): void => {
  // ContractDetailContent handles the action internally, just refresh parent data
  handleContractSheetRefresh()
}

const handleContractReject = (): void => {
  // ContractDetailContent handles the action internally, just refresh parent data
  handleContractSheetRefresh()
}

// Payment-plan actions that keep the same detail host.
const handlePaymentPlanDetailViewContract = (contractId: number): void => {
  const current = detailContextStack.current.value
  if (current?.type === 'payment-plan') {
    const parent = detailContextStack.nodes.value[detailContextStack.nodes.value.length - 2]
    const parentType: DetailObjectType =
      parent?.type === 'opportunity' || parent?.type === 'contract'
        ? parent.type
        : 'customer'
    const contractNode: DetailContextNode = {
      ...createContractContextNode(contractId),
      parentType
    }
    if (parentType === 'customer') {
      if (props.customerId !== null) contractNode.parentId = props.customerId
    } else if (parent !== undefined) {
      contractNode.parentId = parent.id
    }
    detailContextStack.replace(contractNode)
  } else {
    handleViewContract(contractId)
  }
  selectedPlanId.value = null
  selectedRecord.value = null
  selectedOpportunityId.value = null
  selectedContractId.value = contractId
}

const handlePaymentPlanDetailViewCustomer = (customerId: string, _plan: PaymentPlanResponse): void => {
  if (customerId === props.customerId) {
    detailContextStack.reset(props.customerId === null ? [] : [createCustomerContextNode(props.customerId)])
    selectedOpportunityId.value = null
    selectedContractId.value = null
    selectedPlanId.value = null
    selectedRecord.value = null
    return
  }
  emit('view-customer', customerId)
}

const handlePaymentPlanDetailViewApproval = (record: PaymentRecordInfo): void => {
  handleRecordClick(record)
}

// ==================== Watch ====================
watch(() => props.visible, (visible): void => {
  if (!visible) {
    profileRefreshPollGeneration += 1
    refreshingCustomerProfile.value = false
  }

  if (visible && props.customerId !== null) {
    resetLocalNavigation()
    applyNavigationTarget()
    loadAllData(props.customerId)
  } else if (!visible) {
    // 清理状态
    resetLocalNavigation()
    customer.value = null
    customerProfile.value = null
    customerProfileEvidence.value = []
    followUps.value = []
    opportunities.value = []
    contracts.value = []
    paymentPlans.value = []
    invoiceTitles.value = []
    deployments.value = []
    // Clear nested sheet states
    selectedContractId.value = null
    selectedPlanId.value = null
    selectedRecord.value = null
      fixedContractOpportunity.value = null
    customerEditDialogOpen.value = false
    deploymentDialogOpen.value = false
  }
}, { immediate: true })

watch(() => props.customerId, (customerId, previousCustomerId): void => {
  if (customerId !== previousCustomerId) {
    profileRefreshPollGeneration += 1
    refreshingCustomerProfile.value = false
    deploymentDialogOpen.value = false
  }
  if (!props.visible || customerId === null || customerId === previousCustomerId) return
  resetLocalNavigation()
  applyNavigationTarget()
  selectedContractId.value = null
  loadAllData(customerId)
})

watch(() => props.targetOpportunityId, (opportunityId): void => {
  if (!props.visible || opportunityId === undefined || opportunityId === null) return
  handleViewOpportunity(opportunityId)
})

watch(() => props.targetPanel, (panel): void => {
  const hasTargetOpportunity = props.targetOpportunityId !== undefined && props.targetOpportunityId !== null
  if (!props.visible || panel === undefined || panel === null || hasTargetOpportunity) return
  activePanel.value = panel
})
onBeforeUnmount(() => {
  profileRefreshPollGeneration += 1
})

</script>

<template>
  <Sheet :open="visible" @update:open="emit('update:visible', $event)">
    <DetailSheetContent>
      <Transition name="drilldown-fade" mode="out-in">
        <DetailContextHost
          v-if="hasNestedDetail"
          :nodes="detailContextNodes"
          :can-go-back="detailContextCanGoBack"
          @back="handleContextBack"
          @close="handleContextClose"
          @navigate="handleContextNavigate"
        >
          <OpportunityDetailContent
            v-if="selectedOpportunityId !== null"
            ref="opportunityDetailContentRef"
            :opportunity-id="selectedOpportunityId"
            embedded
            :customer-context="{
              customerId: customerId ?? '',
              customerName: customer?.account_name
            }"
            :can-edit-customer-context="canEditCurrentCustomer"
            @back="handleBackFromOpportunity"
            @close="handleContextClose"
            @refresh="handleOpportunityDetailRefresh"
            @create-contract="handleOpportunityDetailCreateContract"
            @edit-contract="handleEditContract"
            @submit-contract-approval="handleSubmitContractApproval"
            @withdraw-contract-approval="handleWithdrawContractApproval"
            @delete-contract="handleDeleteContract"
            @view-contract="handleViewContractFromOpportunity"
            @view-payment-plan="handleViewPaymentPlanFromOpportunity"
            :show-breadcrumb="false"
          />

          <ContractDetailContent
            v-else-if="selectedContractId !== null"
            :contract-id="selectedContractId"
            embedded
            @back="handleBackFromContract"
            @close="handleContextClose"
            @refresh="handleContractSheetRefresh"
            @approve="handleContractApprove"
            @reject="handleContractReject"
            @view-payment-plan="handleViewPaymentPlanFromContract"
            :show-breadcrumb="false"
          />

          <PaymentRecordDetailContent
            v-else-if="selectedRecord !== null"
            :record-id="selectedRecord.record.id"
            :record="selectedRecord.record"
            :stage-name="selectedRecord.stageName"
            :approval="selectedRecord.approval"
            embedded
            @refresh="handlePlanDetailRefresh"
            @edit="handleRecordEdit"
            @resubmit="handleRecordResubmit"
            @close="handleContextClose"
          />

          <PaymentPlanDetailContent
            v-else-if="selectedPlanId !== null"
            :plan-id="selectedPlanId"
            embedded
            @refresh="handlePlanDetailRefresh"
            @record-click="handleRecordClick"
            @view-approval="handlePaymentPlanDetailViewApproval"
            @view-contract="handlePaymentPlanDetailViewContract"
            @view-customer="handlePaymentPlanDetailViewCustomer"
            @close="handleContextClose"
          />
        </DetailContextHost>
      </Transition>

      <template v-if="!hasNestedDetail">
        <!-- Header -->
        <SheetHeader class="customer-detail-sheet__header p-6 border-b border-wolf-border-default-v2">
          <!-- ContextTabs 导航 -->
          <ContextTabs
            :tabs="navTabs"
            :active-tab="activePanel"
            @update:activeTab="setActivePanel"
            class="w-full"
          />
        </SheetHeader>

        <!-- Content -->
        <ScrollArea class="flex-1">
          <div v-if="loading && customer === null" class="customer-detail-loading" aria-busy="true" aria-live="polite">
            <div class="loading-spinner" />
            <span>正在加载客户详情…</span>
          </div>
          <div v-else-if="detailError" class="customer-detail-state">
            <ErrorState
              :variant="detailError.variant ?? 'error'"
              :title="detailError.title"
              :description="detailError.description"
            >
              <template #action>
                <Button v-if="detailError.retryable !== false" type="button" @click="customerId !== null && loadAllData(customerId)">
                  重新加载
                </Button>
              </template>
            </ErrorState>
          </div>
          <div v-else class="p-6 space-y-6">
            <template v-if="activePanel === 'customer-profile'">
              <div
                v-if="panelLoading.customerProfile"
                class="customer-detail-panel-loading"
                aria-busy="true"
                aria-live="polite"
              >
                <div class="loading-spinner loading-spinner--small" />
                <span>正在加载客户档案…</span>
              </div>
              <ErrorState
                v-else-if="panelErrors.customerProfile"
                :variant="panelErrors.customerProfile.variant ?? 'error'"
                :title="panelErrors.customerProfile.title"
                :description="panelErrors.customerProfile.description"
              >
                <template #action>
                  <Button v-if="panelErrors.customerProfile.retryable !== false" type="button" :loading="panelLoading.customerProfile" @click="retryPanel('customerProfile')">
                    重试加载
                  </Button>
                </template>
              </ErrorState>
              <CustomerProfileContent
                v-else
                :profile="customerProfile"
                :evidence="customerProfileEvidence"
                :customer="customer"
                :customer-name="customer?.account_name ?? '客户'"
                :refreshing="refreshingCustomerProfile"
                @refresh="handleRefreshCustomerProfile"
              />
              <ErrorState
                v-if="panelErrors.customerProfileEvidence"
                :variant="panelErrors.customerProfileEvidence.variant ?? 'error'"
                :title="panelErrors.customerProfileEvidence.title"
                :description="panelErrors.customerProfileEvidence.description"
              >
                <template #action>
                  <Button v-if="panelErrors.customerProfileEvidence.retryable !== false" type="button" :loading="panelLoading.customerProfileEvidence" @click="retryPanel('customerProfileEvidence')">
                    重试加载证据
                  </Button>
                </template>
              </ErrorState>
            </template>

            <template v-if="activePanel === 'customer-info'">
              <!-- 基本信息卡片 -->
              <Card class="info-card">
                <CardContent class="p-0">
                  <div class="p-4 border-b border-wolf-border-light-v2">
                    <h3 class="text-sm font-semibold text-wolf-text-primary-v2 truncate">
                      {{ customer?.account_name || '基本信息' }}
                    </h3>
                  </div>
                  <div class="p-4">
                    <div class="attributes-grid">
                      <div class="attribute-item">
                        <div class="attribute-label">客户来源</div>
                        <div class="attribute-value">{{ getAcquisitionSourceDisplayName(customer) }}</div>
                      </div>
                      <div class="attribute-item">
                        <div class="attribute-label">所在城市</div>
                        <div class="attribute-value">{{ customer?.city || '-' }}</div>
                      </div>
                      <div class="attribute-item">
                        <div class="attribute-label">公司地址</div>
                        <div class="attribute-value">{{ customer?.address || '-' }}</div>
                      </div>
                      <div class="attribute-item">
                        <div class="attribute-label">负责销售</div>
                        <div class="attribute-value">{{ customer?.owner_info?.name || '-' }}</div>
                      </div>
                      <div class="attribute-item">
                        <div class="attribute-label">采购方式</div>
                        <div class="attribute-value">{{ customer?.default_procurement_method_info?.name || '-' }}</div>
                      </div>
                      <div class="attribute-item">
                        <div class="attribute-label">授权状态</div>
                        <div class="attribute-value">
                          <span
                            class="license-badge"
                            :class="getLicenseStatusClass(customer?.license_type, customer?.license_expiry_date)"
                          >
                            {{ getLicenseStatusLabel(customer?.license_type, customer?.license_expiry_date) }}
                          </span>
                        </div>
                      </div>
                      <div class="attribute-item">
                        <div class="attribute-label">授权到期</div>
                        <div class="attribute-value">{{ formatDate(customer?.license_expiry_date) }}</div>
                      </div>
                      <div class="attribute-item">
                        <div class="attribute-label">创建人</div>
                        <div class="attribute-value">{{ customer?.creator_info?.name || '-' }}</div>
                      </div>
                      <div class="attribute-item">
                        <div class="attribute-label">创建时间</div>
                        <div class="attribute-value">{{ customer?.created_time ? formatDate(customer.created_time) : '-' }}</div>
                      </div>
                      <div class="attribute-item">
                        <div class="attribute-label">最后修改</div>
                        <div class="attribute-value">{{ customer?.last_modified_time ? formatDate(customer.last_modified_time) : '-' }}</div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <div v-if="panelLoading.contracts" class="customer-detail-panel-loading" aria-busy="true" aria-live="polite">
                <div class="loading-spinner loading-spinner--small" />
                <span>正在加载合同…</span>
              </div>
              <ErrorState
                v-else-if="panelErrors.contracts"
                :variant="panelErrors.contracts.variant ?? 'error'"
                :title="panelErrors.contracts.title"
                :description="panelErrors.contracts.description"
              >
                <template #action>
                  <Button v-if="panelErrors.contracts.retryable !== false" type="button" :loading="panelLoading.contracts" @click="retryPanel('contracts')">
                    重试加载合同
                  </Button>
                </template>
              </ErrorState>
              <ContractsPanel
                v-else
                :customer-id="customerId ?? ''"
                :contracts="contracts"
                :show-add="canCreateContractForCustomer"
                :can-edit="canEditContractRow"
                :can-submit-approval="canSubmitContractApprovalRow"
                :can-withdraw-approval="canWithdrawContractApprovalRow"
                :can-delete="canDeleteContractRow"
                @add="handleCreateContractForCustomer"
                @view="handleViewContract"
                @edit="handleEditContract"
                @submit-approval="handleSubmitContractApproval"
                @withdraw-approval="handleWithdrawContractApproval"
                @delete="handleDeleteContract"
              />

              <ContactsPanel
                :customer-id="customerId ?? ''"
                :contacts="customer?.contacts ?? []"
                :show-add="canCreateContact"
                :can-edit="canEditContact"
                :can-delete="canDeleteContact"
                :can-set-primary="canSetPrimaryContact"
                @add="handleCreateContact"
                @edit="handleEditContact"
                @delete="handleDeleteContact"
                @set-primary="handleSetPrimaryContact"
              />

              <div v-if="panelLoading.invoiceTitles" class="customer-detail-panel-loading" aria-busy="true" aria-live="polite">
                <div class="loading-spinner loading-spinner--small" />
                <span>正在加载发票抬头…</span>
              </div>
              <ErrorState
                v-else-if="panelErrors.invoiceTitles"
                :variant="panelErrors.invoiceTitles.variant ?? 'error'"
                :title="panelErrors.invoiceTitles.title"
                :description="panelErrors.invoiceTitles.description"
              >
                <template #action>
                  <Button v-if="panelErrors.invoiceTitles.retryable !== false" type="button" :loading="panelLoading.invoiceTitles" @click="retryPanel('invoiceTitles')">
                    重试加载发票抬头
                  </Button>
                </template>
              </ErrorState>
              <InvoicesPanel
                v-else
                :customer-id="customerId ?? ''"
                :invoice-titles="invoiceTitles"
                :invoice-applications="[]"
                :show-invoice-applications="false"
                :show-add-title="canCreateInvoiceTitle"
                :show-title-apply-action="false"
                :can-edit-title="canEditInvoiceTitle"
                :can-delete-title="canDeleteInvoiceTitle"
                :can-set-default-title="canSetDefaultInvoiceTitle"
                @add="handleCreateInvoiceTitle"
                @edit="handleEditInvoiceTitle"
                @delete="handleDeleteInvoiceTitle"
                @set-default="handleSetDefaultInvoiceTitle"
              />

              <div v-if="panelLoading.deployments" class="customer-detail-panel-loading" aria-busy="true" aria-live="polite">
                <div class="loading-spinner loading-spinner--small" />
                <span>正在加载部署信息…</span>
              </div>
              <ErrorState
                v-else-if="panelErrors.deployments"
                :variant="panelErrors.deployments.variant ?? 'error'"
                :title="panelErrors.deployments.title"
                :description="panelErrors.deployments.description"
              >
                <template #action>
                  <Button v-if="panelErrors.deployments.retryable !== false" type="button" :loading="panelLoading.deployments" @click="retryPanel('deployments')">
                    重试加载部署信息
                  </Button>
                </template>
              </ErrorState>
              <LicensePanel
                v-else
                :customer-id="customerId ?? ''"
                :customer-name="customer?.account_name ?? null"
                :license-applications="[]"
                :deployments="deployments"
                :show-license-applications="false"
                :show-add-deployment="canCreateDeployment"
                :can-delete-deployment="canDeleteDeployment"
                @add-deployment="handleCreateDeployment"
                @delete-deployment="handleDeleteDeployment"
              />

              <div v-if="panelLoading.customerMembers" class="customer-detail-panel-loading" aria-busy="true" aria-live="polite">
                <div class="loading-spinner loading-spinner--small" />
                <span>正在加载客户团队…</span>
              </div>
              <ErrorState
                v-else-if="panelErrors.customerMembers"
                :variant="panelErrors.customerMembers.variant ?? 'error'"
                :title="panelErrors.customerMembers.title"
                :description="panelErrors.customerMembers.description"
              >
                <template #action>
                  <Button v-if="panelErrors.customerMembers.retryable !== false" type="button" :loading="panelLoading.customerMembers" @click="retryPanel('customerMembers')">
                    重试加载客户团队
                  </Button>
                </template>
              </ErrorState>
              <CustomerMembersPanel
                v-else
                :customer-id="customerId ?? ''"
                :members="customerMembers"
                :can-manage-members="canManageCustomerMembers"
                @refresh="refreshCustomerMembers"
              />
            </template>

            <!-- 根据 activePanel 显示对应面板 -->
            <div v-if="activePanel === 'followup' && panelLoading.followUps" class="customer-detail-panel-loading" aria-busy="true" aria-live="polite">
              <div class="loading-spinner loading-spinner--small" />
              <span>正在加载客户活动…</span>
            </div>
            <ErrorState
              v-else-if="activePanel === 'followup' && panelErrors.followUps"
              :variant="panelErrors.followUps.variant ?? 'error'"
              :title="panelErrors.followUps.title"
              :description="panelErrors.followUps.description"
            >
              <template #action>
                <Button v-if="panelErrors.followUps.retryable !== false" type="button" :loading="panelLoading.followUps" @click="retryPanel('followUps')">
                  重试加载客户活动
                </Button>
              </template>
            </ErrorState>
            <FollowUpPanel
              v-if="activePanel === 'followup' && !panelErrors.followUps"
              :follow-ups="followUps"
              :current-user-id="String(userStore.userInfo?.id)"
              :show-header="false"
              :show-add="canCreateActivity"
              @add="handleCreateFollowUp"
              @delete="handleFollowUpDelete"
            />

            <div v-if="activePanel === 'opportunities' && panelLoading.opportunities" class="customer-detail-panel-loading" aria-busy="true" aria-live="polite">
              <div class="loading-spinner loading-spinner--small" />
              <span>正在加载商机…</span>
            </div>
            <ErrorState
              v-else-if="activePanel === 'opportunities' && panelErrors.opportunities"
              :variant="panelErrors.opportunities.variant ?? 'error'"
              :title="panelErrors.opportunities.title"
              :description="panelErrors.opportunities.description"
            >
              <template #action>
                <Button v-if="panelErrors.opportunities.retryable !== false" type="button" :loading="panelLoading.opportunities" @click="retryPanel('opportunities')">
                  重试加载商机
                </Button>
              </template>
            </ErrorState>
            <OpportunitiesPanel
              v-if="activePanel === 'opportunities' && !panelErrors.opportunities"
              :customer-id="customerId ?? ''"
              :opportunities="opportunities"
              :highlighted-opportunity-id="highlightedOpportunityId ?? undefined"
              :restore-focus-opportunity-id="restoreFocusOpportunityId ?? undefined"
              :show-add="canCreateOpportunityForCustomer"
              @add="handleCreateOpportunity"
              @view="handleViewOpportunity"
            />
          </div>
        </ScrollArea>

        <!-- Footer -->
        <SheetFooter
          v-if="activePanel !== 'customer-profile'"
          class="customer-detail-sheet__footer p-4 border-t border-wolf-border-default-v2"
        >
          <template v-if="activePanel === 'customer-info'">
            <Button v-if="canCreateContact" variant="default" @click="handleCreateContact">
              <Plus class="w-4 h-4 mr-2" />
              新建联系人
            </Button>
            <Button v-if="canCreateInvoiceTitle" variant="outline" @click="handleCreateInvoiceTitle">
              <Plus class="w-4 h-4 mr-2" />
              新建抬头
            </Button>
            <Button v-if="canCreateDeployment" variant="outline" @click="handleCreateDeployment">
              <Plus class="w-4 h-4 mr-2" />
              新建部署
            </Button>
            <Button v-if="canEditCurrentCustomer" variant="outline" @click="handleEdit">
              <Pencil class="w-4 h-4 mr-2" />
              编辑
            </Button>
          </template>

          <template v-else-if="activePanel === 'followup' && canCreateActivity">
            <Button variant="default" @click="handleCreateFollowUp">
              <Plus class="w-4 h-4 mr-2" />
              添加活动
            </Button>
          </template>

          <template v-else-if="activePanel === 'opportunities' && canCreateOpportunityForCustomer">
            <Button variant="default" @click="handleCreateOpportunity">
              <Plus class="w-4 h-4 mr-2" />
              新建商机
            </Button>
          </template>
        </SheetFooter>
      </template>
    </DetailSheetContent>
  </Sheet>

  <!-- Dialogs -->
  <FollowUpFormDialog
    v-if="customerId !== null"
    :customer-id="customerId"
    :open="followUpDialogOpen"
    @update:open="followUpDialogOpen = $event"
    @success="handleFollowUpSuccess"
  />

  <CustomerFormDialog
    v-if="customerId !== null"
    mode="edit"
    :customer-id="customerId"
    :open="customerEditDialogOpen"
    @update:open="customerEditDialogOpen = $event"
    @success="handleCustomerEditSuccess"
  />

  <ContactFormDialog
    v-if="customerId !== null"
    :customer-id="customerId"
    :open="contactDialogOpen"
    :contact="editingContact"
    :available-contacts="customer?.contacts ?? []"
    @update:open="handleContactDialogClose"
    @success="handleContactSuccess"
  />

  <OpportunityFormDialog
    v-if="customerId !== null"
    :customer-id="customerId"
    :customer-name="customer?.account_name"
    :customer-locked="true"
    :open="opportunityDialogOpen"
    @update:open="opportunityDialogOpen = $event"
    @success="handleOpportunitySuccess"
  />

  <ContractFormDialog
    v-if="customerId !== null"
    :customer-id="customerId"
    :customer-name="customer?.account_name"
    :customer-locked="true"
    :open="contractDialogOpen"
    :contract="editingContract"
    :fixed-opportunity="fixedContractOpportunity"
    @update:open="handleContractDialogClose"
    @success="handleContractSuccess"
  />

  <InvoiceTitleFormDialog
    v-if="customerId !== null"
    :customer-id="customerId"
    :open="invoiceTitleDialogOpen"
    :invoice-title="editingInvoiceTitle"
    @update:open="handleInvoiceTitleDialogClose"
    @success="handleInvoiceTitleSuccess"
  />

  <DeploymentInfoFormDialog
    v-if="customerId !== null"
    :customer-id="customerId"
    :open="deploymentDialogOpen"
    @update:open="deploymentDialogOpen = $event"
    @success="handleDeploymentSuccess"
  />

  <EditRecordDialog
    :open="recordEditDialogOpen"
    :record="selectedRecord?.record ?? null"
    :submitting="recordEditSubmitting"
    @update:open="handleRecordEditDialogOpenChange"
    @submit="handleRecordEditSubmit"
  />
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.drilldown-fade-enter-active,
.drilldown-fade-leave-active {
  transition: opacity $wolf-motion-state-duration-v2 ease, transform $wolf-motion-state-duration-v2 ease;
}

.drilldown-fade-enter-from,
.drilldown-fade-leave-to {
  opacity: 0;
  transform: translateX(8px);
}

@media (prefers-reduced-motion: reduce) {
  .drilldown-fade-enter-active,
  .drilldown-fade-leave-active {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}

.customer-detail-sheet__header {
  padding-right: 72px;
}

.customer-detail-sheet__footer {
  display: flex;
  flex-direction: row;
  justify-content: flex-end;
  gap: $wolf-space-sm-v2;
}

.customer-detail-loading,
.customer-detail-state {
  min-height: 320px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: $wolf-space-sm-v2;
  padding: $wolf-page-padding-v2;
}

.customer-detail-loading {
  color: $wolf-text-secondary-v2;
}

.customer-detail-panel-loading {
  min-height: 160px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: $wolf-space-sm-v2;
  color: $wolf-text-secondary-v2;
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid $wolf-border-default-v2;
  border-top-color: $wolf-primary-v2;
  border-radius: 50%;
  animation: customer-detail-spin 1s linear infinite;
}

.loading-spinner--small {
  width: 24px;
  height: 24px;
  border-width: 2px;
}

@keyframes customer-detail-spin {
  to {
    transform: rotate(360deg);
  }
}

.title-avatar {
  width: 48px;
  height: 48px;
  border-radius: $wolf-radius-full-v2;
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: $wolf-font-weight-semibold-v2;
  flex-shrink: 0;
}

.attributes-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: $wolf-space-md-v2 $wolf-space-lg-v2;

  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    grid-template-columns: repeat(2, 1fr);
  }

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
  }
}

.attribute-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.attribute-label {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.attribute-value {
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-secondary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.license-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 52px;
  height: 24px;
  padding: 0 $wolf-space-sm-v2;
  border-radius: $wolf-radius-v2;
  border: 1px solid transparent;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: 1;
  white-space: nowrap;
}

.license-badge--official {
  color: $wolf-success-text-v2;
  background: $wolf-success-bg-v2;
  border-color: $wolf-success-bg-v2;
}

.license-badge--trial {
  color: $wolf-warning-text-v2;
  background: $wolf-warning-bg-v2;
  border-color: $wolf-warning-bg-v2;
}

.license-badge--expired {
  color: $wolf-danger-text-v2;
  background: $wolf-danger-bg-v2;
  border-color: $wolf-danger-bg-v2;
}

.license-badge--none {
  color: $wolf-text-tertiary-v2;
  background: $wolf-bg-muted-v2;
  border-color: $wolf-border-light-v2;
}

</style>
