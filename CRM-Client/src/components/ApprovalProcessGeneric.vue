/**
 * ApprovalProcessGeneric — 通用审批操作组件（Phase C，C-DSG-5 / C-DSG-7）
 *
 * 嵌入业务详情页的审批区。Props：
 *   entityType : 'CONTRACT' | 'PAYMENT' | 'INVOICE'
 *   entityId   : number
 *   canApprove : 是否对当前节点具备审批权（控制同意/驳回按钮显隐）
 *   isSubmitter: 是否为提交人（控制撤回 + 草稿态"提交审批"CTA 显隐）
 *
 * 不直接调 API（COMPONENTS.md「组件禁直接调 API」），统一通过 useApprovalStore()
 * 的 actions：fetchDetail / submitEntity / approveEntity / cancelEntity。
 *
 * 五态覆盖（C-DSG-4）：Loading(Skeleton) / Empty(WolfEmpty 草稿态 CTA) /
 * Error(ErrorState 通用/forbidden) / Success(toast) / Conflict(409 重载保输入)。
 *
 * C-DSG-7 P0 已落：
 *   条2 驳回弹窗 reason 必填；同意 comment 可空（直接按钮）。
 *   条3 按钮 action pending 期间 :loading + :disabled，防双击。
 *   条8 乐观锁冲突→保留 rejectForm.reason→warning toast→重载 detail；
 *       重载后非 PENDING→禁用提交并提示「该审批已由他人处理，无需重复操作」。
 *
 * 响应式（C-DSG-6）：宽屏（≥1024px）水平 timeline，窄屏自动切垂直。matchMedia
 * 不可用时（如 jsdom）回退到水平（isWide=true），不影响功能。
 */
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { PropType, Component } from 'vue'
import { toast } from 'vue-sonner'
import {
  Send,
  CheckCircle2,
  XCircle,
  RotateCcw,
  Download,
  FileText,
  Loader2,
  AlertTriangle
} from 'lucide-vue-next'
import { storeToRefs } from 'pinia'
import { useApprovalStore } from '@/stores/approval'
import type {
  EntityType,
  ApprovalDetail,
  ApprovalRecord
} from '@/schemas/approvalGeneric'
import ApprovalStatusBadge from './ApprovalStatusBadge.vue'
import ErrorState from './ErrorState.vue'
import WolfEmpty from './WolfEmpty.vue'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle
} from '@/components/ui/alert-dialog'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import InvoiceFileUpload from './InvoiceFileUpload.vue'
import { getInvoiceFileUrl } from '@/api/fileUpload'

interface RecordVisual {
  icon: Component
  actionLabel: string
  textVar: string
}

const RECORD_VISUAL: Record<
  'SUBMIT' | 'APPROVE' | 'REJECT' | 'ROLLBACK' | 'CANCEL',
  RecordVisual
> = {
  SUBMIT: { icon: Send, actionLabel: '提交', textVar: '--wolf-approval-pending-text' },
  APPROVE: { icon: CheckCircle2, actionLabel: '同意', textVar: '--wolf-approval-approved-text' },
  REJECT: { icon: XCircle, actionLabel: '驳回', textVar: '--wolf-approval-rejected-text' },
  ROLLBACK: { icon: RotateCcw, actionLabel: '撤回', textVar: '--wolf-approval-cancelled-text' },
  CANCEL: { icon: RotateCcw, actionLabel: '撤回', textVar: '--wolf-approval-cancelled-text' }
}

const SUBMIT_PERMISSION: Record<EntityType, string> = {
  CONTRACT: 'contract:submit',
  PAYMENT: 'payment:submit',
  INVOICE: 'invoice:submit',
  LICENSE: 'license:submit'
}

