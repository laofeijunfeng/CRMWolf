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
 * 五态覆盖（C-DSG-4）：Loading(el-skeleton) / Empty(WolfEmpty 草稿态 CTA) /
 * Error(ErrorState 通用/forbidden) / Success(ElMessage) / Conflict(409 重载保输入)。
 *
 * C-DSG-7 P0 已落：
 *   条2 驳回弹窗 reason 必填 + el-form rule；同意 comment 可空（直接按钮）。
 *   条3 按钮 action pending 期间 :loading + :disabled，防双击。
 *   条8 乐观锁冲突→保留 rejectForm.reason→warning toast→重载 detail；
 *       重载后非 PENDING→禁用提交并提示「该审批已由他人处理，无需重复操作」。
 *
 * 响应式（C-DSG-6）：宽屏（≥1024px）水平 timeline，窄屏自动切垂直。matchMedia
 * 不可用时（如 jsdom）回退到水平（isWide=true），不影响功能。
 */
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { PropType } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Promotion,
  CircleCheckFilled,
  CircleCloseFilled,
  RefreshLeft
} from '@element-plus/icons-vue'
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

interface RecordVisual {
  icon: typeof Promotion
  actionLabel: string
  textVar: string
}

const RECORD_VISUAL: Record<
  'SUBMIT' | 'APPROVE' | 'REJECT' | 'ROLLBACK' | 'CANCEL',
  RecordVisual
> = {
  SUBMIT: { icon: Promotion, actionLabel: '提交', textVar: '--wolf-approval-pending-text' },
  APPROVE: { icon: CircleCheckFilled, actionLabel: '同意', textVar: '--wolf-approval-approved-text' },
  REJECT: { icon: CircleCloseFilled, actionLabel: '驳回', textVar: '--wolf-approval-rejected-text' },
  ROLLBACK: { icon: RefreshLeft, actionLabel: '撤回', textVar: '--wolf-approval-cancelled-text' },
  CANCEL: { icon: RefreshLeft, actionLabel: '撤回', textVar: '--wolf-approval-cancelled-text' }
}

const SUBMIT_PERMISSION: Record<EntityType, string> = {
  CONTRACT: 'contract:submit',
  PAYMENT: 'payment:submit',
  INVOICE: 'invoice:submit'
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
}>()

const store = useApprovalStore()
const { currentApprovalDetail } = storeToRefs(store)

// ===== 本地 UI 状态（必须 ref<Type>(...) 显式类型）=====
const loadError = ref<boolean>(false)
const notFound = ref<boolean>(false)
const actionPending = ref<boolean>(false)
const rejectDialogVisible = ref<boolean>(false)
const rejectForm = ref<{ reason: string }>({ reason: '' })
const isWide = ref<boolean>(true)
const conflictNotice = ref<string>('')

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

