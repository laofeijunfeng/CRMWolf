<script setup lang="ts">
/**
 * PaymentPlanView.vue - Task 7.1 Full Implementation
 *
 * Features:
 * - 12-column table (including remaining_amount, invoiced_amount, invoice_status)
 * - Filter-tabs (no icons, neutral active state per Contracts.vue pattern)
 * - Amount typography: mono-number with tabular-nums, right alignment
 * - Empty state: "还没有回款计划" with Calendar icon + "创建回款计划" button
 * - Loading skeleton: Table skeleton screen
 *
 * Design Constraints:
 * - TypeScript strict mode: No any, as any, ts-ignore directive, or non-null assertion
 * - Design Token: Use $wolf-* Sass variables
 */

import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { showError, showSuccess } from '@/utils/errorMessages'
import { Search } from '@element-plus/icons-vue'
import paymentApi, {
  type PaymentPlanWithDetails,
  type PaymentPlanListParams,
  type PaymentRecordCreate,
  type PaymentPlanStatus
} from '@/api/payment'
import { usePermissionStore } from '@/stores/permissions'
import { useApprovalStore } from '@/stores/approval'
import { usePaymentPlansStore } from '@/stores/paymentPlans'
import { formatCurrency } from '@/utils/format'
import { logger } from '@/utils/logger'
import PaymentEmptyState from '@/components/PaymentEmptyState.vue'

const router = useRouter()
const route = useRoute()
const permissionStore = usePermissionStore()
const approvalStore = useApprovalStore()
const paymentPlansStore = usePaymentPlansStore()

const paymentSubmitPermission = 'payment:submit'
const submittingApprovalId = ref<number | null>(null)

// Task 7.1: Filter-tabs without icons, following Contracts.vue pattern
const tabs = [
  { key: 'pending', label: '待登记' },
  { key: 'partial', label: '部分回款' },
  { key: 'overdue', label: '已逾期' },
  { key: 'upcoming', label: '即将到期' },
  { key: 'all', label: '全部计划' }
]

const activeTab = ref('pending')
const searchForm = ref({
  keyword: '',
  status: '' as PaymentPlanStatus | ''
})
const loading = ref(false)

const paymentPlans = ref<PaymentPlanWithDetails[]>([])
const pagination = ref({
  current: 1,
  pageSize: 20,
  total: 0
})

// Badge counts from store
const tabBadgeCounts = computed(() => ({
  pending: paymentPlansStore.pendingCount,
  partial: paymentPlansStore.partialCount,
  overdue: paymentPlansStore.overdueCount,
  upcoming: 0,
  all: paymentPlansStore.total
}))

const paymentModalVisible = ref(false)
const paymentForm = ref<PaymentRecordCreate>({
  actual_amount: 0,
  payment_date: ''
})
const currentPlan = ref<PaymentPlanWithDetails | null>(null)

// Task 7.4: Deep-link highlight from URL param
const highlightedPlanId = computed(() => {
  const planId = route.query['plan_id']
  return planId !== undefined && planId !== null ? Number(planId) : null
})

// Task 7.5: Responsive column visibility
const showInvoicedColumns = computed(() => {
  return window.innerWidth >= 1280
})

const showOwnerColumn = computed(() => {
  return window.innerWidth >= 1024
})

const getOverdueDays = (dueDate: string): number => {
  const today = new Date()
  const due = new Date(dueDate)
  const diffTime = today.getTime() - due.getTime()
  const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24))
  return diffDays > 0 ? diffDays : 0
}

