<template>
  <div class="page-container">
    <div class="filter-card">
      <el-form :model="filterForm" :inline="true">
        <el-form-item label="报表类型">
          <el-select v-model="filterForm.reportType" placeholder="请选择报表类型" style="width: 150px">
            <el-option value="aging" label="应收账款账龄" />
            <el-option value="revenue" label="收入统计" />
            <el-option value="overdue" label="逾期预警" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker v-model="filterForm.dateRange" type="daterange" style="width: 280px" />
        </el-form-item>
        <el-form-item>
          <el-button size="small" :icon="Search" @click="handleFilter">查询</el-button>
        </el-form-item>
        <el-form-item>
          <el-button size="small" @click="handleReset">重置</el-button>
        </el-form-item>
        <el-form-item>
          <el-button size="small" :icon="Download" @click="handleExportExcel">导出报表</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="tabs-card">
      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <el-tab-pane label="应收账款账龄" name="aging" />
        <el-tab-pane label="收入统计" name="revenue" />
        <el-tab-pane label="逾期预警" name="overdue" />
      </el-tabs>
    </div>

    <div class="content-card" v-loading="loading">
      <div v-if="activeTab === 'aging'" class="aging-report">
        <div class="report-header">
          <h3>应收账款账龄分析</h3>
          <div class="header-info">
            <span class="total-amount">总逾期金额: ¥{{ formatCurrency(agingAnalysis.total_overdue) }}</span>
            <span class="analysis-date">分析日期: {{ agingAnalysis.analysis_date }}</span>
          </div>
        </div>

        <div class="aging-chart">
          <div v-for="item in agingAnalysis.aging_data" :key="item.range" class="aging-item">
            <div class="aging-label">{{ item.range }}</div>
            <div class="aging-bar-container">
              <div
                class="aging-bar"
                :style="{ width: getAagingBarWidth(item.amount), backgroundColor: getAgingColor(item.range) }"
              >
                <span class="aging-amount">¥{{ formatCurrency(item.amount) }}</span>
              </div>
            </div>
            <div class="aging-count">{{ item.count }}笔</div>
          </div>
        </div>

        <el-divider />

        <el-table
          :data="agingAnalysis.aging_data"
          stripe
          style="width: 100%"
        >
          <el-table-column prop="range" label="账龄区间" />
          <el-table-column label="金额">
            <template #default="{ row }">
              <span class="amount">¥{{ formatCurrency(row.amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="count" label="笔数" />
          <el-table-column label="占比">
            <template #default="{ row }">
              {{ getAgingPercentage(row.amount) }}%
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div v-if="activeTab === 'revenue'" class="revenue-report">
        <div class="report-header">
          <h3>合同收入统计</h3>
        </div>

        <el-table
          :data="revenueStats"
          stripe
          style="width: 100%"
        >
          <el-table-column prop="contract_name" label="合同名称" />
          <el-table-column prop="customer_name" label="客户名称" />
          <el-table-column label="合同总额">
            <template #default="{ row }">
              <span class="total-amount">¥{{ formatCurrency(row.total_amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="已回款">
            <template #default="{ row }">
              <span class="paid-amount">¥{{ formatCurrency(row.paid_amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="待回款">
            <template #default="{ row }">
              <span class="remaining-amount">¥{{ formatCurrency(row.remaining_amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="回款进度">
            <template #default="{ row }">
              <el-progress
                :percentage="row.payment_progress"
                :color="getProgressColor(row.payment_progress)"
              />
            </template>
          </el-table-column>
          <el-table-column prop="signing_date" label="签约日期" />
        </el-table>

        <div class="pagination-bar">
          <el-pagination
            v-model:current-page="revenuePagination.current"
            v-model:page-size="revenuePagination.pageSize"
            :total="revenuePagination.total"
            :page-sizes="[10, 20, 50]"
            layout="total, sizes, prev, pager, next"
            @current-change="handleRevenuePageChange"
          />
        </div>
      </div>

      <div v-if="activeTab === 'overdue'" class="overdue-report">
        <div class="report-header">
          <h3>逾期回款预警</h3>
          <span class="alert-tag">{{ overdueAlerts.length }} 笔逾期</span>
        </div>

        <el-table
          :data="overdueAlerts"
          stripe
          style="width: 100%"
        >
          <el-table-column prop="contract_name" label="合同名称" />
          <el-table-column prop="customer_name" label="客户名称" />
          <el-table-column prop="stage_name" label="付款阶段" />
          <el-table-column label="计划金额">
            <template #default="{ row }">
              <span class="amount">¥{{ formatCurrency(row.planned_amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="due_date" label="计划日期" />
          <el-table-column label="逾期天数">
            <template #default="{ row }">
              <span class="overdue-tag">{{ row.overdue_days }}天</span>
            </template>
          </el-table-column>
          <el-table-column prop="owner_name" label="负责人" />
          <el-table-column label="操作">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="goToContract(row.contract_id)">查看合同</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-bar">
          <el-pagination
            v-model:current-page="overduePagination.current"
            v-model:page-size="overduePagination.pageSize"
            :total="overduePagination.total"
            :page-sizes="[10, 20, 50]"
            layout="total, sizes, prev, pager, next"
            @current-change="handleOverduePageChange"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { showError } from '@/utils/errorMessages'
import { Download, Search } from '@element-plus/icons-vue'
import financeApi, { type AccountAgingAnalysis, type ContractRevenueStats, type OverduePaymentAlert } from '@/api/finance'

const router = useRouter()

const loading = ref(false)
const activeTab = ref('aging')

const agingAnalysis = ref<AccountAgingAnalysis>({
  aging_data: [],
  total_overdue: '0',
  analysis_date: ''
})

const revenueStats = ref<ContractRevenueStats[]>([])
const overdueAlerts = ref<OverduePaymentAlert[]>([])

const revenuePagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0
})

const overduePagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0
})

const filterForm = reactive({
  reportType: 'aging',
  dateRange: [] as (Date | undefined)[]
})

const fetchAgingAnalysis = async () => {
  loading.value = true
  try {
    const response = await financeApi.getAccountAgingAnalysis() as any
    agingAnalysis.value = response || { aging_data: [], total_overdue: '0', analysis_date: '' }
  } catch (error) {
    console.error('获取账龄分析失败', error)
    showError(error, '获取账龄分析')
  } finally {
    loading.value = false
  }
}

const fetchRevenueStats = async () => {
  loading.value = true
  try {
    const response = await financeApi.getContractRevenueStats() as any
    revenueStats.value = response || []
    revenuePagination.total = response?.length || 0
  } catch (error) {
    console.error('获取收入统计失败', error)
    showError(error, '获取收入统计')
  } finally {
    loading.value = false
  }
}

const fetchOverdueAlerts = async () => {
  loading.value = true
  try {
    const response = await financeApi.getOverduePaymentAlerts() as any
    overdueAlerts.value = response || []
    overduePagination.total = response?.length || 0
  } catch (error) {
    console.error('获取逾期预警失败', error)
    showError(error, '获取逾期预警')
  } finally {
    loading.value = false
  }
}

const handleTabChange = (key: string) => {
  activeTab.value = key
  filterForm.reportType = key
  if (key === 'aging') fetchAgingAnalysis()
  else if (key === 'revenue') fetchRevenueStats()
  else if (key === 'overdue') fetchOverdueAlerts()
}

const handleFilter = () => {
  if (filterForm.reportType === 'aging') fetchAgingAnalysis()
  else if (filterForm.reportType === 'revenue') fetchRevenueStats()
  else if (filterForm.reportType === 'overdue') fetchOverdueAlerts()
}

const handleReset = () => {
  filterForm.dateRange = []
  handleFilter()
}

const handleRevenuePageChange = (page: number) => {
  revenuePagination.current = page
}

const handleOverduePageChange = (page: number) => {
  overduePagination.current = page
}

// TODO: 导出功能待实现
const handleExportExcel = () => {
  // 导出功能开发中...
}

const goToContract = (contractId: number) => {
  router.push(`/contracts/${contractId}`)
}

const formatCurrency = (amount: string | number) => {
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  return num.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

const getAagingBarWidth = (amount: string) => {
  if (!agingAnalysis.value.aging_data || agingAnalysis.value.aging_data.length === 0) return '0%'
  const maxValue = Math.max(...agingAnalysis.value.aging_data.map(item => parseFloat(item.amount)))
  const currentValue = parseFloat(amount)
  if (maxValue === 0) return '0%'
  return `${(currentValue / maxValue) * 100}%`
}

const getAgingColor = (range: string) => {
  if (range.includes('0-30')) return '#2B633C'
  if (range.includes('31-60')) return '#7A4F1E'
  if (range.includes('61-90')) return '#7A4F1E'
  if (range.includes('90')) return '#7A2828'
  return '#4A6FA5'
}

const getAgingPercentage = (amount: string) => {
  if (!agingAnalysis.value.aging_data || agingAnalysis.value.aging_data.length === 0) return 0
  const total = agingAnalysis.value.aging_data.reduce((sum, item) => sum + parseFloat(item.amount), 0)
  if (total === 0) return 0
  return ((parseFloat(amount) / total) * 100).toFixed(1)
}

const getProgressColor = (percent: number) => {
  if (percent >= 80) return '#2B633C'
  if (percent >= 50) return '#7A4F1E'
  if (percent >= 20) return '#7A4F1E'
  return '#7A2828'
}

onMounted(() => {
  fetchAgingAnalysis()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.page-container {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

.filter-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-card-padding;
  margin-bottom: $wolf-card-gap;
  box-shadow: $wolf-shadow-card;
}

.tabs-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-sm $wolf-card-padding;
  margin-bottom: $wolf-card-gap;
  box-shadow: $wolf-shadow-card;
}

.content-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-card-padding;
  box-shadow: $wolf-shadow-card;
}

.report-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: $wolf-space-lg;

  h3 {
    margin: 0;
    font-size: $wolf-font-size-body;
    font-weight: $wolf-font-weight-medium;
    color: $wolf-text-primary;
  }
}

.header-info {
  display: flex;
  gap: $wolf-space-md;
}

.total-amount {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-danger-text;
}

.analysis-date {
  font-size: $wolf-font-size-auxiliary;
  color: $wolf-text-tertiary;
}

.alert-tag {
  font-size: $wolf-font-size-caption;
  padding: 2px 8px;
  border-radius: $wolf-radius-sm;
  color: $wolf-danger-text;
  background: $wolf-danger-bg;
}

.aging-chart {
  padding: $wolf-space-md 0;
}

.aging-item {
  display: flex;
  align-items: center;
  margin-bottom: $wolf-space-md;
}

.aging-label {
  width: 100px;
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-secondary;
}

.aging-bar-container {
  flex: 1;
  margin: 0 $wolf-space-md;
  background: $wolf-bg-hover;
  border-radius: $wolf-radius-sm;
  height: 40px;
  overflow: hidden;
}

.aging-bar {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: $wolf-space-md;
  transition: width 0.3s;
}

.aging-amount {
  color: $wolf-text-inverse;
  font-weight: $wolf-font-weight-medium;
  font-size: $wolf-font-size-auxiliary;
}

.aging-count {
  width: 80px;
  text-align: right;
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  padding: $wolf-space-md 0;
}

.amount {
  font-weight: $wolf-font-weight-medium;
  color: $wolf-warning-text;
}

.total-amount {
  font-weight: $wolf-font-weight-medium;
  color: $wolf-primary;
}

.paid-amount {
  font-weight: $wolf-font-weight-medium;
  color: $wolf-success-text;
}

.remaining-amount {
  font-weight: $wolf-font-weight-medium;
  color: $wolf-warning-text;
}

.overdue-tag {
  font-size: $wolf-font-size-caption;
  padding: 2px 8px;
  border-radius: $wolf-radius-sm;
  color: $wolf-danger-text;
  background: $wolf-danger-bg;
}
</style>