const props = defineProps({
  entityType: {
    type: String as PropType<EntityType>,
    required: true
  },
  entityId: {
    type: Number,
    required: true
  },
  canApprove: {
    type: Boolean,
    default: false
  },
  isSubmitter: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits<{
  submitted: []
  approved: []
  rejected: []
  withdrawn: []
  resubmit: []
  // Task 6: 发票文件上传事件
  uploaded: [file_path: string, invoice_number: string]
}>()

const store = useApprovalStore()
const { currentApprovalDetail } = storeToRefs(store)

// ===== 本地 UI 状态（必须 ref<Type>(...) 显式类型）=====
const loadError = ref<boolean>(false)
const notFound = ref<boolean>(false)
const actionPending = ref<boolean>(false)
const rejectDialogVisible = ref<boolean>(false)
const withdrawDialogVisible = ref<boolean>(false)
const rejectForm = ref<{ reason: string }>({ reason: '' })
const isWide = ref<boolean>(true)
const conflictNotice = ref<string>('')
// Task 6: 发票文件上传组件 ref
const invoiceFileUploadRef = ref<InstanceType<typeof InvoiceFileUpload>>()

// ===== 计算属性（必须返回类型）=====
const detail = computed<ApprovalDetail | null>(() => currentApprovalDetail.value)

const status = computed<ApprovalDetail['status'] | undefined>(() => detail.value?.status)
const isPending = computed<boolean>(() => status.value === 'PENDING')
// C-DSG-7 条4：REJECTED 态提交人可见「修改并重新提交」CTA（抽屉侧入口）
const isRejected = computed<boolean>(() => status.value === 'REJECTED')
// 冲突重载后启用提交
const isLocked = computed<boolean>(() => conflictNotice.value.length > 0)

const records = computed<ApprovalRecord[]>(() => detail.value?.records ?? [])

const submitPermissionCode = computed<string>(() => SUBMIT_PERMISSION[props.entityType])

// Task 6: 发票审批时是否显示文件上传组件
// 条件：entityType === 'INVOICE' && canApprove && status === 'PENDING_REVIEW'
const showInvoiceFileUpload = computed<boolean>(() =>
  props.entityType === 'INVOICE' &&
  props.canApprove &&
  status.value === 'PENDING' // PENDING 对应后端的 PENDING_REVIEW
)

// Task 6: 发票是否已上传文件（用于显示下载链接）
const hasInvoiceFile = computed<boolean>(() =>
  props.entityType === 'INVOICE' &&
  detail.value?.invoice_file_path != null &&
  detail.value.invoice_file_path.length > 0
)

// ===== 错误识别：仅匹配 axios 风格 error.response.status，不用 any =====
const isAxiosStatus = (err: unknown, code: number): boolean => {
  const r = (err as { response?: { status?: number } } | null)?.response
  return typeof r?.status === 'number' && r.status === code
}

// ===== 方法（必须参数和返回类型）=====
const loadDetail = async (): Promise<void> => {
  loadError.value = false
  notFound.value = false
  conflictNotice.value = ''
  try {
    await store.fetchDetail(props.entityType, props.entityId)
  } catch (err) {
    if (isAxiosStatus(err, 404)) {
      notFound.value = true
    } else {
      loadError.value = true
    }
  }
}

const handleSubmit = async (): Promise<void> => {
  if (actionPending.value || isLocked.value) return
  actionPending.value = true
  try {
    await store.submitEntity(props.entityType, props.entityId)
    toast.success('已提交审批，等待审批人处理')
    emit('submitted')
    await loadDetail()
  } catch {
    // 错误 toast 由 request 拦截器统一处理；这里不抛
  } finally {
    actionPending.value = false
  }
}

const handleApprove = async (): Promise<void> => {
  if (actionPending.value || isLocked.value || !isPending.value) return
  if (detail.value == null) return
  actionPending.value = true
  try {
    await store.approveEntity(
      props.entityType, props.entityId, 'APPROVE', '', detail.value.updated_time
    )
    toast.success('已同意')
    emit('approved')
  } catch (err) {
    if (isAxiosStatus(err, 409)) {
      toast.warning('该审批已被其他人处理，已为你刷新最新状态')
      await loadDetail()
      if (!isPending.value) {
        conflictNotice.value = '该审批已由他人处理，无需重复操作'
      }
    }
    // 其他错误：拦截器已 toast，不抛
  } finally {
    actionPending.value = false
  }
}

const openRejectDialog = (): void => {
  // 不在此处重置 reason：C-DSG-7 条8 冲突后保留已输入
  rejectDialogVisible.value = true
}

const confirmReject = async (): Promise<void> => {
  if (actionPending.value || isLocked.value) return
  // 同步必填守卫（条2）：action 入口必须先校验
  if (!rejectForm.value.reason.trim()) {
    toast.warning('请填写驳回理由，提交人将据此修改')
    return
  }
  if (detail.value == null) return
  actionPending.value = true
  try {
    await store.approveEntity(
      props.entityType, props.entityId, 'REJECT',
      rejectForm.value.reason, detail.value.updated_time
    )
    toast.success('已驳回，申请人可修改后重新提交')
    rejectDialogVisible.value = false
    rejectForm.value.reason = ''
    emit('rejected')
  } catch (err) {
    if (isAxiosStatus(err, 409)) {
      // C-DSG-7 条8：不清空 reason、不关弹窗、提示并重载
      toast.warning('该审批已被他人处理，你的填写已保留')
      await loadDetail()
      if (!isPending.value) {
        conflictNotice.value = '该审批已由他人处理，无需重复操作'
      }
    }
    // 其他错误：拦截器已 toast，不抛、不关弹窗、不清理由
  } finally {
    actionPending.value = false
  }
}

const openWithdrawDialog = (): void => {
  withdrawDialogVisible.value = true
}

const confirmWithdraw = async (): Promise<void> => {
  if (actionPending.value || isLocked.value || !isPending.value) return
  actionPending.value = true
  try {
    await store.cancelEntity(props.entityType, props.entityId)
    toast.success('已撤回')
    withdrawDialogVisible.value = false
    emit('withdrawn')
    await loadDetail()
  } catch {
    // 错误 toast 由拦截器统一处理
  } finally {
    actionPending.value = false
  }
}

// C-DSG-7 条4：REJECTED 态提交人「修改并重新提交」CTA（抽屉侧入口）
// 组件本身不导航（COMPONENTS.md「组件禁直接调 API/禁导航」），仅 emit resubmit
// 由父视图（FinanceApprovalCenter）据 currentRow 走 router.push 跳对应编辑页。
const handleResubmit = (): void => {
  if (actionPending.value || isLocked.value || !isRejected.value) return
  if (!props.isSubmitter) return
  emit('resubmit')
}

// Task 6: 发票文件上传成功处理
const handleFileUploaded = (file_path: string, invoice_number: string): void => {
  emit('uploaded', file_path, invoice_number)
  // 刷新详情以获取最新状态
  loadDetail()
}

// Task 6: 发票文件上传错误处理
const handleUploadError = (message: string): void => {
  toast.error(message.length > 0 ? message : '文件上传失败')
}

// Task 6: 发票文件下载
const downloadInvoiceFile = (): void => {
  if (detail.value == null) return
  const url = getInvoiceFileUrl(props.entityId)
  window.open(url, '_blank')
}

const setupResponsive = (): void => {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    isWide.value = true
    return
  }
  const mql = window.matchMedia('(min-width: 1024px)')
  isWide.value = mql.matches
  mql.addEventListener('change', (e: MediaQueryListEvent) => {
    isWide.value = e.matches
  })
}

const formatDateTime = (iso: string): string => {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  // YYYY-MM-DD HH:mm
  const pad = (n: number): string => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// ===== 生命周期 =====
onMounted(async (): Promise<void> => {
  setupResponsive()
  await loadDetail()
})
</script>

<template>
  <div class="approval-process-generic">
    <!-- 加载骨架（C-DSG-4 Loading） -->
    <div v-if="loadError === false && notFound === false && detail === null" class="space-y-4">
      <Skeleton class="h-32 w-full" />
      <Skeleton class="h-48 w-full" />
    </div>

    <!-- 错误态（C-DSG-4 Error） -->
    <ErrorState
      v-else-if="loadError && !notFound"
      title="审批信息加载失败"
      description="可点击下方按钮重新加载，若持续失败请联系管理员"
    >
      <template #action>
        <Button data-testid="reload-detail-btn" @click="loadDetail">
          重新加载
        </Button>
      </template>
    </ErrorState>

    <!-- 草稿空态（detail===null 且 404）：提交 CTA -->
    <WolfEmpty
      v-else-if="detail === null && notFound"
      title="尚未提交审批"
      description="提交后审批人将收到待办通知"
    >
      <template v-if="isSubmitter" #action>
        <Button
          v-permission="submitPermissionCode"
          data-testid="submit-approval-btn"
          :disabled="actionPending"
          @click="handleSubmit"
        >
          <Loader2 v-if="actionPending" class="mr-2 h-4 w-4 animate-spin" />
          提交审批
        </Button>
      </template>
    </WolfEmpty>

    <!-- 详情态：PENDING / APPROVED / REJECTED / CANCELLED -->
    <div v-else-if="detail" class="approval-process-generic__body">
      <!-- 标题 + 状态徽章 -->
      <div class="approval-process-generic__header">
        <span class="approval-process-generic__title">{{ detail?.flow_name ?? '审批进度' }}</span>
        <ApprovalStatusBadge v-if="status" :status="status" size="small" />
      </div>

      <!-- 冲突锁定提示（C-DSG-7 条8：重载后已由他人终结） -->
      <div v-if="isLocked" class="approval-process-generic__conflict" role="alert">
        <AlertTriangle class="h-4 w-4" />
        <span>{{ conflictNotice }}</span>
      </div>

      <!-- 当前节点意见 -->
      <div v-if="detail?.current_node_name" class="approval-process-generic__current-node">
        <span class="approval-process-generic__current-node-label">当前节点：</span>
        <span class="approval-process-generic__current-node-value">{{ detail.current_node_name }}</span>
      </div>

      <!-- Task 6: 已上传发票文件显示（仅 INVOICE 类型） -->
      <div v-if="hasInvoiceFile" class="approval-process-generic__file-section">
        <div class="file-header">
          <FileText class="h-4 w-4" />
          <span class="file-title">发票文件</span>
        </div>
        <div class="file-info">
          <span v-if="detail?.invoice_number" class="invoice-number">
            发票号码：{{ detail.invoice_number }}
          </span>
          <Button variant="link" size="sm" @click="downloadInvoiceFile">
            <Download class="mr-1 h-4 w-4" />
            下载发票文件
          </Button>
        </div>
      </div>

      <!-- timeline（响应式：宽屏水平 / 窄屏垂直） -->
      <ul
        class="approval-process-generic__timeline"
        :class="{ 'is-wide': isWide }"
        v-if="records.length > 0"
      >
        <li
          v-for="record in records"
          :key="record.id"
          class="approval-process-generic__timeline-item"
          :style="{ color: `var(${RECORD_VISUAL[record.action ?? 'ROLLBACK'].textVar})` }"
        >
          <component
            :is="RECORD_VISUAL[record.action ?? 'ROLLBACK'].icon"
            class="approval-process-generic__timeline-icon"
          />
          <div class="approval-process-generic__timeline-content">
            <span class="approval-process-generic__timeline-action">
              {{ RECORD_VISUAL[record.action ?? 'ROLLBACK'].actionLabel }}
            </span>
            <span v-if="record.approver_name" class="approval-process-generic__timeline-user">
              {{ record.approver_name }}
            </span>
            <span class="approval-process-generic__timeline-time">
              {{ formatDateTime(record.created_time) }}
            </span>
            <span v-if="record.comment" class="approval-process-generic__timeline-comment">
              {{ record.comment }}
            </span>
          </div>
        </li>
      </ul>

      <!-- 操作区 -->
      <div class="approval-process-generic__actions">
        <!-- Task 6: 发票审批时的文件上传区域（替代原有同意/驳回按钮） -->
        <div v-if="showInvoiceFileUpload" class="invoice-file-upload-wrapper">
          <InvoiceFileUpload
            ref="invoiceFileUploadRef"
            :invoice-id="entityId"
            :approval-status="(status as string | undefined)"
            @uploaded="handleFileUploaded"
            @error="handleUploadError"
            @rejected="() => { emit('rejected'); loadDetail() }"
            @status-changed="loadDetail"
          />
        </div>

        <!-- 原有操作按钮（非 INVOICE 或非审批状态时显示） -->
        <template v-if="!showInvoiceFileUpload">
          <Button
            v-if="isSubmitter && isPending"
            variant="outline"
            data-testid="withdraw-btn"
            :disabled="actionPending || isLocked"
            @click="openWithdrawDialog"
          >
            <Loader2 v-if="actionPending" class="mr-2 h-4 w-4 animate-spin" />
            撤回审批
          </Button>
          <Button
            v-if="isSubmitter && isRejected"
            data-testid="resubmit-btn"
            :disabled="actionPending || isLocked"
            @click="handleResubmit"
          >
            <Loader2 v-if="actionPending" class="mr-2 h-4 w-4 animate-spin" />
            修改并重新提交
          </Button>
          <Button
            v-if="canApprove && isPending"
            data-testid="approve-btn"
            :disabled="actionPending || isLocked"
            @click="handleApprove"
          >
            <Loader2 v-if="actionPending" class="mr-2 h-4 w-4 animate-spin" />
            同意
          </Button>
          <Button
            v-if="canApprove && isPending"
            variant="destructive"
            data-testid="reject-btn"
            :disabled="actionPending || isLocked"
            @click="openRejectDialog"
          >
            <Loader2 v-if="actionPending" class="mr-2 h-4 w-4 animate-spin" />
            驳回
          </Button>
        </template>
      </div>

      <!-- 驳回弹窗：reason 必填，C-DSG-7 条2 -->
      <Dialog v-model:open="rejectDialogVisible">
        <DialogContent class="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle>驳回审批</DialogTitle>
            <DialogDescription>
              请填写驳回理由，提交人将据此修改。
            </DialogDescription>
          </DialogHeader>

          <div class="space-y-4">
            <Textarea
              v-model="rejectForm.reason"
              data-testid="reject-reason"
              placeholder="请填写驳回理由，提交人将据此修改"
              :rows="4"
              :maxlength="500"
            />
            <p class="text-sm text-muted-foreground text-right">
              {{ rejectForm.reason.length }} / 500
            </p>
          </div>

          <DialogFooter>
            <Button variant="ghost" @click="rejectDialogVisible = false">
              取消
            </Button>
            <Button
              variant="destructive"
              data-testid="reject-confirm-btn"
              :disabled="!rejectForm.reason.trim() || actionPending"
              @click="confirmReject"
            >
              <Loader2 v-if="actionPending" class="mr-2 h-4 w-4 animate-spin" />
              确定
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <!-- 撤回确认弹窗 -->
      <AlertDialog v-model:open="withdrawDialogVisible">
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>撤回审批</AlertDialogTitle>
            <AlertDialogDescription>
              撤回后审批中止，需重新提交。确定撤回？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel @click="withdrawDialogVisible = false">
              取消
            </AlertDialogCancel>
            <AlertDialogAction
              :disabled="actionPending"
              @click="confirmWithdraw"
            >
              <Loader2 v-if="actionPending" class="mr-2 h-4 w-4 animate-spin" />
              确定撤回
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.approval-process-generic {
  width: 100%;
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-v2;
  padding: $wolf-card-padding-v2;
}

.approval-process-generic__body {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
}

.approval-process-generic__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $wolf-space-sm-v2;
  margin-bottom: $wolf-space-md-v2;
}

.approval-process-generic__title {
  font-family: $wolf-font-display-v2;
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-medium-v2;
  color: $wolf-text-primary-v2;
}

.approval-process-generic__conflict {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-text-v2;
  border-radius: $wolf-radius-sm-v2;
  font-size: $wolf-font-size-auxiliary-v2;
  margin-bottom: $wolf-space-md-v2;
}

.approval-process-generic__current-node {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
  margin-bottom: $wolf-space-md-v2;
  font-size: $wolf-font-size-auxiliary-v2;
  color: $wolf-text-tertiary-v2;

  .approval-process-generic__current-node-value {
    color: $wolf-text-secondary-v2;
    font-weight: $wolf-font-weight-medium-v2;
  }
}

.approval-process-generic__timeline {
  list-style: none;
  margin: 0;
  padding: 0;

  // 宽屏水平
  &.is-wide {
    display: flex;
    align-items: flex-start;
    gap: $wolf-space-md-v2;
    flex-wrap: wrap;
  }

  // 默认（窄屏）垂直
  &:not(.is-wide) {
    display: flex;
    flex-direction: column;
    gap: $wolf-space-md-v2;
  }
}

.approval-process-generic__timeline-item {
  display: flex;
  align-items: flex-start;
  gap: $wolf-space-sm-v2;

  .is-wide & {
    flex: 1 1 200px;
    flex-direction: column;
    align-items: center;
    text-align: center;
  }
}

.approval-process-generic__timeline-icon {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
}

.approval-process-generic__timeline-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: $wolf-font-size-auxiliary-v2;
  line-height: $wolf-line-height-body-v2;
}

