<script setup lang="ts">
/**
 * CustomerDetailSheet.vue - 客户详情抽屉组件
 *
 * 技术栈：shadcn-vue + variables-v2.scss
 * 宽度：75%（w-3/4 Tailwind 内置 class）
 *
 * 导航：使用 ContextTabs（Segmented Control 模式）放在 Header
 */
import { computed, ref, watch } from 'vue'
import {
  SheetHeader,
  SheetFooter
} from '@/components/ui/sheet'
import DetailSheetSurface from '@/components/ui/detail-sheet/DetailSheetSurface.vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import ErrorState from '@/components/ErrorState.vue'
import { ContextTabs } from '@/components/crmwolf'
import ApprovalSourceHeader from '@/components/ApprovalSourceHeader.vue'
import ApprovalSourceFooter from '@/components/ApprovalSourceFooter.vue'

// Panels
import FollowUpPanel from '@/components/panels/FollowUpPanel.vue'
import ContactsPanel from '@/components/panels/ContactsPanel.vue'
import DealJourneysPanel from '@/components/panels/DealJourneysPanel.vue'
import InvoicesPanel from '@/components/panels/InvoicesPanel.vue'
import LicensePanel from '@/components/panels/LicensePanel.vue'
import CustomerMembersPanel from '@/components/panels/CustomerMembersPanel.vue'
import DealJourneyDetailHost from '@/components/business-journey/DealJourneyDetailHost.vue'

// Dialogs
import FollowUpFormDialog from '@/components/dialogs/FollowUpFormDialog.vue'
import CustomerFormDialog from '@/components/dialogs/CustomerFormDialog.vue'
import ContactFormDialog from '@/components/dialogs/ContactFormDialog.vue'
import OpportunityFormDialog from '@/components/dialogs/OpportunityFormDialog.vue'
import InvoiceTitleFormDialog from '@/components/dialogs/InvoiceTitleFormDialog.vue'
import DeploymentInfoFormDialog from '@/components/dialogs/DeploymentInfoFormDialog.vue'

import { Plus, Pencil } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { handleApiError } from '@/utils/errorHandler'
import { formatProductIntentName } from '@/utils/productIntent'
import customerApi, { type CustomerDetailResponse, type ContactResponse, type CustomerMemberResponse } from '@/api/customer'
import { getAcquisitionSourceDisplayName } from '@/schemas/acquisition-source'
import customerActivityApi, { type CustomerActivityResponse } from '@/api/customerActivity'
import { dealJourneyApi, type DealJourney } from '@/api/dealJourney'
import invoiceApi, { type InvoiceTitleResponse } from '@/api/invoice'
import deploymentApi, { type DeploymentInfoResponse } from '@/api/deployment'

import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'
import { toFeedbackError, type FeedbackError } from '@/types/feedback'
import type { DetailContextNode } from '@/types/detailContext'
import type { ApprovalSourceContext } from '@/types/approvalSource'
import { useDetailContextStack } from '@/composables/useDetailContextStack'

// ==================== Props & Emits ====================
type CustomerDetailPanel = 'customer-info' | 'followup' | 'journeys'
type CustomerDetailPanelTarget = CustomerDetailPanel | 'opportunities'

interface Props {
  customerId: string | null
  targetOpportunityId?: string | null
  targetJourneyId?: string | null
  targetPanel?: CustomerDetailPanelTarget | null
  visible: boolean
  elevated?: boolean
  embedded?: boolean
  /** 从审批详情下钻时传入：只读查看客户信息，并显示来源审批与返回入口 */
  sourceApproval?: ApprovalSourceContext | null
}

const props = withDefaults(defineProps<Props>(), {
  targetOpportunityId: null,
  targetJourneyId: null,
  targetPanel: null,
  embedded: false,
  sourceApproval: null,
})
const emit = defineEmits<{
  'update:visible': [value: boolean]
  'refresh': []
  'view-customer': [customerId: string]
  'back': []
}>()

/** 审批来源模式：仅展示客户信息，隐藏所有变更与跳转入口 */
const isSourceMode = computed(() => props.sourceApproval !== null)

const userStore = useUserStore()
const permissionStore = usePermissionStore()
const detailContextStack = useDetailContextStack()

