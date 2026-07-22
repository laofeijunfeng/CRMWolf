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
import { useRouter } from 'vue-router'
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
import { Progress } from '@/components/ui/progress'
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

// Detail Sheets (Task 6)
import PaymentPlanDetailSheet from '@/views/PaymentPlanDetailSheet.vue'
import PaymentRecordDetailSheet from '@/views/PaymentRecordDetailSheet.vue'

import { Plus, Pencil, RefreshCw, Loader2, Sparkles } from 'lucide-vue-next'
import ScoreIndicator from '@/components/ScoreIndicator.vue'
import { toast } from 'vue-sonner'
import { handleApiError } from '@/utils/errorHandler'
import customerApi, { type CustomerDetailResponse, type ContactResponse } from '@/api/customer'
import customerFollowUpApi, { type CustomerFollowUpResponse } from '@/api/customerFollowUp'
import { opportunityApi, type OpportunityListResponse } from '@/api/opportunity'
import contractApi, { type ContractListResponse, type ContractResponse } from '@/api/contract'
import type { PaymentPlanResponse, PaymentRecordInfo, ApprovalInfo, ApprovalInfoLite } from '@/api/payment'
import paymentApi from '@/api/payment'
import invoiceApi, { type InvoiceTitleResponse } from '@/api/invoice'
import deploymentApi, { type DeploymentInfoResponse } from '@/api/deployment'
import { getCustomerScore, type ScoreResponse } from '@/api/score'
import { normalizePaginatedResponse } from '@/types/pagination'
import { useUserStore } from '@/stores/user'
import approvalGenericApi from '@/api/approvalGeneric'
import { confirmDelete } from '@/utils/confirmDialog'

// ==================== Props & Emits ====================
interface Props {
  customerId: number | null
  visible: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:visible': [value: boolean]
  'refresh': []
}>()

const router = useRouter()
const userStore = useUserStore()

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
const selectedRecord = ref<{ record: PaymentRecordInfo; stageName: string; approval: ApprovalInfo | ApprovalInfoLite | null } | null>(null)
const recordSheetVisible = ref(false)
const selectedOpportunityId = ref<number | null>(null)

interface ContractOpportunityContext {
  id: number
  opportunity_name: string
  customer_id: number
  customer_name?: string
  total_amount: number
  user_count: number
  license_type: string
  subscription_years: number | null
}

interface CreateContractPayload {
  opportunityId: number
  customerId: number
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
const score = ref<ScoreResponse | null>(null)
const followUps = ref<CustomerFollowUpResponse[]>([])
const opportunities = ref<OpportunityListResponse[]>([])
const contracts = ref<ContractListResponse[]>([])
const paymentPlans = ref<PaymentPlanResponse[]>([])
const invoiceTitles = ref<InvoiceTitleResponse[]>([])
const deployments = ref<DeploymentInfoResponse[]>([])
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
  // 打开新建商机弹窗
  opportunityDialogOpen.value = true
}

const handleEdit = (): void => {
  customerEditDialogOpen.value = true
}

// 占位方法：Sidebar 面板切换
const setActivePanel = (panel: string): void => {
  activePanel.value = panel
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
  if (status === 'COMPLETED') return '已完成'
  if (status === 'GENERATING') return '生成中'
  if (status === 'FAILED') return '失败'
  return '待生成'
}

const getCustomerBriefStatusClass = (status: string | null | undefined): string => {
  if (status === 'COMPLETED') return 'brief-status-badge--completed'
  if (status === 'GENERATING') return 'brief-status-badge--generating'
  if (status === 'FAILED') return 'brief-status-badge--failed'
  return 'brief-status-badge--pending'
}

