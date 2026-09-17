<script setup lang="ts">
/**
 * OpportunityDetailContent.vue - 可复用商机详情内容组件
 *
 * 仅负责商机自己的基本信息、审批进度、商机进度与编辑 / 赢 / 输。
 * 合同 / 回款 / 发票 / License 在客户 → 业务旅程里操作。
 */
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { Pencil, Trophy, XCircle } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { handleApiError } from '@/utils/errorHandler'
import { formatLocalDate } from '@/utils/format'
import { formatOpportunityProductSummary } from '@/utils/opportunityProduct'
import { AmountText } from '@/components/crmwolf'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger
} from '@/components/ui/accordion'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator
} from '@/components/ui/breadcrumb'
import { ScrollArea } from '@/components/ui/scroll-area'
import OpportunityStageStepper from '@/components/OpportunityStageStepper.vue'
import OpportunityFormDialog from '@/components/dialogs/OpportunityFormDialog.vue'
import OpportunityWinDialog from '@/components/dialogs/OpportunityWinDialog.vue'
import OpportunityLoseDialog from '@/components/dialogs/OpportunityLoseDialog.vue'
import ApprovalProcessGeneric from '@/components/ApprovalProcessGeneric.vue'
import { opportunityApi, type Opportunity } from '@/api/opportunity'
import approvalGenericApi from '@/api/approvalGeneric'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'
import { customerDetailRoute } from '@/utils/customerRoutes'

interface CustomerContext {
  customerId: string
  customerName?: string | undefined
}

interface Props {
  opportunityId: string
  embedded?: boolean
  showBreadcrumb?: boolean
  customerContext?: CustomerContext | null
}

const props = withDefaults(defineProps<Props>(), {
  embedded: false,
  showBreadcrumb: true,
  customerContext: null
})

const emit = defineEmits<{
  'back': []
  'close': []
  'refresh': []
  'edit': [opportunityId: string]
  'view-journey': [{ customerId: string, journeyPublicId: string }]
}>()

const permissionStore = usePermissionStore()
const userStore = useUserStore()

const loading = ref(false)
const loadError = ref(false)
const contentRootRef = ref<HTMLElement | null>(null)
const opportunity = ref<Opportunity | null>(null)
const approvalAccordionValue = ref('approval')
const stageAccordionValue = ref('')
const isStageComplete = ref(false)
const stageWinProbability = ref(0)

const winDialogOpen = ref(false)
const loseDialogOpen = ref(false)

const editDialogOpen = ref(false)
const editMode = ref<'normal' | 'resubmit'>('normal')
const pendingResubmitAfterEdit = ref(false)
const approvalProcessReloadKey = ref(0)

const currentUserId = computed(() => String(userStore.userInfo?.id ?? ''))
const isOwner = computed(() =>
  opportunity.value !== null && opportunity.value.owner_id === currentUserId.value
)
const canEditOpportunity = computed(() => {
  if (opportunity.value === null) return false
  if (permissionStore.hasPermission('opportunity:edit:all')) return true
  return permissionStore.hasPermission('opportunity:edit:own') && isOwner.value
})
const canAdvanceOpportunityStage = computed(() =>
  canEditOpportunity.value && isActive.value && isApprovalApproved.value
)
const canWin = computed(() =>
  canEditOpportunity.value && permissionStore.hasPermission('opportunity:win')
)
const canLose = computed(() =>
  canEditOpportunity.value && permissionStore.hasPermission('opportunity:lose')
)