const getUpcomingDate = (days: number): string => {
  const date = new Date()
  date.setDate(date.getDate() + days)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const fetchPaymentPlans = async (): Promise<void> => {
  loading.value = true
  try {
    const params: PaymentPlanListParams = {
      page: pagination.value.current,
      page_size: pagination.value.pageSize
    }

    if (activeTab.value === 'pending') {
      params.status = 'PENDING'
    } else if (activeTab.value === 'partial') {
      params.status = 'PARTIAL'
    } else if (activeTab.value === 'overdue') {
      params.status = 'OVERDUE'
    } else if (activeTab.value === 'upcoming') {
      const upcomingDate = getUpcomingDate(7)
      params.due_date_end = upcomingDate
    }

    const data = await paymentApi.listPaymentPlans(params)

    let filteredPlans: PaymentPlanWithDetails[] = data.items

    if (searchForm.value.keyword.length > 0) {
      filteredPlans = filteredPlans.filter((plan: PaymentPlanWithDetails) => {
        const keyword = searchForm.value.keyword.toLowerCase()
        return (
          (plan.contract_name?.toLowerCase().includes(keyword) ?? false) ||
          (plan.customer_name?.toLowerCase().includes(keyword) ?? false)
        )
      })
    }

    paymentPlans.value = filteredPlans
    pagination.value.total = data.total
  } catch (error) {
    logger.error('[PaymentPlanView]', '获取回款计划失败', { error })
    showError(error, '获取回款计划')
  } finally {
    loading.value = false
  }
}

const filteredPaymentPlans = computed(() => {
  return paymentPlans.value
})

const handleTabChange = (key: string): void => {
  activeTab.value = key
  pagination.value.current = 1
  searchForm.value.status = ''
  fetchPaymentPlans()
}

const handleSearch = (): void => {
  pagination.value.current = 1
  fetchPaymentPlans()
}

const handleReset = (): void => {
  searchForm.value.keyword = ''
  searchForm.value.status = ''
  pagination.value.current = 1
  fetchPaymentPlans()
}

const handlePageChange = (page: number): void => {
  pagination.value.current = page
  fetchPaymentPlans()
}

const handlePageSizeChange = (pageSize: number): void => {
  pagination.value.pageSize = pageSize
  pagination.value.current = 1
  fetchPaymentPlans()
}

const getStatusText = (status: string): string => {
  const statusMap: Record<string, string> = {
    'PENDING': '待回款',
    'OVERDUE': '已逾期',
    'PARTIAL': '部分回款',
    'COMPLETED': '已完成'
  }
  return statusMap[status] ?? status
}

const getStatusClass = (status: string): string => {
  const classMap: Record<string, string> = {
    'PENDING': 'status-default',
    'OVERDUE': 'status-danger',
    'PARTIAL': 'status-warning',
    'COMPLETED': 'status-success'
  }
  return classMap[status] ?? 'status-default'
}

// Task 7.1: Invoice status helpers
const getInvoiceStatusText = (isInvoiced: boolean | undefined, invoiceCount: number | undefined): string => {
  if (isInvoiced === true && invoiceCount !== undefined && invoiceCount > 0) {
    return `${invoiceCount}张发票`
  }
  return '未开票'
}

const getInvoiceStatusClass = (isInvoiced: boolean | undefined): string => {
  return isInvoiced === true ? 'status-success' : 'status-default'
}

const formatDate = (dateStr: string): string => {
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}

const viewDetail = (plan: PaymentPlanWithDetails): void => {
  router.push(`/payments/${plan.id}`)
}

const handleRegisterPayment = (plan: PaymentPlanWithDetails): void => {
  currentPlan.value = plan
  // Use local timezone, not UTC (toISOString() converts to UTC causing date offset in China)
  const today = new Date()
  const year = today.getFullYear()
  const month = String(today.getMonth() + 1).padStart(2, '0')
  const day = String(today.getDate()).padStart(2, '0')
  const todayStr = `${year}-${month}-${day}`
  paymentForm.value = {
    actual_amount: plan.remaining_amount ?? plan.planned_amount,
    payment_date: todayStr
  }
  paymentModalVisible.value = true
}

const handleCreatePayment = async (): Promise<void> => {
  if (paymentForm.value.actual_amount === null || paymentForm.value.actual_amount <= 0) {
    ElMessage.error('请输入有效的回款金额')
    return
  }

  if (paymentForm.value.payment_date.length === 0) {
    ElMessage.error('请选择回款日期')
    return
  }

  if (currentPlan.value !== null) {
    try {
      await paymentApi.createPaymentRecord(currentPlan.value.id, paymentForm.value)
      showSuccess('登记', '回款')
      paymentModalVisible.value = false
      fetchPaymentPlans()
      paymentPlansStore.fetchBadgeCounts()
    } catch (error: unknown) {
      logger.error('[PaymentPlanView]', '登记回款失败', { error })
      showError(error, '登记回款')
    }
  }
}

// Task 7.3: Submit approval with correct logic
const handleSubmitApproval = async (plan: PaymentPlanWithDetails): Promise<void> => {
  if (submittingApprovalId.value !== null) return

  // Task 7.3: Get latest payment record for approval submission
  const latestRecord = plan.payment_records?.[plan.payment_records.length - 1]
  if (latestRecord === undefined) {
    ElMessage.warning('没有可提交审批的回款记录')
    return
  }

  submittingApprovalId.value = plan.id
  try {
    const res = await approvalStore.submitEntity('PAYMENT', latestRecord.id)
    if (res.approval_id === 0) {
      ElMessage.success('未配置审批流，已转为财务确认')
    } else {
      ElMessage.success('已提交审批，等待审批人处理')
    }
    fetchPaymentPlans()
    paymentPlansStore.fetchBadgeCounts()
  } catch {
    // Error handled by interceptor
  } finally {
    submittingApprovalId.value = null
  }
}

// Task 7.3: Check if approval button should be shown
const canSubmitApproval = (plan: PaymentPlanWithDetails): boolean => {
  const latestRecord = plan.payment_records?.[plan.payment_records.length - 1] as Record<string, unknown> | undefined
  if (latestRecord === undefined) return false

  const confirmationStatus = latestRecord['confirmation_status'] as string | undefined
  const approvalId = latestRecord['approval_id'] as number | undefined

  // Task 7.3: Show button if confirmation_status === 'PENDING' AND approval_id === null
  return confirmationStatus === 'PENDING' && (approvalId === undefined || approvalId === null)
}

// Fetch badge counts on mount
onMounted(() => {
  fetchPaymentPlans()
  paymentPlansStore.fetchBadgeCounts()
})

// Watch for badge count updates
watch(() => paymentPlansStore.pendingApprovalMeCount, () => {
  // Badge on approval status filter updates automatically
})
</script>

<template>
  <div class="payment-plan-view">
    <!-- Task 7.1: Filter-tabs without icons (Contracts.vue pattern) -->
    <div class="filter-tabs-bar">
      <div class="filter-tabs">
        <span
          v-for="tab in tabs"
          :key="tab.key"
          :class="['filter-tab', { active: activeTab === tab.key }]"
          @click="handleTabChange(tab.key)"
        >
          <span class="tab-label">{{ tab.label }}</span>
          <el-badge
            v-if="tabBadgeCounts[tab.key as keyof typeof tabBadgeCounts] > 0"
            :value="tabBadgeCounts[tab.key as keyof typeof tabBadgeCounts]"
            class="tab-badge"
          />
        </span>
      </div>
    </div>

    <!-- Search filter -->
    <div class="filter-card">
      <div class="filter-row">
        <div class="filter-left">
          <el-input
            v-model="searchForm.keyword"
            placeholder="搜索客户/合同名称"
            clearable
            class="search-input"
            @keyup.enter="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </div>
        <div class="filter-right">
          <el-button @click="handleReset">重置</el-button>
          <el-button type="primary" @click="handleSearch">查询</el-button>
        </div>
      </div>
    </div>

    <!-- Task 7.4: Loading skeleton -->
    <template v-if="loading && paymentPlans.length === 0">
      <div class="table-card">
        <div class="payment-skeleton-table">
          <div v-for="i in 5" :key="i" class="skeleton-row">
            <div class="skeleton-cell skeleton-cell-name"></div>
            <div class="skeleton-cell skeleton-cell-name"></div>
            <div class="skeleton-cell skeleton-cell-amount"></div>
            <div class="skeleton-cell skeleton-cell-amount"></div>
            <div class="skeleton-cell skeleton-cell-amount"></div>
            <div class="skeleton-cell skeleton-cell-date"></div>
            <div class="skeleton-cell skeleton-cell-status"></div>
            <div class="skeleton-cell skeleton-cell-owner"></div>
          </div>
        </div>
      </div>
    </template>

    <!-- Task 7.1: Empty state -->
    <template v-else-if="!loading && filteredPaymentPlans.length === 0 && paymentPlans.length === 0">
      <PaymentEmptyState type="no-plans" :show-action="true" />
    </template>

    <!-- Table -->
    <template v-else>
      <div class="table-card payment-table-responsive payment-table-mobile-scroll">
        <el-table
          :data="filteredPaymentPlans"
          v-loading="loading"
          stripe
          style="width: 100%"
          :key="activeTab"
        >
          <!-- Task 7.1: 12 columns including computed fields -->
          <el-table-column prop="customer_name" label="客户名称" min-width="150">
            <template #default="{ row }">
              <!-- Task 7.4: Deep-link highlight -->
              <span
                :class="['link-text', { 'deep-link-highlight': highlightedPlanId === row.id }]"
                @click="viewDetail(row)"
              >
                {{ row.customer_name }}
              </span>
            </template>
          </el-table-column>

          <el-table-column prop="contract_name" label="合同名称" min-width="180" />

          <el-table-column prop="stage_name" label="回款阶段" min-width="120" />

          <!-- Task 7.1: Amount typography - mono-number, right alignment -->
          <el-table-column label="计划金额" min-width="120" align="right">
            <template #default="{ row }">
              <span class="payment-amount">{{ formatCurrency(row.planned_amount) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="已回款" min-width="120" align="right">
            <template #default="{ row }">
              <span class="payment-amount-paid">{{ formatCurrency(row.paid_amount ?? 0) }}</span>
            </template>
          </el-table-column>

          <!-- Task 7.1: New column - remaining_amount -->
          <el-table-column label="待回款" min-width="120" align="right">
            <template #default="{ row }">
              <span class="payment-amount-remaining">{{ formatCurrency(row.remaining_amount ?? 0) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="计划日期" min-width="120">
            <template #default="{ row }">
              {{ formatDate(row.due_date) }}
            </template>
          </el-table-column>

          <!-- Overdue days column (conditional) -->
          <el-table-column v-if="activeTab === 'overdue'" label="逾期天数" width="100" align="right">
            <template #default="{ row }">
              <span class="payment-amount-overdue mono-number">{{ getOverdueDays(row.due_date) }} 天</span>
            </template>
          </el-table-column>

          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <span :class="['status-tag', getStatusClass(row.status)]">
                {{ getStatusText(row.status) }}
              </span>
            </template>
          </el-table-column>

          <!-- Task 7.1: New column - invoiced_amount (responsive, hide below 1280px) -->
          <el-table-column
            v-if="showInvoicedColumns"
            class-name="column-invoiced-amount"
            label="已开票"
            min-width="100"
            align="right"
          >
            <template #default="{ row }">
              <span class="mono-number">{{ formatCurrency(row.invoiced_amount ?? 0) }}</span>
            </template>
          </el-table-column>

          <!-- Task 7.1: New column - invoice_status (responsive, hide below 1280px) -->
          <el-table-column
            v-if="showInvoicedColumns"
            class-name="column-invoice-status"
            label="发票状态"
            min-width="100"
          >
            <template #default="{ row }">
              <span :class="['status-tag', getInvoiceStatusClass(row.is_invoiced)]">
                {{ getInvoiceStatusText(row.is_invoiced, row.invoice_count) }}
              </span>
            </template>
          </el-table-column>

          <!-- Task 7.5: Responsive - hide owner_name below 1024px -->
          <el-table-column
            v-if="showOwnerColumn"
            class-name="column-owner-name"
            prop="owner_name"
            label="负责人"
            min-width="100"
          />

          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <div class="action-cell">
                <span class="action-link" @click="viewDetail(row)">查看</span>
                <span
                  v-if="row.status !== 'COMPLETED' && permissionStore.hasPermission('payment:register')"
                  class="action-link"
                  @click="handleRegisterPayment(row)"
                >登记回款</span>
                <!-- Task 7.3: Correct approval button logic -->
                <span
                  v-if="canSubmitApproval(row) && permissionStore.hasPermission(paymentSubmitPermission)"
                  class="action-link"
                  :class="{ 'row-action-loading': submittingApprovalId === row.id }"
                  @click="handleSubmitApproval(row)"
                >
                  <template v-if="submittingApprovalId === row.id">提交中...</template>
                  <template v-else>提交审批</template>
                </span>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <!-- Pagination -->
        <div class="pagination-bar">
          <span class="total-text mono-number">共 {{ pagination.total }} 条</span>
          <el-pagination
            v-model:current-page="pagination.current"
            v-model:page-size="pagination.pageSize"
            :page-sizes="[10, 20, 50, 100]"
            :total="pagination.total"
            layout="sizes, prev, pager, next, jumper"
            @current-change="handlePageChange"
            @size-change="handlePageSizeChange"
          />
        </div>
      </div>
    </template>

    <!-- Register payment dialog -->
    <el-dialog
      v-model="paymentModalVisible"
      title="登记回款"
      width="500px"
    >
      <el-form :model="paymentForm" label-position="top">
        <el-form-item label="回款金额" required>
          <el-input-number
            v-model="paymentForm.actual_amount"
            placeholder="请输入回款金额"
            :min="0"
            :precision="2"
            :controls="false"
            style="width: 100%"
          >
            <template #prefix>¥</template>
          </el-input-number>
          <div v-if="currentPlan !== null" class="form-extra mono-number">
            待回款：{{ formatCurrency(currentPlan.remaining_amount ?? 0) }}
          </div>
        </el-form-item>
        <el-form-item label="回款日期" required>
          <el-date-picker
            v-model="paymentForm.payment_date"
            type="date"
            placeholder="请选择回款日期"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="凭证附件">
          <el-input v-model="paymentForm.proof_attachment" placeholder="附件URL（可选）" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input
            v-model="paymentForm.notes"
            type="textarea"
            placeholder="备注信息（可选）"
            :maxlength="200"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="paymentModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreatePayment">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;
@use '@/styles/payment.scss' as *;

.payment-plan-view {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

// Filter-tabs bar (Contracts.vue pattern - no icons, neutral active state)
.filter-tabs-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: $wolf-space-md;
}

.filter-tabs {
  display: flex;
  gap: $wolf-space-xs;
}

.filter-tab {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
  padding: 8px $wolf-space-md;
  font-size: $wolf-font-size-auxiliary;
  font-weight: $wolf-font-weight-normal;
  color: $wolf-text-tertiary;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-sm;
  cursor: pointer;
  transition: all 0.2s ease-in-out;

  &:hover:not(.active) {
    background: $wolf-bg-hover;
    color: $wolf-text-secondary;
  }

  // Task 7.1: Neutral active state (no primary color, no scale transform)
  &.active {
    background: $wolf-bg-hover;
    color: $wolf-text-secondary;
    font-weight: $wolf-font-weight-medium;
  }
}

.tab-label {
  font-size: $wolf-font-size-auxiliary;
  line-height: $wolf-line-height-normal;
}

.tab-badge {
  margin-left: $wolf-space-xs;

  .el-badge__content {
    font-family: $wolf-font-mono;
    font-variant-numeric: tabular-nums lining-nums;
    font-size: 10px;
  }
}

// Approval status filter
.approval-status-filter {
  margin-bottom: $wolf-space-md;
  padding: $wolf-space-sm $wolf-space-md;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-sm;
}

// Filter card
.filter-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  margin-bottom: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: $wolf-space-lg;
}

.filter-left {
  flex-shrink: 0;
}

.search-input {
  width: 280px;
}

.filter-right {
  display: flex;
  gap: $wolf-space-xs;
  flex-shrink: 0;
}

// Table styles
.table-card {
  background: transparent;
  overflow: visible;
}

.link-text {
  color: $wolf-text-link;
  cursor: pointer;
  font-weight: $wolf-font-weight-medium;
  &:hover {
    color: $wolf-text-link-hover;
  }
}

// Status tags
.status-tag {
  display: inline-flex;
  padding: 4px 8px;
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-normal;
  border-radius: $wolf-radius-sm;
}

.status-default {
  background: $wolf-bg-hover;
  color: $wolf-text-tertiary;
}

.status-warning {
  background: $wolf-warning-bg;
  color: $wolf-warning-text;
}

.status-danger {
  background: $wolf-danger-bg;
  color: $wolf-danger-text;
}

.status-success {
  background: $wolf-success-bg;
  color: $wolf-success-text;
}

// Action cell
.action-cell {
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
}

.action-link {
  color: $wolf-text-link;
  font-size: $wolf-font-size-auxiliary;
  cursor: pointer;
  &:hover { color: $wolf-text-link-hover; }
}

// Status badge for approval filter
.status-badge {
  margin-left: $wolf-space-xs;
  vertical-align: middle;

  .el-badge__content {
    font-family: $wolf-font-mono;
    font-variant-numeric: tabular-nums lining-nums;
    font-size: 10px;
  }
}

.form-extra {
  color: $wolf-text-secondary;
  font-size: $wolf-font-size-caption;
  margin-top: $wolf-space-xs;
}

// Pagination
.pagination-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: $wolf-space-md;
}

.total-text {
  font-size: $wolf-font-size-auxiliary;
  color: $wolf-text-tertiary;
}

// Responsive
@media (max-width: 768px) {
  .payment-plan-view {
    padding: $wolf-space-md;
  }

  .search-input { width: 100%; }
  .filter-tabs { flex-wrap: wrap; }

  .filter-tab {
    padding: 6px $wolf-space-sm;
    font-size: $wolf-font-size-caption;
  }

  .approval-status-filter {
    .el-radio-group {
      flex-wrap: wrap;
      gap: 4px;
    }

    .el-radio-button {
      margin: 0;
    }

    .el-radio-button__inner {
      padding: 6px 12px;
      font-size: $wolf-font-size-caption;
    }
  }

  .table-card {
    overflow-x: auto;
  }
}

// Fade transition animation
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
