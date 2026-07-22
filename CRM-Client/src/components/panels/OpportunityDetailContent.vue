<script setup lang="ts">
/**
 * OpportunityDetailContent.vue - 可复用商机详情内容组件
 *
 * 仅负责商机详情内容、数据加载与业务动作意图，不包含 Sheet 外壳。
 * 可被 OpportunityDetailSheet 和 CustomerDetailSheet 内部下钻复用。
 */
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { Pencil, Trophy, XCircle, ExternalLink, ArrowLeft, FileText } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { handleApiError } from '@/utils/errorHandler'
import { formatLocalDate } from '@/utils/format'
import { AmountText } from '@/components/crmwolf'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle
} from '@/components/ui/empty'
import OpportunityStageStepper from '@/components/OpportunityStageStepper.vue'
import OpportunityFormDialog from '@/components/dialogs/OpportunityFormDialog.vue'
import OpportunityWinDialog from '@/components/dialogs/OpportunityWinDialog.vue'
import OpportunityLoseDialog from '@/components/dialogs/OpportunityLoseDialog.vue'
import ApprovalProcessGeneric from '@/components/ApprovalProcessGeneric.vue'
import { opportunityApi, type Opportunity } from '@/api/opportunity'
import contractApi, { type ContractListResponse, type ContractStatus } from '@/api/contract'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'

interface CustomerContext {
  customerId: number
  customerName?: string | undefined
}

interface Props {
  opportunityId: number
  embedded?: boolean
  customerContext?: CustomerContext | null
}

const props = withDefaults(defineProps<Props>(), {
  embedded: false,
  customerContext: null
})

const emit = defineEmits<{
  'back': []
  'close': []
  'refresh': []
  'open-full-page': [opportunityId: number]
  'edit': [opportunityId: number]
  'create-contract': [{
    opportunityId: number
    customerId: number
    customerName: string
    opportunityName: string
    totalAmount: number
    userCount: number
    licenseType: string
    subscriptionYears: number | null
  }]
}>()

const permissionStore = usePermissionStore()
const userStore = useUserStore()

const loading = ref(false)
const loadError = ref(false)
const contentRootRef = ref<HTMLElement | null>(null)
const opportunity = ref<Opportunity | null>(null)
const relatedContract = ref<ContractListResponse | null>(null)
const contractLoading = ref(false)

const winDialogOpen = ref(false)
const loseDialogOpen = ref(false)

// 编辑弹窗状态
const editDialogOpen = ref(false)

const canEdit = computed(() =>
  permissionStore.hasAnyPermission(['opportunity:edit:own', 'opportunity:edit:all'])
)
const canWin = computed(() => permissionStore.hasPermission('opportunity:win'))
const canLose = computed(() => permissionStore.hasPermission('opportunity:lose'))

const isActive = computed(() => opportunity.value?.status === 0)
const approvalPhase = computed(() => opportunity.value?.approval_phase)
const isApprovalPending = computed(() => approvalPhase.value === 'pending_review')
const isApprovalApproved = computed(() => approvalPhase.value === 'approved')
const isApprovalSubmitter = computed(() =>
  opportunity.value?.creator_id === String(userStore.userInfo?.id)
)
const canSubmitApproval = computed(() => {
  const currentUserId = String(userStore.userInfo?.id ?? '')
  if (isApprovalSubmitter.value) return true
  if (permissionStore.hasPermission('opportunity:edit:all')) return true
  return permissionStore.hasPermission('opportunity:edit:own')
    && opportunity.value?.owner_id === currentUserId
})

function firstNonEmpty(...values: (string | null | undefined)[]): string {
  const value = values.find(item => item !== undefined && item !== null && item.trim() !== '')
  return value ?? '-'
}

const displayCustomerName = computed(() =>
  firstNonEmpty(
    props.customerContext?.customerName,
    opportunity.value?.customer_info?.account_name,
    opportunity.value?.customer_name
  )
)

interface ResponseStatusError {
  response?: {
    status?: number
  }
}

function hasResponseStatus(error: unknown, status: number): boolean {
  if (typeof error !== 'object' || error === null) return false
  const candidate = error as ResponseStatusError
  return candidate.response?.status === status
}

async function fetchOpportunityDetail(): Promise<void> {
  loading.value = true
  loadError.value = false
  try {
    const data = await opportunityApi.getOpportunity(props.opportunityId)
    opportunity.value = data
    await fetchRelatedContract(data.id)
  } catch (error) {
    loadError.value = true
    opportunity.value = null
    handleApiError(error, '获取商机详情')
  } finally {
    loading.value = false
  }
}

