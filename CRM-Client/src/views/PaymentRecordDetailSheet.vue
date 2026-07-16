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
 * Design: shadcn-vue + variables-v2.scss; no Element Plus imports.
 * Accessibility: focus-visible states, aria labels, touch targets >= 44px, semantic status display.
 */
import { computed, ref, watch } from 'vue'
import {
  AlertCircle,
  Calendar,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileText,
  Loader2,
  RefreshCw,
  User,
  Wallet,
  X
} from 'lucide-vue-next'
import {
  Sheet,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle
} from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
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
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import type {
  ApprovalInfo,
  ApprovalNodeInfo,
  ApprovalStatus,
  PaymentConfirmationStatus,
  PaymentRecordInfo
} from '@/api/payment'
import { formatCurrency, formatLocalDate } from '@/utils/format'

interface Props {
  recordId: number | null
  visible: boolean
  record?: PaymentRecordInfo | null
  stageName?: string
  approval?: ApprovalInfo | null
}

const props = withDefaults(defineProps<Props>(), {
  record: null,
  stageName: '',
  approval: null
})

const emit = defineEmits<{
  'update:visible': [value: boolean]
  close: []
}>()

// Local loading state for future API fetch support
const loading = ref<boolean>(false)
const errorMessage = ref<string>('')

const hasRecord = computed<boolean>(() => props.record !== null)
const hasApproval = computed<boolean>(() => props.approval !== null)
const hasProofAttachment = computed<boolean>(() => {
  const attachment = props.record?.proof_attachment
  return typeof attachment === 'string' && attachment.trim().length > 0
})

const approvalStatus = computed<ApprovalStatus | null>(() => props.approval?.status ?? null)
const isApprovalPending = computed<boolean>(() => approvalStatus.value === 'PENDING')
const isApprovalApproved = computed<boolean>(() => approvalStatus.value === 'APPROVED')
const isApprovalRejected = computed<boolean>(() => approvalStatus.value === 'REJECTED')

const confirmationStatusLabel = computed<string>(() => {
  return getConfirmationStatusLabel(props.record?.confirmation_status)
})

const confirmationStatusClass = computed<string>(() => {
  return getConfirmationStatusClass(props.record?.confirmation_status)
})

const approvalStatusLabel = computed<string>(() => {
  if (approvalStatus.value === null) return ''
  return getApprovalStatusLabel(approvalStatus.value)
})

const approvalStatusClass = computed<string>(() => {
  if (approvalStatus.value === null) return ''
  return getApprovalStatusClass(approvalStatus.value)
})

const currentApproverName = computed<string>(() => {
  if (props.approval === null || props.approval.status !== 'PENDING') return '-'
  const pendingNode = props.approval.nodes.find((node) => node.status === 'PENDING')
  return pendingNode?.approver_name ?? '待分配'
})

const rejectionReason = computed<string | null>(() => {
  const approval = props.approval
  if (approval === null || approval.status !== 'REJECTED') return null
  if (approval.reject_reason !== undefined && approval.reject_reason.trim() !== '') {
    return approval.reject_reason
  }
  const rejectedNode = approval.nodes.find((node) => node.status === 'REJECT' || node.status === 'REJECTED')
  return rejectedNode?.comment ?? '审批被驳回，请查看详情'
})

// Helper functions
function getConfirmationStatusLabel(status: PaymentConfirmationStatus | undefined): string {
  if (status === 'CONFIRMED') return '已确认'
  if (status === 'DISPUTED') return '有争议'
  return '待确认'
}

function getConfirmationStatusClass(status: PaymentConfirmationStatus | undefined): string {
  if (status === 'CONFIRMED') return 'status-success'
  if (status === 'DISPUTED') return 'status-danger'
  return 'status-warning'
}

function getApprovalStatusLabel(status: ApprovalStatus): string {
  const statusMap: Record<ApprovalStatus, string> = {
    PENDING: '审批中',
    APPROVED: '已通过',
    REJECTED: '已驳回'
  }
  return statusMap[status] ?? status
}

function getApprovalStatusClass(status: ApprovalStatus): string {
  const statusMap: Record<ApprovalStatus, string> = {
    PENDING: 'approval-status-warning',
    APPROVED: 'approval-status-success',
    REJECTED: 'approval-status-danger'
  }
  return statusMap[status] ?? ''
}

function getApprovalNodeStatusText(node: ApprovalNodeInfo): string {
  if (node.status === 'SUBMIT') return '已提交'
  if (node.status === 'APPROVE' || node.status === 'APPROVED') return '已通过'
  if (node.status === 'REJECT' || node.status === 'REJECTED') return '已驳回'
  return '待审批'
}

