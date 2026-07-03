<!--
  ApprovalNotificationCenter — 应用内审批通知铃铛（Phase C Task C4）

  目的：让「不盯飞书」的审批人在 CRM 顶栏直接发现待我审批单据。

  组成：
  - 顶栏铃铛 `el-badge`（value = pendingCount 来自 store.fetchList tab=pending）
  - `el-dropdown` 下拉：列最近 N 条待我审批，超时项（overdue_hours >= 48）高亮
    （nc-overdue 类引用 $wolf-warning token）
  - 点击下拉项直跳 FinanceApprovalCenter（/finance/approvals）

  数据源：复用 listApprovals（C1）→ store.fetchList({ tab:'pending', page:1,
  page_size:N })。后端响应含 pending_count，同步落入 store.pendingCount
  （与 C3 侧边栏徽章同源；顶栏铃铛 + 侧边栏菜单徽章共存，不冲突）。

  E10 轮询优化（避免 N 在线审批人持续打后端）：
  - setTimeout 递归调度（非 setInterval，便于退避 + 暂停清理）
  - 监听 document.visibilitychange：后台 tab（document.hidden）暂停轮询；
    前台恢复时立即拉一次并重新调度
  - 请求失败指数退避：60s → 120s → 240s → 480s 截到 maxBackoffMs(300s)；
    成功后重置回 pollIntervalMs(60s)
  - onUnmounted 清理 timer + 移除监听（避免泄漏）

  可见性门控：v-any-permission="['invoice:approve','payment:approve']"——
  无任一审批权限时不渲染铃铛。
-->
<template>
  <div class="approval-notification-center">
    <div
      v-any-permission="['invoice:approve', 'payment:approve']"
      data-testid="approval-bell"
    >
      <el-dropdown
        trigger="click"
        placement="bottom-end"
        @command="handleItemClick"
        @visible-change="handleDropdownVisible"
      >
        <el-badge
          :value="displayCount"
          :hidden="displayCount === 0"
          :max="99"
          type="danger"
          data-testid="approval-bell-badge"
        >
          <el-icon class="bell-icon"><Bell /></el-icon>
        </el-badge>
        <template #dropdown>
          <el-dropdown-menu class="nc-dropdown">
            <div class="nc-header">待我审批</div>
            <div v-if="loading" class="nc-loading" data-testid="approval-bell-loading">
              加载中…
            </div>
            <div v-else-if="items.length === 0" class="nc-empty" data-testid="approval-bell-empty">
              暂无待我审批
            </div>
            <template v-else>
              <el-dropdown-item
                v-for="item in items"
                :key="item.id"
                :command="item"
                :class="{ 'nc-overdue': isOverdue(item) }"
                :data-testid="`approval-bell-item-${item.id}`"
              >
                <div class="nc-item">
                  <div class="nc-item-top">
                    <span class="nc-item-type">{{ businessTypeLabel(item.business_type) }}</span>
                    <span class="nc-item-no">{{ item.application_number }}</span>
                  </div>
                  <div class="nc-item-bottom">
                    <span class="nc-item-name">{{ item.entity_name || '—' }}</span>
                    <span v-if="isOverdue(item)" class="nc-item-overdue">
                      超时 {{ Math.round(item.overdue_hours ?? 0) }}h
                    </span>
                  </div>
                </div>
              </el-dropdown-item>
              <el-dropdown-item divided :command="GOTO_CENTER" data-testid="approval-bell-goto">
                <span class="nc-goto">查看全部 →</span>
              </el-dropdown-item>
            </template>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { Bell } from '@element-plus/icons-vue'
import { useApprovalStore } from '@/stores/approval'
import type { ApprovalListItem, EntityType } from '@/schemas/approvalGeneric'
import { logger } from '@/utils/logger'

interface Props {
  /** 基础轮询间隔（ms），默认 60s */
  pollIntervalMs?: number
  /** 退避上限（ms），默认 300s（5min） */
  maxBackoffMs?: number
  /** 下拉列表拉取条数（page_size），默认 8 */
  listLimit?: number
}

const props = withDefaults(defineProps<Props>(), {
  pollIntervalMs: 60_000,
  maxBackoffMs: 300_000,
  listLimit: 8
})

const OVERDUE_THRESHOLD_HOURS = 48

// 「查看全部」占位 command（与 ApprovalListItem 区分）
const GOTO_CENTER = '__goto_center__' as const

const router = useRouter()
const store = useApprovalStore()
const { pendingCount } = storeToRefs(store)

const items = ref<ApprovalListItem[]>([])
const loading = ref<boolean>(false)

// 当前退避间隔（成功后重置回 pollIntervalMs）
const currentDelay = ref<number>(props.pollIntervalMs)
let timerId: number | null = null

