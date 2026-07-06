<script setup lang="ts">
/**
 * PaymentRecordView.vue - Task 7.2 Full Implementation
 *
 * Features:
 * - 12-column table (approval_status, current_approver_name, invoice_application_count, notes)
 * - Filter-tabs with Badge showing pending_approval_me_count (margin-left positioning)
 * - Approval status badge with pulse animation for "审批中" state
 * - Row-level loading: Button loading state for approval submission
 * - Empty state: "还没有登记回款" with Wallet icon + "前往回款计划" button
 *
 * Design Constraints:
 * - TypeScript strict mode: No any, as any, ts-ignore directive, or non-null assertion
 * - Design Token: Use $wolf-* Sass variables
 */

import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { showError } from '@/utils/errorMessages'
import { Search } from '@element-plus/icons-vue'
import paymentApi, {
  type PaymentRecordWithDetails,
  type PaymentRecordListParams,
  type ApprovalStatus,
  type PaymentConfirmationStatus
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

const paymentConfirmPermission = 'payment:confirm'
const submittingRecordId = ref<number | null>(null)

// Task 7.2: Filter-tabs with Badge
const tabs = [
  { key: 'all', label: '全部记录' },
  { key: 'pending_submit', label: '待提交审批' },
  { key: 'pending_approval', label: '审批中', showBadge: true },
  { key: 'confirmed', label: '已确认' },
  { key: 'rejected', label: '已驳回' }
]

const activeTab = ref('all')
const searchForm = ref({
  keyword: ''
})
const loading = ref(false)

const paymentRecords = ref<PaymentRecordWithDetails[]>([])
const pagination = ref({
  current: 1,
  pageSize: 20,
  total: 0
})

// Task 7.4: Deep-link highlight from URL param
const highlightedRecordId = computed(() => {
  const recordId = route.query['record_id']
  return recordId !== undefined && recordId !== null ? Number(recordId) : null
})

// Task 7.5: Responsive column visibility
const showOwnerColumn = computed(() => {
  return window.innerWidth >= 1024
})

const fetchPaymentRecords = async (): Promise<void> => {
  loading.value = true
  try {
    const params: PaymentRecordListParams = {
      page: pagination.value.current,
      page_size: pagination.value.pageSize
    }

    const data = await paymentApi.listPaymentRecords(params)

    let filteredRecords: PaymentRecordWithDetails[] = data.items

    // Client-side filtering based on activeTab
    if (activeTab.value !== 'all') {
      filteredRecords = filteredRecords.filter((record: PaymentRecordWithDetails) => {
        const approvalStatus = record.approval_status
        const confirmationStatus = record.confirmation_status

        switch (activeTab.value) {
          case 'pending_submit':
            // PENDING confirmation with NO approval submitted
            return confirmationStatus === 'PENDING' && (record.approval_id === undefined || record.approval_id === null)
          case 'pending_approval':
            // PENDING approval status
            return approvalStatus === 'PENDING'
          case 'confirmed':
            return confirmationStatus === 'CONFIRMED'
          case 'rejected':
            return approvalStatus === 'REJECTED'
          default:
            return true
        }
      })
    }

    if (searchForm.value.keyword.length > 0) {
      filteredRecords = filteredRecords.filter((record: PaymentRecordWithDetails) => {
        const keyword = searchForm.value.keyword.toLowerCase()
        return (
          (record.contract_name?.toLowerCase().includes(keyword) ?? false) ||
          (record.customer_name?.toLowerCase().includes(keyword) ?? false) ||
          (record.stage_name?.toLowerCase().includes(keyword) ?? false)
        )
      })
    }

    paymentRecords.value = filteredRecords
    pagination.value.total = filteredRecords.length
  } catch (error) {
    logger.error('[PaymentRecordView]', '获取回款记录失败', { error })
    showError(error, '获取回款记录')
  } finally {
    loading.value = false
  }
}

const handleTabChange = (key: string): void => {
  activeTab.value = key
  pagination.value.current = 1
  fetchPaymentRecords()
}

const handleSearch = (): void => {
  pagination.value.current = 1
  fetchPaymentRecords()
}

const handleReset = (): void => {
  searchForm.value.keyword = ''
  pagination.value.current = 1
  fetchPaymentRecords()
}

const handlePageChange = (page: number): void => {
  pagination.value.current = page
  fetchPaymentRecords()
}

const handlePageSizeChange = (pageSize: number): void => {
  pagination.value.pageSize = pageSize
  pagination.value.current = 1
  fetchPaymentRecords()
}

// Task 7.2: Approval status helpers
const getApprovalStatusText = (status: ApprovalStatus | undefined): string => {
  if (status === undefined) return '未提交'
  const statusMap: Record<ApprovalStatus, string> = {
    'PENDING': '审批中',
    'APPROVED': '已通过',
    'REJECTED': '已驳回'
  }
  return statusMap[status] ?? '未提交'
}

const getApprovalStatusClass = (status: ApprovalStatus | undefined): string => {
  if (status === undefined) return 'approval-badge-default'
  const classMap: Record<ApprovalStatus, string> = {
    'PENDING': 'approval-badge-pending',
    'APPROVED': 'approval-badge-approved',
    'REJECTED': 'approval-badge-rejected'
  }
  return classMap[status] ?? 'approval-badge-default'
}

// Task 7.2: Confirmation status helpers
const getConfirmationStatusText = (status: PaymentConfirmationStatus | undefined): string => {
  if (status === undefined) return '未知'
  const statusMap: Record<PaymentConfirmationStatus, string> = {
    'PENDING': '待确认',
    'CONFIRMED': '已确认',
    'DISPUTED': '有争议'
  }
  return statusMap[status] ?? '未知'
}

const getConfirmationStatusClass = (status: PaymentConfirmationStatus | undefined): string => {
  if (status === undefined) return 'status-default'
  const classMap: Record<PaymentConfirmationStatus, string> = {
    'PENDING': 'status-warning',
    'CONFIRMED': 'status-success',
    'DISPUTED': 'status-danger'
  }
  return classMap[status] ?? 'status-default'
}

const formatDate = (dateStr: string): string => {
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}

const formatDateTime = (dateTimeStr: string): string => {
  const date = new Date(dateTimeStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const viewPlanDetail = (record: PaymentRecordWithDetails): void => {
  router.push(`/payments/${record.plan_id}`)
}

const viewApprovalDetail = (record: PaymentRecordWithDetails): void => {
  if (record.approval_id !== undefined && record.approval_id !== null) {
    router.push(`/approvals/${record.approval_id}`)
  } else {
    ElMessage.warning('该记录尚未提交审批')
  }
}

// Task 7.2: Confirm payment record (finance action)
const handleConfirmPayment = async (record: PaymentRecordWithDetails): Promise<void> => {
  if (submittingRecordId.value !== null) return

  submittingRecordId.value = record.id
  try {
    // Call approval store to confirm payment (bypasses approval if configured)
    const res = await approvalStore.submitEntity('PAYMENT', record.id)
    if (res.approval_id === 0) {
      ElMessage.success('已直接确认为财务确认状态')
    } else {
      ElMessage.success('已提交审批，等待审批人处理')
    }
    fetchPaymentRecords()
    paymentPlansStore.fetchBadgeCounts()
  } catch {
    // Error handled by interceptor
  } finally {
    submittingRecordId.value = null
  }
}

// Check if confirm button should be shown
const canConfirmPayment = (record: PaymentRecordWithDetails): boolean => {
  return (
    record.confirmation_status === 'PENDING' &&
    (record.approval_id === undefined || record.approval_id === null) &&
    permissionStore.hasPermission(paymentConfirmPermission)
  )
}

// Fetch badge counts on mount
onMounted(() => {
  fetchPaymentRecords()
  paymentPlansStore.fetchBadgeCounts()
})

// Watch for badge count updates
watch(() => paymentPlansStore.pendingApprovalMeCount, () => {
  // Badge on approval filter updates automatically
})
</script>

<template>
  <div class="payment-record-view">
    <!-- Task 7.2: Filter-tabs with Badge -->
    <div class="filter-tabs-bar">
      <div class="filter-tabs">
        <span
          v-for="tab in tabs"
          :key="tab.key"
          :class="['filter-tab', { active: activeTab === tab.key }]"
          @click="handleTabChange(tab.key)"
        >
          <span class="tab-label">{{ tab.label }}</span>
          <!-- Task 7.2: Badge with margin-left positioning for pending_approval_me_count -->
          <el-badge
            v-if="tab.showBadge && paymentPlansStore.pendingApprovalMeCount > 0"
            :value="paymentPlansStore.pendingApprovalMeCount"
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
            placeholder="搜索合同/客户/阶段名称"
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
    <template v-if="loading && paymentRecords.length === 0">
      <div class="table-card">
        <div class="payment-skeleton-table">
          <div v-for="i in 5" :key="i" class="skeleton-row">
            <div class="skeleton-cell skeleton-cell-name"></div>
            <div class="skeleton-cell skeleton-cell-name"></div>
            <div class="skeleton-cell skeleton-cell-amount"></div>
            <div class="skeleton-cell skeleton-cell-date"></div>
            <div class="skeleton-cell skeleton-cell-status"></div>
            <div class="skeleton-cell skeleton-cell-status"></div>
            <div class="skeleton-cell skeleton-cell-owner"></div>
          </div>
        </div>
      </div>
    </template>

    <!-- Task 7.2: Empty state -->
    <template v-else-if="!loading && paymentRecords.length === 0">
      <PaymentEmptyState type="no-records" :show-action="true" />
    </template>

    <!-- Table -->
    <template v-else>
      <div class="table-card payment-table-responsive payment-table-mobile-scroll">
        <el-table
          :data="paymentRecords"
          v-loading="loading"
          stripe
          style="width: 100%"
          :key="activeTab"
        >
          <!-- Task 7.2: 12 columns -->
          <el-table-column prop="customer_name" label="客户名称" min-width="150">
            <template #default="{ row }">
              <!-- Task 7.4: Deep-link highlight -->
              <span
                :class="['link-text', { 'deep-link-highlight': highlightedRecordId === row.id }]"
                @click="viewPlanDetail(row)"
              >
                {{ row.customer_name ?? '-' }}
              </span>
            </template>
          </el-table-column>

          <el-table-column prop="contract_name" label="合同名称" min-width="180">
            <template #default="{ row }">
              {{ row.contract_name ?? '-' }}
            </template>
          </el-table-column>

          <el-table-column prop="stage_name" label="回款阶段" min-width="120">
            <template #default="{ row }">
              {{ row.stage_name ?? '-' }}
            </template>
          </el-table-column>

          <!-- Task 7.2: Amount typography - mono-number, right alignment -->
          <el-table-column label="回款金额" min-width="120" align="right">
            <template #default="{ row }">
              <span class="payment-amount">{{ formatCurrency(row.actual_amount) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="回款日期" min-width="120">
            <template #default="{ row }">
              {{ formatDate(row.payment_date) }}
            </template>
          </el-table-column>

          <!-- Task 7.2: Confirmation status -->
          <el-table-column label="确认状态" min-width="100">
            <template #default="{ row }">
              <span :class="['status-tag', getConfirmationStatusClass(row.confirmation_status)]">
                {{ getConfirmationStatusText(row.confirmation_status) }}
              </span>
            </template>
          </el-table-column>

          <!-- Task 7.2: Approval status badge with pulse animation -->
          <el-table-column label="审批状态" min-width="120">
            <template #default="{ row }">
              <span :class="['approval-badge', getApprovalStatusClass(row.approval_status)]">
                <!-- Task 7.2: Pulse animation for "审批中" state -->
                <span v-if="row.approval_status === 'PENDING'" class="approval-pulse"></span>
                {{ getApprovalStatusText(row.approval_status) }}
              </span>
            </template>
          </el-table-column>

          <!-- Task 7.2: Current approver display -->
          <el-table-column label="当前审批人" min-width="120">
            <template #default="{ row }">
              <div v-if="row.approval_status === 'PENDING' && row.current_approver_name" class="current-approver-cell">
                <el-avatar :size="20" class="approver-avatar" />
                <span class="approver-name">{{ row.current_approver_name }}</span>
              </div>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>

          <!-- Task 7.2: Invoice application count -->
          <el-table-column label="发票申请数" min-width="100" align="right">
            <template #default="{ row }">
              <span class="mono-number">{{ row.invoice_application_count ?? 0 }}</span>
            </template>
          </el-table-column>

          <!-- Task 7.2: Notes column -->
          <el-table-column prop="notes" label="备注" min-width="150">
            <template #default="{ row }">
              {{ row.notes ?? '-' }}
            </template>
          </el-table-column>

          <!-- Task 7.5: Responsive - hide creator_name below 1024px -->
          <el-table-column
            v-if="showOwnerColumn"
            class-name="column-owner-name"
            prop="creator_name"
            label="登记人"
            min-width="100"
          >
            <template #default="{ row }">
              {{ row.creator_name ?? '-' }}
            </template>
          </el-table-column>

          <el-table-column label="登记时间" min-width="150">
            <template #default="{ row }">
              {{ formatDateTime(row.created_time) }}
            </template>
          </el-table-column>

          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <div class="action-cell">
                <span class="action-link" @click="viewPlanDetail(row)">查看计划</span>
                <!-- Task 7.2: View approval detail -->
                <span
                  v-if="row.approval_id !== undefined && row.approval_id !== null"
                  class="action-link"
                  @click="viewApprovalDetail(row)"
                >审批详情</span>
                <!-- Task 7.2: Row-level loading for confirm button -->
                <span
                  v-if="canConfirmPayment(row)"
                  class="action-link"
                  :class="{ 'row-action-loading': submittingRecordId === row.id }"
                  @click="handleConfirmPayment(row)"
                >
                  <template v-if="submittingRecordId === row.id">提交中...</template>
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
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;
@use '@/styles/payment.scss' as *;

.payment-record-view {
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

  // Neutral active state (no primary color)
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

// Task 7.2: Badge with margin-left positioning
.tab-badge {
  margin-left: $wolf-space-xs;

  .el-badge__content {
    font-family: $wolf-font-mono;
    font-variant-numeric: tabular-nums lining-nums;
    font-size: 10px;
  }
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

.text-muted {
  color: $wolf-text-tertiary;
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

// Task 7.2: Approval badge default state
.approval-badge-default {
  background: $wolf-bg-hover;
  color: $wolf-text-tertiary;
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
  .payment-record-view {
    padding: $wolf-space-md;
  }

  .search-input { width: 100%; }
  .filter-tabs { flex-wrap: wrap; }

  .filter-tab {
    padding: 6px $wolf-space-sm;
    font-size: $wolf-font-size-caption;
  }

  .table-card {
    overflow-x: auto;
  }
}
</style>