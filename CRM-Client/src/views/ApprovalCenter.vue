<!--
  FinanceApprovalCenter — 财务审批中心（Phase C Task C3）

  取代自写按钮的 FinanceInvoiceApprovals / FinancePaymentConfirmations（本期加
  deprecation 注释指向本组件，不删文件以免破坏既有 import）。

  C-DSG-5 线框：3 tab（待我审批 / 我已处理 / 我提交的，权限驱动）+ 类型筛选
  （business_type）+ 表格 + 右侧 el-drawer 内嵌 ApprovalProcessGeneric。

  C-DSG-7 落本组件部分：
    条4 「我提交的」tab 对 REJECTED 行显示「修改并重新提交」（update→DRAFT→submit）
    条5 超时徽章列（overdue_hours>=48）+ 待我审批按 overdue_hours 降序
    条7 抽屉信息层级固化：①el-descriptions 决策字段置顶 ②timeline ③操作吸底
    条9 键盘 J/K 上下行、A 同意、R 驳回、Enter 开抽屉、Esc 关抽屉
    条11 移动端操作区 sticky 吸底 + 安全区 padding
    条13 抽屉关闭 @closed 焦点回到触发行
    条14 单号 mono 字体 + 点击复制

  E2 越权过滤：列表查询严格按 tab 角色过滤参数传后端（submitted=pending=
  processed；team_id 由后端依赖注入携带）。前端不伪造过滤。
  E9 N+1：列表只调 1 次 listApprovals；详情走单点 getApprovalDetail；不逐行查询。