// ==================== State ====================
const loading = ref(false)  // TODO: Task 3 - 加载客户详情数据时使用
const detailError = ref<FeedbackError | null>(null)
const activePanel = ref('customer-info')  // Sidebar 导航切换

// ==================== Dialog States ====================
const followUpDialogOpen = ref(false)
const customerEditDialogOpen = ref(false)
const contactDialogOpen = ref(false)
const opportunityDialogOpen = ref(false)
const invoiceTitleDialogOpen = ref(false)
const deploymentDialogOpen = ref(false)

// ==================== Edit States ====================
const editingContact = ref<ContactResponse | null>(null)
const editingInvoiceTitle = ref<InvoiceTitleResponse | null>(null)

// ==================== Detail Sheet States (Task 6) ====================
const selectedJourneyId = ref<string | null>(null)
const highlightedJourneyId = ref<string | null>(null)
const restoreFocusJourneyId = ref<string | null>(null)

// ==================== Data Loading State ====================
const customer = ref<CustomerDetailResponse | null>(null)
const followUps = ref<CustomerActivityResponse[]>([])
const journeys = ref<DealJourney[]>([])
const selectedJourney = computed(() => (
  selectedJourneyId.value === null
    ? null
    : journeys.value.find(item => item.public_id === selectedJourneyId.value) ?? null
))
const invoiceTitles = ref<InvoiceTitleResponse[]>([])
const deployments = ref<DeploymentInfoResponse[]>([])
const customerMembers = ref<CustomerMemberResponse[]>([])
type CustomerDetailPanelKey =
  | 'followUps'
  | 'journeys'
  | 'invoiceTitles'
  | 'deployments'
  | 'customerMembers'
const panelErrors = ref<Partial<Record<CustomerDetailPanelKey, FeedbackError | undefined>>>({})
const panelLoading = ref<Record<CustomerDetailPanelKey, boolean>>({
  followUps: false,
  journeys: false,
  invoiceTitles: false,
  deployments: false,
  customerMembers: false,
})
const CUSTOMER_DETAIL_PANELS: CustomerDetailPanelKey[] = [
  'followUps',
  'journeys',
  'invoiceTitles',
  'deployments',
  'customerMembers',
]
const panelRequestIds: Record<CustomerDetailPanelKey, number> = {
  followUps: 0,
  journeys: 0,
  invoiceTitles: 0,
  deployments: 0,
  customerMembers: 0,
}
let latestLoadRequestId = 0

// ==================== Navigation Tabs ====================
interface NavTabItem {
  key: string
  label: string
}

const navTabs: NavTabItem[] = [
  { key: 'customer-info', label: '客户信息' },
  { key: 'followup', label: '客户活动' },
  { key: 'journeys', label: '业务旅程' }
]

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

const createJourneyContextNode = (journeyId: string): DetailContextNode => {
  const journey = journeys.value.find(item => item.public_id === journeyId)
  const journeyName = journey?.name?.trim()
  const node: DetailContextNode = {
    type: 'journey',
    id: journeyId,
    label: journeyName !== undefined && journeyName.length > 0 ? journeyName : '业务旅程',
    parentType: 'customer',
    source: 'related-object'
  }
  if (props.customerId !== null) node.parentId = props.customerId
  return node
}

const resetDetailContext = (): void => {
  if (props.customerId === null) {
    detailContextStack.closeRoot()
    return
  }
  detailContextStack.reset([createCustomerContextNode(props.customerId)])
}

const resetLocalNavigation = (): void => {
  activePanel.value = 'customer-info'
  selectedJourneyId.value = null
  highlightedJourneyId.value = null
  restoreFocusJourneyId.value = null
  resetDetailContext()
}

const setActivePanel = (panel: string): void => {
  activePanel.value = panel
  selectedJourneyId.value = null
  highlightedJourneyId.value = null
  restoreFocusJourneyId.value = null
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
  if (isSourceMode.value || !customer.value) return false
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
  if (isSourceMode.value || !customer.value) return false
  if (permissionStore.hasPermission('customer:edit:all')) return true
  if (currentCustomerMember.value?.access_level === 'EDIT') return true
  return customer.value.owner_id === String(userStore.userInfo?.id) && permissionStore.hasPermission('customer:edit:own')
})

