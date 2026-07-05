<!-- eslint-disable vue/multi-word-component-names -- 路由页面以资源名单词命名，重命名将破坏 router 注册与既有深链 -->
<template>
  <div class="payments-page">
    <!-- 快捷筛选标签 -->
    <div class="filter-tabs">
      <span
        :class="['filter-tab', { active: activeTab === 'pending' }]"
        @click="handleTabChange('pending')"
      >待处理回款</span>
      <span
        :class="['filter-tab', { active: activeTab === 'upcoming' }]"
        @click="handleTabChange('upcoming')"
      >即将到期</span>
      <span
        :class="['filter-tab', { active: activeTab === 'overdue' }]"
        @click="handleTabChange('overdue')"
      >已逾期</span>
      <span
        :class="['filter-tab', { active: activeTab === 'all' }]"
        @click="handleTabChange('all')"
      >全部计划</span>
      <span
        :class="['filter-tab', { active: activeTab === 'records' }]"
        @click="handleTabChange('records')"
      >回款记录</span>
    </div>

    <!-- 搜索筛选区 -->
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

    <!-- 表格区 -->
    <div class="table-card">
      <el-table
        v-if="activeTab !== 'records'"
        :data="paymentPlans"
        v-loading="loading"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="customer_name" label="客户名称" min-width="150">
          <template #default="{ row }">
            <span class="link-text" @click="viewDetail(row)">{{ row.customer_name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="contract_name" label="合同名称" min-width="180" />
        <el-table-column prop="stage_name" label="回款阶段" min-width="120" />
        <el-table-column label="计划金额" min-width="120">
          <template #default="{ row }">
            <span class="amount">{{ formatCurrency(row.planned_amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="已回款" min-width="120">
          <template #default="{ row }">
            <span class="paid">{{ formatCurrency(row.paid_amount || 0) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计划日期" min-width="120">
          <template #default="{ row }">
            {{ formatDate(row.due_date) }}
          </template>
        </el-table-column>
        <el-table-column v-if="activeTab === 'overdue'" label="逾期天数" width="100">
          <template #default="{ row }">
            <span class="overdue-days">{{ getOverdueDays(row.due_date) }} 天</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <span :class="['status-tag', getStatusClass(row.status)]">
              {{ getStatusText(row.status) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="owner_name" label="负责人" min-width="100" />
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <div class="action-cell">
              <span class="action-link" @click="viewDetail(row)">查看</span>
              <span
                v-if="row.status !== 'COMPLETED' && permissionStore.hasPermission('payment:register')"
                class="action-link"
                @click="handleRegisterPayment(row)"
              >登记回款</span>
              <el-button
                v-permission="paymentSubmitPermission"
                data-testid="submit-approval-btn"
                link
                type="primary"
                size="small"
                :loading="submittingApprovalId === row.id"
                :disabled="submittingApprovalId === row.id"
                class="action-link"
                @click="handleSubmitApproval(row)"
              >提交审批</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <el-table
        v-else
        :data="paymentRecords"
        v-loading="recordsLoading"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="contract_name" label="合同名称" min-width="180" />
        <el-table-column prop="stage_name" label="回款阶段" min-width="120" />
        <el-table-column label="回款金额" min-width="120">
          <template #default="{ row }">
            <span class="amount">¥{{ formatAmount(row.actual_amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="回款日期" min-width="120">
          <template #default="{ row }">
            {{ formatDate(row.payment_date) }}
          </template>
        </el-table-column>
        <el-table-column prop="creator_name" label="登记人" min-width="100" />
        <el-table-column prop="notes" label="备注" min-width="150" />
        <el-table-column label="登记时间" min-width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.created_time) }}
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-bar">
        <span class="total-text">共 {{ activeTab !== 'records' ? pagination.total : recordsPagination.total }} 条</span>
        <el-pagination
          v-if="activeTab !== 'records'"
          v-model:current-page="pagination.current"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          layout="sizes, prev, pager, next, jumper"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
        <el-pagination
          v-else
          v-model:current-page="recordsPagination.current"
          v-model:page-size="recordsPagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="recordsPagination.total"
          layout="sizes, prev, pager, next, jumper"
          @current-change="handleRecordsPageChange"
          @size-change="handleRecordsPageSizeChange"
        />
      </div>
    </div>

    <!-- 登记回款弹窗 -->
    <el-dialog
      v-model="paymentModalVisible"
      title="登记回款"
      width="500px"
    >
      <el-form :model="paymentForm" label-position="top">
        <el-form-item label="回款金额" required>
          <el-input-number v-model="paymentForm.actual_amount" placeholder="请输入回款金额" :min="0" :precision="2" :controls="false" style="width: 100%">
            <template #prefix>¥</template>
          </el-input-number>
          <div v-if="currentPlan" class="form-extra">
            待回款：¥{{ formatAmount(currentPlan.remaining_amount || 0) }}
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
          <el-input v-model="paymentForm.notes" type="textarea" placeholder="备注信息（可选）" :maxlength="200" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="paymentModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreatePayment">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { showError, showSuccess } from '@/utils/errorMessages'
import { Search } from '@element-plus/icons-vue'
import paymentApi, {
  type PaymentPlanWithDetails,
  type PaymentRecordWithDetails,
  type PaymentPlanListParams,
  type PaymentRecordListParams,
  type PaymentRecordCreate,
  type PaymentPlanStatus
} from '@/api/payment'
import { usePermissionStore } from '@/stores/permissions'
import { useApprovalStore } from '@/stores/approval'
import { formatCurrency } from '@/utils/format'
import { logger } from '@/utils/logger'

const router = useRouter()
const permissionStore = usePermissionStore()
const approvalStore = useApprovalStore()

// v-permission 门控：仅 payment:submit 持有者见「提交审批」按钮
const paymentSubmitPermission = 'payment:submit'

// 正在提交审批的回款计划 ID（按钮 :loading + :disabled 防双提交）
const submittingApprovalId = ref<number | null>(null)

const activeTab = ref('pending')
const searchForm = ref({
  keyword: '',
  status: '' as PaymentPlanStatus | ''
})
const loading = ref(false)
const recordsLoading = ref(false)

const paymentPlans = ref<PaymentPlanWithDetails[]>([])
const pagination = ref({
  current: 1,
  pageSize: 20,
  total: 0
})

const paymentRecords = ref<PaymentRecordWithDetails[]>([])
const recordsPagination = ref({
  current: 1,
  pageSize: 20,
  total: 0
})

const paymentModalVisible = ref(false)
const paymentForm = ref<PaymentRecordCreate>({
  actual_amount: 0,
  payment_date: ''
})
const currentPlan = ref<PaymentPlanWithDetails | null>(null)

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
  // Use local timezone, not UTC (toISOString() converts to UTC causing date offset in China)
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
      params.status = searchForm.value.status === '' ? 'PENDING' : searchForm.value.status
    } else if (activeTab.value === 'completed') {
      params.status = 'COMPLETED'
    } else if (activeTab.value === 'upcoming') {
      const upcomingDate = getUpcomingDate(7)
      params.due_date_end = upcomingDate
      params.status = 'PENDING'
    } else if (activeTab.value === 'overdue') {
      params.status = 'OVERDUE'
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
    logger.error('[Payments]', '获取回款计划失败', { error })
    showError(error, '获取回款计划')
  } finally {
    loading.value = false
  }
}

const fetchPaymentRecords = async (): Promise<void> => {
  recordsLoading.value = true
  try {
    const params: PaymentRecordListParams = {
      page: recordsPagination.value.current,
      page_size: recordsPagination.value.pageSize
    }

    const data = await paymentApi.listPaymentRecords(params)

    paymentRecords.value = data.items
    recordsPagination.value.total = data.total
  } catch (error) {
    logger.error('[Payments]', '获取回款记录失败', { error })
    showError(error, '获取回款记录')
  } finally {
    recordsLoading.value = false
  }
}

const handleTabChange = (key: string): void => {
  activeTab.value = key
  pagination.value.current = 1
  recordsPagination.value.current = 1
  searchForm.value.status = ''

  if (key === 'records') {
    fetchPaymentRecords()
  } else {
    fetchPaymentPlans()
  }
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

const handleRecordsPageChange = (page: number): void => {
  recordsPagination.value.current = page
  fetchPaymentRecords()
}

const handleRecordsPageSizeChange = (pageSize: number): void => {
  recordsPagination.value.pageSize = pageSize
  recordsPagination.value.current = 1
  fetchPaymentRecords()
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

const formatAmount = (amount: number): string => {
  return amount.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

const formatDate = (dateStr: string): string => {
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}

const formatDateTime = (dateStr: string): string => {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const viewDetail = (plan: PaymentPlanWithDetails): void => {
  if (plan.contract_id) {
    router.push(`/contracts/${plan.contract_id}`)
  }
}

const handleRegisterPayment = (plan: PaymentPlanWithDetails): void => {
  currentPlan.value = plan
  paymentForm.value = {
    actual_amount: 0,
    payment_date: ''
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

  if (currentPlan.value) {
    try {
      await paymentApi.createPaymentRecord(currentPlan.value.id, paymentForm.value)
      showSuccess('登记', '回款')
      paymentModalVisible.value = false
      fetchPaymentPlans()
    } catch (error: unknown) {
      logger.error('[Payments]', '登记回款失败', { error })
      showError(error, '登记回款')
    }
  }
}

// 提交审批（Phase C / Task C3）：调通用审批 store，PAYMENT 类型 + 计划 ID。
// 后端 match_flow_generic(PAYMENT) 未匹配到流时直通（approval_id=0, APPROVED），
// 此处按响应 toast；未配置流时提示「未配置审批流，已转为财务确认」。
const handleSubmitApproval = async (plan: PaymentPlanWithDetails): Promise<void> => {
  if (submittingApprovalId.value !== null) return
  submittingApprovalId.value = plan.id
  try {
    const res = await approvalStore.submitEntity('PAYMENT', plan.id)
    if (res.approval_id === 0) {
      // E5：未配置审批流，后端直通财务确认
      ElMessage.success('未配置审批流，已转为财务确认')
    } else {
      ElMessage.success('已提交审批，等待审批人处理')
    }
    fetchPaymentPlans()
  } catch {
    // 错误 toast 由 request 拦截器统一处理
  } finally {
    submittingApprovalId.value = null
  }
}

onMounted(() => {
  fetchPaymentPlans()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.payments-page {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

// 快捷筛选标签
.filter-tabs {
  display: flex;
  gap: $wolf-space-xs;
  margin-bottom: $wolf-space-md;
}

.filter-tab {
  padding: 8px $wolf-space-md;
  font-size: $wolf-font-size-auxiliary;
  font-weight: $wolf-font-weight-normal;
  color: $wolf-text-tertiary;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-sm;
  cursor: pointer;
  transition: all 0.2s ease-in-out;

  &:hover {
    background: $wolf-bg-hover;
    color: $wolf-text-secondary;
  }

  &.active {
    background: $wolf-bg-hover;
    color: $wolf-text-secondary;
    font-weight: $wolf-font-weight-medium;
  }
}

// 筛选区
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

// 表格样式由全局 wolf-design.scss 统一控制
.table-card {
  background: transparent;
  overflow: visible;
}

// 链接样式
.link-text {
  color: $wolf-text-link;
  cursor: pointer;
  font-weight: $wolf-font-weight-medium;
  &:hover {
    color: $wolf-text-link-hover;
  }
}

// 状态标签（浅底色 + 同色系文字）
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

// 操作区
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

.amount {
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-primary;
}

.paid {
  color: $wolf-success-text;
  font-weight: $wolf-font-weight-medium;
}

.overdue-days {
  color: $wolf-danger-text;
  font-weight: $wolf-font-weight-semibold;
}

// 分页
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

.form-extra {
  color: $wolf-text-secondary;
  font-size: $wolf-font-size-caption;
  margin-top: $wolf-space-xs;
}

// 响应式
@media (max-width: 768px) {
  .payments-page { padding: $wolf-space-md; }
  .search-input { width: 100%; }
  .filter-tabs { flex-wrap: wrap; }
}
</style>