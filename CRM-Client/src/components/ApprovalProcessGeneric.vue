/**
 * ApprovalProcessGeneric — 通用审批操作组件
 *
 * 嵌入业务详情页的审批区。Props：
 *   entityType : 'CONTRACT' | 'PAYMENT' | 'INVOICE' | 'INVOICE_REISSUE' | 'LICENSE' | 'OPPORTUNITY'
 *   entityId   : number | string（OPPORTUNITY 使用 opp_ public_id）
 *   canApprove : 是否对当前节点具备审批权（控制同意/驳回按钮显隐）
 *   isSubmitter: 是否为提交人（控制撤回 + 草稿态"提交审批"CTA 显隐）
 *
 * 只承载审批状态、审批记录和审批动作。业务附件、开票、重开发票完成、
 * License 发放等动作由对应业务页面或审批中心 footer 承载。
 */
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { PropType } from 'vue'
import { toast } from 'vue-sonner'
import {
  Loader2,
  AlertTriangle
} from 'lucide-vue-next'
import { useApprovalStore } from '@/stores/approval'
import { handleApiError } from '@/utils/errorHandler'
import type {
  EntityType,
  ApprovalDetail,
  ApprovalRecord
} from '@/schemas/approvalGeneric'
import type { ApprovalEntityId } from '@/api/approvalGeneric'
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

const SUBMIT_PERMISSIONS: Record<EntityType, string[]> = {
  CONTRACT: ['contract:submit'],
  PAYMENT: ['payment:submit'],
  INVOICE: ['invoice:submit'],
  INVOICE_REISSUE: ['invoice_reissue:submit'],
  LICENSE: ['license:submit'],
  OPPORTUNITY: ['opportunity:create', 'opportunity:edit:own', 'opportunity:edit:all']
}