const canCreateActivity = computed(() => {
  if (isSourceMode.value || !customer.value) return false
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
): Promise<boolean> => {
  const requestId = panelRequestIds[panel] + 1
  panelRequestIds[panel] = requestId
  setPanelLoading(panel, true)
  setPanelError(panel, null)

  try {
    const value = await request()
    if (requestId !== panelRequestIds[panel]) return false
    apply(value)
    return true
  } catch (error) {
    if (requestId !== panelRequestIds[panel]) return false
    setPanelError(panel, toFeedbackError(error, context))
    return false
  } finally {
    if (requestId === panelRequestIds[panel]) {
      setPanelLoading(panel, false)
    }
  }
}

const loadAllData = async (customerId: string): Promise<boolean> => {
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
      journeysResult,
      invoiceTitlesResult,
      deploymentsResult,
      customerMembersResult
    ] = await Promise.allSettled([
      customerApi.getCustomerDetail(customerId),
      customerActivityApi.getActivities(customerId),
      dealJourneyApi.listByCustomer(customerId),
      invoiceApi.getInvoiceTitles(customerId),
      deploymentApi.list(customerId),
      customerApi.getCustomerMembers(customerId),
    ])

    if (customerDetailResult.status === 'rejected') {
      detailError.value = toFeedbackError(customerDetailResult.reason, '客户详情')
      return false
    }

    if (loadRequestId !== latestLoadRequestId) return false

    customer.value = customerDetailResult.value
    const panelLoadSucceeded: Record<CustomerDetailPanelKey, boolean> = {
      followUps: followUpsResult.status === 'fulfilled' && isCurrentPanelLoad('followUps'),
      journeys: journeysResult.status === 'fulfilled' && isCurrentPanelLoad('journeys'),
      invoiceTitles: invoiceTitlesResult.status === 'fulfilled' && isCurrentPanelLoad('invoiceTitles'),
      deployments: deploymentsResult.status === 'fulfilled' && isCurrentPanelLoad('deployments'),
      customerMembers: customerMembersResult.status === 'fulfilled' && isCurrentPanelLoad('customerMembers'),
    }
    const followUpsData = readPanel(followUpsResult, 'followUps', '客户活动', followUps.value)
    const journeysData = readPanel(journeysResult, 'journeys', '业务旅程', journeys.value)
    const invoiceTitlesData = readPanel(invoiceTitlesResult, 'invoiceTitles', '发票抬头', { invoice_titles: invoiceTitles.value })
    const deploymentsData = readPanel(deploymentsResult, 'deployments', '部署信息', deployments.value)
    const customerMembersData = readPanel(customerMembersResult, 'customerMembers', '客户团队', customerMembers.value)
    if (isCurrentPanelLoad('followUps')) followUps.value = followUpsData
    if (isCurrentPanelLoad('journeys')) {
      journeys.value = journeysData
      if (navigationTargetPending && journeysResult.status === 'fulfilled') applyNavigationTarget(true)
    }
    if (isCurrentPanelLoad('invoiceTitles')) invoiceTitles.value = invoiceTitlesData.invoice_titles ?? []
    if (isCurrentPanelLoad('deployments')) deployments.value = deploymentsData
    if (isCurrentPanelLoad('customerMembers')) customerMembers.value = customerMembersData

    CUSTOMER_DETAIL_PANELS.forEach((panel) => {
      if (isCurrentPanelLoad(panel)) setPanelLoading(panel, false)
    })

    return Object.values(panelLoadSucceeded).every(Boolean)
  } catch (error) {
    if (loadRequestId !== latestLoadRequestId) return false
    detailError.value = toFeedbackError(error, '客户详情')
    return false
  } finally {
    if (loadRequestId === latestLoadRequestId) {
      loading.value = false
      CUSTOMER_DETAIL_PANELS.forEach((panel) => {
        if (isCurrentPanelLoad(panel) && panelLoading.value[panel]) setPanelLoading(panel, false)
      })
    }
  }
}

/**
 * Allow the owning list page to refresh this customer when a sibling dialog
 * saves the same entity. The sheet keeps ownership of its panel read models.
 */