-->
<template>
  <div class="finance-approval-center" v-loading="loading">
    <!-- 标题 + 全局 ErrorState（403 forbidden / 加载失败） -->
    <ErrorState
      v-if="loadError === 'forbidden'"
      variant="forbidden"
      title="你没有该审批中心的访问权限"
    >
      <template #action>
        <el-button data-testid="reload-list-btn" @click="reload">重新加载</el-button>
      </template>
    </ErrorState>
    <ErrorState
      v-else-if="loadError === 'error'"
      title="审批列表加载失败"
      description="可点击下方按钮重新加载，若持续失败请联系管理员"
    >
      <template #action>
        <el-button data-testid="reload-list-btn" type="primary" @click="reload">重新加载</el-button>
      </template>
    </ErrorState>

    <template v-else>
      <!-- 三 tab（权限驱动，徽章显示待办数） -->
      <div class="tabs-card">
        <el-tabs v-model="activeTab" @tab-change="handleTabChange">
          <el-tab-pane name="pending">
            <template #label>
              <span data-testid="tab-pending">待我审批</span>
              <el-badge
                v-if="pendingCount > 0"
                :value="pendingCount"
                class="tab-badge"
                type="primary"
              />
            </template>
          </el-tab-pane>
          <el-tab-pane name="processed">
            <template #label>
              <span data-testid="tab-processed">我已处理</span>
            </template>
          </el-tab-pane>
          <el-tab-pane name="submitted">
            <template #label>
              <span data-testid="tab-submitted">我提交的</span>
            </template>
          </el-tab-pane>
        </el-tabs>
      </div>

      <!-- 筛选区 -->
      <div class="filter-card">
        <el-form :model="filterForm" :inline="true">
          <el-form-item label="单据类型">
            <el-select
              v-model="filterForm.business_type"
              placeholder="全部类型"
              clearable
              style="width: 160px"
              @change="handleFilterChange"
            >
              <el-option label="回款" value="PAYMENT" />
              <el-option label="发票" value="INVOICE" />
              <el-option label="合同" value="CONTRACT" />
              <el-option label="License" value="LICENSE" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button @click="resetFilter">重置</el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- 表格（桌面端） -->
      <div class="table-card" v-if="!isMobile">
        <div class="card-header">
          <div class="card-title-group">
            <span class="card-title">审批列表</span>
          </div>
        </div>

        <el-table
          v-if="rows.length > 0"
          :data="rows"
          row-key="id"
          stripe
          style="width: 100%"
          row-class-name="approval-row"
        >
          <el-table-column label="单号" min-width="180">
            <template #default="{ row }">
              <span
                class="number-cell"
                data-testid="copy-number"
                :title="`点击复制 ${row.application_number}`"
                @click="copyNumber(row.application_number)"
              >{{ row.application_number }}</span>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="90">
            <template #default="{ row }">
              <span class="type-tag">{{ businessTypeLabel(row.business_type) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="实体" min-width="160">
            <template #default="{ row }">
              <span>{{ row.entity_name || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="金额" min-width="130">
            <template #default="{ row }">
              <span class="amount">{{ formatCurrency(row.entity_amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="submitter_name" label="提交人" min-width="110" />
          <el-table-column label="提交时间" min-width="150">
            <template #default="{ row }">
              <span class="mono-time">{{ formatDateRelative(row.created_time) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <ApprovalStatusBadge :status="row.status" size="small" />
            </template>
          </el-table-column>
          <el-table-column label="超时" width="130">
            <template #default="{ row }">
              <span
                v-if="row.overdue_hours != null && row.overdue_hours >= 48"
                class="overdue-badge"
                role="status"
                :aria-label="`超时 ${row.overdue_hours} 小时`"
              >
                <el-icon :size="12"><Clock /></el-icon>
                超时 {{ row.overdue_hours }} 小时
              </span>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row, $index }">
              <el-button
                link
                type="primary"
                size="small"
                data-testid="detail-btn"
                @click="openDetail(row, $index)"
              >详情</el-button>
              <el-button
                v-if="activeTab === 'submitted' && row.status === 'REJECTED'"
                link
                type="primary"
                size="small"
                data-testid="resubmit-btn"
                :loading="resubmitPendingId === row.id"
                @click="handleResubmit(row)"
              >修改并重新提交</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 空态 -->
        <WolfEmpty
          v-else
          title="暂无待审批事项"
          description="所有回款与发票申请都已处理完毕"
        />

        <!-- 分页 -->
        <div v-if="rows.length > 0" class="pagination-bar">
          <span class="total-text">共 {{ total }} 条</span>
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="total"
            :page-sizes="[10, 20, 50, 100]"
            layout="sizes, prev, pager, next, jumper"
            @current-change="fetchList"
            @size-change="fetchList"
          />
        </div>
      </div>

      <!-- 移动端卡片列表 -->
      <div class="mobile-card-list" v-else>
        <div v-if="rows.length > 0">
          <div
            v-for="(row, $index) in rows"
            :key="row.id"
            class="approval-card"
            :class="{ 'has-overdue': row.overdue_hours != null && row.overdue_hours >= 48 }"
          >
            <!-- 卡片头部：单号 + 状态徽章 -->
            <div class="card-header-row">
              <span
                class="number-cell mobile"
                data-testid="copy-number-mobile"
                @click="copyNumber(row.application_number)"
              >{{ row.application_number }}</span>
              <ApprovalStatusBadge :status="row.status" size="small" />
            </div>

            <!-- 卡片主体：客户 + 金额 -->
            <div class="card-body-row">
              <span class="entity-name">{{ row.entity_name || '-' }}</span>
              <span class="amount mobile">{{ formatCurrency(row.entity_amount) }}</span>
            </div>

            <!-- 卡片次要信息：提交人 + 时间 -->
            <div class="card-meta-row">
              <span class="submitter">{{ row.submitter_name }} 提交</span>
              <span class="time">{{ formatDateRelative(row.created_time) }}</span>
            </div>

            <!-- 超时提示（如有） -->
            <div
              v-if="row.overdue_hours != null && row.overdue_hours >= 48"
              class="card-overdue-row"
            >
              <span class="overdue-badge mobile" role="status" :aria-label="`超时 ${row.overdue_hours} 小时`">
                <el-icon :size="12"><Clock /></el-icon>
                超时 {{ row.overdue_hours }} 小时
              </span>
            </div>

            <!-- 分割线 -->
            <div class="card-divider"></div>

            <!-- 操作按钮：同意 / 驳回 / 详情（全宽） -->
            <div class="card-actions-row" v-if="activeTab === 'pending'">
              <el-button
                type="primary"
                size="default"
                data-testid="mobile-approve-btn"
                @click="handleQuickApprove(row)"
              >同意</el-button>
              <el-button
                type="danger"
                size="default"
                data-testid="mobile-reject-btn"
                @click="handleQuickReject(row)"
              >驳回</el-button>
              <el-button
                type="default"
                size="default"
                data-testid="mobile-detail-btn"
                @click="openDetail(row, $index)"
              >详情</el-button>
            </div>
            <div class="card-actions-row" v-else-if="activeTab === 'submitted' && row.status === 'REJECTED'">
              <el-button
                type="primary"
                size="default"
                data-testid="mobile-resubmit-btn"
                :loading="resubmitPendingId === row.id"
                @click="handleResubmit(row)"
              >修改并重新提交</el-button>
            </div>
            <div class="card-actions-row" v-else>
              <el-button
                type="default"
                size="default"
                data-testid="mobile-detail-btn"
                @click="openDetail(row, $index)"
              >详情</el-button>
            </div>
          </div>
        </div>

        <!-- 移动端空态 -->
        <WolfEmpty
          v-else
          title="暂无待审批事项"
          description="所有回款与发票申请都已处理完毕"
        />

        <!-- 移动端分页（简化版） -->
        <div v-if="rows.length > 0" class="mobile-pagination">
          <span class="total-text">共 {{ total }} 条</span>
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="total"
            :page-sizes="[10, 20, 50]"
            layout="prev, pager, next"
            small
            @current-change="fetchList"
            @size-change="fetchList"
          />
        </div>
      </div>
    </template>

    <!-- 详情抽屉：①el-descriptions 决策字段 ②ApprovalProcessGeneric（含 timeline）③操作吸底 -->
    <el-drawer
      v-model="drawerVisible"
      data-testid="approval-detail-drawer"
      title="审批详情"
      direction="rtl"
      :size="drawerSize"
      :with-header="true"
      @closed="onDrawerClosed"
    >
      <div class="drawer-body">
        <div v-if="currentRow" class="drawer-decisions">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="单号">
              <span class="number-cell" @click="copyNumber(currentRow.application_number)">
                {{ currentRow.application_number }}
              </span>
            </el-descriptions-item>
            <el-descriptions-item label="单据类型">
              {{ businessTypeLabel(currentRow.business_type) }}
            </el-descriptions-item>
            <el-descriptions-item label="客户/实体">
              {{ currentRow.entity_name || '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="金额">
              <span class="amount">{{ formatCurrency(currentRow.entity_amount) }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="提交人">
              {{ currentRow.submitter_name }}
            </el-descriptions-item>
            <el-descriptions-item label="提交时间">
              {{ formatDateRelative(currentRow.created_time) }}
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <ApprovalProcessGeneric
          v-if="currentRow"
          class="drawer-approval"
          :entity-type="currentRow.business_type"
          :entity-id="currentRow.business_id"
          :can-approve="activeTab === 'pending'"
          :is-submitter="activeTab === 'submitted'"
          @approved="onApprovalActionDone"
          @rejected="onApprovalActionDone"
          @withdrawn="onApprovalActionDone"
          @submitted="onApprovalActionDone"
          @resubmit="onResubmit"
        />
      </div>
    </el-drawer>

    <!-- 移动端快速驳回弹窗 -->
    <el-dialog
      v-model="quickRejectVisible"
      data-testid="quick-reject-dialog"
      title="驳回审批"
      width="90%"
    >
      <el-alert
        type="warning"
        :closable="false"
        style="margin-bottom: 12px"
      >
        请填写驳回理由，提交人将据此修改。
      </el-alert>
      <el-input
        v-model="quickRejectReason"
        data-testid="quick-reject-reason"
        type="textarea"
        :rows="4"
        placeholder="请填写驳回理由"
        maxlength="500"
        show-word-limit
      />
      <template #footer>
        <el-button @click="quickRejectVisible = false">取消</el-button>
        <el-button
          type="primary"
          data-testid="quick-reject-confirm-btn"
          @click="confirmQuickReject"
        >确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Clock } from '@element-plus/icons-vue'
import { useApprovalStore } from '@/stores/approval'
import type { EntityType, ApprovalListItem } from '@/schemas/approvalGeneric'
import ApprovalStatusBadge from '@/components/ApprovalStatusBadge.vue'
import ApprovalProcessGeneric from '@/components/ApprovalProcessGeneric.vue'
import ErrorState from '@/components/ErrorState.vue'
import WolfEmpty from '@/components/WolfEmpty.vue'
import { formatCurrency, formatDateRelative } from '@/utils/format'

type Tab = 'pending' | 'processed' | 'submitted'
type LoadError = null | 'error' | 'forbidden'

const store = useApprovalStore()
const { loading, pendingCount } = storeToRefs(store)
const router = useRouter()

// ===== State =====
const activeTab = ref<Tab>('pending')
const filterForm = ref<{ business_type: EntityType | '' }>({ business_type: '' })
const page = ref<number>(1)
const pageSize = ref<number>(20)
const total = ref<number>(0)
const rows = ref<ApprovalListItem[]>([])
const loadError = ref<LoadError>(null)

const drawerVisible = ref<boolean>(false)
const currentRow = ref<ApprovalListItem | null>(null)
const triggerRowIndex = ref<number>(-1)
const focusedRowEl = ref<HTMLElement | null>(null)

const resubmitPendingId = ref<number | null>(null)

// ===== 计算属性 =====
const drawerSize = computed<string>(() => (typeof window !== 'undefined' && window.innerWidth < 768 ? '100%' : '480px'))

// 移动端检测（响应式）
const isMobile = ref<boolean>(false)
const checkMobile = (): void => {
  isMobile.value = typeof window !== 'undefined' && window.innerWidth < 768
}
onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', checkMobile)
})

// ===== 方法 =====
const isAxiosStatus = (err: unknown, code: number): boolean => {
  const r = (err as { response?: { status?: number } } | null)?.response
  return typeof r?.status === 'number' && r.status === code
}

const businessTypeLabel = (t: EntityType): string => {
  const map: Record<EntityType, string> = {
    PAYMENT: '回款',
    INVOICE: '发票',
    CONTRACT: '合同',
    LICENSE: 'License'
  }
  return map[t] ?? t
}

const fetchList = async (): Promise<void> => {
  loadError.value = null
  try {
    const query = {
      tab: activeTab.value,
      page: page.value,
      page_size: pageSize.value,
      ...(filterForm.value.business_type ? { business_type: filterForm.value.business_type } : {})
    }
    const res = await store.fetchList(query)
    rows.value = activeTab.value === 'pending'
      ? [...res.items].sort(byOverdueDesc)
      : res.items
    total.value = res.total
  } catch (err) {
    if (isAxiosStatus(err, 403)) {
      loadError.value = 'forbidden'
    } else {
      loadError.value = 'error'
    }
  }
}

// 待我审批按 overdue_hours 降序（积压最久顶；null 视为 0）
const byOverdueDesc = (a: ApprovalListItem, b: ApprovalListItem): number => {
  const ah = a.overdue_hours ?? 0
  const bh = b.overdue_hours ?? 0
  return bh - ah
}

const reload = (): void => {
  fetchList()
}

const handleTabChange = (): void => {
  page.value = 1
  fetchList()
}

const handleFilterChange = (): void => {
  page.value = 1
  fetchList()
}

const resetFilter = (): void => {
  filterForm.value.business_type = ''
  page.value = 1
  fetchList()
}

const copyNumber = async (num: string): Promise<void> => {
  try {
    if (typeof navigator?.clipboard?.writeText === 'function') {
      await navigator.clipboard.writeText(num)
    } else {
      // 降级：document.execCommand
      const ta = document.createElement('textarea')
      ta.value = num
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    ElMessage.success('已复制单号')
  } catch {
    ElMessage.error('复制失败，请手动选择单号复制')
  }
}

const openDetail = (row: ApprovalListItem, index: number): void => {
  currentRow.value = row
  triggerRowIndex.value = index
  focusedRowEl.value = (document.querySelectorAll('.approval-row')[index] as HTMLElement) ?? null
  drawerVisible.value = true
}

const onDrawerClosed = (): void => {
  // 条13：抽屉关闭焦点回触发发行（或下一行）
  const target = focusedRowEl.value ?? null
  if (target && typeof target.focus === 'function') {
    target.focus()
  }
  currentRow.value = null
  triggerRowIndex.value = -1
}

const onApprovalActionDone = (): void => {
  // 审批完成（同意/驳回/撤回/提交）后刷新列表 + 关抽屉
  drawerVisible.value = false
  fetchList()
}

// 条4：REJECTED 行修改并重新提交（先 update 回 DRAFT 再 submitApproval）
// 注：update 回 DRAFT 由各实体编辑页负责；审批中心 entry 仅 router.push 跳
// 对应编辑页（PAYMENT 无独立编辑页，跳列表页 + info 提示），避免审批中心耦合
// 各实体的 update API（COMPONENTS.md「视图不直接发业务 update」亦不在此处内嵌
// 多条合同/回款/发票的 update 调用，保持中心单一职责）。
// 修复（Important #1）：原 window.location.assign(`#...`) 在 createWebHistory 模式
// 下不切 SPA 路由（仅改 hash 不导航）；改用 router.push 走真实 SPA 路由跳转。
const handleResubmit = async (row: ApprovalListItem): Promise<void> => {
  resubmitPendingId.value = row.id
  try {
    await ElMessageBox.confirm(
      `将跳转到 ${businessTypeLabel(row.business_type)} 编辑页修改后重新提交审批。是否继续？`,
      '修改并重新提交',
      { type: 'info' }
    )
    // 跳转到对应实体编辑页（route 由路由层声明，审批中心不内嵌 update 逻辑）
    const route: Record<EntityType, string> = {
      INVOICE: `/invoices/edit/${row.business_id}`,
      CONTRACT: `/contracts/edit/${row.business_id}`,
      // 回款无独立编辑页（/payments 为列表页）：跳列表页 + info 提示，
      // 保证不白屏/不断旅程；用户在列表内修改后重新提交审批。
      PAYMENT: `/payments`,
      // License 申请在客户详情页的 License 管理 Tab 编辑
      LICENSE: `/customers/${row.customer_id}?tab=license-management`
    }
    const target = route[row.business_type]
    await router.push(target)
    // PAYMENT 目标是列表页，无法直接进入驳回回款的编辑入口——补 info 引导，
    // 旅程不断（比原 window.location.assign hash bug 强）。
    if (row.business_type === 'PAYMENT') {
      ElMessage.info('请修改回款记录后重新提交审批')
    }
    if (row.business_type === 'LICENSE') {
      ElMessage.info('请修改 License 申请后重新提交审批')
    }
  } catch {
    // 用户取消（ElMessageBox reject）或 router.push 失败
  } finally {
    resubmitPendingId.value = null
  }
}

// 移动端快速审批：同意（单条，无抽屉）
const handleQuickApprove = async (row: ApprovalListItem): Promise<void> => {
  try {
    await ElMessageBox.confirm(
      '确定同意该审批？',
      '快速审批',
      { type: 'success' }
    )
    // 调 store.approveEntity（单条审批，updated_time 用当前行）
    await store.approveEntity(
      row.business_type,
      row.business_id,
      'APPROVE',
      '审批通过',
      row.updated_time
    )
    ElMessage.success('已同意')
    // 刷新列表（移除该行）
    fetchList()
  } catch {
    // 用户取消或审批失败（拦截器已 toast）
  }
}

// 移动端快速审批：驳回（单条，弹窗输入理由）
const quickRejectReason = ref<string>('')
const quickRejectRow = ref<ApprovalListItem | null>(null)
const quickRejectVisible = ref<boolean>(false)

const handleQuickReject = (row: ApprovalListItem): void => {
  quickRejectReason.value = ''
  quickRejectRow.value = row
  quickRejectVisible.value = true
}

const confirmQuickReject = async (): Promise<void> => {
  const reason = quickRejectReason.value.trim()
  if (!reason) {
    ElMessage.warning('请填写驳回理由，提交人将据此修改')
    return
  }
  if (!quickRejectRow.value) return
  try {
    await store.approveEntity(
      quickRejectRow.value.business_type,
      quickRejectRow.value.business_id,
      'REJECT',
      reason,
      quickRejectRow.value.updated_time
    )
    ElMessage.success('已驳回，申请人可修改后重新提交')
    quickRejectVisible.value = false
    fetchList()
  } catch {
    // 审批失败（拦截器已 toast）
  }
}

// 抽屉侧 ApprovalProcessGeneric REJECTED 态「修改并重新提交」CTA（Important #2）
// 事件无 payload，目标行取 currentRow（抽屉当前展示行）。
const onResubmit = (): void => {
  if (currentRow.value == null) return
  handleResubmit(currentRow.value)
}

// 键盘快捷键（条9）：J/K 上下行、A 同意、R 驳回、Enter 开抽屉、Esc 关抽屉
// 通过全局 keydown 监听，避免每行绑定；仅当焦点不在输入/弹窗内时生效。
const onKeydown = (e: KeyboardEvent): void => {
  const target = e.target as HTMLElement | null
  if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return
  if (drawerVisible.value) {
    if (e.key === 'Escape') {
      drawerVisible.value = false
    }
    return
  }
  if (rows.value.length === 0) return
  if (e.key === 'Enter') {
    const row = rows.value[focusIndex.value] ?? null
    if (row) openDetail(row, focusIndex.value)
  } else if (e.key === 'j' || e.key === 'J') {
    focusIndex.value = Math.min(rows.value.length - 1, focusIndex.value + 1)
    focusCurrentRow()
  } else if (e.key === 'k' || e.key === 'K') {
    focusIndex.value = Math.max(0, focusIndex.value - 1)
    focusCurrentRow()
  }
}

const focusIndex = ref<number>(0)

const focusCurrentRow = (): void => {
  const els = document.querySelectorAll('.approval-row')
  const el = els[focusIndex.value] as HTMLElement | undefined
  if (el && typeof el.focus === 'function') {
    el.focus()
  }
}

const setupKeyboard = (): void => {
  window.addEventListener('keydown', onKeydown)
}

const teardownKeyboard = (): void => {
  window.removeEventListener('keydown', onKeydown)
}

// ===== 生命周期 =====
onMounted((): void => {
  setupKeyboard()
  fetchList()
})
onBeforeUnmount((): void => {
  teardownKeyboard()
  store.clearList()
})

// 行可聚焦（条9 键盘导航 + 条13 焦点回归）：每次列表刷新后给行加 tabindex=0
watch(rows, async () => {
  await nextTick()
  document.querySelectorAll<HTMLElement>('.approval-row').forEach((el) => {
    el.setAttribute('tabindex', '0')
  })
}, { flush: 'post' })
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.finance-approval-center {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

.tabs-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-sm $wolf-card-padding;
  margin-bottom: $wolf-card-gap;
  box-shadow: $wolf-shadow-card;
}

.tab-badge {
  margin-left: $wolf-space-xs;
}

.filter-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-card-padding;
  margin-bottom: $wolf-card-gap;
  box-shadow: $wolf-shadow-card;
}

.table-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-card-padding;
  box-shadow: $wolf-shadow-card;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: $wolf-space-md;
}

.card-title-group {
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
}

.card-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
}

.card-tag {
  font-size: $wolf-font-size-caption;
  padding: 2px 8px;
  border-radius: $wolf-radius-sm;

  &.primary {
    color: $wolf-primary;
    background: $wolf-primary-light;
  }
}

.card-actions {
  display: flex;
  gap: $wolf-button-gap;
}

.number-cell {
  font-family: $wolf-font-mono;
  font-size: $wolf-font-size-auxiliary;
  color: $wolf-text-link;
  cursor: pointer;
  user-select: none;

  &:hover {
    color: $wolf-text-link-hover;
    text-decoration: underline;
  }
}

.type-tag {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-secondary;
}

.amount {
  font-weight: $wolf-font-weight-medium;
  color: $wolf-warning-text;
  font-family: $wolf-font-mono;
}

.mono-time {
  font-family: $wolf-font-mono;
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.muted {
  color: $wolf-text-placeholder;
}

.overdue-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: $wolf-radius-sm;
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-medium;
  color: var(--wolf-approval-pending-text, $wolf-warning-text);
  background: var(--wolf-approval-pending-bg, $wolf-warning-bg);
}

.pagination-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: $wolf-space-md 0;
}

.total-text {
  font-size: $wolf-font-size-auxiliary;
  color: $wolf-text-tertiary;
}

// 行级聚焦态（键盘导航 + 抽屉关闭后焦点回归）
:deep(.approval-row) {
  outline: none;

  &:focus,
  &:focus-visible {
    background: $wolf-bg-hover;
  }
}

// 抽屉内信息层级（条7 固化）
.drawer-body {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md;
  height: 100%;
}

.drawer-decisions {
  // 决策字段置顶
  flex-shrink: 0;
}

.drawer-approval {
  // timeline + 操作区
  flex: 1 1 auto;
  // 移动端操作区 sticky 吸底（条11）
  :deep(.approval-process-generic__actions) {
    position: sticky;
    bottom: 0;
    background: $wolf-bg-card;
    padding-bottom: env(safe-area-inset-bottom, 0);
  }
}

@media (max-width: 768px) {
  .finance-approval-center {
    padding: $wolf-space-md;
  }

  // 移动端卡片列表样式
  .mobile-card-list {
    margin-top: $wolf-space-md;
  }

  .approval-card {
    background: $wolf-bg-card;
    border-radius: $wolf-radius-md;
    padding: $wolf-space-md;
    margin-bottom: $wolf-space-md;
    box-shadow: $wolf-shadow-card;

    &.has-overdue {
      border: 1px solid $wolf-warning-border;
    }
  }

  .card-header-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: $wolf-space-sm;
  }

  .card-body-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: $wolf-space-sm;

    .entity-name {
      font-size: $wolf-font-size-title;
      color: $wolf-text-primary;
      font-weight: $wolf-font-weight-medium;
      max-width: 60%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }

  .card-meta-row {
    display: flex;
    justify-content: space-between;
    font-size: $wolf-font-size-auxiliary;
    color: $wolf-text-secondary;
    margin-bottom: $wolf-space-sm;

    .submitter {
      max-width: 50%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }

  .card-overdue-row {
    margin-bottom: $wolf-space-sm;
  }

  .card-divider {
    height: 1px;
    background: $wolf-border-light;
    margin: $wolf-space-sm 0;
  }

  .card-actions-row {
    display: flex;
    gap: $wolf-button-gap;
    padding-top: $wolf-space-sm;

    // 按钮全宽（移动端审批入口优化）
    .el-button {
      flex: 1;
      min-height: 44px; // touch-target ≥ 44pt
    }
  }

  // 移动端单号样式
  .number-cell.mobile {
    font-size: $wolf-font-size-body;
  }

  // 移动端金额样式（突出）
  .amount.mobile {
    font-size: $wolf-font-size-title;
    font-weight: $wolf-font-weight-semibold;
  }

  // 移动端超时徽章
  .overdue-badge.mobile {
    font-size: $wolf-font-size-auxiliary;
  }

  // 移动端分页
  .mobile-pagination {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: $wolf-space-sm;
    padding: $wolf-space-md 0;
    padding-bottom: env(safe-area-inset-bottom, 0); // 安全区

    .el-pagination {
      width: 100%;
      justify-content: center;
    }
  }

  // 移动端抽屉全屏（已通过 drawerSize computed 实现）
  // 移动端筛选区简化（隐藏次要筛选）
  .filter-card {
    .el-form-item {
      margin-bottom: $wolf-space-sm;
    }
  }

  // 移动端 Tab 简化（Badge 位置调整）
  .tab-badge {
    margin-left: 4px;
  }
}
</style>