<script setup lang="ts">
/**
 * PaymentRecordDetailSheet - Payment Record Detail Drawer
 *
 * Task 5: Single-panel Sheet layout for read-only payment record display.
 * - Header: payment record number or stable identifier + approval status badge; amount summary
 * - Content: basic information card with payment stage, payment date, voucher attachment preview,
 *   remarks, registrant, and timestamps where available
 * - Conditional approval progress display using V2 design system
 * - Footer close button
 *
 * Design: shadcn-vue + base.css 设计令牌.
 * Accessibility: focus-visible states, aria labels, touch targets >= 44px, semantic status display.
 */
import { computed, ref, watch } from 'vue'
import {
  AlertCircle,
  Calendar,
  Eye,
  FileText,
  Pencil,
  RefreshCw,
  User,
  Wallet,
  X
} from 'lucide-vue-next'
import { DetailSheetDescription, DetailSheetFooter, DetailSheetHeader, DetailSheetTitle } from '@/components/ui/detail-sheet'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import ApprovalProcessGeneric from '@/components/ApprovalProcessGeneric.vue'
import ApprovalStatusBadge from '@/components/crmwolf/ApprovalStatusBadge.vue'
import StatusBadge from '@/components/crmwolf/StatusBadge.vue'
import ErrorState from '@/components/crmwolf/ErrorState.vue'
import { AmountText, DataViewStatePanel, FilePreviewDialog } from '@/components/crmwolf'
import { getFilePreviewKind } from '@/components/crmwolf/filePreview'
import type { FileAttachmentItem } from '@/types/fileAttachment'
import paymentApi, {
  type ApprovalInfo,
  type ApprovalInfoLite,
  type PaymentPlanStatusSummary,
  type PaymentRecordDetailResponse,
  type PaymentRecordInfo
} from '@/api/payment'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'
import { formatLocalDate } from '@/utils/format'
import { toFeedbackError, type FeedbackError } from '@/types/feedback'

/**
 * Local type extending PaymentRecordInfo for detail sheet display.
 * Includes record_number from PaymentRecordResponse/PaymentRecordWithDetails
 * which is not present in the base PaymentRecordInfo type.
 */
type PaymentRecordDetailInfo = PaymentRecordInfo & {
  record_number?: string
  creator_id?: string
  payment_plan_id?: number
  contract_name?: string
  stage_name?: string
  updated_time?: string | null
  payment_plan?: PaymentPlanStatusSummary
}

/**
 * Union type for approval prop supporting both full ApprovalInfo (from latest_approval)
 * and ApprovalInfoLite (from record.approval). The component renders full node details
 * only when the approval has nodes array populated.
 */
type ApprovalInfoInput = ApprovalInfo | ApprovalInfoLite

interface Props {
  recordId: number | null
  visible?: boolean
  embedded?: boolean
  record?: PaymentRecordDetailInfo | null
  stageName?: string
  approval?: ApprovalInfoInput | null
  /** 只读查看（如从审批详情下钻）：隐藏编辑、审批流程与关闭等操作，403/404 以内联错误呈现。 */
  readonly?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  visible: true,
  embedded: false,
  record: null,
  stageName: '',
  approval: null,
  readonly: false
})

const emit = defineEmits<{
  'update:visible': [value: boolean]
  close: []
  refresh: []
  edit: []
  resubmit: []
}>()

const permissionStore = usePermissionStore()
const userStore = useUserStore()

// Keep the parent-provided record visible while the authoritative detail request runs.
// This avoids adding a confirmation page or a manual refresh step to the normal path.
const detailRecord = ref<PaymentRecordDetailInfo | null>(props.record)
const detailApproval = ref<ApprovalInfoInput | null>(props.approval)
const loading = ref<boolean>(false)
const errorMessage = ref<string>('')
// Readonly-only terminal load failure (403/404): replaces the record entirely, never shows stale data.
const readonlyLoadError = ref<FeedbackError | null>(null)
let detailRequestSequence = 0

