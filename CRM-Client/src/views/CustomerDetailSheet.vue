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
  Sheet,
  SheetHeader,
  SheetFooter
} from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ContextTabs, HoverInfo } from '@/components/crmwolf'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle
} from '@/components/ui/empty'

// Panels
import FollowUpPanel from '@/components/panels/FollowUpPanel.vue'
import ContactsPanel from '@/components/panels/ContactsPanel.vue'
import OpportunitiesPanel from '@/components/panels/OpportunitiesPanel.vue'
import InvoicesPanel from '@/components/panels/InvoicesPanel.vue'
import LicensePanel from '@/components/panels/LicensePanel.vue'
import CustomerMembersPanel from '@/components/panels/CustomerMembersPanel.vue'
import OpportunityDetailContent from '@/components/panels/OpportunityDetailContent.vue'
import ContractDetailContent from '@/components/panels/ContractDetailContent.vue'

// Dialogs
import FollowUpFormDialog from '@/components/dialogs/FollowUpFormDialog.vue'
import CustomerFormDialog from '@/components/dialogs/CustomerFormDialog.vue'
import ContactFormDialog from '@/components/dialogs/ContactFormDialog.vue'
import OpportunityFormDialog from '@/components/dialogs/OpportunityFormDialog.vue'
import ContractFormDialog from '@/components/dialogs/ContractFormDialog.vue'
import InvoiceTitleFormDialog from '@/components/dialogs/InvoiceTitleFormDialog.vue'
import DeploymentInfoFormDialog from '@/components/dialogs/DeploymentInfoFormDialog.vue'
import EditRecordDialog from '@/components/dialogs/EditRecordDialog.vue'

// Detail Sheets (Task 6)
import PaymentPlanDetailSheet from '@/views/PaymentPlanDetailSheet.vue'
import PaymentRecordDetailSheet from '@/views/PaymentRecordDetailSheet.vue'

import { Plus, Pencil, RefreshCw, Loader2, Sparkles } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { handleApiError } from '@/utils/errorHandler'
import customerApi, { type CustomerDetailResponse, type ContactResponse, type CustomerMemberResponse } from '@/api/customer'
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

// ==================== Props & Emits ====================
type CustomerDetailPanel = 'customer-brief' | 'customer-info' | 'followup' | 'opportunities'

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

// ==================== State ====================
const loading = ref(false)  // TODO: Task 3 - 加载客户详情数据时使用
const activePanel = ref('customer-brief')  // Sidebar 导航切换
const regeneratingBrief = ref(false)

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
const planSheetVisible = ref(false)
const selectedRecord = ref<{ record: PaymentRecordInfo; stageName: string; approval: ApprovalInfo | ApprovalInfoLite | null; planId: number | null } | null>(null)
const recordSheetVisible = ref(false)
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
const followUps = ref<CustomerActivityResponse[]>([])
const opportunities = ref<OpportunityListResponse[]>([])
const contracts = ref<ContractListResponse[]>([])
const paymentPlans = ref<PaymentPlanResponse[]>([])
const invoiceTitles = ref<InvoiceTitleResponse[]>([])
const deployments = ref<DeploymentInfoResponse[]>([])
const customerMembers = ref<CustomerMemberResponse[]>([])
let latestLoadRequestId = 0

interface CustomerBriefCitation {
  source_type?: string
  source_id?: string
  title?: string
  excerpt?: string
}

type CustomerBriefCitationMap = Record<string, CustomerBriefCitation>

interface CustomerBriefInlineNode {
  type: 'text' | 'strong' | 'citation'
  text: string
  citationKey?: string
  citation?: CustomerBriefCitation
  sourceLabel?: string
}

interface CustomerBriefBlock {
  type: 'h2' | 'h3' | 'p' | 'ul' | 'ol'
  nodes?: CustomerBriefInlineNode[]
  items?: CustomerBriefInlineNode[][]
}

