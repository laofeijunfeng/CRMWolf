<script setup lang="ts">
/**
 * ContractDetailSheet.vue - 合同详情抽屉组件基础版
 *
 * Task 1 scope:
 * - shadcn-vue Sheet single-panel structure
 * - Header summary, basic attributes grid, conditional approval progress
 * - Loading, error/empty, responsive states
 * - Dialogs intentionally remain outside this Sheet; approve/reject events are seams for later tasks.
 */
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { AlertCircle, FileText, Pencil, ReceiptText, RefreshCw, X } from 'lucide-vue-next'
import {
  Sheet,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter
} from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import ApprovalProcessGeneric from '@/components/ApprovalProcessGeneric.vue'
import ContractPaymentPlans from '@/components/ContractPaymentPlans.vue'
import ContractFormDialog from '@/components/dialogs/ContractFormDialog.vue'
import contractApi, { type ContractResponse, type ContractStatus, type LicenseType } from '@/api/contract'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'
import { handleApiError } from '@/utils/errorHandler'
import { formatCurrency } from '@/utils/format'

// ==================== Props & Emits ====================
interface Props {
  contractId: number | null
  visible: boolean
  canApprove?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  canApprove: false
})

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'approve': [contractId: number]
  'reject': [contractId: number]
  'refresh': []
}>()

interface PaymentContractInfo {
  contract_name: string
  contract_number: string
  total_amount: number
  customer_info?: { account_name: string }
  effective_date?: string
  signing_date?: string
}

// ==================== State ====================
const userStore = useUserStore()
const permissionStore = usePermissionStore()
const { userInfo } = storeToRefs(userStore)

const loading = ref(false)
const contractInfo = ref<ContractResponse | null>(null)
const errorMessage = ref('')
const activeRequestId = ref(0)
const editDialogOpen = ref<boolean>(false)

const statusesWithPaymentPlans: readonly ContractStatus[] = [
  'SIGNED',
  'EFFECTIVE',
  'EXPIRED'
]

const currentUserId = computed<string>(() => {
  const id = userInfo.value?.id
  return id === undefined || id === null ? '' : String(id)
})

const canEditContract = computed<boolean>(() => {
  const contract = contractInfo.value
  if (contract?.status !== 'DRAFT') return false
  if (permissionStore.canEditAll('contract')) return true
  return permissionStore.canEditOwn('contract') && contract.creator_id === currentUserId.value
})

const contractEntityType = 'CONTRACT' as const

const isSubmitterGeneric = computed<boolean>(() => {
  return contractInfo.value?.creator_id === currentUserId.value
})

const canApproveGeneric = computed<boolean>(() => {
  return contractInfo.value?.status === 'PENDING_REVIEW' &&
    (
      props.canApprove ||
      permissionStore.canApproveAll('contract') ||
      permissionStore.canApproveOwn('contract')
    )
})

const canShowPaymentPlans = computed<boolean>(() => {
  const status = contractInfo.value?.status
  return status !== undefined && statusesWithPaymentPlans.includes(status)
})

const paymentContractInfo = computed<PaymentContractInfo | undefined>(() => {
  const contract = contractInfo.value
  if (contract === null) return undefined

  const totalAmount = Number.parseFloat(contract.total_amount)

  const info: PaymentContractInfo = {
    contract_name: contract.contract_name,
    contract_number: contract.contract_number,
    total_amount: Number.isFinite(totalAmount) ? totalAmount : 0
  }

  if (contract.customer_info !== undefined) {
    info.customer_info = contract.customer_info
  }

  if (contract.effective_date !== null) {
    info.effective_date = contract.effective_date
  }

  if (contract.signing_date !== null) {
    info.signing_date = contract.signing_date
  }

  return info
})

// ==================== Data Loading ====================
const fetchContractDetail = async (contractId: number): Promise<void> => {
  const requestId = activeRequestId.value + 1
  activeRequestId.value = requestId

  loading.value = true
  errorMessage.value = ''
  contractInfo.value = null

  try {
    const data = await contractApi.getContract(contractId)
    if (requestId !== activeRequestId.value) return

    contractInfo.value = data
  } catch (error) {
    if (requestId !== activeRequestId.value) return

    contractInfo.value = null
    errorMessage.value = '合同信息加载失败，请稍后重试'
    handleApiError(error, '获取合同详情')
  } finally {
    if (requestId === activeRequestId.value) {
      loading.value = false
    }
  }
}