// ==================== Data Loading ====================
const loadAllData = async (customerId: number): Promise<void> => {
  const loadRequestId = latestLoadRequestId + 1
  latestLoadRequestId = loadRequestId
  loading.value = true

  try {
    const [
      customerDetail,
      scoreData,
      followUpsData,
      opportunitiesData,
      contractsData,
      invoiceTitlesData,
      deploymentsData
    ] = await Promise.all([
      customerApi.getCustomerDetail(customerId),
      getCustomerScore(customerId).catch(() => null),
      customerFollowUpApi.getFollowUps(customerId).catch(() => []),
      opportunityApi.getOpportunities({ customer_id: customerId }).catch(() => []),
      contractApi.getCustomerContracts(customerId).catch(() => []),
      invoiceApi.getInvoiceTitles(customerId).catch(() => ({ invoice_titles: [] })),
      deploymentApi.list(customerId).catch(() => [])
    ])

    if (loadRequestId !== latestLoadRequestId) {
      return
    }

    customer.value = customerDetail
    score.value = scoreData
    followUps.value = followUpsData
    opportunities.value = normalizePaginatedResponse(opportunitiesData).items
    contracts.value = contractsData
    invoiceTitles.value = invoiceTitlesData.invoice_titles ?? []
    deployments.value = deploymentsData

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

// ==================== Score Helpers ====================
// 获取分数对应颜色（用于 Progress 组件的 CSS variable）
// 颜色映射与 Leads.vue 保持一致
const getScoreColorValue = (scoreValue: number | null): string => {
  if (scoreValue === null) return '#94A3B8' // gray-400
  if (scoreValue >= 80) return '#DC2626'    // danger (高/热)
  if (scoreValue >= 60) return '#F59E0B'    // warning
  if (scoreValue >= 40) return '#10B981'    // success
  return '#94A3B8'                           // gray-400 (低/未知)
}

const scoreDetailsDialogOpen = ref(false)

const handleRegenerateBrief = async (): Promise<void> => {
  if (props.customerId === null) return
  regeneratingBrief.value = true
  try {
    await customerApi.regenerateCustomerBrief(props.customerId)
    toast.success('客户档案生成中，请稍后刷新')
    await loadAllData(props.customerId)
  } catch (error) {
    handleApiError(error, '生成客户档案')
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
    await customerFollowUpApi.deleteFollowUp(followUp.id)
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

const handleViewOpportunity = (opportunityId: number): void => {
  selectedOpportunityId.value = opportunityId
}

const handleBackFromOpportunity = (): void => {
  selectedOpportunityId.value = null
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
    approval
  }
  recordSheetVisible.value = true
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

const handlePaymentPlanDetailViewCustomer = (customerId: number): void => {
  // If same customer, close nested sheets and return focus to current customer
  if (customerId === props.customerId) {
    planSheetVisible.value = false
    selectedPlanId.value = null
    recordSheetVisible.value = false
    selectedRecord.value = null
    return
  }
  // Navigate to different customer using router
  router.push({ path: '/customers', query: { customerId: String(customerId) } })
}

const handlePaymentPlanDetailViewApproval = (record: PaymentRecordInfo): void => {
  // Reuse handleRecordClick to open PaymentRecordDetailSheet
  handleRecordClick(record)
}

// ==================== Watch ====================
watch(() => props.visible, (visible): void => {
  if (visible && props.customerId !== null) {
    loadAllData(props.customerId)
  } else if (!visible) {
    // 清理状态
    activePanel.value = 'customer-brief'
    customer.value = null
    score.value = null
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
    selectedOpportunityId.value = null
    fixedContractOpportunity.value = null
    customerEditDialogOpen.value = false
    deploymentDialogOpen.value = false
  }
}, { immediate: true })

watch(() => props.customerId, (customerId, previousCustomerId): void => {
  if (!props.visible || customerId === null || customerId === previousCustomerId) return
  activePanel.value = 'customer-brief'
  selectedOpportunityId.value = null
  selectedContractId.value = null
  loadAllData(customerId)
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
          customerId: customerId ?? 0,
          customerName: customer?.account_name
        }"
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
            @update:active-tab="setActivePanel"
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
                    <div class="flex items-center gap-2 min-w-0">
                      <Sparkles class="h-4 w-4 text-wolf-primary-v2 flex-shrink-0" aria-hidden="true" />
                      <h3 class="text-sm font-semibold text-wolf-text-primary-v2">客户档案</h3>
                      <Badge
                        variant="outline"
                        class="brief-status-badge"
                        :class="getCustomerBriefStatusClass(customer?.customer_brief_status)"
                      >
                        {{ getCustomerBriefStatusLabel(customer?.customer_brief_status) }}
                      </Badge>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      class="h-8 w-8 text-wolf-text-tertiary-v2 hover:text-wolf-primary-v2"
                      :disabled="regeneratingBrief || customer?.customer_brief_status === 'GENERATING'"
                      @click="handleRegenerateBrief"
                    >
                      <RefreshCw
                        class="h-4 w-4"
                        :class="{ 'animate-spin': regeneratingBrief || customer?.customer_brief_status === 'GENERATING' }"
                        aria-hidden="true"
                      />
                      <span class="sr-only">生成客户档案</span>
                    </Button>
                  </div>

                  <div class="p-4">
                    <div
                      v-if="customer?.customer_brief_status === 'COMPLETED' && renderedCustomerBrief.length > 0"
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
                      v-else-if="customer?.customer_brief_status === 'GENERATING'"
                      class="brief-inline-state"
                    >
                      <Loader2 class="h-4 w-4 animate-spin text-wolf-primary-v2" aria-hidden="true" />
                      <span>客户档案正在生成中，请稍后刷新查看</span>
                    </div>
                    <Empty
                      v-else-if="customer?.customer_brief_status === 'FAILED'"
                      class="min-h-[160px] border-0 py-4"
                    >
                      <EmptyHeader>
                        <EmptyMedia variant="icon">
                          <Sparkles class="h-5 w-5" aria-hidden="true" />
                        </EmptyMedia>
                        <EmptyTitle class="text-sm font-medium">客户档案生成失败</EmptyTitle>
                        <EmptyDescription>
                          {{ customer?.customer_brief_error_message || '请稍后重新生成' }}
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
                          重新生成
                        </Button>
                      </EmptyContent>
                    </Empty>
                    <Empty v-else class="min-h-[160px] border-0 py-4">
                      <EmptyHeader>
                        <EmptyMedia variant="icon">
                          <Sparkles class="h-5 w-5" aria-hidden="true" />
                        </EmptyMedia>
                        <EmptyTitle class="text-sm font-medium">暂无客户档案</EmptyTitle>
                        <EmptyDescription>生成后可查看销售侧客户经营摘要</EmptyDescription>
                      </EmptyHeader>
                      <EmptyContent>
                        <Button
                          variant="outline"
                          size="sm"
                          :disabled="regeneratingBrief"
                          @click="handleRegenerateBrief"
                        >
                          <RefreshCw class="w-4 h-4 mr-2" :class="{ 'animate-spin': regeneratingBrief }" />
                          生成概况
                        </Button>
                      </EmptyContent>
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
                    <h3 class="text-sm font-semibold text-wolf-text-primary-v2">基本信息</h3>
                  </div>
                  <div class="p-4">
                    <div class="attributes-grid">
                      <div class="attribute-item">
                        <div class="attribute-label">客户来源</div>
                        <div class="attribute-value">{{ customer?.source || '-' }}</div>
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

              <!-- 热力值卡片 -->
              <Card v-if="score" class="score-card">
                <CardContent class="p-0">
                  <div class="p-4 border-b border-wolf-border-light-v2">
                    <h3 class="text-sm font-semibold text-wolf-text-primary-v2">热力值</h3>
                  </div>
                  <div class="p-4">
                    <div class="flex items-center gap-4">
                      <div class="flex-shrink-0">
                        <ScoreIndicator :score="score.score" mode="card" show-level />
                      </div>
                      <div class="flex-1">
                        <Progress
                          :model-value="score.score || 0"
                          class="h-2"
                          :style="{ '--progress-background': getScoreColorValue(score.score) }"
                        />
                        <div class="flex items-center gap-2 mt-3 text-xs text-wolf-text-tertiary-v2">
                          <template v-for="(detail, idx) in score.details?.slice(0, 2)" :key="detail.id">
                            <span>
                              {{ detail.factor_name }}:
                              <span :class="detail.score_change >= 0 ? 'text-wolf-success-text-v2' : 'text-wolf-danger-text-v2'">
                                {{ detail.score_change >= 0 ? '+' : '' }}{{ detail.score_change }}
                              </span>
                            </span>
                            <span v-if="idx < 1 && score.details?.length > 1">·</span>
                          </template>
                          <Button
                            v-if="score.details?.length > 0"
                            variant="link"
                            size="sm"
                            class="h-auto p-0 text-xs"
                            @click="scoreDetailsDialogOpen = true"
                          >
                            详情
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <ContactsPanel
                :customer-id="customerId ?? 0"
                :contacts="customer?.contacts ?? []"
                @add="contactDialogOpen = true"
                @edit="handleEditContact"
                @delete="handleDeleteContact"
                @set-primary="handleSetPrimaryContact"
              />

              <InvoicesPanel
                :customer-id="customerId ?? 0"
                :invoice-titles="invoiceTitles"
                :invoice-applications="[]"
                :show-invoice-applications="false"
                :show-title-apply-action="false"
                @add="invoiceTitleDialogOpen = true"
                @edit="handleEditInvoiceTitle"
                @delete="handleDeleteInvoiceTitle"
                @set-default="handleSetDefaultInvoiceTitle"
              />

              <LicensePanel
                :customer-id="customerId ?? 0"
                :customer-name="customer?.account_name ?? null"
                :license-applications="[]"
                :deployments="deployments"
                :show-license-applications="false"
                @add-deployment="handleCreateDeployment"
              />
            </template>

            <!-- 根据 activePanel 显示对应面板 -->
            <FollowUpPanel
              v-if="activePanel === 'followup'"
              :follow-ups="followUps"
              :current-user-id="String(userStore.userInfo?.id)"
              :show-header="false"
              @add="followUpDialogOpen = true"
              @delete="handleFollowUpDelete"
            />

            <OpportunitiesPanel
              v-if="activePanel === 'opportunities'"
              :customer-id="customerId ?? 0"
              :opportunities="opportunities"
              @add="opportunityDialogOpen = true"
              @view="handleViewOpportunity"
            />
          </div>
        </ScrollArea>

        <!-- Footer -->
        <SheetFooter class="customer-detail-sheet__footer p-4 border-t border-wolf-border-default-v2">
          <template v-if="activePanel === 'customer-brief'">
            <Button
              variant="default"
              :disabled="regeneratingBrief || customer?.customer_brief_status === 'GENERATING'"
              @click="handleRegenerateBrief"
            >
              <RefreshCw
                class="w-4 h-4 mr-2"
                :class="{ 'animate-spin': regeneratingBrief || customer?.customer_brief_status === 'GENERATING' }"
              />
              生成概况
            </Button>
          </template>

          <template v-else-if="activePanel === 'customer-info'">
            <Button variant="default" @click="contactDialogOpen = true">
              <Plus class="w-4 h-4 mr-2" />
              新建联系人
            </Button>
            <Button variant="outline" @click="invoiceTitleDialogOpen = true">
              <Plus class="w-4 h-4 mr-2" />
              新建抬头
            </Button>
            <Button variant="outline" @click="handleCreateDeployment">
              <Plus class="w-4 h-4 mr-2" />
              新建部署
            </Button>
            <Button variant="outline" @click="handleEdit">
              <Pencil class="w-4 h-4 mr-2" />
              编辑
            </Button>
          </template>

          <template v-else-if="activePanel === 'followup'">
            <Button variant="default" @click="followUpDialogOpen = true">
              <Plus class="w-4 h-4 mr-2" />
              添加跟进
            </Button>
          </template>

          <template v-else-if="activePanel === 'opportunities'">
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
  border-radius: $wolf-radius-lg-v2;
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

.brief-status-badge {
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

// Score card styles
.score-card {
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-lg-v2;
  background: $wolf-bg-card-v2;
}
</style>
