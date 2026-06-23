<template>
  <div class="page-container">
    <!-- 操作区 -->
    <div class="action-bar">
      <el-button size="small" @click="fetchDashboardStats">
        <el-icon><Refresh /></el-icon>
        刷新数据
      </el-button>
    </div>

    <el-row :gutter="16">
      <el-col :span="18">
        <el-row :gutter="16">
          <el-col :span="8">
            <div class="stat-card" :class="{ 'is-loading': statsLoading }" @click="navigateTo('/invoices?status=PENDING_REVIEW')">
              <div class="stat-icon pending">
                <el-icon><Document /></el-icon>
              </div>
              <div class="stat-content">
                <div class="stat-value">{{ dashboardStats.pending_invoice_approvals }}</div>
                <div class="stat-label">待审批发票</div>
              </div>
              <div class="stat-footer">点击处理</div>
            </div>
          </el-col>

          <el-col :span="8">
            <div class="stat-card" :class="{ 'is-loading': statsLoading }" @click="navigateTo('/finance/payment-confirmations')">
              <div class="stat-icon warning">
                <el-icon><RefreshRight /></el-icon>
              </div>
              <div class="stat-content">
                <div class="stat-value">{{ dashboardStats.pending_payment_confirmations }}</div>
                <div class="stat-label">待确认回款</div>
              </div>
              <div class="stat-footer">点击处理</div>
            </div>
          </el-col>

          <el-col :span="8">
            <div class="stat-card" :class="{ 'is-loading': statsLoading }">
              <div class="stat-icon danger">
                <el-icon><Warning /></el-icon>
              </div>
              <div class="stat-content">
                <div class="stat-value danger">¥{{ formatCurrency(dashboardStats.overdue_amount) }}</div>
                <div class="stat-label">逾期款项总额</div>
              </div>
              <div class="stat-footer">需要关注</div>
            </div>
          </el-col>
        </el-row>

        <div class="chart-card">
          <div class="card-header">
            <span class="card-title">应收账款账龄分析</span>
            <el-button link size="small" @click="navigateTo('/finance/reports')">查看详情</el-button>
          </div>
          <div class="aging-chart" v-loading="agingLoading">
            <div v-for="item in agingData" :key="item.range" class="aging-item">
              <div class="aging-label">{{ item.range }}</div>
              <div class="aging-bar-container">
                <div class="aging-bar" :style="{ width: getAgingBarWidth(item.amount), backgroundColor: getAgingColor(item.range) }">
                  <span class="aging-amount">¥{{ formatCurrency(item.amount) }}</span>
                </div>
              </div>
              <div class="aging-count">{{ item.count }}笔</div>
            </div>
          </div>
        </div>

        <div class="chart-card">
          <div class="card-header">
            <span class="card-title">本月收入概览</span>
          </div>
          <el-row :gutter="16">
            <el-col :span="12">
              <div class="revenue-item">
                <div class="revenue-label">本月预计回款</div>
                <div class="revenue-value warning">¥{{ formatCurrency(dashboardStats.monthly_expected_revenue) }}</div>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="revenue-item">
                <div class="revenue-label">已确认回款</div>
                <div class="revenue-value success">¥{{ formatCurrency(dashboardStats.confirmed_revenue) }}</div>
              </div>
            </el-col>
          </el-row>
        </div>
      </el-col>

      <el-col :span="6">
        <div class="action-card">
          <div class="card-header">
            <span class="card-title">快捷操作</span>
          </div>
          <div class="action-list">
            <el-button size="small" @click="navigateTo('/finance/invoice-approvals')">
              <el-icon><Select /></el-icon>
              发票审批中心
            </el-button>
            <el-button size="small" @click="navigateTo('/finance/payment-confirmations')">
              <el-icon><CircleCheck /></el-icon>
              回款确认
            </el-button>
            <el-button size="small" @click="navigateTo('/finance/reports')">
              <el-icon><TrendCharts /></el-icon>
              财务报表
            </el-button>
            <el-button size="small" @click="navigateTo('/invoices')">
              <el-icon><Document /></el-icon>
              发票管理
            </el-button>
            <el-button size="small" @click="navigateTo('/payments')">
              <el-icon><Money /></el-icon>
              回款管理
            </el-button>
          </div>
        </div>

        <div class="alert-card" v-loading="alertsLoading">
          <div class="card-header">
            <span class="card-title">逾期预警</span>
            <el-button link size="small" @click="navigateTo('/finance/reports')">全部</el-button>
          </div>
          <div v-if="overdueAlerts.length > 0" class="alerts-list">
            <div v-for="alert in overdueAlerts.slice(0, 5)" :key="alert.contract_id" class="alert-item">
              <div class="alert-header">
                <span class="alert-customer">{{ alert.customer_name }}</span>
                <span class="alert-tag">{{ alert.overdue_days }}天</span>
              </div>
              <div class="alert-info">
                <div class="alert-contract">{{ alert.contract_name }}</div>
                <div class="alert-amount">¥{{ formatCurrency(alert.planned_amount) }}</div>
              </div>
            </div>
          </div>
          <el-empty v-else description="添加回款计划，预防逾期风险" :image-size="80" />
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Document,
  Refresh,
  RefreshRight,
  Warning,
  Select,
  CircleCheck,
  TrendCharts,
  Money
} from '@element-plus/icons-vue'
import financeApi, { type DashboardStats, type AccountAging, type OverduePaymentAlert } from '@/api/finance'
import invoiceApi from '@/api/invoice'