const isActive = computed(() => opportunity.value?.status === 0)
const approvalPhase = computed(() => opportunity.value?.approval_phase)
const isApprovalPending = computed(() => approvalPhase.value === 'pending_review')
const isApprovalApproved = computed(() => approvalPhase.value === 'approved')
const isApprovalRejected = computed(() => approvalPhase.value === 'rejected')
const isApprovalSubmitter = computed(() =>
  opportunity.value?.creator_id === String(userStore.userInfo?.id)
)
const canSubmitApproval = computed(() => {
  if (isApprovalSubmitter.value) return true
  if (permissionStore.hasPermission('opportunity:edit:all')) return true
  return permissionStore.hasPermission('opportunity:edit:own')
    && opportunity.value?.owner_id === currentUserId.value
})
const canShowFooterEdit = computed(() =>
  canEditOpportunity.value && !isApprovalPending.value && !isApprovalRejected.value
)
const canViewDealJourney = computed(() => {
  const journeyId = opportunity.value?.deal_journey_id
  return typeof journeyId === 'string' && journeyId.length > 0
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

const stageProgressText = computed(() => `${Math.round(stageWinProbability.value)}%`)

function syncStageStateFromOpportunity(opportunityData: Opportunity): void {
  const winProbability = opportunityData.win_probability ?? 0
  const isComplete = winProbability >= 100
  stageWinProbability.value = winProbability
  isStageComplete.value = isComplete
  stageAccordionValue.value = isComplete ? '' : 'stage'
}

async function fetchOpportunityDetail(): Promise<boolean> {
  loading.value = true
  loadError.value = false
  try {
    const data = await opportunityApi.getOpportunity(props.opportunityId)
    opportunity.value = data
    syncStageStateFromOpportunity(data)
    return true
  } catch (error) {
    loadError.value = true
    opportunity.value = null
    handleApiError(error, '获取商机详情')
    return false
  } finally {
    loading.value = false
  }
}

function handleEdit(): void {
  if (!opportunity.value) return
  if (isApprovalPending.value) {
    toast.warning('商机审批中，暂不能编辑')
    return
  }
  if (!canEditOpportunity.value) {
    toast.error('你没有编辑该商机的权限')
    return
  }
  editMode.value = 'normal'
  pendingResubmitAfterEdit.value = false
  editDialogOpen.value = true
}

function handleResubmitEdit(): void {
  if (!opportunity.value) return
  if (!isApprovalRejected.value) {
    toast.warning('当前商机不需要重新提交审批')
    return
  }
  if (!canSubmitApproval.value) {
    toast.error('你没有重新提交该商机审批的权限')
    return
  }
  if (!canEditOpportunity.value) {
    toast.error('你没有编辑该商机的权限')
    return
  }
  editMode.value = 'resubmit'
  pendingResubmitAfterEdit.value = true
  editDialogOpen.value = true
}

function handleEditDialogOpenChange(open: boolean): void {
  editDialogOpen.value = open
  if (!open) editMode.value = 'normal'
}

async function handleEditSuccess(): Promise<void> {
  const shouldResubmit = pendingResubmitAfterEdit.value
  const savedOpportunityId = opportunity.value?.id
  editDialogOpen.value = false
  editMode.value = 'normal'
  pendingResubmitAfterEdit.value = false

  if (shouldResubmit && savedOpportunityId !== undefined) {
    try {
      await approvalGenericApi.submitApproval('OPPORTUNITY', savedOpportunityId)
      toast.success('商机已重新提交审批')
    } catch (error) {
      handleApiError(error, '重新提交商机审批')
    }
  }

  const refreshed = await fetchOpportunityDetail()
  approvalProcessReloadKey.value += 1
  if (!refreshed) {
    toast.warning('商机已保存，但详情刷新失败，请稍后重试。')
  }
  emit('refresh')
}

async function handleWinSuccess(): Promise<void> {
  winDialogOpen.value = false
  const refreshed = await fetchOpportunityDetail()
  if (!refreshed) {
    toast.warning('商机已标记为赢单，但详情刷新失败，请稍后重试。')
  }
  emit('refresh')
}

async function handleStageAdvanced(): Promise<void> {
  const refreshed = await fetchOpportunityDetail()
  if (!refreshed) {
    toast.warning('商机阶段已推进，但详情刷新失败，请稍后重试。')
  }
  emit('refresh')
}

async function handleLoseSuccess(): Promise<void> {
  loseDialogOpen.value = false
  const refreshed = await fetchOpportunityDetail()
  if (!refreshed) {
    toast.warning('商机已标记为输单，但详情刷新失败，请稍后重试。')
  }
  emit('refresh')
}

function handleViewJourney(): void {
  const current = opportunity.value
  const journeyPublicId = current?.deal_journey_id
  if (current === null || typeof journeyPublicId !== 'string' || journeyPublicId.length === 0) return
  emit('view-journey', {
    customerId: current.customer_id,
    journeyPublicId,
  })
}

function normalizeAccordionValue(value: string | string[] | undefined): string {
  return typeof value === 'string' ? value : ''
}

function handleApprovalAccordionUpdate(value: string | string[] | undefined): void {
  approvalAccordionValue.value = normalizeAccordionValue(value)
}

function handleStageAccordionUpdate(value: string | string[] | undefined): void {
  stageAccordionValue.value = normalizeAccordionValue(value)
}

function handleStageStatusChange(status: { currentWinProbability: number; isComplete: boolean }): void {
  const wasComplete = isStageComplete.value
  stageWinProbability.value = status.currentWinProbability
  isStageComplete.value = status.isComplete
  if (!status.isComplete) {
    stageAccordionValue.value = 'stage'
    return
  }
  if (!wasComplete) {
    stageAccordionValue.value = ''
  }
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

defineExpose({
  refresh: fetchOpportunityDetail
})

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
  const map: Record<string, string> = { NEW: 'status-warning', RENEWAL: 'status-success', EXPANSION: 'status-info' }
  return map[type] ?? ''
}

function getLicenseTypeText(type: string | undefined): string {
  if (type === undefined || type.trim() === '') return '-'
  return type === 'SUBSCRIPTION' ? '订阅制' : '买断制'
}

watch(() => props.opportunityId, () => {
  opportunity.value = null
  stageWinProbability.value = 0
  isStageComplete.value = false
  fetchOpportunityDetail()
  focusBackButton()
}, { immediate: true })

watch(approvalPhase, phase => {
  approvalAccordionValue.value = phase === 'approved' ? '' : 'approval'
  if (phase !== 'approved') {
    stageAccordionValue.value = ''
    isStageComplete.value = false
    return
  }
  if (opportunity.value) {
    syncStageStateFromOpportunity(opportunity.value)
  }
})
</script>

<template>
  <div
    ref="contentRootRef"
    class="opportunity-detail-content"
    data-testid="opportunity-detail-content"
    :data-opportunity-id="opportunityId"
  >
    <div class="opportunity-detail-header p-6 pb-4 border-b border-wolf-border-default-v2">
      <Breadcrumb v-if="embedded && showBreadcrumb" class="detail-breadcrumb">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink as-child>
              <button
                type="button"
                class="detail-breadcrumb-link"
                aria-label="返回客户详情"
                data-testid="opportunity-detail-back"
                @click="emit('back')"
              >
                客户详情
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>商机详情</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

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
        <div v-if="opportunity" class="flex items-center gap-3">
          <Button
            v-if="canViewDealJourney"
            type="button"
            variant="outline"
            size="sm"
            data-testid="view-deal-journey"
            @click="handleViewJourney"
          >
            查看业务旅程
          </Button>
          <div class="text-right">
            <div class="text-xs text-wolf-text-tertiary-v2">预计金额</div>
            <AmountText :value="opportunity.total_amount" size="lg" tone="primary" />
          </div>
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
                      :to="customerDetailRoute(opportunity.customer_id)"
                      class="attribute-value link-text"
                      @click="emit('close')"
                    >
                      {{ opportunity.customer_info?.account_name || '-' }}
                    </RouterLink>
                    <span v-else class="attribute-value">{{ displayCustomerName }}</span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">产品</div>
                    <span class="attribute-value" :class="{ 'not-filled': formatOpportunityProductSummary(opportunity) === '-' }">
                      {{ formatOpportunityProductSummary(opportunity) }}
                    </span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">产品模块</div>
                    <span class="attribute-value" :class="{ 'not-filled': !opportunity.product_modules?.length }">
                      {{ opportunity.product_modules?.length ? opportunity.product_modules.map(module => module.name).join('、') : '-' }}
                    </span>
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

          <Accordion
            :model-value="approvalAccordionValue"
            type="single"
            collapsible
            class="approval-accordion"
            @update:model-value="handleApprovalAccordionUpdate"
          >
            <AccordionItem value="approval">
              <AccordionTrigger class="px-4 py-3 hover:no-underline">
                <div class="flex items-center gap-2 w-full">
                  <span class="text-sm font-semibold text-wolf-text-primary-v2">审批进度</span>
                  <Badge :class="['status-badge', getApprovalPhaseClass(opportunity.approval_phase)]">
                    {{ getApprovalPhaseText(opportunity.approval_phase) }}
                  </Badge>
                </div>
              </AccordionTrigger>
              <AccordionContent class="px-4 pb-4">
                <ApprovalProcessGeneric
                  :key="`${opportunity.id}-${approvalProcessReloadKey}`"
                  entity-type="OPPORTUNITY"
                  :entity-id="opportunity.id"
                  :is-submitter="canSubmitApproval"
                  @submitted="fetchOpportunityDetail"
                  @approved="fetchOpportunityDetail"
                  @rejected="fetchOpportunityDetail"
                  @withdrawn="fetchOpportunityDetail"
                  @resubmit="handleResubmitEdit"
                />
              </AccordionContent>
            </AccordionItem>
          </Accordion>

          <Accordion
            v-if="isApprovalApproved"
            :model-value="stageAccordionValue"
            type="single"
            collapsible
            class="stage-accordion"
            @update:model-value="handleStageAccordionUpdate"
          >
            <AccordionItem value="stage">
              <AccordionTrigger class="px-4 py-3 hover:no-underline">
                <div class="flex items-center gap-2 w-full">
                  <span class="text-sm font-semibold text-wolf-text-primary-v2">商机进度</span>
                  <Badge :class="['status-badge', isStageComplete ? 'status-success' : 'status-info']">
                    {{ stageProgressText }}
                  </Badge>
                </div>
              </AccordionTrigger>
              <AccordionContent class="px-4 pb-4">
                <OpportunityStageStepper
                  :opportunity-id="opportunity.id"
                  embedded
                  :can-advance="canAdvanceOpportunityStage"
                  @advanced="handleStageAdvanced"
                  @stage-status-change="handleStageStatusChange"
                />
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </template>
      </div>
    </ScrollArea>

    <div class="opportunity-detail-footer p-4 border-t border-wolf-border-default-v2 flex flex-row justify-end gap-2">
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
        v-if="canShowFooterEdit"
        variant="outline"
        @click="handleEdit"
      >
        <Pencil class="w-4 h-4 mr-2" />
        编辑
      </Button>
    </div>

    <OpportunityWinDialog
      :opportunity-id="opportunity?.id ?? null"
      :open="winDialogOpen"
      @update:open="winDialogOpen = $event"
      @success="handleWinSuccess"
    />

    <OpportunityLoseDialog
      :opportunity-id="opportunity?.id ?? null"
      :open="loseDialogOpen"
      @update:open="loseDialogOpen = $event"
      @success="handleLoseSuccess"
    />

    <OpportunityFormDialog
      v-if="opportunity"
      :open="editDialogOpen"
      :opportunity="opportunity"
      :dialog-title="editMode === 'resubmit' ? '修改并重新提交商机' : undefined"
      :submit-text="editMode === 'resubmit' ? '重新提交审批' : undefined"
      :submitting-text="editMode === 'resubmit' ? '提交中...' : undefined"
      :success-message="editMode === 'resubmit' ? null : undefined"
      customer-locked
      @update:open="handleEditDialogOpenChange"
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

.detail-breadcrumb {
  margin-bottom: $wolf-space-md-v2;
}

.detail-breadcrumb-link {
  border: 0;
  background: transparent;
  padding: 0;
  color: $wolf-text-link-v2;
  cursor: pointer;
  font: inherit;

  &:hover {
    color: $wolf-text-link-hover-v2;
  }

  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
    border-radius: $wolf-radius-control-v2;
  }
}

.approval-accordion,
.stage-accordion {
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-surface-v2;
  background: $wolf-bg-card-v2;
  overflow: hidden;
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