const props = defineProps({
  entityType: {
    type: String as PropType<EntityType>,
    required: true
  },
  entityId: {
    type: [Number, String] as PropType<ApprovalEntityId>,
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
  title: {
    type: String,
    default: ''
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

// ===== 本地 UI 状态（必须 ref<Type>(...) 显式类型）=====
const detail = ref<ApprovalDetail | null>(null)
const loadError = ref<boolean>(false)
const notFound = ref<boolean>(false)
const actionPending = ref<boolean>(false)
const rejectDialogVisible = ref<boolean>(false)
const withdrawDialogVisible = ref<boolean>(false)
const rejectForm = ref<{ reason: string }>({ reason: '' })
const conflictNotice = ref<string>('')
const detailRequestId = ref<number>(0)

// ===== 计算属性（必须返回类型）=====
const status = computed<ApprovalDetail['status'] | undefined>(() => detail.value?.status)
const isPending = computed<boolean>(() => status.value === 'PENDING')
// C-DSG-7 条4：REJECTED/CANCELLED 态提交人可见重新提交 CTA（抽屉侧入口）
const isRejected = computed<boolean>(() => status.value === 'REJECTED')
const isCancelled = computed<boolean>(() => status.value === 'CANCELLED')
const canResubmit = computed<boolean>(() => isRejected.value || isCancelled.value)
// 冲突重载后启用提交
const isLocked = computed<boolean>(() => conflictNotice.value.length > 0)

const records = computed<ApprovalRecord[]>(() => detail.value?.records ?? [])

const submitPermissionCodes = computed<string[]>(() => SUBMIT_PERMISSIONS[props.entityType])
const approvalTitle = computed<string>(() =>
  props.title.trim().length > 0 ? props.title.trim() : detail.value?.flow_name ?? '审批进度'
)

// ===== 错误识别：仅匹配 axios 风格 error.response.status，不用 any =====
const isAxiosStatus = (err: unknown, code: number): boolean => {
  const r = (err as { response?: { status?: number } } | null)?.response
  return typeof r?.status === 'number' && r.status === code
}

// ===== 方法（必须参数和返回类型）=====
const loadDetail = async (): Promise<void> => {
  const requestId = detailRequestId.value + 1
  detailRequestId.value = requestId

  loadError.value = false
  notFound.value = false
  conflictNotice.value = ''
  detail.value = null
  try {
    const loadedDetail = await store.fetchDetail(props.entityType, props.entityId)
    if (requestId === detailRequestId.value) {
      detail.value = loadedDetail
    }
  } catch (err) {
    if (requestId !== detailRequestId.value) return
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
  } catch (error: unknown) {
    handleApiError(error, '提交审批')
  } finally {
    actionPending.value = false
  }
}

const handleApprove = async (): Promise<void> => {
  if (actionPending.value || isLocked.value || !isPending.value) return
  if (detail.value == null) return
  actionPending.value = true
  try {
    const updatedDetail = await store.approveEntity(
      props.entityType, props.entityId, 'APPROVE', '', detail.value.updated_time
    )
    detail.value = updatedDetail
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
    const updatedDetail = await store.approveEntity(
      props.entityType, props.entityId, 'REJECT',
      rejectForm.value.reason, detail.value.updated_time
    )
    detail.value = updatedDetail
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
    detail.value = null
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

// C-DSG-7 条4：REJECTED/CANCELLED 态提交人重新提交 CTA（抽屉侧入口）
// 组件本身不导航（COMPONENTS.md「组件禁直接调 API/禁导航」），仅 emit resubmit
// 由父视图（FinanceApprovalCenter）据 currentRow 走 router.push 跳对应编辑页。
const handleResubmit = (): void => {
  if (actionPending.value || isLocked.value || !isRejected.value) return
  if (!props.isSubmitter) return
  emit('resubmit')
}

const handleResubmitAction = (): void => {
  if (!props.isSubmitter || actionPending.value || isLocked.value || !canResubmit.value) return
  if (isCancelled.value) {
    void handleSubmit()
    return
  }
  handleResubmit()
}

// ===== 生命周期 =====
watch(
  [(): EntityType => props.entityType, (): ApprovalEntityId => props.entityId],
  (): void => {
    void loadDetail()
  },
  { immediate: true }
)
</script>

<template>
  <div class="approval-process-generic">
    <!-- 加载骨架（C-DSG-4 Loading） -->
    <div v-if="loadError === false && notFound === false && detail === null" class="space-y-2">
      <Skeleton class="h-8 w-full" />
      <Skeleton class="h-20 w-full" />
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
      class="min-h-[112px] border-0 py-3"
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
          v-any-permission="submitPermissionCodes"
          size="sm"
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
        <span class="approval-process-generic__title">{{ approvalTitle }}</span>
        <ApprovalStatusBadge v-if="status" :status="status" size="small" />
      </div>

      <!-- 冲突锁定提示（C-DSG-7 条8：重载后已由他人终结） -->
      <div v-if="isLocked" class="approval-process-generic__conflict" role="alert">
        <AlertTriangle class="h-4 w-4" />
        <span>{{ conflictNotice }}</span>
      </div>

      <!-- 当前节点意见 -->
      <div v-if="detail?.current_node_name && records.length === 0" class="approval-process-generic__current-node">
        <span class="approval-process-generic__current-node-label">当前节点：</span>
        <span class="approval-process-generic__current-node-value">{{ detail.current_node_name }}</span>
      </div>

      <!-- 审批流程 Stepper -->
      <ApprovalProcessStepper
        v-if="records.length > 0"
        :records="records"
        :is-pending="isPending"
        :current-node-name="detail.current_node_name ?? ''"
      />

      <!-- 操作区 -->
      <div class="approval-process-generic__actions">
        <Button
          v-if="isSubmitter && isPending"
          variant="outline"
          size="sm"
          data-testid="withdraw-btn"
          :disabled="actionPending || isLocked"
          @click="openWithdrawDialog"
        >
          <Loader2 v-if="actionPending" class="mr-2 h-4 w-4 animate-spin" />
          撤回审批
        </Button>
        <Button
          v-if="isSubmitter && canResubmit"
          size="sm"
          data-testid="resubmit-btn"
          :disabled="actionPending || isLocked"
          @click="handleResubmitAction"
        >
          <Loader2 v-if="actionPending" class="mr-2 h-4 w-4 animate-spin" />
          {{ isCancelled ? '重新提交审批' : '修改并重新提交' }}
        </Button>
        <Button
          v-if="canApprove && isPending"
          size="sm"
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
          size="sm"
          data-testid="reject-btn"
          :disabled="actionPending || isLocked"
          @click="openRejectDialog"
        >
          <Loader2 v-if="actionPending" class="mr-2 h-4 w-4 animate-spin" />
          驳回
        </Button>

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
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.approval-process-generic {
  width: 100%;
  background: transparent;
  border-radius: $wolf-radius-v2;
  padding: 0;
}

.approval-process-generic__body {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm-v2;
}

.approval-process-generic__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $wolf-space-sm-v2;
  margin-bottom: 0;
}

.approval-process-generic__title {
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
  line-height: $wolf-line-height-body-v2;
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
}

.approval-process-generic__current-node {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
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
  margin-top: $wolf-space-xs-v2;
  padding-top: $wolf-space-sm-v2;
  border-top: 1px solid $wolf-border-light-v2;
}

</style>