const hasRecord = computed<boolean>(() => detailRecord.value !== null)
const hasProofAttachment = computed<boolean>(() => {
  const attachment = detailRecord.value?.proof_attachment
  return typeof attachment === 'string' && attachment.trim().length > 0
})

const proofAttachmentUrl = computed<string>(() => {
  return detailRecord.value?.proof_attachment?.trim() ?? ''
})

/** The voucher is an external URL; its last path segment is the best available file name. */
const proofFile = computed<FileAttachmentItem | null>(() => {
  const url = proofAttachmentUrl.value
  if (url === '') return null
  const segment = url.split(/[?#]/)[0]?.split('/').pop() ?? ''
  let name = segment
  try {
    name = decodeURIComponent(segment)
  } catch {
    // Keep the raw segment when it is not valid percent-encoding.
  }
  return { id: 'proof', name: name !== '' ? name : '凭证附件', url }
})

const isImageAttachment = computed<boolean>(() =>
  proofFile.value !== null && getFilePreviewKind(proofFile.value) === 'image'
)

const proofPreviewOpen = ref<boolean>(false)

const recordEntityId = computed<number | null>(() => detailRecord.value?.id ?? props.recordId)

const currentUserId = computed<string>(() => {
  const id = userStore.userInfo?.id
  return id === undefined || id === null ? '' : String(id)
})

const canApproveGeneric = computed<boolean>(() => {
  return permissionStore.hasAnyPermission([
    'payment:approve',
    'payment:approve:own',
    'payment:approve:all'
  ])
})

const isSubmitterGeneric = computed<boolean>(() => {
  const approval = detailApproval.value
  if (approval !== null && 'submitter_id' in approval && approval.submitter_id !== undefined) {
    return approval.submitter_id === currentUserId.value
  }
  return detailRecord.value?.creator_id === currentUserId.value
})

const canEditRecord = computed<boolean>(() => {
  const record = detailRecord.value
  if (record === null) return false
  if (
    record.approval_phase !== 'draft' &&
    record.approval_phase !== 'rejected'
  ) {
    return false
  }
  const approvalStatus = detailApproval.value?.status ?? record.approval?.status
  if (approvalStatus === 'PENDING') return false
  if (record.confirmation_status === 'CONFIRMED') return false
  if (permissionStore.hasAnyPermission(['payment:record:edit', 'payment:edit'])) return true
  return record.creator_id === currentUserId.value
})

const approvalStatus = computed<string | undefined>(() => {
  const approval = detailApproval.value
  if (approval?.status !== undefined) return approval.status

  const phase = detailRecord.value?.approval_phase
  if (phase === 'pending_review') return 'PENDING'
  if (phase === 'approved') return 'APPROVED'
  if (phase === 'rejected') return 'REJECTED'
  return phase
})

// A record awaiting submission is not a generic approval instance.
const isDraftApprovalPhase = computed<boolean>(() =>
  detailApproval.value?.status === undefined && detailRecord.value?.approval_phase === 'draft'
)

const rejectionReason = computed<string>(() => {
  const approval = detailApproval.value
  if (approval !== null && 'reject_reason' in approval && approval.reject_reason?.trim()) {
    return approval.reject_reason.trim()
  }

  const rejectedNode = approval?.nodes.find((node) =>
    node.status === 'REJECT' || node.status === 'REJECTED'
  )
  return rejectedNode?.comment?.trim() ?? ''
})

// Helper functions
function formatDate(dateStr: string | undefined): string {
  if (dateStr === undefined || dateStr === null || dateStr.trim() === '') return '-'
  const date = new Date(dateStr)
  return Number.isNaN(date.getTime()) ? '-' : formatLocalDate(date)
}

function formatDateTime(dateStr: string | null | undefined): string {
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

function formatText(value: string | number | boolean | undefined | null): string {
  if (value === undefined || value === null || value === '') return '-'
  return String(value)
}

function formatCreator(record: PaymentRecordDetailInfo | null | undefined): string {
  if (record === null || record === undefined) return '-'
  const creatorName = record.creator_name?.trim()
  return creatorName === undefined || creatorName === '' ? '未知登记人' : creatorName
}


function closeSheet(): void {
  emit('update:visible', false)
  emit('close')
}

function openProofPreview(): void {
  if (proofFile.value !== null) proofPreviewOpen.value = true
}

function handleApprovalChanged(): void {
  emit('refresh')
}

function handleApprovalResubmit(): void {
  emit('resubmit')
}

function handleEditRecord(): void {
  emit('edit')
}

interface ApiErrorLike {
  response?: {
    status?: number
    data?: {
      detail?: unknown
    }
  }
}

function getDetailErrorMessage(error: unknown): string {
  const apiError = error as ApiErrorLike
  const detail = apiError.response?.data?.detail
  if (apiError.response?.status === 404) return '回款记录不存在或已被删除'
  if (typeof detail === 'string' && detail.trim() !== '') return detail
  return '回款记录最终状态暂时无法确认'
}

async function loadDetail(): Promise<void> {
  const recordId = props.recordId
  if (!props.visible || recordId === null) return

  const requestSequence = ++detailRequestSequence
  loading.value = detailRecord.value === null
  errorMessage.value = ''
  readonlyLoadError.value = null

  try {
    const detail: PaymentRecordDetailResponse = await paymentApi.getPaymentRecordDetail(recordId)
    if (
      requestSequence !== detailRequestSequence ||
      !props.visible ||
      props.recordId !== recordId
    ) return

    detailRecord.value = detail
    detailApproval.value = detail.approval ?? null
  } catch (error: unknown) {
    if (requestSequence !== detailRequestSequence) return
    const status = (error as ApiErrorLike).response?.status
    if (props.readonly && (status === 403 || status === 404)) {
      detailRecord.value = null
      detailApproval.value = null
      readonlyLoadError.value = toFeedbackError(error, '回款记录')
      return
    }
    errorMessage.value = getDetailErrorMessage(error)
  } finally {
    if (requestSequence === detailRequestSequence) {
      loading.value = false
    }
  }
}

// Load the server-authoritative state whenever the sheet opens for a record.
// A stale response cannot overwrite a newly selected record.
watch(
  [(): PaymentRecordDetailInfo | null => props.record, (): ApprovalInfoInput | null => props.approval],
  ([record, approval]): void => {
    // Refreshes from the parent may keep the same record ID while replacing its
    // status/approval snapshot. Reflect that update without adding another step.
    // A readonly 403/404 is terminal for this record: never fall back to the parent snapshot.
    if (readonlyLoadError.value !== null) return
    if (record !== null) detailRecord.value = record
    detailApproval.value = approval
  }
)

watch(
  () => [props.visible, props.recordId] as const,
  ([visible, recordId]) => {
    if (!visible || recordId === null) {
      detailRequestSequence += 1
      loading.value = false
      errorMessage.value = ''
      readonlyLoadError.value = null
      if (!visible) {
        detailRecord.value = props.record
        detailApproval.value = props.approval
      }
      return
    }

    detailRecord.value = props.record
    detailApproval.value = props.approval
    void loadDetail()
  },
  { immediate: true }
)
</script>

<template>

  <div class="detail-embedded-content">

      <DetailSheetHeader class="record-sheet-header">
        <div class="record-header-summary">
          <div v-if="hasRecord" class="title-avatar" aria-hidden="true">
            {{ (detailRecord?.record_number ?? '款').charAt(0) }}
          </div>

          <div class="header-title-block">
            <DetailSheetTitle class="record-sheet-title">
              {{ detailRecord?.record_number ?? '回款记录详情' }}
            </DetailSheetTitle>
            <DetailSheetDescription class="record-sheet-description">
              <StatusBadge
                v-if="hasRecord"
                type="paymentConfirmation"
                :status="detailRecord?.confirmation_status ?? 'PENDING'"
              />
              <Badge
                v-if="hasRecord && isDraftApprovalPhase"
                variant="status"
                data-tone="neutral"
                data-status-domain="paymentApprovalPhase"
                data-status-value="draft"
                role="status"
                aria-label="审批状态：待提交"
              >
                待提交
              </Badge>
              <ApprovalStatusBadge
                v-else-if="hasRecord && approvalStatus"
                :status="approvalStatus ?? ''"
                size="small"
              />
              <span v-if="detailRecord?.stage_name ?? props.stageName" class="stage-name">{{ detailRecord?.stage_name ?? props.stageName }}</span>
              <span v-else>{{ loading ? '正在加载回款记录' : '查看回款详情与审批进度' }}</span>
            </DetailSheetDescription>
          </div>

          <div v-if="hasRecord" class="amount-summary" aria-label="回款金额">
            <div class="amount-summary-item">
              <span class="amount-summary-label">回款金额</span>
              <AmountText :value="detailRecord?.actual_amount ?? 0" size="lg" />
            </div>
          </div>
        </div>
      </DetailSheetHeader>

      <ScrollArea class="record-sheet-scroll">
        <div class="sheet-body">
          <template v-if="loading">
            <div class="loading-stack" aria-live="polite" aria-busy="true">
              <Skeleton class="h-28 w-full" />
              <Skeleton class="h-48 w-full" />
            </div>
          </template>

          <div v-else-if="readonlyLoadError" class="readonly-error-state">
            <ErrorState
              :variant="readonlyLoadError.variant ?? 'error'"
              :title="readonlyLoadError.title"
              :description="readonlyLoadError.description"
            />
          </div>

          <template v-else-if="errorMessage && !hasRecord">
            <Card class="state-card">
              <CardContent class="state-card-content">
                <Empty>
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <AlertCircle aria-hidden="true" />
                    </EmptyMedia>
                    <EmptyTitle>{{ errorMessage }}</EmptyTitle>
                    <EmptyDescription>请检查网络连接后重试。</EmptyDescription>
                  </EmptyHeader>
                </Empty>
                <Button variant="outline" type="button" @click="loadDetail">
                  <RefreshCw data-icon="inline-start" aria-hidden="true" />
                  重新加载
                </Button>
              </CardContent>
            </Card>
          </template>

          <template v-else-if="hasRecord">
            <Card v-if="errorMessage" class="state-card" role="alert">
              <CardContent class="state-card-content state-card-content-inline">
                <div>
                  <EmptyTitle>{{ errorMessage }}</EmptyTitle>
                  <EmptyDescription>当前显示的是最近一次已知状态，可重新加载确认最终结果。</EmptyDescription>
                </div>
                <Button variant="outline" type="button" @click="loadDetail">
                  <RefreshCw data-icon="inline-start" aria-hidden="true" />
                  重新加载
                </Button>
              </CardContent>
            </Card>

            <Card class="info-card">
              <CardHeader class="section-heading">
                <CardTitle class="section-title">基本信息</CardTitle>
                <CardDescription>回款阶段、日期、凭证与登记人信息。</CardDescription>
              </CardHeader>
              <CardContent class="section-content">
                <div class="attributes-grid">
                  <div v-if="detailRecord?.stage_name ?? props.stageName" class="attribute-item">
                    <span class="attribute-label">
                      <Wallet aria-hidden="true" class="attribute-icon" />
                      回款阶段
                    </span>
                    <span class="attribute-value">{{ formatText(detailRecord?.stage_name ?? props.stageName) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <Calendar aria-hidden="true" class="attribute-icon" />
                      回款日期
                    </span>
                    <span class="attribute-value mono-value">{{ formatDate(detailRecord?.payment_date) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <User aria-hidden="true" class="attribute-icon" />
                      实际付款方
                    </span>
                    <span class="attribute-value">{{ formatText(detailRecord?.actual_payer_name) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <User aria-hidden="true" class="attribute-icon" />
                      登记人
                    </span>
                    <span class="attribute-value">{{ formatCreator(detailRecord) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">登记时间</span>
                    <span class="attribute-value mono-value">{{ formatDateTime(detailRecord?.created_time) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">最后更新时间</span>
                    <span class="attribute-value mono-value">{{ formatDateTime(detailRecord?.updated_time) }}</span>
                  </div>
                </div>

                <!-- Voucher/Proof Attachment -->
                <div v-if="hasProofAttachment" class="voucher-section">
                  <span class="attribute-label">
                    <FileText aria-hidden="true" class="attribute-icon" />
                    凭证附件
                  </span>

                  <!-- Inline thumbnail for image URLs with lazy loading -->
                  <div v-if="isImageAttachment" class="voucher-preview">
                    <button
                      type="button"
                      class="voucher-thumb"
                      aria-label="放大预览凭证附件"
                      @click="openProofPreview"
                    >
                      <img
                        :src="proofAttachmentUrl"
                        alt="凭证附件预览"
                        loading="lazy"
                        class="voucher-image"
                      />
                    </button>
                  </div>

                  <Button
                    variant="outline"
                    size="sm"
                    type="button"
                    class="voucher-link"
                    aria-label="预览凭证附件"
                    @click="openProofPreview"
                  >
                    <Eye aria-hidden="true" />
                    预览凭证
                  </Button>
                  <p v-if="!isImageAttachment" class="voucher-hint">支持在线预览图片、PDF 和 DOCX，其他格式可在新标签页打开</p>
                </div>
              </CardContent>
            </Card>

            <Card v-if="detailRecord?.composition" class="info-card">
              <CardHeader class="section-heading">
                <CardTitle class="section-title">构成</CardTitle>
                <CardDescription>续购和增购的人数与金额。</CardDescription>
              </CardHeader>
              <CardContent class="section-content">
                <div class="attributes-grid">
                  <div class="attribute-item">
                    <span class="attribute-label">续购人数</span>
                    <span class="attribute-value mono-value">{{ detailRecord.composition.renewal.headcount }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">续购金额</span>
                    <AmountText :value="detailRecord.composition.renewal.amount" />
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">增购人数</span>
                    <span class="attribute-value mono-value">{{ detailRecord.composition.expansion.headcount }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">增购金额</span>
                    <AmountText :value="detailRecord.composition.expansion.amount" />
                  </div>
                </div>
              </CardContent>
            </Card>

            <!-- Payment Plan Status Card: useful when confirming a timed-out submission. -->
            <Card v-if="detailRecord?.payment_plan" class="info-card">
              <CardHeader class="section-heading">
                <CardTitle class="section-title">所属回款计划</CardTitle>
                <CardDescription>计划金额与当前累计回款状态。</CardDescription>
              </CardHeader>
              <CardContent class="section-content">
                <div class="attributes-grid">
                  <div class="attribute-item">
                    <span class="attribute-label">计划编号</span>
                    <span class="attribute-value mono-value">{{ formatText(detailRecord.payment_plan.plan_number) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">计划金额</span>
                    <AmountText :value="detailRecord.payment_plan.planned_amount" />
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">已回款</span>
                    <AmountText :value="detailRecord.payment_plan.paid_amount" />
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">剩余金额</span>
                    <AmountText :value="detailRecord.payment_plan.remaining_amount" />
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">计划到期日</span>
                    <span class="attribute-value mono-value">{{ formatDate(detailRecord.payment_plan.due_date) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">计划状态</span>
                    <span class="attribute-value">{{ formatText(detailRecord.payment_plan.status) }}</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <!-- Notes Card -->
            <Card v-if="detailRecord?.notes" class="notes-card">
              <CardHeader class="section-heading">
                <CardTitle class="section-title">备注</CardTitle>
              </CardHeader>
              <CardContent class="section-content">
                <p class="notes-text">{{ detailRecord.notes }}</p>
              </CardContent>
            </Card>

            <Card v-if="approvalStatus === 'REJECTED' && rejectionReason" class="rejection-card" role="alert">
              <CardHeader class="section-heading">
                <CardTitle class="section-title">审批被驳回</CardTitle>
                <CardDescription>请根据驳回理由修改后重新提交。</CardDescription>
              </CardHeader>
              <CardContent class="section-content">
                <p class="rejection-reason">{{ rejectionReason }}</p>
              </CardContent>
            </Card>

            <!-- Approval Process Card -->
            <Card v-if="!readonly && recordEntityId !== null" class="approval-card">
              <CardHeader class="section-heading">
                <CardTitle class="section-title">审批流程</CardTitle>
                <CardDescription>回款记录的审批历史与当前处理状态。</CardDescription>
              </CardHeader>
              <CardContent class="section-content">
                <ApprovalProcessGeneric
                  entity-type="PAYMENT"
                  :entity-id="recordEntityId"
                  :can-approve="canApproveGeneric"
                  :is-submitter="isSubmitterGeneric"
                  @submitted="handleApprovalChanged"
                  @approved="handleApprovalChanged"
                  @rejected="handleApprovalChanged"
                  @withdrawn="handleApprovalChanged"
                  @resubmit="handleApprovalResubmit"
                />
              </CardContent>
            </Card>
          </template>

          <template v-else>
            <Card class="state-card">
              <CardContent class="state-card-content">
                <DataViewStatePanel
                  state="empty"
                  empty-title="暂无回款记录信息"
                  empty-description="请选择一个回款记录查看详情。"
                />
              </CardContent>
            </Card>
          </template>
        </div>
      </ScrollArea>

      <DetailSheetFooter v-if="!readonly" class="record-sheet-footer">
        <Button
          v-if="canEditRecord"
          variant="outline"
          type="button"
          @click="handleEditRecord"
        >
          <Pencil data-icon="inline-start" aria-hidden="true" />
          编辑回款记录
        </Button>
        <Button v-if="!embedded" variant="outline" type="button" @click="closeSheet">
          <X data-icon="inline-start" aria-hidden="true" />
          关闭
        </Button>
      </DetailSheetFooter>

      <FilePreviewDialog
        v-model:open="proofPreviewOpen"
        :file="proofFile"
        :allow-download="false"
        allow-open-in-new-tab
      />
  </div>

</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

$record-border-width: 1px;
$record-title-avatar-size: calc(var(--touch-target) + $space-1);
$record-header-mobile-indent: calc($record-title-avatar-size + $space-3);
$record-sheet-min-height: calc(#{var(--touch-target)} * 8 + #{$space-8});
$record-empty-min-height: calc(#{var(--touch-target)} * 6 + #{$space-4});

.detail-embedded-content {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  background: hsl(var(--card));
}

.record-sheet-scroll {
  flex: 1 1 auto;
  min-height: 0;
}

.readonly-error-state {
  padding: $space-4 0;
}

.record-sheet-header {
  padding: $space-6;
  padding-bottom: $space-4;
  border-bottom: $record-border-width solid hsl(var(--border));
}

.record-header-summary {
  display: flex;
  align-items: center;
  gap: $space-3;
  min-width: 0;

  @media (max-width: $bp-sm - 1) {
    align-items: flex-start;
    flex-wrap: wrap;
  }
}

.title-avatar {
  width: $record-title-avatar-size;
  height: $record-title-avatar-size;
  border-radius: 9999px;
  background: var(--wash-hover);
  color: hsl(var(--brand));
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 600;
  flex-shrink: 0;
}

.header-title-block {
  flex: 1;
  min-width: 0;
}

.record-sheet-title {
  color: hsl(var(--foreground));
  font-size: var(--font-size-body-strong);
  font-weight: 600;
  line-height: 24px;
}

.record-sheet-description {
  display: flex;
  align-items: center;
  gap: $space-2;
  min-height: var(--touch-target);
  color: hsl(var(--muted-foreground));
  flex-wrap: wrap;
}

.stage-name {
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-caption);
}

.amount-summary {
  display: flex;
  gap: $space-3;
  align-items: center;

  @media (max-width: $bp-sm - 1) {
    width: 100%;
    padding-left: $record-header-mobile-indent;
  }
}

.amount-summary-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: $space-1;
  padding: $space-2 $space-3;
  border: $record-border-width solid hsl(var(--border));
  border-radius: var(--radius-md);
  background: hsl(var(--muted));

  strong {
    color: hsl(var(--status-success));
    font-family: var(--font-mono);
    font-size: var(--font-size-body);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
}

.amount-summary-label {
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-caption);
}

.sheet-body {
  padding: $space-6;
  display: flex;
  flex-direction: column;
  gap: $space-6;
  min-height: $record-sheet-min-height;

  @media (max-width: $bp-sm - 1) {
    padding: $space-3;
    gap: $space-4;
  }
}

.loading-stack {
  display: flex;
  flex-direction: column;
  gap: $space-3;
}

.info-card,
.notes-card,
.rejection-card,
.approval-card,
.state-card {
  background: hsl(var(--card));
  border: $record-border-width solid hsl(var(--border));
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-1);
}

.section-heading {
  padding: $space-3 $space-4;
  border-bottom: $record-border-width solid hsl(var(--border));
  display: flex;
  flex-direction: column;
  gap: $space-1;
}

.section-title {
  margin: 0;
  color: hsl(var(--foreground));
  font-size: var(--font-size-body);
  font-weight: 600;
}

.section-content {
  padding: $space-4;
}

.attributes-grid,
.approval-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: $space-3 $space-4;

  @media (max-width: $bp-md - 1) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  @media (max-width: $bp-sm - 1) {
    grid-template-columns: 1fr;
  }
}

.approval-summary-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));

  @media (max-width: $bp-sm - 1) {
    grid-template-columns: 1fr;
  }
}

.attribute-item {
  display: flex;
  flex-direction: column;
  gap: $space-1;
  min-width: 0;
}

.attribute-label {
  display: flex;
  align-items: center;
  gap: $space-1;
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-caption);
  font-weight: 500;
}

.attribute-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.attribute-value {
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-body);
  font-weight: 500;
  line-height: 20px;
  word-break: break-word;
}

.attribute-item > :deep(.amount-text) {
  align-self: flex-start;
}

.mono-value {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

.voucher-section {
  margin-top: $space-4;
  padding-top: $space-4;
  border-top: $record-border-width solid hsl(var(--border));
  display: flex;
  flex-direction: column;
  gap: $space-2;
}

.voucher-preview {
  display: flex;
  flex-direction: column;
  gap: $space-2;
}

.voucher-thumb {
  align-self: flex-start;
  max-width: 100%;
  padding: 0;
  border: 0;
  border-radius: var(--radius-md);
  background: none;
  cursor: zoom-in;

  &:focus-visible {
    outline: 2px solid hsl(var(--brand));
    outline-offset: 2px;
  }
}

.voucher-image {
  display: block;
  max-width: 100%;
  max-height: 240px;
  border-radius: var(--radius-md);
  border: $record-border-width solid hsl(var(--border));
  transition: transform 0.15s ease;

  .voucher-thumb:hover & {
    transform: scale(1.02);
  }
}

.voucher-link {
  min-height: var(--touch-target);
  align-self: flex-start;
}

.voucher-hint {
  margin: 0;
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-body);
}

.notes-text {
  margin: 0;
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-body);
  line-height: 20px;
  white-space: pre-wrap;
  word-break: break-word;
}

.rejection-card {
  border-color: hsl(var(--status-danger));
  background: color-mix(in srgb, hsl(var(--status-danger)) var(--status-bg-mix), transparent);
}

.rejection-reason {
  margin: 0;
  color: hsl(var(--foreground));
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.approval-heading {
  flex-direction: row;
  align-items: flex-start;
  justify-content: space-between;
  gap: $space-3;
}

.approval-content {
  display: flex;
  flex-direction: column;
  gap: $space-4;
}

.state-card-content {
  min-height: $record-empty-min-height;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: $space-3;
  padding: $space-6;
}

.state-card-content-inline {
  min-height: 0;
  align-items: flex-start;
  flex-direction: row;
  justify-content: space-between;
}

.record-sheet-footer {
  padding: $space-4;
  border-top: $record-border-width solid hsl(var(--border));
  display: flex;
  flex: 0 0 auto;
  flex-direction: row;
  justify-content: flex-end;
  gap: $space-2;
  flex-wrap: wrap;

  @media (max-width: $bp-sm - 1) {
    :deep(button) {
      flex: 1 1 100%;
    }
  }
}

@media (prefers-reduced-motion: reduce) {
  .record-header-summary {
    transition-duration: 0.01ms;
  }
}
</style>
