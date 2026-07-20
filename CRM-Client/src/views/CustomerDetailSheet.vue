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
import { ContextTabs } from '@/components/crmwolf'
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent
} from '@/components/ui/accordion'
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
import ContractsPanel from '@/components/panels/ContractsPanel.vue'
import PaymentsPanel from '@/components/panels/PaymentsPanel.vue'
import InvoicesPanel from '@/components/panels/InvoicesPanel.vue'
import LicensePanel from '@/components/panels/LicensePanel.vue'

// Dialogs
import FollowUpFormDialog from '@/components/dialogs/FollowUpFormDialog.vue'
import ContactFormDialog from '@/components/dialogs/ContactFormDialog.vue'
import OpportunityFormDialog from '@/components/dialogs/OpportunityFormDialog.vue'
import ContractFormDialog from '@/components/dialogs/ContractFormDialog.vue'
import InvoiceTitleFormDialog from '@/components/dialogs/InvoiceTitleFormDialog.vue'
import InvoiceApplicationFormDialog from '@/components/dialogs/InvoiceApplicationFormDialog.vue'
import DeploymentInfoFormDialog from '@/components/dialogs/DeploymentInfoFormDialog.vue'
import LicenseApplicationFormDialog from '@/components/dialogs/LicenseApplicationFormDialog.vue'

// Detail Sheets (Task 6)
import ContractDetailSheet from '@/views/ContractDetailSheet.vue'
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
import licenseApplicationApi, { type LicenseApplicationResponse } from '@/api/licenseApplication'
import deploymentApi, { type DeploymentInfoResponse } from '@/api/deployment'
import { getCustomerScore, type ScoreResponse } from '@/api/score'
import { normalizePaginatedResponse } from '@/types/pagination'

// ==================== Props & Emits ====================
interface Props {
  customerId: number | null
  visible: boolean
}

const props = defineProps<Props>()
defineEmits<{
  'update:visible': [value: boolean]
  'refresh': []
}>()

const router = useRouter()

// ==================== State ====================
const loading = ref(false)  // TODO: Task 3 - 加载客户详情数据时使用
const activePanel = ref('customer-brief')  // Sidebar 导航切换
const regeneratingProfile = ref(false)  // 档案重新生成状态
const regeneratingBrief = ref(false)

// ==================== Dialog States ====================
const followUpDialogOpen = ref(false)
const contactDialogOpen = ref(false)
const opportunityDialogOpen = ref(false)
const contractDialogOpen = ref(false)
const invoiceTitleDialogOpen = ref(false)
const invoiceApplicationDialogOpen = ref(false)
const deploymentDialogOpen = ref(false)
const licenseApplicationDialogOpen = ref(false)

// ==================== Edit States ====================
const editingContact = ref<ContactResponse | null>(null)
const editingContract = ref<ContractResponse | null>(null)
const editingInvoiceTitle = ref<InvoiceTitleResponse | null>(null)
const applyingInvoiceTitle = ref<InvoiceTitleResponse | null>(null)

// ==================== Detail Sheet States (Task 6) ====================
const selectedContractId = ref<number | null>(null)
const contractSheetVisible = ref(false)
const selectedPlanId = ref<number | null>(null)
const planSheetVisible = ref(false)
const selectedRecord = ref<{ record: PaymentRecordInfo; stageName: string; approval: ApprovalInfo | ApprovalInfoLite | null } | null>(null)
const recordSheetVisible = ref(false)

// ==================== Data Loading State ====================
const customer = ref<CustomerDetailResponse | null>(null)
const score = ref<ScoreResponse | null>(null)
const followUps = ref<CustomerFollowUpResponse[]>([])
const opportunities = ref<OpportunityListResponse[]>([])
const contracts = ref<ContractListResponse[]>([])
const paymentPlans = ref<PaymentPlanResponse[]>([])
const invoiceTitles = ref<InvoiceTitleResponse[]>([])
const licenseApplications = ref<LicenseApplicationResponse[]>([])
const deployments = ref<DeploymentInfoResponse[]>([])
let latestLoadRequestId = 0

interface CustomerBriefCitation {
  source_type?: string
  source_id?: string
  title?: string
  excerpt?: string
}

type CustomerBriefCitationMap = Record<string, CustomerBriefCitation>

const escapeHtml = (value: string): string =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