const getCitationSourceLabel = (sourceType: string | undefined): string => {
  const labels: Record<string, string> = {
    customer: '客户',
    customer_profile: '客户档案',
    contact: '联系人',
    opportunity: '商机',
    contract: '合同',
    payment_plan: '回款计划',
    payment_record: '回款记录',
    follow_up: '客户活动'
  }
  return sourceType !== undefined && sourceType !== '' ? labels[sourceType] ?? sourceType : '来源'
}

const parseInlineMarkdown = (value: string, citationMap: CustomerBriefCitationMap): CustomerBriefInlineNode[] => {
  const nodes: CustomerBriefInlineNode[] = []
  const pattern = /(\*\*([^*]+)\*\*|\[(\d+)\])/g
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = pattern.exec(value)) !== null) {
    if (match.index > lastIndex) {
      nodes.push({ type: 'text', text: value.slice(lastIndex, match.index) })
    }

    const strongText = match[2]
    const citationKey = match[3]
    if (strongText !== undefined) {
      nodes.push({ type: 'strong', text: strongText })
    } else if (citationKey !== undefined) {
      const citation = citationMap[citationKey]
      if (citation === undefined) {
        nodes.push({ type: 'text', text: match[0] })
      } else {
        nodes.push({
          type: 'citation',
          text: `[${citationKey}]`,
          citationKey,
          citation,
          sourceLabel: getCitationSourceLabel(citation.source_type)
        })
      }
    }

    lastIndex = pattern.lastIndex
  }

  if (lastIndex < value.length) {
    nodes.push({ type: 'text', text: value.slice(lastIndex) })
  }

  return nodes
}

const parseSimpleMarkdown = (value: string, citationMap: CustomerBriefCitationMap): CustomerBriefBlock[] => {
  const lines = value.split('\n')
  const blocks: CustomerBriefBlock[] = []
  let listType: 'ul' | 'ol' | null = null
  let listItems: CustomerBriefInlineNode[][] = []

  const closeList = (): void => {
    if (listType !== null) {
      blocks.push({ type: listType, items: listItems })
      listType = null
      listItems = []
    }
  }

  for (const line of lines) {
    const text = line.trim()
    if (text === '') {
      closeList()
      continue
    }

    if (text.startsWith('## ')) {
      closeList()
      blocks.push({ type: 'h2', nodes: parseInlineMarkdown(text.slice(3), citationMap) })
      continue
    }

    if (text.startsWith('### ')) {
      closeList()
      blocks.push({ type: 'h3', nodes: parseInlineMarkdown(text.slice(4), citationMap) })
      continue
    }

    if (/^- /.test(text)) {
      if (listType !== 'ul') {
        closeList()
        listType = 'ul'
      }
      listItems.push(parseInlineMarkdown(text.slice(2), citationMap))
      continue
    }

    const orderedMatch = text.match(/^\d+\.\s+(.+)$/)
    if (orderedMatch !== null) {
      if (listType !== 'ol') {
        closeList()
        listType = 'ol'
      }
      listItems.push(parseInlineMarkdown(orderedMatch[1] ?? '', citationMap))
      continue
    }

    closeList()
    blocks.push({ type: 'p', nodes: parseInlineMarkdown(text, citationMap) })
  }

  closeList()
  return blocks
}

const customerBriefCitationMap = computed<CustomerBriefCitationMap>(() => {
  const rawCitations = customer.value?.customer_brief_citations
  if (rawCitations === undefined || rawCitations === null || rawCitations.trim() === '') return {}

  try {
    const parsed = JSON.parse(rawCitations) as unknown
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return parsed as CustomerBriefCitationMap
  } catch {
    return {}
  }
})

const renderedCustomerBrief = computed<CustomerBriefBlock[]>(() => {
  const markdownText = customer.value?.customer_brief_markdown?.trim()
  if (markdownText === undefined || markdownText === null || markdownText === '') return []
  return parseSimpleMarkdown(markdownText, customerBriefCitationMap.value)
})