defineExpose({
  refresh: async (): Promise<boolean> => {
    if (props.customerId === null) return false
    return loadAllData(props.customerId)
  }
})

const retryPanel = async (panel: CustomerDetailPanelKey): Promise<boolean> => {
  if (props.customerId === null) return false
  activePanel.value = panel === 'followUps' ? 'followup'
    : panel === 'journeys' ? 'journeys'
      : 'customer-info'
  const customerId = props.customerId
  switch (panel) {
    case 'followUps':
      return runPanelRequest(panel, '客户活动', () => customerActivityApi.getActivities(customerId), (data) => { followUps.value = data })
    case 'journeys':
      return runPanelRequest(panel, '业务旅程', () => dealJourneyApi.listByCustomer(customerId), (data) => {
        journeys.value = data
      })
    case 'invoiceTitles':
      return runPanelRequest(panel, '发票抬头', () => invoiceApi.getInvoiceTitles(customerId), (data) => { invoiceTitles.value = data.invoice_titles ?? [] })
    case 'deployments':
      return runPanelRequest(panel, '部署信息', () => deploymentApi.list(customerId), (data) => { deployments.value = data })
    case 'customerMembers':
      return runPanelRequest(panel, '客户团队', () => customerApi.getCustomerMembers(customerId), (data) => { customerMembers.value = data })
  }
}

const refreshCustomerMembers = async (): Promise<void> => {
  const refreshed = await retryPanel('customerMembers')
  warnIfCustomerDetailRefreshFailed(refreshed, '客户团队操作')
  emit('refresh')
}

// ==================== Dialog Handlers ====================
const warnIfCustomerDetailRefreshFailed = (refreshed: boolean, action: string): void => {
  if (!refreshed) {
    toast.warning(`${action}已完成，但客户详情刷新失败，请稍后重试。`)
  }
}

const handleCustomerEditSuccess = async (): Promise<void> => {
  customerEditDialogOpen.value = false
  if (props.customerId !== null) {
    const refreshed = await loadAllData(props.customerId)
    warnIfCustomerDetailRefreshFailed(refreshed, '客户信息更新')
  }
  emit('refresh')
}

// FollowUp handlers
const handleFollowUpSuccess = async (): Promise<void> => {
  followUpDialogOpen.value = false
  if (props.customerId !== null) {
    const refreshed = await loadAllData(props.customerId)
    warnIfCustomerDetailRefreshFailed(refreshed, '客户活动更新')
    window.setTimeout(() => {
      if (props.visible && props.customerId !== null) {
        void loadAllData(props.customerId)
      }
    }, 3000)
  }
  emit('refresh')
}

const handleFollowUpDelete = async (followUp: { id: number }): Promise<void> => {
  try {
    await customerActivityApi.deleteActivity(followUp.id)
    toast.success('客户活动已删除')
    if (props.customerId !== null) {
      const refreshed = await loadAllData(props.customerId)
      warnIfCustomerDetailRefreshFailed(refreshed, '客户活动删除')
    }
    emit('refresh')
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

const handleContactSuccess = async (): Promise<void> => {
  contactDialogOpen.value = false
  editingContact.value = null
  if (props.customerId !== null) {
    const refreshed = await loadAllData(props.customerId)
    warnIfCustomerDetailRefreshFailed(refreshed, '联系人更新')
  }
  emit('refresh')
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
      const refreshed = await loadAllData(props.customerId)
      warnIfCustomerDetailRefreshFailed(refreshed, '联系人删除')
    }
    emit('refresh')
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
      const refreshed = await loadAllData(props.customerId)
      warnIfCustomerDetailRefreshFailed(refreshed, '主要联系人设置')
    }
    emit('refresh')
  } catch (error) {
    handleApiError(error, '设置主要联系人')
  }
}

// Opportunity handlers
const handleOpportunitySuccess = async (): Promise<void> => {
  opportunityDialogOpen.value = false
  if (props.customerId !== null) {
    const refreshed = await loadAllData(props.customerId)
    warnIfCustomerDetailRefreshFailed(refreshed, '商机更新')
  }
  emit('refresh')
}