const rejectFormRule = computed<{ required: boolean; message: string; trigger: string }[]>(
  () => [{ required: true, message: '请填写驳回理由，提交人将据此修改', trigger: 'blur' }]
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
    ElMessage.success('已提交审批，等待审批人处理')
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
    ElMessage.success('已同意')
    emit('approved')
  } catch (err) {
    if (isAxiosStatus(err, 409)) {
      ElMessage.warning('该审批已被其他人处理，已为你刷新最新状态')
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
  // 同步必填守卫（条2）：el-form rule 仅做视觉提示，action 入口必须先校验
  if (!rejectForm.value.reason.trim()) {
    ElMessage.warning('请填写驳回理由，提交人将据此修改')
    return
  }
  if (detail.value == null) return
  actionPending.value = true
  try {
    await store.approveEntity(
      props.entityType, props.entityId, 'REJECT',
      rejectForm.value.reason, detail.value.updated_time
    )
    ElMessage.success('已驳回，申请人可修改后重新提交')
    rejectDialogVisible.value = false
    rejectForm.value.reason = ''
    emit('rejected')
  } catch (err) {
    if (isAxiosStatus(err, 409)) {
      // C-DSG-7 条8：不清空 reason、不关弹窗、提示并重载
      ElMessage.warning('该审批已被他人处理，你的填写已保留')
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

const handleWithdraw = async (): Promise<void> => {
  if (actionPending.value || isLocked.value || !isPending.value) return
  try {
    await ElMessageBox.confirm(
      '撤回后审批中止，需重新提交。确定撤回？',
      '撤回审批',
      { type: 'warning' }
    )
  } catch {
    // 用户取消，不做任何事
    return
  }
  actionPending.value = true
  try {
    await store.cancelEntity(props.entityType, props.entityId)
    ElMessage.success('已撤回')
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
    <el-skeleton v-if="loadError === false && notFound === false && detail === null" :rows="3" animated />

    <!-- 错误态（C-DSG-4 Error） -->
    <ErrorState
      v-else-if="loadError && !notFound"
      title="审批信息加载失败"
      description="可点击下方按钮重新加载，若持续失败请联系管理员"
    >
      <template #action>
        <el-button data-testid="reload-detail-btn" type="primary" @click="loadDetail">
          重新加载
        </el-button>
      </template>
    </ErrorState>

    <!-- 草稿空态（detail===null 且 404）：提交 CTA -->
    <WolfEmpty
      v-else-if="detail === null && notFound"
      title="尚未提交审批"
      description="提交后审批人将收到待办通知"
    >
      <template v-if="isSubmitter" #action>
        <el-button
          v-permission="submitPermissionCode"
          data-testid="submit-approval-btn"
          type="primary"
          :loading="actionPending"
          :disabled="actionPending"
          @click="handleSubmit"
        >
          提交审批
        </el-button>
      </template>
    </WolfEmpty>

    <!-- 详情态：PENDING / APPROVED / REJECTED / CANCELLED -->
    <div v-else class="approval-process-generic__body">
      <!-- 标题 + 状态徽章 -->
      <div class="approval-process-generic__header">
        <span class="approval-process-generic__title">{{ detail?.flow_name ?? '审批进度' }}</span>
        <ApprovalStatusBadge v-if="status" :status="status" size="small" />
      </div>

      <!-- 冲突锁定提示（C-DSG-7 条8：重载后已由他人终结） -->
      <div v-if="isLocked" class="approval-process-generic__conflict" role="alert">
        <el-icon><CircleCloseFilled /></el-icon>
        <span>{{ conflictNotice }}</span>
      </div>

      <!-- 当前节点意见 -->
      <div v-if="detail?.current_node_name" class="approval-process-generic__current-node">
        <span class="approval-process-generic__current-node-label">当前节点：</span>
        <span class="approval-process-generic__current-node-value">{{ detail.current_node_name }}</span>
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
          <el-icon class="approval-process-generic__timeline-icon" :size="18">
            <component :is="RECORD_VISUAL[record.action ?? 'ROLLBACK'].icon" />
          </el-icon>
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
        <el-button
          v-if="isSubmitter && isPending"
          data-testid="withdraw-btn"
          :loading="actionPending"
          :disabled="actionPending || isLocked"
          @click="handleWithdraw"
        >
          撤回审批
        </el-button>
        <el-button
          v-if="isSubmitter && isRejected"
          data-testid="resubmit-btn"
          type="primary"
          :loading="actionPending"
          :disabled="actionPending || isLocked"
          @click="handleResubmit"
        >
          修改并重新提交
        </el-button>
        <el-button
          v-if="canApprove && isPending"
          data-testid="approve-btn"
          type="primary"
          :loading="actionPending"
          :disabled="actionPending || isLocked"
          @click="handleApprove"
        >
          同意
        </el-button>
        <el-button
          v-if="canApprove && isPending"
          data-testid="reject-btn"
          type="danger"
          :loading="actionPending"
          :disabled="actionPending || isLocked"
          @click="openRejectDialog"
        >
          驳回
        </el-button>
      </div>

      <!-- 驳回弹窗：reason 必填 + el-form rule，C-DSG-7 条2 -->
      <el-dialog
        v-model="rejectDialogVisible"
        data-testid="reject-dialog"
        title="驳回审批"
        width="480px"
        :close-on-click-modal="false"
      >
        <el-form ref="rejectFormRef" :model="rejectForm" :rules="rejectFormRule" label-position="top">
          <el-form-item label="驳回理由" prop="reason" required>
            <el-input
              v-model="rejectForm.reason"
              data-testid="reject-reason"
              type="textarea"
              :rows="4"
              placeholder="请填写驳回理由，提交人将据此修改"
              maxlength="500"
              show-word-limit
            />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button
            data-testid="reject-cancel-btn"
            :disabled="actionPending"
            @click="rejectDialogVisible = false"
          >
            取消
          </el-button>
          <el-button
            data-testid="reject-confirm-btn"
            type="primary"
            :loading="actionPending"
            :disabled="actionPending || isLocked"
            @click="confirmReject"
          >
            确定
          </el-button>
        </template>
      </el-dialog>
    </div>
  </div>
</template>

<style scoped lang="scss">
@import '@/styles/variables.scss';

.approval-process-generic {
  width: 100%;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-card-padding;
}

.approval-process-generic__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $wolf-space-sm;
  margin-bottom: $wolf-space-md;
}

.approval-process-generic__title {
  font-family: $wolf-font-display;
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
}

.approval-process-generic__conflict {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  padding: $wolf-space-sm $wolf-space-md;
  background: var(--wolf-approval-rejected-bg, $wolf-approval-rejected-bg);
  color: var(--wolf-approval-rejected-text, $wolf-approval-rejected-text);
  border-radius: $wolf-radius-sm;
  font-size: $wolf-font-size-auxiliary;
  margin-bottom: $wolf-space-md;
}

.approval-process-generic__current-node {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
  margin-bottom: $wolf-space-md;
  font-size: $wolf-font-size-auxiliary;
  color: $wolf-text-tertiary;

  .approval-process-generic__current-node-value {
    color: $wolf-text-secondary;
    font-weight: $wolf-font-weight-medium;
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
    gap: $wolf-space-md;
    flex-wrap: wrap;
  }

  // 默认（窄屏）垂直
  &:not(.is-wide) {
    display: flex;
    flex-direction: column;
    gap: $wolf-space-md;
  }
}

.approval-process-generic__timeline-item {
  display: flex;
  align-items: flex-start;
  gap: $wolf-space-sm;

  .is-wide & {
    flex: 1 1 200px;
    flex-direction: column;
    align-items: center;
    text-align: center;
  }
}

.approval-process-generic__timeline-icon {
  flex-shrink: 0;
}

.approval-process-generic__timeline-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: $wolf-font-size-auxiliary;
  line-height: $wolf-line-height-body;
}

.approval-process-generic__timeline-action {
  font-weight: $wolf-font-weight-medium;
  color: inherit;
}

.approval-process-generic__timeline-user {
  color: $wolf-text-secondary;
}

.approval-process-generic__timeline-time {
  color: $wolf-text-placeholder;
  font-family: $wolf-font-mono;
  font-size: $wolf-font-size-caption;
}

.approval-process-generic__timeline-comment {
  color: $wolf-text-secondary;
  margin-top: $wolf-space-xs;
}

.approval-process-generic__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: $wolf-button-gap;
  margin-top: $wolf-space-lg;
  padding-top: $wolf-space-md;
  border-top: 1px solid $wolf-border-light;
}
</style>