async function fetchRelatedContract(opportunityId: number): Promise<void> {
  contractLoading.value = true
  try {
    relatedContract.value = await contractApi.getContractByOpportunity(opportunityId)
  } catch (error: unknown) {
    if (!hasResponseStatus(error, 404)) {
      handleApiError(error, '获取关联合同')
    }
    relatedContract.value = null
  } finally {
    contractLoading.value = false
  }
}

// 编辑功能
function handleEdit(): void {
  if (!opportunity.value) return
  if (isApprovalPending.value) {
    toast.warning('商机审批中，暂不能编辑')
    return
  }
  editDialogOpen.value = true
}

// 编辑成功回调
function handleEditSuccess(): void {
  editDialogOpen.value = false
  fetchOpportunityDetail()
  emit('refresh')
}

// 赢单成功回调
function handleWinSuccess(): void {
  winDialogOpen.value = false
  fetchOpportunityDetail()
  emit('refresh')
}

function handleStageAdvanced(): void {
  fetchOpportunityDetail()
  emit('refresh')
}

// 输单成功回调
function handleLoseSuccess(): void {
  loseDialogOpen.value = false
  fetchOpportunityDetail()
  emit('refresh')
}

function handleCreateContract(): void {
  if (!opportunity.value) return
  if (!isApprovalApproved.value) {
    toast.warning('商机审批通过后才能创建合同')
    return
  }
  emit('create-contract', {
    opportunityId: opportunity.value.id,
    customerId: opportunity.value.customer_id,
    customerName: opportunity.value.customer_info?.account_name ?? opportunity.value.customer_name ?? '',
    opportunityName: opportunity.value.opportunity_name,
    totalAmount: opportunity.value.total_amount,
    userCount: opportunity.value.user_count,
    licenseType: opportunity.value.license_type,
    subscriptionYears: opportunity.value.subscription_years
  })
}

function handleViewContract(): void {
  toast.info('请在合同列表查看合同详情')
}

// TODO: 打开完整详情功能待优化，暂时用 toast 提示
function handleOpenFullPage(): void {
  toast.info('完整详情功能优化中')
  // emit('open-full-page', props.opportunityId)
}

async function focusBackButton(): Promise<void> {
  if (!props.embedded) return
  await nextTick()
  const button = contentRootRef.value?.querySelector<HTMLElement>('[data-testid="opportunity-detail-back"]')
  button?.focus()
}

function retryFetchOpportunityDetail(): void {
  fetchOpportunityDetail()
}

function formatDate(dateStr: string | undefined | null): string {
  if (dateStr === undefined || dateStr === null || dateStr.trim() === '') return '-'
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return '-'
  return formatLocalDate(date)
}