const hasCustomerBriefContent = computed(() => renderedCustomerBrief.value.length > 0)
const hasCustomerIntelligenceInputs = computed(() => {
  if (customer.value === null) return false
  if (customer.value.customer_intelligence_has_inputs !== undefined) {
    return customer.value.customer_intelligence_has_inputs
  }
  return (
    (customer.value.contacts ?? []).length > 0 ||
    followUps.value.length > 0 ||
    opportunities.value.length > 0 ||
    contracts.value.length > 0 ||
    paymentPlans.value.length > 0 ||
    invoiceTitles.value.length > 0 ||
    deployments.value.length > 0
  )
})
const isCustomerBriefRefreshing = computed(() => (
  regeneratingBrief.value || customer.value?.customer_brief_status === 'GENERATING'
))
const isCustomerBriefAwaitingAutoBuild = computed(() => (
  !hasCustomerBriefContent.value &&
  hasCustomerIntelligenceInputs.value &&
  (
    customer.value?.customer_brief_status === 'PENDING' ||
    customer.value?.customer_brief_status === undefined ||
    customer.value?.customer_brief_status === null
  )
))

// ==================== Navigation Tabs ====================
interface NavTabItem {
  key: string
  label: string
}

const navTabs: NavTabItem[] = [
  { key: 'customer-brief', label: '客户档案' },
  { key: 'customer-info', label: '客户信息' },
  { key: 'followup', label: '客户活动' },
  { key: 'opportunities', label: '项目旅程' }
]

// ==================== Methods ====================
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

const resetLocalNavigation = (): void => {
  activePanel.value = 'customer-brief'
  selectedOpportunityId.value = null
  highlightedOpportunityId.value = null
  restoreFocusOpportunityId.value = null
}

