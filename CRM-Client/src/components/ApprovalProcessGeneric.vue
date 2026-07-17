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
 * 五态覆盖（C-DSG-4）：Loading(Skeleton) / Empty(components/ui/empty 草稿态 CTA) /
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
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { PropType } from 'vue'
import { toast } from 'vue-sonner'
import {
  Loader2,
  AlertTriangle
} from 'lucide-vue-next'
import { storeToRefs } from 'pinia'
import { useApprovalStore } from '@/stores/approval'
import { usePermissionStore } from '@/stores/permissions'
import type {
  EntityType,
  ApprovalDetail,
  ApprovalRecord
} from '@/schemas/approvalGeneric'
import { FileAttachment } from '@/components/crmwolf'
import ApprovalStatusBadge from './ApprovalStatusBadge.vue'
import ApprovalProcessStepper from './ApprovalProcessStepper.vue'
import ErrorState from './ErrorState.vue'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle
} from '@/components/ui/empty'
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
import InvoiceMarkIssuedDialog from '@/components/dialogs/InvoiceMarkIssuedDialog.vue'
import LicenseIssueDialog from '@/components/dialogs/LicenseIssueDialog.vue'
import {
  createInvoiceFileObjectUrl,
  downloadInvoiceFile as downloadInvoiceFileApi,
} from '@/api/fileUpload'
import type { FileAttachmentItem } from '@/types/fileAttachment'

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
  },
  showInvoiceUploadAction: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits<{
  submitted: []
  approved: []
  rejected: []
  withdrawn: []
  resubmit: []
}>()

const store = useApprovalStore()
const { currentApprovalDetail } = storeToRefs(store)
const permissionStore = usePermissionStore()

// ===== 本地 UI 状态（必须 ref<Type>(...) 显式类型）=====
const loadError = ref<boolean>(false)
const notFound = ref<boolean>(false)
const actionPending = ref<boolean>(false)
const rejectDialogVisible = ref<boolean>(false)
const withdrawDialogVisible = ref<boolean>(false)
const rejectForm = ref<{ reason: string }>({ reason: '' })
const conflictNotice = ref<string>('')
const invoiceFilePreviewUrl = ref<string>('')
const invoiceFilePreviewLoading = ref<boolean>(false)
const invoiceFilePreviewRequestId = ref<number>(0)

// 开票对话框
const markIssuedDialogVisible = ref<boolean>(false)

// License 发放对话框
const issueLicenseDialogVisible = ref<boolean>(false)

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

// 发票是否已上传文件（用于显示下载链接）
const hasInvoiceFile = computed<boolean>(() =>
  props.entityType === 'INVOICE' &&
  detail.value?.invoice_file_path != null &&
  detail.value.invoice_file_path.length > 0
)

const invoiceFiles = computed<FileAttachmentItem[]>(() => {
  if (!hasInvoiceFile.value || detail.value == null) return []

  const file: FileAttachmentItem = {
    id: props.entityId,
    name: getInvoiceFileName(),
    extension: getFileExtension(detail.value.invoice_file_path ?? ''),
    status: invoiceFilePreviewLoading.value ? 'processing' : 'done'
  }

  if (invoiceFilePreviewUrl.value.length > 0) {
    file.url = invoiceFilePreviewUrl.value
  }

  if (detail.value.invoice_number != null && detail.value.invoice_number.trim() !== '') {
    file.description = `发票号码：${detail.value.invoice_number}`
  }

  return [file]
})

// 发票开票按钮显示条件
const showMarkIssued = computed<boolean>(() =>
  props.entityType === 'INVOICE' &&
  status.value === 'APPROVED' &&
  !hasInvoiceFile.value &&
  permissionStore.hasPermission('invoice:mark_issued')
)

// License 发放按钮显示条件
const showIssueLicense = computed<boolean>(() =>
  props.entityType === 'LICENSE' &&
  status.value === 'APPROVED' &&
  detail.value?.license_status !== 'ISSUED' &&
  permissionStore.hasPermission('license:issue')
)

// ===== 错误识别：仅匹配 axios 风格 error.response.status，不用 any =====
const isAxiosStatus = (err: unknown, code: number): boolean => {
  const r = (err as { response?: { status?: number } } | null)?.response
  return typeof r?.status === 'number' && r.status === code
}

const revokeInvoiceFilePreviewUrl = (): void => {
  if (invoiceFilePreviewUrl.value.length === 0) return
  window.URL.revokeObjectURL(invoiceFilePreviewUrl.value)
  invoiceFilePreviewUrl.value = ''
}

const loadInvoiceFilePreviewUrl = async (): Promise<void> => {
  const requestId = invoiceFilePreviewRequestId.value + 1
  invoiceFilePreviewRequestId.value = requestId
  revokeInvoiceFilePreviewUrl()

  if (!hasInvoiceFile.value || props.entityType !== 'INVOICE') {
    invoiceFilePreviewLoading.value = false
    return
  }

  invoiceFilePreviewLoading.value = true
  try {
    const objectUrl = await createInvoiceFileObjectUrl(props.entityId)
    if (requestId === invoiceFilePreviewRequestId.value && hasInvoiceFile.value) {
      invoiceFilePreviewUrl.value = objectUrl
    } else {
      window.URL.revokeObjectURL(objectUrl)
    }
  } catch {
    toast.error('发票文件预览加载失败')
  } finally {
    if (requestId === invoiceFilePreviewRequestId.value) {
      invoiceFilePreviewLoading.value = false
    }
  }
}