.approval-process-generic__timeline-action {
  font-weight: $wolf-font-weight-medium-v2;
  color: inherit;
}

.approval-process-generic__timeline-user {
  color: $wolf-text-secondary-v2;
}

.approval-process-generic__timeline-time {
  color: $wolf-text-placeholder-v2;
  font-family: $wolf-font-mono-v2;
  font-size: $wolf-font-size-caption-v2;
}

.approval-process-generic__timeline-comment {
  color: $wolf-text-secondary-v2;
  margin-top: $wolf-space-xs-v2;
}

.approval-process-generic__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: $wolf-space-sm-v2;
  margin-top: $wolf-space-lg-v2;
  padding-top: $wolf-space-md-v2;
  border-top: 1px solid $wolf-border-light-v2;
}

// Task 6: 发票文件上传区域样式
.invoice-file-upload-wrapper {
  width: 100%;
}

// Task 6: 已上传文件显示区域样式
.approval-process-generic__file-section {
  background: $wolf-bg-hover-v2;
  border-radius: $wolf-radius-sm-v2;
  padding: $wolf-space-md-v2;
  margin-bottom: $wolf-space-md-v2;

  .file-header {
    display: flex;
    align-items: center;
    gap: $wolf-space-xs-v2;
    margin-bottom: $wolf-space-sm-v2;
    color: $wolf-text-secondary-v2;
    font-weight: $wolf-font-weight-medium-v2;
  }

  .file-title {
    font-size: $wolf-font-size-body-v2;
  }

  .file-info {
    display: flex;
    align-items: center;
    gap: $wolf-space-md-v2;

    .invoice-number {
      font-size: $wolf-font-size-caption-v2;
      color: $wolf-text-tertiary-v2;
    }
  }
}
</style>