const setActivePanel = (panel: string): void => {
  activePanel.value = panel
  selectedOpportunityId.value = null
  highlightedOpportunityId.value = null
  restoreFocusOpportunityId.value = null
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

const getCustomerBriefStatusLabel = (status: string | null | undefined): string => {
  if (status === 'COMPLETED') return '已整理'
  if (status === 'GENERATING') return '整理中'
  if (status === 'PENDING') return '待整理'
  if (status === 'FAILED') return '需关注'
  return '暂无档案'
}

const getCustomerBriefStatusClass = (status: string | null | undefined): string => {
  if (status === 'COMPLETED') return 'brief-status-badge--completed'
  if (status === 'GENERATING') return 'brief-status-badge--generating'
  if (status === 'FAILED') return 'brief-status-badge--failed'
  return 'brief-status-badge--pending'
}

const customerBriefUpdatedText = computed(() => {
  const generatedTime = customer.value?.customer_brief_generated_time
  if (generatedTime === undefined || generatedTime === null || generatedTime.trim() === '') return ''
  return `更新于 ${formatDate(generatedTime)}`
})

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
const canCreateOpportunityForCustomer = computed(() => (
  permissionStore.hasPermission('opportunity:create') && canEditCurrentCustomer.value
))

// ==================== Data Loading ====================
const loadAllData = async (customerId: string): Promise<void> => {
  const loadRequestId = latestLoadRequestId + 1
  latestLoadRequestId = loadRequestId
  loading.value = true

  try {
    const [
      customerDetail,
      followUpsData,
      opportunitiesData,
      contractsData,
      invoiceTitlesData,
      deploymentsData,
      customerMembersData
    ] = await Promise.all([
      customerApi.getCustomerDetail(customerId),
      customerActivityApi.getActivities(customerId).catch(() => []),
      opportunityApi.getOpportunities({ customer_id: customerId }).catch(() => []),
      contractApi.getCustomerContracts(customerId).catch(() => []),
      invoiceApi.getInvoiceTitles(customerId).catch(() => ({ invoice_titles: [] })),
      deploymentApi.list(customerId).catch(() => []),
      customerApi.getCustomerMembers(customerId).catch(() => [])
    ])

    if (loadRequestId !== latestLoadRequestId) {
      return
    }

    customer.value = customerDetail
    followUps.value = followUpsData
    opportunities.value = normalizePaginatedResponse(opportunitiesData).items
    contracts.value = contractsData
    invoiceTitles.value = invoiceTitlesData.invoice_titles ?? []
    deployments.value = deploymentsData
    customerMembers.value = customerMembersData

    if (contractsData.length > 0) {
      const paymentPlanPromises = contractsData.map((contract) =>
        paymentApi.getPaymentPlans(contract.id).catch(() => [])
      )
      const paymentPlanResults = await Promise.all(paymentPlanPromises)
      if (loadRequestId !== latestLoadRequestId) {
        return
      }
      paymentPlans.value = paymentPlanResults.flat()
    } else {
      paymentPlans.value = []
    }

  } catch (error) {
    if (loadRequestId !== latestLoadRequestId) {
      return
    }
    handleApiError(error, '加载客户详情')
  } finally {
    if (loadRequestId === latestLoadRequestId) {
      loading.value = false
    }
  }
}

const refreshCustomerMembers = async (): Promise<void> => {
  if (props.customerId === null) return
  try {
    customerMembers.value = await customerApi.getCustomerMembers(props.customerId)
  } catch (error) {
    handleApiError(error, '刷新客户团队成员')
  }
}

const handleRegenerateBrief = async (): Promise<void> => {
  if (props.customerId === null) return
  regeneratingBrief.value = true
  try {
    await customerApi.regenerateCustomerIntelligence(props.customerId, 'full')
    toast.success('客户智能档案正在刷新')
    await loadAllData(props.customerId)
  } catch (error) {
    handleApiError(error, '刷新客户智能档案')
  } finally {
    regeneratingBrief.value = false
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

const handleActivityProcess = async (followUp: { id: number }): Promise<void> => {
  try {
    await customerActivityApi.processActivity(followUp.id)
    toast.success('客户活动整理中，请稍后刷新')
    if (props.customerId !== null) {
      await loadAllData(props.customerId)
      window.setTimeout(() => {
        if (props.visible && props.customerId !== null) {
          loadAllData(props.customerId)
        }
      }, 3000)
    }
  } catch (error) {
    handleApiError(error, '重新整理客户活动')
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

const handleBackFromOpportunity = (): void => {
  const previousOpportunityId = selectedOpportunityId.value
  selectedOpportunityId.value = null
  if (previousOpportunityId !== null) {
    highlightedOpportunityId.value = previousOpportunityId
    restoreFocusOpportunityId.value = previousOpportunityId
  }
}

const handleBackFromContract = (): void => {
  selectedContractId.value = null
}

const handleOpportunityDetailRefresh = (): void => {
  if (props.customerId !== null) {
    loadAllData(props.customerId)
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
  if (props.customerId !== null) {
    loadAllData(props.customerId)
  }
}

const refreshContractRelations = (): void => {
  void opportunityDetailContentRef.value?.refresh()
  if (props.customerId !== null) {
    loadAllData(props.customerId)
  }
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
  if (props.customerId !== null) {
    loadAllData(props.customerId)
  }
}

const handleDeleteInvoiceTitle = async (titleId: number): Promise<void> => {
  if (!canDeleteInvoiceTitle.value) {
    toast.error('你没有删除该客户发票抬头的权限')
    return
  }
  try {
    await invoiceApi.deleteInvoiceTitle(titleId)
    toast.success('发票抬头已删除')
    if (props.customerId !== null) {
      loadAllData(props.customerId)
    }
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
    if (props.customerId !== null) {
      loadAllData(props.customerId)
    }
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
  if (props.customerId !== null) {
    loadAllData(props.customerId)
  }
}

// Contract detail sheet handlers (Task 6)
const handleViewContract = (contractId: number): void => {
  selectedContractId.value = contractId
}

const handleContractSheetRefresh = (): void => {
  if (props.customerId !== null) {
    loadAllData(props.customerId)
  }
}

const handlePlanSheetRefresh = (): void => {
  if (props.customerId !== null) {
    loadAllData(props.customerId)
  }
}

// Payment record detail sheet handler (Task 6)
const handleRecordClick = (record: PaymentRecordInfo): void => {
  const plan = paymentPlans.value.find((p) =>
    p.payment_records?.some((r) => r.id === record.id)
  )
  // Get approval from record or from plan's latest approval if this is the latest record
  const approval = record.approval ?? (plan?.latest_record_id === record.id ? plan.latest_approval : null) ?? null
  selectedRecord.value = {
    record,
    stageName: plan?.stage_name ?? '',
    approval,
    planId: plan?.id ?? null
  }
  recordSheetVisible.value = true
}

const syncSelectedPaymentRecord = (): void => {
  const selected = selectedRecord.value
  if (selected === null) return
  const plan = paymentPlans.value.find((item) =>
    item.payment_records?.some((record) => record.id === selected.record.id)
  )
  const updatedRecord = plan?.payment_records?.find((record) => record.id === selected.record.id)
  if (updatedRecord === undefined) return
  selectedRecord.value = {
    record: updatedRecord,
    stageName: plan?.stage_name ?? selected.stageName,
    approval: updatedRecord.approval ?? (plan?.latest_record_id === updatedRecord.id ? plan.latest_approval : null) ?? null,
    planId: plan?.id ?? selected.planId
  }
}

const handleRecordSheetRefresh = async (): Promise<void> => {
  if (props.customerId !== null) {
    await loadAllData(props.customerId)
    syncSelectedPaymentRecord()
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
    await handleRecordSheetRefresh()
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

// Payment plan detail sheet nested event handlers (Task 6 fix)
const handlePaymentPlanDetailViewContract = (contractId: number): void => {
  planSheetVisible.value = false
  selectedPlanId.value = null
  handleViewContract(contractId)
}

const handlePaymentPlanDetailViewCustomer = (customerId: string): void => {
  // If same customer, close nested sheets and return focus to current customer
  if (customerId === props.customerId) {
    planSheetVisible.value = false
    selectedPlanId.value = null
    recordSheetVisible.value = false
    selectedRecord.value = null
    return
  }
  emit('view-customer', customerId)
}

const handlePaymentPlanDetailViewApproval = (record: PaymentRecordInfo): void => {
  // Reuse handleRecordClick to open PaymentRecordDetailSheet
  handleRecordClick(record)
}

// ==================== Watch ====================
watch(() => props.visible, (visible): void => {
  if (visible && props.customerId !== null) {
    resetLocalNavigation()
    applyNavigationTarget()
    loadAllData(props.customerId)
  } else if (!visible) {
    // 清理状态
    resetLocalNavigation()
    customer.value = null
    followUps.value = []
    opportunities.value = []
    contracts.value = []
    paymentPlans.value = []
    invoiceTitles.value = []
    deployments.value = []
    // Clear nested sheet states
    selectedContractId.value = null
    selectedPlanId.value = null
    planSheetVisible.value = false
    selectedRecord.value = null
    recordSheetVisible.value = false
    fixedContractOpportunity.value = null
    customerEditDialogOpen.value = false
    deploymentDialogOpen.value = false
  }
}, { immediate: true })

watch(() => props.customerId, (customerId, previousCustomerId): void => {
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
</script>

<template>
  <Sheet :open="visible" @update:open="emit('update:visible', $event)">
    <DetailSheetContent>
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
        @close="emit('update:visible', false)"
        @refresh="handleOpportunityDetailRefresh"
        @create-contract="handleOpportunityDetailCreateContract"
        @edit-contract="handleEditContract"
        @submit-contract-approval="handleSubmitContractApproval"
        @withdraw-contract-approval="handleWithdrawContractApproval"
        @delete-contract="handleDeleteContract"
      />

      <ContractDetailContent
        v-else-if="selectedContractId !== null"
        :contract-id="selectedContractId"
        embedded
        @back="handleBackFromContract"
        @close="emit('update:visible', false)"
        @refresh="handleContractSheetRefresh"
        @approve="handleContractApprove"
        @reject="handleContractReject"
      />

      <template v-else>
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
          <div class="p-6 space-y-6">
            <template v-if="activePanel === 'customer-brief'">
              <!-- 客户档案卡片 -->
              <Card class="customer-brief-card">
                <CardContent class="p-0">
                  <div class="brief-card-header">
                    <div class="brief-card-title">
                      <Sparkles class="h-4 w-4 text-wolf-primary-v2 flex-shrink-0" aria-hidden="true" />
                      <h3 class="text-sm font-semibold text-wolf-text-primary-v2 truncate">客户档案</h3>
                      <Badge
                        variant="outline"
                        class="brief-status-badge"
                        :class="getCustomerBriefStatusClass(customer?.customer_brief_status)"
                      >
                        {{ getCustomerBriefStatusLabel(customer?.customer_brief_status) }}
                      </Badge>
                      <span v-if="customerBriefUpdatedText" class="brief-card-meta">
                        {{ customerBriefUpdatedText }}
                      </span>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      class="h-8 w-8 text-wolf-text-tertiary-v2 hover:text-wolf-primary-v2"
                      :disabled="isCustomerBriefRefreshing"
                      @click="handleRegenerateBrief"
                    >
                      <RefreshCw
                        class="h-4 w-4"
                        :class="{ 'animate-spin': isCustomerBriefRefreshing }"
                        aria-hidden="true"
                      />
                      <span class="sr-only">刷新智能档案</span>
                    </Button>
                  </div>

                  <div class="p-4">
                    <div
                      v-if="hasCustomerBriefContent"
                      class="customer-brief-content"
                    >
                      <template v-for="(block, blockIndex) in renderedCustomerBrief" :key="blockIndex">
                        <component :is="block.type" v-if="block.type === 'h2' || block.type === 'h3' || block.type === 'p'">
                          <template v-for="(node, nodeIndex) in block.nodes" :key="`${blockIndex}-${nodeIndex}`">
                            <strong v-if="node.type === 'strong'">{{ node.text }}</strong>
                            <HoverInfo
                              v-else-if="node.type === 'citation' && node.citation"
                              side="top"
                              align="center"
                              content-class="customer-brief-citation-hover-card"
                            >
                              <template #trigger>
                                <span
                                  class="customer-brief-citation"
                                  tabindex="0"
                                  :aria-label="`引用 ${node.citationKey}，${node.sourceLabel}`"
                                >
                                  {{ node.text }}
                                </span>
                              </template>
                              <div class="customer-brief-citation-card">
                                <div class="customer-brief-citation-title">
                                  {{ node.citation.title?.trim() || node.sourceLabel }}
                                </div>
                                <div
                                  v-if="node.citation.excerpt?.trim()"
                                  class="customer-brief-citation-excerpt"
                                >
                                  {{ node.citation.excerpt.trim() }}
                                </div>
                              </div>
                            </HoverInfo>
                            <span v-else>{{ node.text }}</span>
                          </template>
                        </component>
                        <component :is="block.type" v-else-if="block.type === 'ul' || block.type === 'ol'">
                          <li v-for="(item, itemIndex) in block.items" :key="`${blockIndex}-${itemIndex}`">
                            <template v-for="(node, nodeIndex) in item" :key="`${blockIndex}-${itemIndex}-${nodeIndex}`">
                              <strong v-if="node.type === 'strong'">{{ node.text }}</strong>
                              <HoverInfo
                                v-else-if="node.type === 'citation' && node.citation"
                                side="top"
                                align="center"
                                content-class="customer-brief-citation-hover-card"
                              >
                                <template #trigger>
                                  <span
                                    class="customer-brief-citation"
                                    tabindex="0"
                                    :aria-label="`引用 ${node.citationKey}，${node.sourceLabel}`"
                                  >
                                    {{ node.text }}
                                  </span>
                                </template>
                                <div class="customer-brief-citation-card">
                                  <div class="customer-brief-citation-title">
                                    {{ node.citation.title?.trim() || node.sourceLabel }}
                                  </div>
                                  <div
                                    v-if="node.citation.excerpt?.trim()"
                                    class="customer-brief-citation-excerpt"
                                  >
                                    {{ node.citation.excerpt.trim() }}
                                  </div>
                                </div>
                              </HoverInfo>
                              <span v-else>{{ node.text }}</span>
                            </template>
                          </li>
                        </component>
                      </template>
                    </div>
                    <div
                      v-else-if="customer?.customer_brief_status === 'GENERATING' || isCustomerBriefAwaitingAutoBuild"
                      class="brief-inline-state"
                    >
                      <Loader2
                        v-if="customer?.customer_brief_status === 'GENERATING'"
                        class="h-4 w-4 animate-spin text-wolf-primary-v2"
                        aria-hidden="true"
                      />
                      <Sparkles
                        v-else
                        class="h-4 w-4 text-wolf-primary-v2"
                        aria-hidden="true"
                      />
                      <span>客户智能档案正在整理，会根据客户活动和业务进展自动更新</span>
                    </div>
                    <Empty
                      v-else-if="customer?.customer_brief_status === 'FAILED'"
                      class="min-h-[160px] border-0 py-4"
                    >
                      <EmptyHeader>
                        <EmptyMedia variant="icon">
                          <Sparkles class="h-5 w-5" aria-hidden="true" />
                        </EmptyMedia>
                        <EmptyTitle class="text-sm font-medium">客户智能档案暂未刷新成功</EmptyTitle>
                        <EmptyDescription>
                          {{ customer?.customer_brief_error_message || '可稍后重试' }}
                        </EmptyDescription>
                      </EmptyHeader>
                      <EmptyContent>
                        <Button
                          variant="outline"
                          size="sm"
                          :disabled="regeneratingBrief"
                          @click="handleRegenerateBrief"
                        >
                          <RefreshCw class="w-4 h-4 mr-2" :class="{ 'animate-spin': regeneratingBrief }" />
                          重新整理
                        </Button>
                      </EmptyContent>
                    </Empty>
                    <Empty v-else class="min-h-[160px] border-0 py-4">
                      <EmptyHeader>
                        <EmptyMedia variant="icon">
                          <Sparkles class="h-5 w-5" aria-hidden="true" />
                        </EmptyMedia>
                        <EmptyTitle class="text-sm font-medium">暂无客户智能档案</EmptyTitle>
                        <EmptyDescription>
                          有客户活动、商机、合同、回款等业务进展后，这里会自动更新
                        </EmptyDescription>
                      </EmptyHeader>
                    </Empty>
                  </div>
                </CardContent>
              </Card>
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

              <InvoicesPanel
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

              <LicensePanel
                :customer-id="customerId ?? ''"
                :customer-name="customer?.account_name ?? null"
                :license-applications="[]"
                :deployments="deployments"
                :show-license-applications="false"
                :show-add-deployment="canCreateDeployment"
                @add-deployment="handleCreateDeployment"
              />

              <CustomerMembersPanel
                :customer-id="customerId ?? ''"
                :members="customerMembers"
                :can-manage-members="canManageCustomerMembers"
                @refresh="refreshCustomerMembers"
              />
            </template>

            <!-- 根据 activePanel 显示对应面板 -->
            <FollowUpPanel
              v-if="activePanel === 'followup'"
              :follow-ups="followUps"
              :current-user-id="String(userStore.userInfo?.id)"
              :show-header="false"
              :show-add="canCreateActivity"
              @add="handleCreateFollowUp"
              @delete="handleFollowUpDelete"
              @process="handleActivityProcess"
            />

            <OpportunitiesPanel
              v-if="activePanel === 'opportunities'"
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
          v-if="activePanel !== 'customer-brief'"
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

  <!-- Payment Plan Detail Sheet (Task 6) -->
  <PaymentPlanDetailSheet
    :plan-id="selectedPlanId"
    :visible="planSheetVisible"
    @update:visible="planSheetVisible = $event"
    @refresh="handlePlanSheetRefresh"
    @record-click="handleRecordClick"
    @view-contract="handlePaymentPlanDetailViewContract"
    @view-customer="handlePaymentPlanDetailViewCustomer"
    @view-approval="handlePaymentPlanDetailViewApproval"
  />

  <!-- Payment Record Detail Sheet (Task 6) -->
  <PaymentRecordDetailSheet
    :record-id="selectedRecord?.record.id ?? null"
    :visible="recordSheetVisible"
    :record="selectedRecord?.record ?? null"
    :stage-name="selectedRecord?.stageName ?? ''"
    :approval="selectedRecord?.approval ?? null"
    @update:visible="recordSheetVisible = $event"
    @refresh="handleRecordSheetRefresh"
    @edit="handleRecordEdit"
    @resubmit="handleRecordResubmit"
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

.customer-detail-sheet__header {
  padding-right: 72px;
}

.customer-detail-sheet__footer {
  display: flex;
  flex-direction: row;
  justify-content: flex-end;
  gap: $wolf-space-sm-v2;
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

// Customer brief card styles
.customer-brief-card {
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-surface-v2;
  background: $wolf-bg-card-v2;
}

.brief-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $wolf-space-md-v2;
  padding: $wolf-space-lg-v2;
  border-bottom: 1px solid $wolf-border-light-v2;
}

.brief-card-title {
  display: flex;
  min-width: 0;
  flex: 1;
  align-items: center;
  gap: $wolf-space-sm-v2;
}

.brief-card-meta {
  min-width: fit-content;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
}

.brief-status-badge {
  flex-shrink: 0;
  height: 22px;
  border-radius: $wolf-radius-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.brief-status-badge--completed {
  color: $wolf-success-text-v2;
  background: $wolf-success-bg-v2;
  border-color: $wolf-success-bg-v2;
}

.brief-status-badge--generating {
  color: $wolf-warning-text-v2;
  background: $wolf-warning-bg-v2;
  border-color: $wolf-warning-bg-v2;
}

.brief-status-badge--failed {
  color: $wolf-danger-text-v2;
  background: $wolf-danger-bg-v2;
  border-color: $wolf-danger-bg-v2;
}

.brief-status-badge--pending {
  color: $wolf-text-tertiary-v2;
  background: $wolf-bg-muted-v2;
  border-color: $wolf-border-light-v2;
}

.brief-inline-state {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  min-height: 96px;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-body-v2;
}

.customer-brief-content {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-body-v2;
  line-height: $wolf-line-height-body-v2;
}

.customer-brief-content h2 {
  margin: 0 0 $wolf-space-sm-v2;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  line-height: $wolf-line-height-title-v2;
}

.customer-brief-content h3 {
  margin: $wolf-space-lg-v2 0 $wolf-space-sm-v2;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  line-height: $wolf-line-height-body-v2;
}

.customer-brief-content h2:first-child,
.customer-brief-content h3:first-child {
  margin-top: 0;
}

.customer-brief-content p {
  margin: 0 0 $wolf-space-sm-v2;
}

.customer-brief-content ul,
.customer-brief-content ol {
  margin: 0 0 $wolf-space-md-v2;
  padding-left: $wolf-space-xl-v2;
}

.customer-brief-content li {
  margin: $wolf-space-xs-v2 0;
}

.customer-brief-content strong {
  color: $wolf-text-primary-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.customer-brief-citation {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  margin-left: 2px;
  padding: 0 4px;
  border-radius: $wolf-radius-sm-v2;
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: 1;
  cursor: help;
  vertical-align: baseline;
}

.customer-brief-citation:hover,
.customer-brief-citation:focus-visible {
  background: $wolf-bg-hover-v2;
  color: $wolf-primary-hover-v2;
  outline: none;
}

:global(.customer-brief-citation-hover-card) {
  max-width: 280px;
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
}

.customer-brief-citation-card {
  display: grid;
  gap: $wolf-space-xs-v2;
}

.customer-brief-citation-title {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.customer-brief-citation-excerpt {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
  white-space: pre-line;
}

.customer-brief-content blockquote {
  margin: $wolf-space-md-v2 0;
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
  border-left: 3px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-sm-v2;
  background: $wolf-bg-muted-v2;
  color: $wolf-text-secondary-v2;
}

</style>