const handleViewJourney = (journeyId: string): void => {
  activePanel.value = 'journeys'
  if (props.customerId !== null) {
    detailContextStack.reset([createCustomerContextNode(props.customerId)])
    detailContextStack.push(createJourneyContextNode(journeyId))
  }
  selectedJourneyId.value = journeyId
  highlightedJourneyId.value = null
  restoreFocusJourneyId.value = null
}

const resolveTargetJourneyId = (): string | null => {
  if (props.targetJourneyId !== undefined && props.targetJourneyId !== null) {
    return props.targetJourneyId
  }
  if (props.targetOpportunityId === undefined || props.targetOpportunityId === null) {
    return null
  }
  const matched = journeys.value.find(item => item.primary_opportunity?.public_id === props.targetOpportunityId)
  return matched?.public_id ?? null
}

const resolveTargetPanel = (panel: CustomerDetailPanelTarget): CustomerDetailPanel =>
  panel === 'opportunities' ? 'journeys' : panel

let navigationTargetPending = false

const markNavigationTargetPending = (): void => {
  navigationTargetPending = true
}

const applyNavigationTarget = (fromJourneysLoad = false): void => {
  if (isSourceMode.value) {
    activePanel.value = 'customer-info'
    selectedJourneyId.value = null
    navigationTargetPending = false
    return
  }
  const journeyId = resolveTargetJourneyId()
  if (journeyId !== null) {
    handleViewJourney(journeyId)
    navigationTargetPending = false
    return
  }

  if (props.targetOpportunityId !== undefined && props.targetOpportunityId !== null) {
    activePanel.value = 'journeys'
    if (fromJourneysLoad) navigationTargetPending = false
    return
  }

  if (props.targetPanel !== undefined && props.targetPanel !== null) {
    setActivePanel(resolveTargetPanel(props.targetPanel))
  }
  navigationTargetPending = false
}

const handleContextClose = (): void => {
  detailContextStack.closeRoot()
  selectedJourneyId.value = null
  emit('update:visible', false)
}

function handleJourneyHostViewCustomer(customerId: string): void {
  if (customerId === props.customerId) {
    selectedJourneyId.value = null
    resetDetailContext()
    return
  }
  emit('view-customer', customerId)
}