const resetState = (): void => {
  activeRequestId.value += 1
  loading.value = false
  contractInfo.value = null
  errorMessage.value = ''
}

// ==================== Event Seams ====================
const handleOpenChange = (open: boolean): void => {
  emit('update:visible', open)
}

const closeSheet = (): void => {
  emit('update:visible', false)
}

const handleRetry = (): void => {
  if (props.contractId !== null) {
    void fetchContractDetail(props.contractId)
  }
}

const refreshCurrentContract = async (): Promise<void> => {
  const contractId = contractInfo.value?.id
  if (contractId !== undefined) {
    await fetchContractDetail(contractId)
  }
}

const handleEditContract = (): void => {
  if (!canEditContract.value) return
  editDialogOpen.value = true
}

const handleEditSuccess = async (): Promise<void> => {
  editDialogOpen.value = false
  await refreshCurrentContract()
  emit('refresh')
}

const handlePaymentPlanUpdated = async (): Promise<void> => {
  await refreshCurrentContract()
  emit('refresh')
}

const handleApprovalActionDone = async (): Promise<void> => {
  await refreshCurrentContract()
  emit('refresh')
}

const handleApprovalApproved = async (): Promise<void> => {
  if (contractInfo.value === null) return
  emit('approve', contractInfo.value.id)
  await handleApprovalActionDone()
}

const handleApprovalRejected = async (): Promise<void> => {
  if (contractInfo.value === null) return
  emit('reject', contractInfo.value.id)
  await handleApprovalActionDone()
}

const handleApprovalResubmit = (): void => {
  if (!isSubmitterGeneric.value) return
  editDialogOpen.value = true
}

// ==================== Format Helpers ====================
const formatText = (value: string | number | null | undefined): string => {
  if (value === null || value === undefined || value === '') return '-'
  return String(value)
}

const formatUserCount = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '-'
  return `${value} 人`
}