const displayCount = computed<number>(() => pendingCount.value)

const businessTypeLabel = (t: EntityType): string => {
  const map: Record<EntityType, string> = {
    PAYMENT: '回款',
    INVOICE: '发票',
    CONTRACT: '合同'
  }
  return map[t] ?? t
}

const isOverdue = (item: ApprovalListItem): boolean =>
  (item.overdue_hours ?? 0) >= OVERDUE_THRESHOLD_HOURS

const clearTimer = (): void => {
  if (timerId !== null) {
    window.clearTimeout(timerId)
    timerId = null
  }
}

const scheduleNext = (): void => {
  clearTimer()
  // 后台 tab 不调度（由 visibilitychange 恢复时重启）
  if (typeof document !== 'undefined' && document.hidden) return
  timerId = window.setTimeout(() => {
    void doFetch()
  }, currentDelay.value)
}

/**
 * 拉取待我审批列表（tab=pending）。成功后更新 items + 重置退避；
 * 失败后指数退避（封顶 maxBackoffMs）。无论成败，finally 重新调度下一轮。
 */
const doFetch = async (): Promise<void> => {
  // 后台 tab 跳过本次请求（由 visibilitychange 恢复时立即拉）
  if (typeof document !== 'undefined' && document.hidden) return
  loading.value = true
  try {
    const res = await store.fetchList({
      tab: 'pending',
      page: 1,
      page_size: props.listLimit
    })
    items.value = res.items
    currentDelay.value = props.pollIntervalMs
  } catch (err) {
    // 指数退避：失败翻倍，封顶 maxBackoffMs
    currentDelay.value = Math.min(currentDelay.value * 2, props.maxBackoffMs)
    logger.warn('[ApprovalNotificationCenter]', '拉取待审批列表失败，已退避', {
      nextDelayMs: currentDelay.value,
      error: err
    })
  } finally {
    loading.value = false
    scheduleNext()
  }
}

const handleItemClick = (command: ApprovalListItem | typeof GOTO_CENTER): void => {
  if (command === GOTO_CENTER) {
    void router.push({ path: '/finance/approvals' })
    return
  }
  const item = command as ApprovalListItem
  // FinanceApprovalCenter 默认打开 pending tab；带 query 便于中心后续支持
  // 自动展开抽屉（当前中心未消费 query，故仅跳转，符合 brief「至少跳到中心」）
  void router.push({
    path: '/finance/approvals',
    query: {
      detail: `${item.business_type}:${item.business_id}`
    }
  })
}

// 下拉打开时立即刷新一次（用户主动展开 → 给最新数据）
const handleDropdownVisible = (visible: boolean): void => {
  if (visible) void doFetch()
}

const onVisibilityChange = (): void => {
  if (typeof document === 'undefined') return
  if (document.hidden) {
    // 后台暂停：清掉已调度的定时器（已 in-flight 的请求不取消）
    clearTimer()
  } else {
    // 前台恢复：立即拉一次 → 成功/失败后重新调度
    void doFetch()
  }
}

onMounted(() => {
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisibilityChange)
  }
  // 挂载即拉一次，随后递归调度
  void doFetch()
})

onUnmounted(() => {
  clearTimer()
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', onVisibilityChange)
  }
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.approval-notification-center {
  display: inline-flex;
  align-items: center;
  cursor: pointer;
}

.bell-icon {
  font-size: 20px;
  color: $wolf-text-secondary;
  transition: color 0.15s ease;
}

.approval-notification-center:hover .bell-icon {
  color: $wolf-primary;
}

.nc-dropdown {
  min-width: 280px;
  max-width: 320px;
}

.nc-header {
  padding: $wolf-space-sm $wolf-space-md;
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-tertiary;
  border-bottom: 1px solid $wolf-border-default;
}

.nc-loading,
.nc-empty {
  padding: $wolf-space-lg $wolf-space-md;
  text-align: center;
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.nc-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
}

.nc-item-top {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
}

.nc-item-type {
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-tertiary;
}

.nc-item-no {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-secondary;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.nc-item-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $wolf-space-sm;
}

.nc-item-name {
  font-size: $wolf-font-size-body;
  color: $wolf-text-primary;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

// 超时高亮：引用 $wolf-warning token（颜色非唯一指示，附「超时 Nh」文字）
.nc-overdue {
  :deep(.nc-item-name) {
    color: $wolf-warning-text;
    font-weight: $wolf-font-weight-semibold;
  }

  .nc-item-overdue {
    font-size: $wolf-font-size-caption;
    color: $wolf-warning-text;
    flex-shrink: 0;
  }
}

.nc-goto {
  width: 100%;
  text-align: center;
  font-size: $wolf-font-size-caption;
  color: $wolf-primary;
}
</style>