const router = useRouter()

const statsLoading = ref(false)
const agingLoading = ref(false)
const alertsLoading = ref(false)

const dashboardStats = ref<DashboardStats>({
  pending_invoice_approvals: 0,
  pending_payment_confirmations: 0,
  monthly_expected_revenue: '0',
  confirmed_revenue: '0',
  overdue_amount: '0'
})

const agingData = ref<AccountAging[]>([])
const overdueAlerts = ref<OverduePaymentAlert[]>([])
const selectedDate = ref<Date | undefined>(undefined)

const fetchDashboardStats = async () => {
  statsLoading.value = true
  try {
    const [statsResponse, pendingInvoices] = await Promise.all([
      financeApi.getDashboardStats() as any,
      invoiceApi.getInvoiceApplications({ status: 'PENDING_REVIEW', page: 1, page_size: 1 }) as any
    ])

    dashboardStats.value = statsResponse
    dashboardStats.value.pending_invoice_approvals = pendingInvoices.total || 0
  } catch (error) {
    console.error('获取统计数据失败', error)
  } finally {
    statsLoading.value = false
  }
}

const fetchAgingAnalysis = async () => {
  agingLoading.value = true
  try {
    const response = await financeApi.getAccountAgingAnalysis() as any
    agingData.value = response.aging_data || []
  } catch (error) {
    console.error('获取账龄分析失败', error)
  } finally {
    agingLoading.value = false
  }
}

const fetchOverdueAlerts = async () => {
  alertsLoading.value = true
  try {
    const response = await financeApi.getOverduePaymentAlerts({ days_overdue_min: 1, limit: 10 }) as any
    overdueAlerts.value = response || []
  } catch (error) {
    console.error('获取逾期预警失败', error)
  } finally {
    alertsLoading.value = false
  }
}

const navigateTo = (path: string) => {
  router.push(path)
}