const formatDate = (dateStr: string | null | undefined): string => {
  if (dateStr === null || dateStr === undefined || dateStr === '') return '-'
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return '-'

  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const formatDateTime = (dateStr: string | null | undefined): string => {
  if (dateStr === null || dateStr === undefined || dateStr === '') return '-'
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return '-'

  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}`
}

const getStatusText = (status: ContractStatus | undefined): string => {
  if (status === undefined) return '-'
  const map: Record<ContractStatus, string> = {
    DRAFT: '草稿',
    PENDING_REVIEW: '审批中',
    SIGNED: '已签署',
    EFFECTIVE: '生效中',
    EXPIRED: '已到期',
    TERMINATED: '已终止'
  }
  return map[status]
}

const getStatusClass = (status: ContractStatus | undefined): string => {
  if (status === undefined) return 'status-default'
  const map: Record<ContractStatus, string> = {
    DRAFT: 'status-default',
    PENDING_REVIEW: 'status-warning',
    SIGNED: 'status-info',
    EFFECTIVE: 'status-success',
    EXPIRED: 'status-danger',
    TERMINATED: 'status-muted'
  }
  return map[status]
}

const getLicenseTypeText = (type: LicenseType | undefined): string => {
  if (type === undefined) return '-'
  const map: Record<LicenseType, string> = {
    SUBSCRIPTION: '订阅制',
    PERPETUAL: '买断制'
  }
  return map[type]
}

// ==================== Watch ====================
watch(
  [(): boolean => props.visible, (): number | null => props.contractId],
  ([visible, contractId]): void => {
    if (!visible) {
      resetState()
    } else if (contractId !== null) {
      void fetchContractDetail(contractId)
    } else {
      resetState()
    }
  },
  { immediate: true }
)
</script>

<template>
  <Sheet :open="visible" @update:open="handleOpenChange">
    <DetailSheetContent>
      <!-- Header -->
      <SheetHeader class="p-6 pb-4 border-b border-wolf-border-default-v2">
        <div class="contract-header-summary">
          <div v-if="contractInfo" class="title-avatar" aria-hidden="true">
            {{ contractInfo.contract_name?.charAt(0) || '合' }}
          </div>

          <div class="header-title-block">
            <SheetTitle class="text-lg font-semibold truncate">
              {{ contractInfo?.contract_name || '合同详情' }}
            </SheetTitle>
            <SheetDescription class="flex items-center gap-2 mt-1 min-h-6">
              <Badge v-if="contractInfo" :class="['status-badge', getStatusClass(contractInfo.status)]">
                {{ getStatusText(contractInfo.status) }}
              </Badge>
              <span v-else class="text-sm text-wolf-text-tertiary-v2">
                {{ loading ? '正在加载合同信息' : '查看合同基础信息与审批进度' }}
              </span>
            </SheetDescription>
          </div>

          <div v-if="contractInfo" class="amount-summary">
            <div class="amount-label">合同总金额</div>
            <div class="amount-value">
              {{ formatCurrency(contractInfo.total_amount) }}
            </div>
          </div>
        </div>
      </SheetHeader>

      <!-- Content -->
      <ScrollArea class="flex-1">
        <div class="sheet-body">
          <template v-if="loading">
            <div class="loading-stack" aria-live="polite" aria-busy="true">
              <Skeleton class="h-32 w-full" />
              <Skeleton class="h-48 w-full" />
              <Skeleton class="h-32 w-full" />
            </div>
          </template>

          <template v-else-if="errorMessage">
            <Card class="state-card">
              <CardContent class="state-card-content">
                <Empty>
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <AlertCircle class="w-10 h-10" />
                    </EmptyMedia>
                  </EmptyHeader>
                  <EmptyTitle>{{ errorMessage }}</EmptyTitle>
                  <EmptyDescription>请检查网络连接后重试。</EmptyDescription>
                </Empty>
                <Button variant="outline" @click="handleRetry">
                  <RefreshCw class="w-4 h-4 mr-2" />
                  重新加载
                </Button>
              </CardContent>
            </Card>
          </template>

          <template v-else-if="contractInfo">
            <!-- 基本信息卡片 -->
            <Card class="info-card">
              <CardContent class="p-0">
                <div class="section-heading">
                  <h3 class="section-title">基本信息</h3>
                </div>
                <div class="section-content">
                  <div class="attributes-grid">
                    <div class="attribute-item">
                      <div class="attribute-label">合同编号</div>
                      <div class="attribute-value">{{ formatText(contractInfo.contract_number) }}</div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">客户名称</div>
                      <div class="attribute-value">{{ formatText(contractInfo.customer_info?.account_name) }}</div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">商机名称</div>
                      <div class="attribute-value">{{ formatText(contractInfo.opportunity_info?.opportunity_name) }}</div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">签约人</div>
                      <div class="attribute-value" :class="{ 'not-filled': !contractInfo.contact_info?.name }">
                        {{ formatText(contractInfo.contact_info?.name) }}
                      </div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">采购用户数</div>
                      <div class="attribute-value">{{ formatUserCount(contractInfo.user_count) }}</div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">授权类型</div>
                      <div class="attribute-value">{{ getLicenseTypeText(contractInfo.license_type) }}</div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">签署日期</div>
                      <div class="attribute-value" :class="{ 'not-filled': !contractInfo.signing_date }">
                        {{ formatDate(contractInfo.signing_date) }}
                      </div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">生效日期</div>
                      <div class="attribute-value" :class="{ 'not-filled': !contractInfo.effective_date }">
                        {{ formatDate(contractInfo.effective_date) }}
                      </div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">到期日期</div>
                      <div class="attribute-value" :class="{ 'not-filled': !contractInfo.expiry_date }">
                        {{ formatDate(contractInfo.expiry_date) }}
                      </div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">创建人</div>
                      <div class="attribute-value" :class="{ 'not-filled': !contractInfo.creator_info?.name }">
                        {{ formatText(contractInfo.creator_info?.name) }}
                      </div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">创建时间</div>
                      <div class="attribute-value">{{ formatDateTime(contractInfo.created_time) }}</div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <!-- 审批进度卡片：复用审批中心同款通用审批组件 -->
            <ApprovalProcessGeneric
              :entity-type="contractEntityType"
              :entity-id="contractInfo.id"
              :can-approve="canApproveGeneric"
              :is-submitter="isSubmitterGeneric"
              @submitted="handleApprovalActionDone"
              @approved="handleApprovalApproved"
              @rejected="handleApprovalRejected"
              @withdrawn="handleApprovalActionDone"
              @resubmit="handleApprovalResubmit"
            />

            <!-- 回款计划卡片 -->
            <ContractPaymentPlans
              v-if="canShowPaymentPlans && paymentContractInfo !== undefined"
              :contract-id="contractInfo.id"
              :contract-status="contractInfo.status"
              :contract-info="paymentContractInfo"
              @plan-updated="handlePaymentPlanUpdated"
            />
            <Card v-else class="state-card">
              <CardContent class="payment-placeholder-content">
                <Empty>
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <ReceiptText class="w-10 h-10" />
                    </EmptyMedia>
                  </EmptyHeader>
                  <EmptyTitle>回款计划暂不可用</EmptyTitle>
                  <EmptyDescription>合同签署后可创建和登记回款计划。</EmptyDescription>
                </Empty>
              </CardContent>
            </Card>
          </template>

          <template v-else>
            <Card class="state-card">
              <CardContent class="state-card-content">
                <Empty>
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <FileText class="w-10 h-10" />
                    </EmptyMedia>
                  </EmptyHeader>
                  <EmptyTitle>暂无合同信息</EmptyTitle>
                  <EmptyDescription>请选择一个合同查看详情。</EmptyDescription>
                </Empty>
              </CardContent>
            </Card>
          </template>
        </div>
      </ScrollArea>

      <!-- Footer -->
      <SheetFooter class="p-4 border-t border-wolf-border-default-v2 footer-actions">
        <Button
          v-if="canEditContract"
          variant="outline"
          @click="handleEditContract"
        >
          <Pencil class="w-4 h-4 mr-2" aria-hidden="true" />
          编辑合同
        </Button>
        <Button variant="outline" @click="closeSheet">
          <X class="w-4 h-4 mr-2" aria-hidden="true" />
          关闭
        </Button>
      </SheetFooter>
    </DetailSheetContent>
  </Sheet>

  <ContractFormDialog
    v-if="contractInfo"
    v-model:open="editDialogOpen"
    :customer-id="contractInfo.customer_id"
    :contract="contractInfo"
    @success="handleEditSuccess"
  />
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.contract-header-summary {
  display: flex;
  align-items: center;
  gap: $wolf-space-md-v2;
  min-width: 0;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    align-items: flex-start;
    flex-wrap: wrap;
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

.header-title-block {
  flex: 1;
  min-width: 0;
}

.amount-summary {
  text-align: right;
  flex-shrink: 0;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    width: 100%;
    text-align: left;
    padding-left: 64px;
  }
}

.amount-label {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
  margin-bottom: $wolf-space-xs-v2;
}

.amount-value {
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
  line-height: $wolf-line-height-title-v2;
}

.sheet-body {
  padding: $wolf-space-xl-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xl-v2;
  min-height: 600px;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    padding: $wolf-space-md-v2;
    gap: $wolf-space-lg-v2;
  }
}

.loading-stack {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
}

.info-card,
.state-card {
  background: $wolf-bg-card-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-lg-v2;
  box-shadow: $wolf-shadow-card-v2;
}

.section-heading {
  padding: $wolf-space-md-v2;
  border-bottom: 1px solid $wolf-border-light-v2;
}

.section-title {
  margin: 0;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
}

.section-content {
  padding: $wolf-space-md-v2;
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
  min-width: 0;
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
  line-height: $wolf-line-height-body-v2;
  word-break: break-word;

  &.not-filled {
    color: $wolf-text-placeholder-v2;
  }
}

.state-card-content,
.payment-placeholder-content {
  min-height: 280px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: $wolf-space-md-v2;
  padding: $wolf-space-xl-v2;
}

.footer-actions {
  display: flex;
  flex-direction: row;
  justify-content: flex-end;
  gap: $wolf-space-sm-v2;
  flex-wrap: wrap;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    :deep(button) {
      flex: 1 1 100%;
    }
  }
}

// 状态 Badge
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: $wolf-space-xs-v2 $wolf-space-sm-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  border-radius: $wolf-radius-full-v2;
  white-space: nowrap;
}

.status-default {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-tertiary-v2;
}

.status-info {
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
}

.status-warning {
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
}

.status-success {
  background: $wolf-success-bg-v2;
  color: $wolf-success-text-v2;
}

.status-danger {
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-text-v2;
}

.status-muted {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-placeholder-v2;
}

// Reduced Motion 支持
@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>