const getCitationSourceLabel = (sourceType: string | undefined): string => {
  const labels: Record<string, string> = {
    customer: '客户',
    customer_profile: '客户档案',
    contact: '联系人',
    opportunity: '商机',
    contract: '合同',
    payment_plan: '回款计划',
    payment_record: '回款记录',
    follow_up: '跟进记录'
  }
  return sourceType !== undefined && sourceType !== '' ? labels[sourceType] ?? sourceType : '来源'
}

const buildCitationTooltip = (citation: CustomerBriefCitation): string => {
  const trimmedTitle = citation.title?.trim()
  const title = trimmedTitle !== undefined && trimmedTitle !== ''
    ? trimmedTitle
    : getCitationSourceLabel(citation.source_type)
  const excerpt = citation.excerpt?.trim()
  if (excerpt === undefined || excerpt === '') return title
  return `${title}\n${excerpt}`
}

const renderInlineMarkdown = (value: string, citationMap: CustomerBriefCitationMap): string => {
  const escaped = escapeHtml(value)
  return escaped
    .replace(/\[(\d+)\]/g, (match, citationKey: string) => {
      const citation = citationMap[citationKey]
      if (citation === undefined) return match

      const tooltip = escapeHtml(buildCitationTooltip(citation))
      const sourceLabel = escapeHtml(getCitationSourceLabel(citation.source_type))
      return [
        '<span',
        ' class="customer-brief-citation"',
        ' tabindex="0"',
        ` aria-label="引用 ${citationKey}，${sourceLabel}"`,
        ` data-citation-tooltip="${tooltip}"`,
        '>',
        `[${citationKey}]`,
        '</span>'
      ].join('')
    })
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
}