const handleJourneyDetailRefresh = async (): Promise<void> => {
  if (props.customerId !== null) {
    const refreshed = await loadAllData(props.customerId)
    warnIfCustomerDetailRefreshFailed(refreshed, '业务旅程操作')
  }
  emit('refresh')
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

const handleInvoiceTitleSuccess = async (): Promise<void> => {
  invoiceTitleDialogOpen.value = false
  editingInvoiceTitle.value = null
  const refreshed = await retryPanel('invoiceTitles')
  warnIfCustomerDetailRefreshFailed(refreshed, '发票抬头更新')
  emit('refresh')
}

const handleDeleteInvoiceTitle = async (titleId: number): Promise<void> => {
  if (!canDeleteInvoiceTitle.value) {
    toast.error('你没有删除该客户发票抬头的权限')
    return
  }
  try {
    await invoiceApi.deleteInvoiceTitle(titleId)
    toast.success('发票抬头已删除')
    const refreshed = await retryPanel('invoiceTitles')
    warnIfCustomerDetailRefreshFailed(refreshed, '发票抬头删除')
    emit('refresh')
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
    const refreshed = await retryPanel('invoiceTitles')
    warnIfCustomerDetailRefreshFailed(refreshed, '默认发票抬头设置')
    emit('refresh')
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

const handleDeploymentSuccess = async (): Promise<void> => {
  deploymentDialogOpen.value = false
  const refreshed = await retryPanel('deployments')
  warnIfCustomerDetailRefreshFailed(refreshed, '部署信息更新')
  emit('refresh')
}

const handleDeleteDeployment = async (deploymentId: number): Promise<void> => {
  if (!canDeleteDeployment.value) {
    toast.error('你没有删除该客户部署信息的权限')
    return
  }
  try {
    await deploymentApi.deleteDeployment(deploymentId)
    toast.success('部署信息已删除')
    const refreshed = await retryPanel('deployments')
    warnIfCustomerDetailRefreshFailed(refreshed, '部署信息删除')
    emit('refresh')
  } catch (error) {
    handleApiError(error, '删除部署信息')
  }
}

// ==================== Watch ====================
watch(() => props.visible, (visible): void => {
  if (visible && props.customerId !== null) {
    resetLocalNavigation()
    markNavigationTargetPending()
    applyNavigationTarget()
    loadAllData(props.customerId)
  } else if (!visible) {
    // 清理状态
    resetLocalNavigation()
    customer.value = null
    followUps.value = []
    journeys.value = []
    invoiceTitles.value = []
    deployments.value = []
    // Clear nested sheet states
    customerEditDialogOpen.value = false
    deploymentDialogOpen.value = false
  }
}, { immediate: true })

watch(() => props.customerId, (customerId, previousCustomerId): void => {
  if (customerId !== previousCustomerId) {
    deploymentDialogOpen.value = false
  }
  if (!props.visible || customerId === null || customerId === previousCustomerId) return
  resetLocalNavigation()
  markNavigationTargetPending()
  applyNavigationTarget()
  loadAllData(customerId)
})

watch(() => [props.targetJourneyId, props.targetOpportunityId], (): void => {
  if (!props.visible) return
  markNavigationTargetPending()
  applyNavigationTarget()
})

watch(() => props.targetPanel, (panel): void => {
  const hasTargetJourney = resolveTargetJourneyId() !== null
  const hasTargetOpportunity = props.targetOpportunityId !== undefined && props.targetOpportunityId !== null
  if (!props.visible || isSourceMode.value || panel === undefined || panel === null || hasTargetJourney || hasTargetOpportunity) return
  setActivePanel(resolveTargetPanel(panel))
})

</script>

<template>
  <DetailSheetSurface
    :open="visible"
    :embedded="embedded"
    :elevated="elevated"
    @update:open="emit('update:visible', $event)"
  >
      <ApprovalSourceHeader
        v-if="sourceApproval"
        :source="sourceApproval"
        subject-label="客户详情"
        @back="emit('back')"
      />
      <Transition name="drilldown-fade" mode="out-in">
        <DealJourneyDetailHost v-bind="elevated ? { elevated: true } : {}"
          v-if="selectedJourneyId !== null && !isSourceMode"
          :journey-id="selectedJourneyId"
          :journey-name="selectedJourney?.name ?? ''"
          :customer-id="customerId ?? ''"
          :customer-name="customer?.account_name"
          :journey="selectedJourney"
          :context-prefix="customerId === null ? [] : [createCustomerContextNode(customerId)]"
          embedded
          :can-edit-customer-context="canEditCurrentCustomer"
          @close="handleContextClose"
          @refresh="handleJourneyDetailRefresh"
          @view-customer="handleJourneyHostViewCustomer"
        />
      </Transition>

      <template v-if="selectedJourneyId === null || isSourceMode">
        <!-- Header（审批来源模式只保留客户信息，不显示导航） -->
        <SheetHeader v-if="!isSourceMode" class="customer-detail-sheet__header p-6 border-b border-wolf-border-default-v2">
          <!-- ContextTabs 导航 -->
          <ContextTabs
            :tabs="navTabs"
            :active-tab="activePanel"
            @update:activeTab="setActivePanel"
            class="w-full"
          />
        </SheetHeader>

        <!-- Content -->
        <ScrollArea class="flex-1" :class="isSourceMode ? 'min-h-0' : undefined">
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
                        <div class="attribute-label">产品</div>
                        <div class="attribute-value">{{ formatProductIntentName(customer ?? {}) }}</div>
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
                        <div class="attribute-label">授权人数</div>
                        <div class="attribute-value">{{ customer?.license_authorized_users ?? '-' }}</div>
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

              <ContactsPanel
                :customer-id="customerId ?? ''"
                :contacts="customer?.contacts ?? []"
                :show-add="!isSourceMode && canCreateContact"
                :can-edit="!isSourceMode && canEditContact"
                :can-delete="!isSourceMode && canDeleteContact"
                :can-set-primary="!isSourceMode && canSetPrimaryContact"
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
                :show-add-title="!isSourceMode && canCreateInvoiceTitle"
                :show-title-apply-action="false"
                :can-edit-title="!isSourceMode && canEditInvoiceTitle"
                :can-delete-title="!isSourceMode && canDeleteInvoiceTitle"
                :can-set-default-title="!isSourceMode && canSetDefaultInvoiceTitle"
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
                :show-add-deployment="!isSourceMode && canCreateDeployment"
                :can-delete-deployment="!isSourceMode && canDeleteDeployment"
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
                :readonly="isSourceMode"
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

            <div v-if="activePanel === 'journeys' && panelLoading.journeys" class="customer-detail-panel-loading" aria-busy="true" aria-live="polite">
              <div class="loading-spinner loading-spinner--small" />
              <span>正在加载业务旅程…</span>
            </div>
            <ErrorState
              v-else-if="activePanel === 'journeys' && panelErrors.journeys"
              :variant="panelErrors.journeys.variant ?? 'error'"
              :title="panelErrors.journeys.title"
              :description="panelErrors.journeys.description"
            >
              <template #action>
                <Button v-if="panelErrors.journeys.retryable !== false" type="button" :loading="panelLoading.journeys" @click="retryPanel('journeys')">
                  重试加载业务旅程
                </Button>
              </template>
            </ErrorState>
            <DealJourneysPanel
              v-if="activePanel === 'journeys' && !panelErrors.journeys"
              :customer-id="customerId ?? ''"
              :journeys="journeys"
              :highlighted-journey-id="highlightedJourneyId"
              :restore-focus-journey-id="restoreFocusJourneyId"
              :show-add="canCreateOpportunityForCustomer"
              @add="handleCreateOpportunity"
              @view="handleViewJourney"
            />
          </div>
        </ScrollArea>

        <!-- Footer -->
        <SheetFooter
          v-if="!isSourceMode"
          
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

          <template v-else-if="activePanel === 'journeys' && canCreateOpportunityForCustomer">
            <Button variant="default" @click="handleCreateOpportunity">
              <Plus class="w-4 h-4 mr-2" />
              新建商机
            </Button>
          </template>
        </SheetFooter>
      </template>
      <ApprovalSourceFooter v-if="isSourceMode" @back="emit('back')" />
  </DetailSheetSurface>

  <!-- Dialogs -->
  <FollowUpFormDialog v-bind="elevated ? { elevated: true } : {}"
    v-if="customerId !== null"
    :customer-id="customerId"
    :open="followUpDialogOpen"
    @update:open="followUpDialogOpen = $event"
    @success="handleFollowUpSuccess"
  />

  <CustomerFormDialog v-bind="elevated ? { elevated: true } : {}"
    v-if="customerId !== null"
    mode="edit"
    :customer-id="customerId"
    :customer="customer ?? null"
    :open="customerEditDialogOpen"
    @update:open="customerEditDialogOpen = $event"
    @success="handleCustomerEditSuccess"
  />

  <ContactFormDialog v-bind="elevated ? { elevated: true } : {}"
    v-if="customerId !== null"
    :customer-id="customerId"
    :open="contactDialogOpen"
    :contact="editingContact"
    :available-contacts="customer?.contacts ?? []"
    @update:open="handleContactDialogClose"
    @success="handleContactSuccess"
  />

  <OpportunityFormDialog v-bind="elevated ? { elevated: true } : {}"
    v-if="customerId !== null"
    :customer-id="customerId"
    :customer-name="customer?.account_name"
    :customer-locked="true"
    :open="opportunityDialogOpen"
    @update:open="opportunityDialogOpen = $event"
    @success="handleOpportunitySuccess"
  />

  <InvoiceTitleFormDialog v-bind="elevated ? { elevated: true } : {}"
    v-if="customerId !== null"
    :customer-id="customerId"
    :open="invoiceTitleDialogOpen"
    :invoice-title="editingInvoiceTitle"
    @update:open="handleInvoiceTitleDialogClose"
    @success="handleInvoiceTitleSuccess"
  />

  <DeploymentInfoFormDialog v-bind="elevated ? { elevated: true } : {}"
    v-if="customerId !== null"
    :customer-id="customerId"
    :open="deploymentDialogOpen"
    @update:open="deploymentDialogOpen = $event"
    @success="handleDeploymentSuccess"
  />
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.drilldown-fade-enter-active,
.drilldown-fade-leave-active {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
  flex-direction: column;
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