const formatCurrency = (amount: string | number) => {
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  return num.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

const getAgingBarWidth = (amount: string) => {
  const maxValue = Math.max(...agingData.value.map(item => parseFloat(item.amount)))
  const currentValue = parseFloat(amount)
  return `${(currentValue / maxValue) * 100}%`
}

const getAgingColor = (range: string) => {
  if (range.includes('0-30')) return '#2B633C'
  if (range.includes('31-60')) return '#7A4F1E'
  if (range.includes('61-90')) return '#7A4F1E'
  if (range.includes('90')) return '#7A2828'
  return '#4A6FA5'
}

onMounted(() => {
  fetchDashboardStats()
  fetchAgingAnalysis()
  fetchOverdueAlerts()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.page-container {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

.action-bar {
  margin-bottom: $wolf-space-md;
}

// 统计卡片
.stat-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-card-padding;
  margin-bottom: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
  min-height: 120px;

  &:hover {
    transform: translateY(-2px);
    box-shadow: $wolf-shadow-hover;
  }
}

.stat-icon {
  width: 40px;
  height: 40px;
  border-radius: $wolf-radius-sm;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: $wolf-space-sm;
  font-size: 20px;
  color: $wolf-text-secondary;
  background: $wolf-bg-hover;

  &.pending {
    color: $wolf-warning-text;
    background: $wolf-warning-bg;
  }

  &.warning {
    color: $wolf-warning-text;
    background: $wolf-warning-bg;
  }

  &.danger {
    color: $wolf-danger-text;
    background: $wolf-danger-bg;
  }
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin-bottom: $wolf-space-xs;

  &.danger {
    color: $wolf-danger-text;
  }
}

.stat-label {
  font-size: $wolf-font-size-body;
  color: $wolf-text-tertiary;
}

.stat-footer {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-placeholder;
  margin-top: $wolf-space-sm;
}

// 图表卡片
.chart-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-card-padding;
  margin-bottom: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: $wolf-space-md;
}

.card-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
}

.aging-chart {
  padding: $wolf-space-sm 0;
}

.aging-item {
  display: flex;
  align-items: center;
  margin-bottom: $wolf-space-md;
}

.aging-label {
  width: 80px;
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-secondary;
}

.aging-bar-container {
  flex: 1;
  margin: 0 $wolf-space-md;
  background: $wolf-bg-hover;
  border-radius: $wolf-radius-sm;
  height: 32px;
  overflow: hidden;
}

.aging-bar {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: $wolf-space-md;
  transition: width 0.3s ease;
}

.aging-amount {
  color: $wolf-text-inverse;
  font-weight: $wolf-font-weight-medium;
  font-size: $wolf-font-size-auxiliary;
}

.aging-count {
  width: 60px;
  text-align: right;
  color: $wolf-text-tertiary;
  font-size: $wolf-font-size-caption;
}

// 收入概览
.revenue-item {
  padding: $wolf-space-md;
  border-radius: $wolf-radius-sm;
  background: $wolf-bg-hover;
  text-align: center;
}

.revenue-label {
  font-size: $wolf-font-size-body;
  color: $wolf-text-tertiary;
  margin-bottom: $wolf-space-sm;
}

.revenue-value {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;

  &.warning {
    color: $wolf-warning-text;
  }

  &.success {
    color: $wolf-success-text;
  }
}

// 快捷操作卡片
.action-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-card-padding;
  box-shadow: $wolf-shadow-card;
  margin-bottom: $wolf-space-md;
}

.action-list {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm;

  .el-button {
    width: 100%;
    justify-content: flex-start;
    background: $wolf-bg-hover;
    border: none;
    color: $wolf-text-secondary;

    &:hover {
      background: $wolf-bg-hover;
      color: $wolf-text-primary;
    }
  }
}

// 预警卡片
.alert-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-card-padding;
  box-shadow: $wolf-shadow-card;
}

.alerts-list {
  max-height: 300px;
  overflow-y: auto;
}

.alert-item {
  padding: $wolf-space-sm;
  border-bottom: 1px solid $wolf-border-light;

  &:last-child {
    border-bottom: none;
  }
}

.alert-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: $wolf-space-xs;
}

.alert-customer {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
}

.alert-tag {
  font-size: $wolf-font-size-caption;
  padding: 2px 8px;
  border-radius: $wolf-radius-sm;
  color: $wolf-danger-text;
  background: $wolf-danger-bg;
}

.alert-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.alert-contract {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  flex: 1;
}

.alert-amount {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-danger-text;
}
</style>