const renderSimpleMarkdown = (value: string, citationMap: CustomerBriefCitationMap): string => {
  const lines = value.split('\n')
  const html: string[] = []
  let listType: 'ul' | 'ol' | null = null

  const closeList = (): void => {
    if (listType !== null) {
      html.push(`</${listType}>`)
      listType = null
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
      html.push(`<h2>${renderInlineMarkdown(text.slice(3), citationMap)}</h2>`)
      continue
    }

    if (text.startsWith('### ')) {
      closeList()
      html.push(`<h3>${renderInlineMarkdown(text.slice(4), citationMap)}</h3>`)
      continue
    }

    if (/^- /.test(text)) {
      if (listType !== 'ul') {
        closeList()
        html.push('<ul>')
        listType = 'ul'
      }
      html.push(`<li>${renderInlineMarkdown(text.slice(2), citationMap)}</li>`)
      continue
    }

    const orderedMatch = text.match(/^\d+\.\s+(.+)$/)
    if (orderedMatch !== null) {
      if (listType !== 'ol') {
        closeList()
        html.push('<ol>')
        listType = 'ol'
      }
      html.push(`<li>${renderInlineMarkdown(orderedMatch[1] ?? '', citationMap)}</li>`)
      continue
    }

    closeList()
    html.push(`<p>${renderInlineMarkdown(text, citationMap)}</p>`)
  }

  closeList()
  return html.join('')
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

const renderedCustomerBrief = computed<string>(() => {
  const markdownText = customer.value?.customer_brief_markdown?.trim()
  if (markdownText === undefined || markdownText === null || markdownText === '') return ''
  return renderSimpleMarkdown(markdownText, customerBriefCitationMap.value)
})

// ==================== Navigation Tabs ====================
interface NavTabItem {
  key: string
  label: string
}

const navTabs: NavTabItem[] = [
  { key: 'customer-brief', label: '客户概况' },
  { key: 'followup', label: '跟进记录' },
  { key: 'contacts', label: '联系人' },
  { key: 'opportunities', label: '商机' },
  { key: 'contracts', label: '合同' },
  { key: 'payments', label: '回款' },
  { key: 'invoices', label: '发票' },
  { key: 'license-management', label: 'License' }
]

// ==================== Methods ====================
const handleCreateOpportunity = (): void => {
  // 打开新建商机弹窗
  opportunityDialogOpen.value = true
}

const handleCreateContract = (): void => {
  // TODO: 打开新建合同弹窗
}

const handleEdit = (): void => {
  // TODO: 跳转编辑页面
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
      licenseApplicationsData,
      deploymentsData
    ] = await Promise.all([
      customerApi.getCustomerDetail(customerId),
      getCustomerScore(customerId).catch(() => null),
      customerFollowUpApi.getFollowUps(customerId).catch(() => []),
      opportunityApi.getOpportunities({ customer_id: customerId }).catch(() => []),
      contractApi.getCustomerContracts(customerId).catch(() => []),
      invoiceApi.getInvoiceTitles(customerId).catch(() => ({ invoice_titles: [] })),
      licenseApplicationApi.list(customerId).catch(() => []),
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
    licenseApplications.value = licenseApplicationsData
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

// ==================== Profile Actions ====================
const handleRegenerateProfile = async (): Promise<void> => {
  if (props.customerId === null) return
  regeneratingProfile.value = true
  try {
    await customerApi.regenerateProfile(props.customerId)
    toast.success('档案生成中，请稍后刷新')
  } catch (error) {
    handleApiError(error, '生成档案')
  } finally {
    regeneratingProfile.value = false
  }
}

const handleRegenerateBrief = async (): Promise<void> => {
  if (props.customerId === null) return
  regeneratingBrief.value = true
  try {
    await customerApi.regenerateCustomerBrief(props.customerId)
    toast.success('客户概况生成中，请稍后刷新')
    await loadAllData(props.customerId)
  } catch (error) {
    handleApiError(error, '生成客户概况')
  } finally {
    regeneratingBrief.value = false
  }
}

// ==================== Dialog Handlers ====================
// FollowUp handlers
const handleFollowUpSuccess = (): void => {
  followUpDialogOpen.value = false
  if (props.customerId !== null) {
    loadAllData(props.customerId)
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

// Contract handlers
const handleContractDialogClose = (open: boolean): void => {
  contractDialogOpen.value = open
  if (!open) {
    editingContract.value = null
  }
}

const handleContractSuccess = (): void => {
  contractDialogOpen.value = false
  editingContract.value = null
  if (props.customerId !== null) {
    loadAllData(props.customerId)
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

const handleApplyInvoice = (invoiceTitle: InvoiceTitleResponse): void => {
  applyingInvoiceTitle.value = invoiceTitle
  invoiceApplicationDialogOpen.value = true
}

const handleInvoiceApplicationDialogClose = (open: boolean): void => {
  invoiceApplicationDialogOpen.value = open
  if (!open) {
    applyingInvoiceTitle.value = null
  }
}

const handleInvoiceApplicationSuccess = (): void => {
  invoiceApplicationDialogOpen.value = false
  applyingInvoiceTitle.value = null
  if (props.customerId !== null) {
    loadAllData(props.customerId)
  }
}

// Payment handlers
const handleRecordPayment = (): void => {
  // TODO: 打开回款记录对话框
  toast.info('回款记录功能开发中')
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

const handleApplyLicense = (): void => {
  licenseApplicationDialogOpen.value = true
}

const handleLicenseApplicationSuccess = (): void => {
  licenseApplicationDialogOpen.value = false
  if (props.customerId !== null) {
    loadAllData(props.customerId)
  }
}

// Contract detail sheet handlers (Task 6)
const handleViewContract = (contractId: number): void => {
  selectedContractId.value = contractId
  contractSheetVisible.value = true
}

const handleContractSheetRefresh = (): void => {
  if (props.customerId !== null) {
    loadAllData(props.customerId)
  }
}

// Payment plan detail sheet handlers (Task 6)
const handleViewPaymentPlan = (planId: number): void => {
  selectedPlanId.value = planId
  planSheetVisible.value = true
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

// Contract detail sheet approval handlers (Task 6 fix)
const handleContractApprove = (): void => {
  // ContractDetailSheet handles the action internally, just refresh parent data
  handleContractSheetRefresh()
}

const handleContractReject = (): void => {
  // ContractDetailSheet handles the action internally, just refresh parent data
  handleContractSheetRefresh()
}

// Payment plan detail sheet nested event handlers (Task 6 fix)
const handlePaymentPlanDetailViewContract = (contractId: number): void => {
  // Close the plan sheet and open contract sheet
  planSheetVisible.value = false
  selectedPlanId.value = null
  // Open contract sheet
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
    licenseApplications.value = []
    deployments.value = []
    // Clear nested sheet states
    selectedContractId.value = null
    contractSheetVisible.value = false
    selectedPlanId.value = null
    planSheetVisible.value = false
    selectedRecord.value = null
    recordSheetVisible.value = false
    deploymentDialogOpen.value = false
    licenseApplicationDialogOpen.value = false
  }
}, { immediate: true })

watch(() => props.customerId, (customerId, previousCustomerId): void => {
  if (!props.visible || customerId === null || customerId === previousCustomerId) return
  activePanel.value = 'customer-brief'
  loadAllData(customerId)
})
</script>

<template>
  <Sheet :open="visible" @update:open="$emit('update:visible', $event)">
    <DetailSheetContent>
      <!-- Header -->
      <SheetHeader class="p-6 border-b border-wolf-border-default-v2">
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
              <!-- 客户概况卡片 -->
              <Card class="customer-brief-card">
                <CardContent class="p-0">
                  <div class="brief-card-header">
                    <div class="flex items-center gap-2 min-w-0">
                      <Sparkles class="h-4 w-4 text-wolf-primary-v2 flex-shrink-0" aria-hidden="true" />
                      <h3 class="text-sm font-semibold text-wolf-text-primary-v2">客户概况</h3>
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
                      <span class="sr-only">生成客户概况</span>
                    </Button>
                  </div>

                  <div class="p-4">
                    <div
                      v-if="customer?.customer_brief_status === 'COMPLETED' && renderedCustomerBrief"
                      class="customer-brief-content"
                      v-html="renderedCustomerBrief"
                    />
                    <div
                      v-else-if="customer?.customer_brief_status === 'GENERATING'"
                      class="brief-inline-state"
                    >
                      <Loader2 class="h-4 w-4 animate-spin text-wolf-primary-v2" aria-hidden="true" />
                      <span>客户概况正在生成中，请稍后刷新查看</span>
                    </div>
                    <Empty
                      v-else-if="customer?.customer_brief_status === 'FAILED'"
                      class="min-h-[160px] border-0 py-4"
                    >
                      <EmptyHeader>
                        <EmptyMedia variant="icon">
                          <Sparkles class="h-5 w-5" aria-hidden="true" />
                        </EmptyMedia>
                        <EmptyTitle class="text-sm font-medium">客户概况生成失败</EmptyTitle>
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
                        <EmptyTitle class="text-sm font-medium">暂无客户概况</EmptyTitle>
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

            <template v-if="activePanel === 'followup'">
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

              <!-- 客户档案卡片（Accordion） -->
              <Accordion type="single" collapsible class="profile-accordion">
                <AccordionItem value="profile">
                  <AccordionTrigger class="px-4 py-3 hover:no-underline">
                    <div class="flex items-center gap-2 w-full">
                      <span class="text-sm font-semibold text-wolf-text-primary-v2">客户档案</span>
                      <Badge
                        v-if="customer?.profile_status"
                        variant="outline"
                        class="ml-2"
                      >
                        {{ customer.profile_status === 'PENDING' ? '待生成' : customer.profile_status === 'GENERATING' ? '生成中' : customer.profile_status === 'COMPLETED' ? '已完成' : '失败' }}
                      </Badge>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent class="px-4 pb-4">
                    <!-- 生成中状态 -->
                    <div v-if="customer?.profile_status === 'GENERATING'" class="flex items-center gap-3 py-4">
                      <Loader2 class="w-5 h-5 animate-spin text-wolf-primary-v2" />
                      <span class="text-sm text-wolf-text-secondary-v2">档案正在生成中，请稍后刷新查看...</span>
                    </div>

                    <!-- 待生成状态 -->
                    <Empty v-else-if="customer?.profile_status === 'PENDING' || !customer?.profile_status" class="min-h-[160px] border-0 py-4">
                      <EmptyHeader>
                        <EmptyMedia variant="icon">
                          <RefreshCw class="h-5 w-5" aria-hidden="true" />
                        </EmptyMedia>
                        <EmptyTitle class="text-sm font-medium">暂无客户档案</EmptyTitle>
                        <EmptyDescription>生成后可查看客户画像与分析摘要</EmptyDescription>
                      </EmptyHeader>
                      <EmptyContent>
                      <Button
                        variant="outline"
                        size="sm"
                        :disabled="regeneratingProfile"
                        @click="handleRegenerateProfile"
                      >
                        <RefreshCw class="w-4 h-4 mr-2" :class="{ 'animate-spin': regeneratingProfile }" />
                        生成档案
                      </Button>
                      </EmptyContent>
                    </Empty>

                    <!-- 失败状态 -->
                    <div v-else-if="customer?.profile_status === 'FAILED'" class="flex flex-col gap-3 py-4">
                      <div class="text-sm text-wolf-danger-text-v2">
                        档案生成失败: {{ customer?.profile_error_message || '未知错误' }}
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        :disabled="regeneratingProfile"
                        @click="handleRegenerateProfile"
                      >
                        <RefreshCw class="w-4 h-4 mr-2" :class="{ 'animate-spin': regeneratingProfile }" />
                        重新生成
                      </Button>
                    </div>

                    <!-- 已完成状态 -->
                    <div v-else-if="customer?.profile_status === 'COMPLETED'" class="space-y-4">
                      <!-- 企业背景 -->
                      <div v-if="customer?.company_background" class="profile-item">
                        <div class="profile-label">企业背景</div>
                        <div class="profile-value">{{ customer.company_background }}</div>
                      </div>

                      <!-- 公司网站 -->
                      <div v-if="customer?.company_website" class="profile-item">
                        <div class="profile-label">公司网站</div>
                        <a
                          :href="customer.company_website"
                          target="_blank"
                          rel="noopener noreferrer"
                          class="profile-link"
                        >
                          {{ customer.company_website }}
                        </a>
                      </div>

                      <!-- 主营业务 -->
                      <div v-if="customer?.main_business" class="profile-item">
                        <div class="profile-label">主营业务</div>
                        <div class="profile-value">{{ customer.main_business }}</div>
                      </div>

                      <!-- 项目背景 -->
                      <div v-if="customer?.project_background" class="profile-item">
                        <div class="profile-label">项目背景</div>
                        <div class="profile-value">{{ customer.project_background }}</div>
                      </div>

                      <!-- 重新生成按钮 -->
                      <div class="pt-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          :disabled="regeneratingProfile"
                          @click="handleRegenerateProfile"
                        >
                          <RefreshCw class="w-4 h-4 mr-2" :class="{ 'animate-spin': regeneratingProfile }" />
                          重新生成档案
                        </Button>
                      </div>
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </template>

            <!-- 根据 activePanel 显示对应面板 -->
            <FollowUpPanel
              v-if="activePanel === 'followup'"
              :follow-ups="followUps"
              @add="followUpDialogOpen = true"
            />

            <ContactsPanel
              v-if="activePanel === 'contacts'"
              :customer-id="customerId ?? 0"
              :contacts="customer?.contacts ?? []"
              @add="contactDialogOpen = true"
              @edit="handleEditContact"
              @delete="handleDeleteContact"
              @set-primary="handleSetPrimaryContact"
            />

            <OpportunitiesPanel
              v-if="activePanel === 'opportunities'"
              :customer-id="customerId ?? 0"
              :opportunities="opportunities"
              @add="opportunityDialogOpen = true"
            />

            <ContractsPanel
              v-if="activePanel === 'contracts'"
              :customer-id="customerId ?? 0"
              :contracts="contracts"
              @add="contractDialogOpen = true"
              @view="handleViewContract"
            />

            <PaymentsPanel
              v-if="activePanel === 'payments'"
              :customer-id="customerId ?? 0"
              :payments="paymentPlans"
              @record="handleRecordPayment"
              @view="handleViewPaymentPlan"
            />

            <InvoicesPanel
              v-if="activePanel === 'invoices'"
              :customer-id="customerId ?? 0"
              :invoice-titles="invoiceTitles"
              @add="invoiceTitleDialogOpen = true"
              @edit="handleEditInvoiceTitle"
              @delete="handleDeleteInvoiceTitle"
              @set-default="handleSetDefaultInvoiceTitle"
              @apply="handleApplyInvoice"
            />

            <LicensePanel
              v-if="activePanel === 'license-management'"
              :customer-id="customerId ?? 0"
              :customer-name="customer?.account_name ?? null"
              :license-applications="licenseApplications"
              :deployments="deployments"
              @add-deployment="handleCreateDeployment"
              @apply="handleApplyLicense"
            />
          </div>
        </ScrollArea>

        <!-- Footer -->
        <SheetFooter class="p-4 border-t border-wolf-border-default-v2 flex flex-row gap-2">
          <Button variant="default" @click="handleCreateOpportunity">
            <Plus class="w-4 h-4 mr-2" />
            新建商机
          </Button>
          <Button variant="outline" @click="handleCreateContract">
            <Plus class="w-4 h-4 mr-2" />
            新建合同
          </Button>
          <Button variant="outline" @click="handleEdit">
            <Pencil class="w-4 h-4 mr-2" />
            编辑
          </Button>
        </SheetFooter>
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

  <InvoiceApplicationFormDialog
    v-if="customerId !== null && customer !== null"
    mode="create"
    :open="invoiceApplicationDialogOpen"
    :fixed-customer="{ id: customer.id, account_name: customer.account_name }"
    :fixed-invoice-title="applyingInvoiceTitle"
    @update:open="handleInvoiceApplicationDialogClose"
    @success="handleInvoiceApplicationSuccess"
  />

  <DeploymentInfoFormDialog
    v-if="customerId !== null"
    :customer-id="customerId"
    :open="deploymentDialogOpen"
    @update:open="deploymentDialogOpen = $event"
    @success="handleDeploymentSuccess"
  />

  <LicenseApplicationFormDialog
    v-if="customerId !== null"
    :customer-id="customerId"
    :open="licenseApplicationDialogOpen"
    :deployments="deployments"
    :contracts="contracts"
    @update:open="licenseApplicationDialogOpen = $event"
    @success="handleLicenseApplicationSuccess"
  />

  <!-- Contract Detail Sheet (Task 6) -->
  <ContractDetailSheet
    :contract-id="selectedContractId"
    :visible="contractSheetVisible"
    @update:visible="contractSheetVisible = $event"
    @refresh="handleContractSheetRefresh"
    @approve="handleContractApprove"
    @reject="handleContractReject"
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

// Profile card styles
.profile-accordion {
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-lg-v2;
  background: $wolf-bg-card-v2;
}

.profile-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.profile-label {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.profile-value {
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-secondary-v2;
  line-height: $wolf-line-height-body-v2;
}

.profile-link {
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-link-v2;
  text-decoration: underline;

  &:hover {
    color: $wolf-text-link-hover-v2;
  }
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

.customer-brief-content :deep(h2) {
  margin: 0 0 $wolf-space-sm-v2;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  line-height: $wolf-line-height-title-v2;
}

.customer-brief-content :deep(h3) {
  margin: $wolf-space-lg-v2 0 $wolf-space-sm-v2;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  line-height: $wolf-line-height-body-v2;
}

.customer-brief-content :deep(h2:first-child),
.customer-brief-content :deep(h3:first-child) {
  margin-top: 0;
}

.customer-brief-content :deep(p) {
  margin: 0 0 $wolf-space-sm-v2;
}

.customer-brief-content :deep(ul),
.customer-brief-content :deep(ol) {
  margin: 0 0 $wolf-space-md-v2;
  padding-left: $wolf-space-xl-v2;
}

.customer-brief-content :deep(li) {
  margin: $wolf-space-xs-v2 0;
}

.customer-brief-content :deep(strong) {
  color: $wolf-text-primary-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.customer-brief-content :deep(.customer-brief-citation) {
  position: relative;
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

.customer-brief-content :deep(.customer-brief-citation:hover),
.customer-brief-content :deep(.customer-brief-citation:focus-visible) {
  background: $wolf-bg-hover-v2;
  color: $wolf-primary-hover-v2;
  outline: none;
}

.customer-brief-content :deep(.customer-brief-citation::after) {
  position: absolute;
  left: 50%;
  bottom: calc(100% + 8px);
  z-index: 20;
  width: max-content;
  max-width: 280px;
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-bg-elevated-v2;
  box-shadow: $wolf-shadow-modal-v2;
  color: $wolf-text-primary-v2;
  content: attr(data-citation-tooltip);
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-normal-v2;
  line-height: $wolf-line-height-body-v2;
  opacity: 0;
  pointer-events: none;
  text-align: left;
  transform: translate(-50%, 4px);
  transition: opacity 120ms ease, transform 120ms ease;
  white-space: pre-line;
}

.customer-brief-content :deep(.customer-brief-citation:hover::after),
.customer-brief-content :deep(.customer-brief-citation:focus-visible::after) {
  opacity: 1;
  transform: translate(-50%, 0);
}

.customer-brief-content :deep(blockquote) {
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