function formatDateTime(dateStr: string | undefined | null): string {
  if (dateStr === undefined || dateStr === null || dateStr.trim() === '') return '-'
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return '-'
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}`
}

function getStatusText(status: number | undefined): string {
  if (status === undefined) return '-'
  const map: Record<number, string> = { 0: '跟进中', 1: '已赢单', 2: '已输单' }
  return map[status] ?? '未知'
}

function getStatusClass(status: number | undefined): string {
  if (status === undefined) return ''
  const map: Record<number, string> = {
    0: 'status-warning',
    1: 'status-success',
    2: 'status-danger'
  }
  return map[status] ?? ''
}

function getApprovalPhaseText(phase: string | undefined): string {
  const map: Record<string, string> = {
    draft: '待提交',
    pending_review: '审批中',
    approved: '审批通过',
    rejected: '审批拒绝'
  }
  return phase === undefined ? '-' : (map[phase] ?? phase)
}

function getApprovalPhaseClass(phase: string | undefined): string {
  const map: Record<string, string> = {
    draft: 'status-default',
    pending_review: 'status-warning',
    approved: 'status-success',
    rejected: 'status-danger'
  }
  return phase === undefined ? '' : (map[phase] ?? '')
}

function getPurchaseTypeText(type: string | undefined): string {
  if (type === undefined || type.trim() === '') return '-'
  const map: Record<string, string> = { NEW: '新购', RENEWAL: '续购', EXPANSION: '增购' }
  return map[type] ?? type
}

function getPurchaseTypeClass(type: string | undefined): string {
  if (type === undefined || type.trim() === '') return ''
  const map: Record<string, string> = { NEW: 'status-info', RENEWAL: 'status-success', EXPANSION: 'status-warning' }
  return map[type] ?? ''
}

function getLicenseTypeText(type: string | undefined): string {
  if (type === undefined || type.trim() === '') return '-'
  return type === 'SUBSCRIPTION' ? '订阅制' : '买断制'
}

function getContractStatusText(status: ContractStatus | undefined): string {
  if (status === undefined) return '-'
  const map: Record<string, string> = {
    DRAFT: '草稿',
    PENDING_REVIEW: '待审核',
    SIGNED: '已签署',
    EFFECTIVE: '生效中',
    EXPIRED: '已过期',
    TERMINATED: '已终止'
  }
  return map[status] ?? status
}

function getContractStatusClass(status: ContractStatus | undefined): string {
  if (status === undefined) return ''
  const map: Record<string, string> = {
    DRAFT: 'status-default',
    PENDING_REVIEW: 'status-warning',
    SIGNED: 'status-info',
    EFFECTIVE: 'status-success',
    EXPIRED: 'status-danger',
    TERMINATED: 'status-danger'
  }
  return map[status] ?? ''
}

watch(() => props.opportunityId, () => {
  opportunity.value = null
  relatedContract.value = null
  fetchOpportunityDetail()
  focusBackButton()
}, { immediate: true })
</script>

<template>
  <div
    ref="contentRootRef"
    class="opportunity-detail-content"
    data-testid="opportunity-detail-content"
    :data-opportunity-id="opportunityId"
  >
    <div class="opportunity-detail-header p-6 pb-4 border-b border-wolf-border-default-v2">
      <Button
        v-if="embedded"
        type="button"
        variant="ghost"
        size="sm"
        class="mb-4"
        aria-label="返回商机列表"
        data-testid="opportunity-detail-back"
        @click="emit('back')"
      >
        <ArrowLeft class="w-4 h-4 mr-2" />
        返回商机列表
      </Button>

      <div class="flex items-center gap-4">
        <div v-if="opportunity" class="title-avatar">
          {{ opportunity.opportunity_name?.charAt(0) || '商' }}
        </div>
        <div class="flex-1 min-w-0">
          <h2 class="text-lg font-semibold truncate text-wolf-text-primary-v2">
            {{ opportunity?.opportunity_name || '商机详情' }}
          </h2>
          <div class="flex flex-wrap items-center gap-2 mt-1">
            <Badge v-if="opportunity" :class="['status-badge', getStatusClass(opportunity.status)]">
              {{ getStatusText(opportunity.status) }}
            </Badge>
            <Badge v-if="opportunity" :class="['status-badge', getApprovalPhaseClass(opportunity.approval_phase)]">
              {{ getApprovalPhaseText(opportunity.approval_phase) }}
            </Badge>
            <Badge v-if="opportunity" :class="['status-badge', getPurchaseTypeClass(opportunity.purchase_type)]">
              {{ getPurchaseTypeText(opportunity.purchase_type) }}
            </Badge>
            <span v-if="embedded" class="text-sm text-wolf-text-tertiary-v2">
              客户：{{ displayCustomerName }}
            </span>
          </div>
        </div>
        <div v-if="opportunity" class="text-right">
          <div class="text-xs text-wolf-text-tertiary-v2">预计金额</div>
          <AmountText :value="opportunity.total_amount" size="lg" tone="primary" />
        </div>
      </div>
    </div>

    <ScrollArea class="flex-1">
      <div class="p-6 space-y-6">
        <div
          v-if="loading"
          role="status"
          aria-live="polite"
          class="py-8 text-center text-wolf-text-tertiary-v2"
        >
          加载中...
        </div>

        <div
          v-else-if="loadError"
          role="alert"
          class="py-8 text-center"
        >
          <p class="text-sm text-wolf-danger-text-v2 mb-4">商机详情加载失败，请稍后重试</p>
          <Button
            type="button"
            variant="outline"
            data-testid="retry-opportunity-detail"
            @click="retryFetchOpportunityDetail"
          >
            重试
          </Button>
        </div>

        <template v-else-if="opportunity">
          <Card class="info-card">
            <CardContent class="p-0">
              <div class="p-4 border-b border-wolf-border-light-v2">
                <h3 class="text-sm font-semibold text-wolf-text-primary-v2">基本信息</h3>
              </div>
              <div class="p-4">
                <div class="attributes-grid">
                  <div class="attribute-item">
                    <div class="attribute-label">客户名称</div>
                    <RouterLink
                      v-if="opportunity.customer_info && !embedded"
                      :to="`/customers/${opportunity.customer_id}`"
                      class="attribute-value link-text"
                      @click="emit('close')"
                    >
                      {{ opportunity.customer_info?.account_name || '-' }}
                    </RouterLink>
                    <span v-else class="attribute-value">{{ displayCustomerName }}</span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">审批状态</div>
                    <span class="attribute-value">
                      <Badge :class="['status-badge', getApprovalPhaseClass(opportunity.approval_phase)]">
                        {{ getApprovalPhaseText(opportunity.approval_phase) }}
                      </Badge>
                    </span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">负责人</div>
                    <span class="attribute-value" :class="{ 'not-filled': !opportunity.owner_info?.name }">
                      {{ opportunity.owner_info?.name || '待分配' }}
                    </span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">采购用户数</div>
                    <span class="attribute-value">{{ opportunity.user_count || '-' }} 人</span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">标准单价</div>
                    <span class="attribute-value">
                      <AmountText :value="opportunity.unit_price" tone="primary" />
                    </span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">采购方式</div>
                    <span class="attribute-value">
                      <Badge
                        v-if="opportunity.current_stage_snapshot?.procurement_method?.name"
                        class="status-badge status-info"
                      >
                        {{ opportunity.current_stage_snapshot.procurement_method.name }}
                      </Badge>
                      <span v-else>-</span>
                    </span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">预计成交日期</div>
                    <span class="attribute-value">{{ formatDate(opportunity.expected_closing_date) }}</span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">授权模式</div>
                    <span class="attribute-value">{{ getLicenseTypeText(opportunity.license_type) }}</span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">订阅年限</div>
                    <span class="attribute-value" :class="{ 'not-filled': !opportunity.subscription_years }">
                      {{ opportunity.subscription_years ? `${opportunity.subscription_years} 年` : '-' }}
                    </span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">实际成交日期</div>
                    <span class="attribute-value" :class="{ 'not-filled': !opportunity.actual_closing_date }">
                      {{ formatDate(opportunity.actual_closing_date) }}
                    </span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">创建时间</div>
                    <span class="attribute-value">{{ formatDateTime(opportunity.created_time) }}</span>
                  </div>

                  <div v-if="opportunity.status === 2" class="attribute-item">
                    <div class="attribute-label">输单原因</div>
                    <span class="attribute-value" :class="{ 'not-filled': !opportunity.loss_reason }">
                      {{ opportunity.loss_reason || '-' }}
                    </span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <OpportunityStageStepper
            v-if="isApprovalApproved"
            :opportunity-id="opportunity.id"
            @advanced="handleStageAdvanced"
          />

          <Card class="approval-card">
            <CardHeader class="p-4 border-b border-wolf-border-light-v2">
              <h3 class="text-sm font-semibold text-wolf-text-primary-v2">审批流程</h3>
            </CardHeader>
            <CardContent class="p-4">
              <ApprovalProcessGeneric
                entity-type="OPPORTUNITY"
                :entity-id="opportunity.id"
                :is-submitter="canSubmitApproval"
                @submitted="fetchOpportunityDetail"
                @approved="fetchOpportunityDetail"
                @rejected="fetchOpportunityDetail"
                @withdrawn="fetchOpportunityDetail"
                @resubmit="handleEdit"
              />
            </CardContent>
          </Card>

          <Card class="contract-card">
            <CardHeader class="p-4 border-b border-wolf-border-light-v2">
              <h3 class="text-sm font-semibold text-wolf-text-primary-v2">关联合同</h3>
            </CardHeader>
            <CardContent class="p-4">
              <div v-if="contractLoading" class="py-8 text-center text-wolf-text-tertiary-v2">
                加载中...
              </div>

              <Empty v-else-if="!relatedContract" class="min-h-[180px] border-0 py-6">
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <FileText class="h-5 w-5" aria-hidden="true" />
                  </EmptyMedia>
                  <EmptyTitle class="text-sm font-medium">暂无关联合同</EmptyTitle>
                  <EmptyDescription v-if="opportunity.status === 1">
                    商机已赢单，请及时创建合同以锁定交易
                  </EmptyDescription>
                </EmptyHeader>
                <EmptyContent v-if="opportunity.status === 1 && isApprovalApproved">
                  <Button size="sm" @click="handleCreateContract">创建合同</Button>
                </EmptyContent>
              </Empty>

              <div v-else class="contract-content">
                <div class="contract-header">
                  <div class="flex items-center gap-3">
                    <div class="contract-avatar">
                      {{ relatedContract.contract_name?.charAt(0) || '合' }}
                    </div>
                    <div>
                      <div class="font-medium text-wolf-text-primary-v2">{{ relatedContract.contract_name }}</div>
                      <div class="flex items-center gap-2 mt-1">
                        <Badge :class="['status-badge', getContractStatusClass(relatedContract.status)]">
                          {{ getContractStatusText(relatedContract.status) }}
                        </Badge>
                        <span class="text-xs text-wolf-text-tertiary-v2">{{ relatedContract.contract_number }}</span>
                      </div>
                    </div>
                  </div>
                  <Button variant="ghost" size="sm" @click="handleViewContract">
                    <ExternalLink class="w-4 h-4 mr-1" />
                    查看详情
                  </Button>
                </div>

                <Separator class="my-4" />

                <div class="attributes-grid grid-cols-4">
                  <div class="attribute-item">
                    <div class="attribute-label">采购用户数</div>
                    <span class="attribute-value">{{ relatedContract.user_count || '-' }} 人</span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-label">合同金额</div>
                    <span class="attribute-value">
                      <AmountText :value="relatedContract.total_amount" />
                    </span>
                  </div>
                  <div v-if="relatedContract.license_type === 'SUBSCRIPTION'" class="attribute-item">
                    <div class="attribute-label">订阅年限</div>
                    <span class="attribute-value" :class="{ 'not-filled': !relatedContract.subscription_years }">
                      {{ relatedContract.subscription_years ? `${relatedContract.subscription_years} 年` : '-' }}
                    </span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-label">到期日期</div>
                    <span class="attribute-value" :class="{ 'not-filled': !relatedContract.expiry_date }">
                      {{ relatedContract.expiry_date || '-' }}
                    </span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </template>
      </div>
    </ScrollArea>

    <div class="opportunity-detail-footer p-4 border-t border-wolf-border-default-v2 flex flex-row gap-2">
      <Button
        v-if="embedded"
        variant="outline"
        @click="handleOpenFullPage"
      >
        <ExternalLink class="w-4 h-4 mr-2" />
        打开完整商机详情
      </Button>
      <Button
        v-if="isActive && canWin && isApprovalApproved"
        variant="default"
        class="bg-wolf-success-v2 hover:bg-wolf-success-v2/90"
        @click="winDialogOpen = true"
      >
        <Trophy class="w-4 h-4 mr-2" />
        赢单
      </Button>
      <Button
        v-if="isActive && canLose && isApprovalApproved"
        variant="outline"
        class="text-wolf-danger-v2 border-wolf-danger-v2 hover:bg-wolf-danger-bg-v2"
        @click="loseDialogOpen = true"
      >
        <XCircle class="w-4 h-4 mr-2" />
        输单
      </Button>
      <Button
        v-if="canEdit && !isApprovalPending"
        variant="outline"
        @click="handleEdit"
      >
        <Pencil class="w-4 h-4 mr-2" />
        编辑
      </Button>
    </div>

    <!-- 赢单弹窗 -->
    <OpportunityWinDialog
      :opportunity-id="opportunity?.id ?? null"
      :open="winDialogOpen"
      @update:open="winDialogOpen = $event"
      @success="handleWinSuccess"
    />

    <!-- 输单弹窗 -->
    <OpportunityLoseDialog
      :opportunity-id="opportunity?.id ?? null"
      :open="loseDialogOpen"
      @update:open="loseDialogOpen = $event"
      @success="handleLoseSuccess"
    />

    <!-- 编辑商机弹窗 -->
    <OpportunityFormDialog
      v-if="opportunity"
      :open="editDialogOpen"
      :opportunity="opportunity"
      customer-locked
      @update:open="editDialogOpen = $event"
      @success="handleEditSuccess"
    />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.opportunity-detail-content {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  background: $wolf-bg-card-v2;
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

.contract-avatar {
  width: 40px;
  height: 40px;
  border-radius: $wolf-radius-full-v2;
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
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
  word-break: break-all;

  &.not-filled {
    color: $wolf-text-placeholder-v2;
  }
}

.link-text {
  color: $wolf-text-link-v2;
  cursor: pointer;
  font-weight: $wolf-font-weight-medium-v2;

  &:hover {
    color: $wolf-text-link-hover-v2;
  }
}

.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
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

.contract-content {
  width: 100%;
}

.contract-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: $wolf-space-md-v2;
}

@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .opportunity-detail-header,
  .opportunity-detail-footer {
    padding-left: $wolf-card-padding-mobile-v2;
    padding-right: $wolf-card-padding-mobile-v2;
  }

  .opportunity-detail-footer {
    flex-wrap: wrap;
    padding-bottom: calc($wolf-card-padding-mobile-v2 + $wolf-safe-area-bottom-v2);
  }
}

@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>