function getApprovalNodeClass(node: ApprovalNodeInfo): string {
  if (node.status === 'APPROVE' || node.status === 'APPROVED' || node.status === 'SUBMIT') {
    return 'node-approved'
  }
  if (node.status === 'REJECT' || node.status === 'REJECTED') {
    return 'node-rejected'
  }
  return 'node-pending'
}

function formatDate(dateStr: string | undefined): string {
  if (dateStr === undefined || dateStr.trim() === '') return '-'
  const date = new Date(dateStr)
  return Number.isNaN(date.getTime()) ? '-' : formatLocalDate(date)
}

function formatDateTime(dateStr: string | undefined): string {
  if (dateStr === undefined || dateStr.trim() === '') return '-'
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

function formatCreator(record: PaymentRecordInfo): string {
  const creatorName = record.creator_name?.trim()
  return creatorName === undefined || creatorName === '' ? '未知登记人' : creatorName
}

function handleOpenChange(open: boolean): void {
  emit('update:visible', open)
  if (!open) {
    emit('close')
  }
}

function closeSheet(): void {
  emit('update:visible', false)
  emit('close')
}

function handleProofClick(): void {
  const attachment = props.record?.proof_attachment
  if (typeof attachment === 'string' && attachment.trim().length > 0) {
    window.open(attachment, '_blank', 'noopener,noreferrer')
  }
}

// Reset state when closing
watch(
  () => props.visible,
  (visible) => {
    if (!visible) {
      errorMessage.value = ''
    }
  }
)
</script>

<template>
  <Sheet :open="visible" @update:open="handleOpenChange">
    <DetailSheetContent>
      <SheetHeader class="record-sheet-header">
        <div class="record-header-summary">
          <div v-if="hasRecord" class="title-avatar" aria-hidden="true">
            {{ (props.record?.record_number ?? '款').charAt(0) }}
          </div>

          <div class="header-title-block">
            <SheetTitle class="record-sheet-title">
              {{ props.record?.record_number ?? '回款记录详情' }}
            </SheetTitle>
            <SheetDescription class="record-sheet-description">
              <Badge
                v-if="hasRecord"
                :class="['record-status-badge', confirmationStatusClass]"
                role="status"
                :aria-label="confirmationStatusLabel"
              >
                {{ confirmationStatusLabel }}
              </Badge>
              <span v-if="props.stageName" class="stage-name">{{ props.stageName }}</span>
              <span v-else>{{ loading ? '正在加载回款记录' : '查看回款详情与审批进度' }}</span>
            </SheetDescription>
          </div>

          <div v-if="hasRecord" class="amount-summary" aria-label="回款金额">
            <div class="amount-summary-item">
              <span class="amount-summary-label">回款金额</span>
              <strong>{{ formatCurrency(props.record?.actual_amount ?? 0) }}</strong>
            </div>
          </div>
        </div>
      </SheetHeader>

      <ScrollArea class="flex-1">
        <div class="sheet-body">
          <template v-if="loading">
            <div class="loading-stack" aria-live="polite" aria-busy="true">
              <Skeleton class="h-28 w-full" />
              <Skeleton class="h-48 w-full" />
            </div>
          </template>

          <template v-else-if="errorMessage">
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
                <Button variant="outline" type="button" @click="closeSheet">
                  <RefreshCw data-icon="inline-start" aria-hidden="true" />
                  重新加载
                </Button>
              </CardContent>
            </Card>
          </template>

          <template v-else-if="hasRecord">
            <Card class="info-card">
              <CardHeader class="section-heading">
                <CardTitle class="section-title">基本信息</CardTitle>
                <CardDescription>回款阶段、日期、凭证与登记人信息。</CardDescription>
              </CardHeader>
              <CardContent class="section-content">
                <div class="attributes-grid">
                  <div v-if="props.stageName" class="attribute-item">
                    <span class="attribute-label">
                      <Wallet aria-hidden="true" class="attribute-icon" />
                      回款阶段
                    </span>
                    <span class="attribute-value">{{ formatText(props.stageName) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <Calendar aria-hidden="true" class="attribute-icon" />
                      回款日期
                    </span>
                    <span class="attribute-value mono-value">{{ formatDate(props.record?.payment_date) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <User aria-hidden="true" class="attribute-icon" />
                      登记人
                    </span>
                    <span class="attribute-value">{{ formatCreator(props.record!) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">登记时间</span>
                    <span class="attribute-value mono-value">{{ formatDateTime(props.record?.created_time) }}</span>
                  </div>
                </div>

                <!-- Voucher/Proof Attachment -->
                <div v-if="hasProofAttachment" class="voucher-section">
                  <span class="attribute-label">
                    <FileText aria-hidden="true" class="attribute-icon" />
                    凭证附件
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    type="button"
                    class="voucher-link"
                    :aria-label="`查看凭证附件，将在新标签页打开`"
                    @click="handleProofClick"
                  >
                    <ExternalLink aria-hidden="true" />
                    查看凭证
                  </Button>
                  <p class="voucher-hint">点击按钮在新标签页打开凭证附件</p>
                </div>
              </CardContent>
            </Card>

            <!-- Notes Card -->
            <Card v-if="props.record?.notes" class="notes-card">
              <CardHeader class="section-heading">
                <CardTitle class="section-title">备注</CardTitle>
              </CardHeader>
              <CardContent class="section-content">
                <p class="notes-text">{{ props.record.notes }}</p>
              </CardContent>
            </Card>

            <!-- Approval Progress Card -->
            <Card v-if="hasApproval" class="approval-card">
              <CardHeader class="section-heading approval-heading">
                <div>
                  <CardTitle class="section-title">审批进度</CardTitle>
                  <CardDescription>回款记录的审批状态。</CardDescription>
                </div>
                <Badge :class="['approval-status-badge', approvalStatusClass]">
                  {{ approvalStatusLabel }}
                </Badge>
              </CardHeader>
              <CardContent class="section-content approval-content">
                <Alert v-if="isApprovalRejected" variant="destructive">
                  <AlertCircle aria-hidden="true" />
                  <AlertTitle>审批被驳回</AlertTitle>
                  <AlertDescription>{{ rejectionReason ?? '请查看驳回原因并修正后重新提交' }}</AlertDescription>
                </Alert>

                <div class="approval-summary-grid">
                  <div class="attribute-item">
                    <span class="attribute-label">当前审批人</span>
                    <span class="attribute-value">{{ currentApproverName }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">提交时间</span>
                    <span class="attribute-value mono-value">{{ formatDateTime(props.approval?.created_time) }}</span>
                  </div>
                </div>

                <ol v-if="props.approval?.nodes?.length" class="approval-node-list" aria-label="审批节点">
                  <li
                    v-for="node in props.approval.nodes"
                    :key="node.id"
                    :class="['approval-node', getApprovalNodeClass(node)]"
                  >
                    <div class="node-marker" aria-hidden="true" />
                    <div class="node-content">
                      <div class="node-title-line">
                        <span class="node-name">{{ node.node_name }}</span>
                        <Badge variant="outline">{{ getApprovalNodeStatusText(node) }}</Badge>
                      </div>
                      <div class="node-meta">
                        <span>{{ node.approver_name ?? node.approve_role }}</span>
                        <span v-if="node.approved_time">{{ formatDateTime(node.approved_time) }}</span>
                      </div>
                      <p v-if="node.comment" class="node-comment">{{ node.comment }}</p>
                    </div>
                  </li>
                </ol>
              </CardContent>
            </Card>
          </template>

          <template v-else>
            <Card class="state-card">
              <CardContent class="state-card-content">
                <Empty>
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <FileText aria-hidden="true" />
                    </EmptyMedia>
                    <EmptyTitle>暂无回款记录信息</EmptyTitle>
                    <EmptyDescription>请选择一个回款记录查看详情。</EmptyDescription>
                  </EmptyHeader>
                </Empty>
              </CardContent>
            </Card>
          </template>
        </div>
      </ScrollArea>

      <SheetFooter class="record-sheet-footer">
        <Button
          v-if="isApprovalPending"
          variant="secondary"
          type="button"
          disabled
        >
          <Loader2 data-icon="inline-start" aria-hidden="true" class="animate-spin" />
          审批中...
        </Button>
        <Button
          v-else-if="isApprovalApproved"
          variant="secondary"
          type="button"
          disabled
        >
          <CheckCircle2 data-icon="inline-start" aria-hidden="true" />
          已通过
        </Button>
        <Button variant="outline" type="button" @click="closeSheet">
          <X data-icon="inline-start" aria-hidden="true" />
          关闭
        </Button>
      </SheetFooter>
    </DetailSheetContent>
  </Sheet>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

$record-border-width: $wolf-focus-ring-width-subtle-v2;
$record-title-avatar-size: calc($wolf-touch-target-min-v2 + $wolf-space-xs-v2);
$record-header-mobile-indent: calc($record-title-avatar-size + $wolf-space-md-v2);
$record-sheet-min-height: ($wolf-touch-target-min-v2 * 8) + $wolf-space-2xl-v2;
$record-empty-min-height: ($wolf-touch-target-min-v2 * 6) + $wolf-space-lg-v2;

.record-sheet-header {
  padding: $wolf-space-xl-v2;
  padding-bottom: $wolf-space-lg-v2;
  border-bottom: $record-border-width solid $wolf-border-default-v2;
}

.record-header-summary {
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
  width: $record-title-avatar-size;
  height: $record-title-avatar-size;
  border-radius: $wolf-radius-full-v2;
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: $wolf-topbar-title-font-size-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  flex-shrink: 0;
}

.header-title-block {
  flex: 1;
  min-width: 0;
}

.record-sheet-title {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  line-height: $wolf-line-height-title-v2;
}

.record-sheet-description {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  min-height: $wolf-touch-target-min-v2;
  color: $wolf-text-tertiary-v2;
  flex-wrap: wrap;
}

.stage-name {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
}

.amount-summary {
  display: flex;
  gap: $wolf-space-md-v2;
  align-items: center;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    width: 100%;
    padding-left: $record-header-mobile-indent;
  }
}

.amount-summary-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
  border: $record-border-width solid $wolf-border-light-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-bg-muted-v2;

  strong {
    color: $wolf-success-text-v2;
    font-family: $wolf-font-mono-v2;
    font-size: $wolf-font-size-body-v2;
    font-weight: $wolf-font-weight-semibold-v2;
    font-variant-numeric: tabular-nums;
  }
}

.amount-summary-label {
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
}

.sheet-body {
  padding: $wolf-space-xl-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xl-v2;
  min-height: $record-sheet-min-height;

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
.notes-card,
.approval-card,
.state-card {
  background: $wolf-bg-card-v2;
  border: $record-border-width solid $wolf-border-default-v2;
  border-radius: $wolf-radius-lg-v2;
  box-shadow: $wolf-shadow-card-v2;
}

.section-heading {
  padding: $wolf-space-md-v2 $wolf-space-lg-v2;
  border-bottom: $record-border-width solid $wolf-border-light-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.section-title {
  margin: 0;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.section-content {
  padding: $wolf-space-lg-v2;
}

.attributes-grid,
.approval-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: $wolf-space-md-v2 $wolf-space-lg-v2;

  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
  }
}

.approval-summary-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));

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
  display: flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.attribute-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.attribute-value {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: $wolf-line-height-body-v2;
  word-break: break-word;
}

.mono-value {
  font-family: $wolf-font-mono-v2;
  font-variant-numeric: tabular-nums;
}

.voucher-section {
  margin-top: $wolf-space-lg-v2;
  padding-top: $wolf-space-lg-v2;
  border-top: $record-border-width solid $wolf-border-light-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm-v2;
}

.voucher-link {
  min-height: $wolf-touch-target-min-v2;
  align-self: flex-start;
}

.voucher-hint {
  margin: 0;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-auxiliary-v2;
}

.notes-text {
  margin: 0;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-body-v2;
  line-height: $wolf-line-height-body-v2;
  white-space: pre-wrap;
  word-break: break-word;
}

.approval-heading {
  flex-direction: row;
  align-items: flex-start;
  justify-content: space-between;
  gap: $wolf-space-md-v2;
}

.approval-content {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
}

.record-status-badge,
.approval-status-badge,
.approval-node :deep([data-slot='badge']) {
  white-space: nowrap;
}

.record-status-badge,
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

.approval-status-warning {
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
  border-color: transparent;
}

.approval-status-success {
  background: $wolf-success-bg-v2;
  color: $wolf-success-text-v2;
  border-color: transparent;
}

.approval-status-danger {
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-text-v2;
  border-color: transparent;
}

.approval-node-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
}

.approval-node {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: $wolf-space-md-v2;
  min-height: $wolf-touch-target-min-v2;
}

.node-marker {
  width: $wolf-space-md-v2;
  height: $wolf-space-md-v2;
  margin-top: $wolf-space-xs-v2;
  border-radius: $wolf-radius-full-v2;
  background: $wolf-border-default-v2;
}

.node-approved .node-marker {
  background: $wolf-success-v2;
}

.node-rejected .node-marker {
  background: $wolf-danger-v2;
}

.node-pending .node-marker {
  background: $wolf-warning-v2;
}

.node-content {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  min-width: 0;
}

.node-title-line {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  flex-wrap: wrap;
}

.node-name {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.node-meta,
.node-comment {
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
}

.node-meta {
  display: flex;
  gap: $wolf-space-sm-v2;
  flex-wrap: wrap;
}

.node-comment {
  margin: 0;
  color: $wolf-text-secondary-v2;
}

.state-card-content {
  min-height: $record-empty-min-height;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: $wolf-space-md-v2;
  padding: $wolf-space-xl-v2;
}

.record-sheet-footer {
  padding: $wolf-space-lg-v2;
  border-top: $record-border-width solid $wolf-border-default-v2;
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

@media (prefers-reduced-motion: reduce) {
  .record-header-summary,
  .approval-node {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>