// ===== 方法（必须参数和返回类型）=====
const loadDetail = async (): Promise<void> => {
  loadError.value = false
  notFound.value = false
  conflictNotice.value = ''
  store.clearDetail()
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

// 发票文件下载 - 使用 invoice API 的下载接口
const downloadInvoiceFile = async (): Promise<void> => {
  if (detail.value == null || props.entityType !== 'INVOICE') return
  try {
    await downloadInvoiceFileApi(props.entityId)
  } catch {
    toast.error('文件下载失败')
  }
}

const getFileExtension = (filePath: string): string => {
  return filePath.toLowerCase().split('?')[0]?.split('.').pop() ?? ''
}

const getInvoiceFileName = (): string => {
  const extension = getFileExtension(detail.value?.invoice_file_path ?? '')
  return extension ? `发票文件.${extension}` : '发票文件'
}

// 打开对话框方法
const openMarkIssuedDialog = (): void => {
  markIssuedDialogVisible.value = true
}

const openIssueDialog = (): void => {
  issueLicenseDialogVisible.value = true
}

// 对话框成功回调
const onMarkIssuedSuccess = (): void => {
  markIssuedDialogVisible.value = false
  emit('approved')
  loadDetail()
}

const onIssueSuccess = (): void => {
  issueLicenseDialogVisible.value = false
  emit('approved')
  loadDetail()
}

// ===== 生命周期 =====
watch(
  [(): EntityType => props.entityType, (): number => props.entityId],
  (): void => {
    void loadDetail()
  },
  { immediate: true }
)

watch(
  [hasInvoiceFile, (): number => props.entityId],
  (): void => {
    void loadInvoiceFilePreviewUrl()
  },
  { immediate: true }
)

onBeforeUnmount((): void => {
  invoiceFilePreviewRequestId.value += 1
  revokeInvoiceFilePreviewUrl()
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
    <Empty
      v-else-if="detail === null && notFound"
      class="min-h-[200px] border-0"
    >
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <Loader2 class="h-5 w-5" aria-hidden="true" />
        </EmptyMedia>
        <EmptyTitle>尚未提交审批</EmptyTitle>
        <EmptyDescription>提交后审批人将收到待办通知</EmptyDescription>
      </EmptyHeader>
      <EmptyContent v-if="isSubmitter">
        <Button
          v-permission="submitPermissionCode"
          data-testid="submit-approval-btn"
          :disabled="actionPending"
          @click="handleSubmit"
        >
          <Loader2 v-if="actionPending" class="mr-2 h-4 w-4 animate-spin" />
          提交审批
        </Button>
      </EmptyContent>
    </Empty>

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
        <FileAttachment
          title="发票文件"
          mode="readonly"
          :files="invoiceFiles"
          empty-text="暂无发票文件"
          @download="() => downloadInvoiceFile()"
        />
      </div>

      <!-- 审批流程 Stepper -->
      <ApprovalProcessStepper
        v-if="records.length > 0"
        :records="records"
        :is-pending="isPending"
      />

      <!-- 操作区 -->
      <div class="approval-process-generic__actions">
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

        <!-- 发票开票区 -->
        <div v-if="showInvoiceUploadAction && showMarkIssued" class="mark-issued-section">
          <Button
            data-testid="mark-issued-btn"
            aria-label="上传发票文件，审批已通过"
            @click="openMarkIssuedDialog"
          >
            上传发票文件
          </Button>
        </div>

        <!-- License 发放区 -->
        <div v-if="showIssueLicense" class="issue-license-section">
          <p class="text-sm text-muted-foreground mb-2">审批已通过，可进行发放操作</p>
          <Button
            data-testid="issue-license-btn"
            aria-label="发放 License，审批已通过"
            @click="openIssueDialog"
          >
            发放 License
          </Button>
        </div>
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
              :disabled="!rejectForm.reason.trim() || actionPending || isLocked"
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

      <!-- 发票开票对话框 -->
      <InvoiceMarkIssuedDialog
        v-model:open="markIssuedDialogVisible"
        :application-id="entityId"
        @issued="onMarkIssuedSuccess"
      />

      <!-- License 发放对话框 -->
      <LicenseIssueDialog
        v-model:open="issueLicenseDialogVisible"
        :application-id="entityId"
        @issued="onIssueSuccess"
      />
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

.approval-process-generic__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: $wolf-space-sm-v2;
  margin-top: $wolf-space-lg-v2;
  padding-top: $wolf-space-md-v2;
  border-top: 1px solid $wolf-border-light-v2;
}

// 已上传文件显示区域样式
.approval-process-generic__file-section {
  background: $wolf-bg-hover-v2;
  border-radius: $wolf-radius-sm-v2;
  padding: $wolf-space-md-v2;
  margin-bottom: $wolf-space-md-v2;
}

// 开票/发放操作区
.mark-issued-section,
.issue-license-section {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: $wolf-space-sm-v2;
  padding-top: $wolf-space-md-v2;
  border-top: 1px solid $wolf-border-light-v2;
  margin-top: $wolf-space-md-v2;
}
</style>
