<template>
  <div class="page-container">
    <div class="filter-card">
      <el-form :model="searchForm" :inline="true">
        <el-form-item label="客户名称">
          <el-input v-model="searchForm.customer_name" placeholder="请输入客户名称" clearable />
        </el-form-item>
        <el-form-item label="合同名称">
          <el-input v-model="searchForm.contract_name" placeholder="请输入合同名称" clearable />
        </el-form-item>
        <el-form-item label="付款日期">
          <el-date-picker v-model="searchForm.payment_date_range" type="daterange" style="width: 280px" />
        </el-form-item>
        <el-form-item>
          <el-button size="small" :icon="Search" @click="handleSearch">搜索</el-button>
        </el-form-item>
        <el-form-item>
          <el-button size="small" @click="handleReset">重置</el-button>
        </el-form-item>
        <el-form-item>
          <el-button size="small" :icon="Refresh" @click="fetchData">刷新</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="table-card">
      <div class="card-header">
        <span class="card-title">待确认回款列表</span>
        <span class="card-tag">{{ tableData.length }} 笔待确认</span>
      </div>

      <el-table
        :data="tableData"
        v-loading="loading"
        :border="false"
        stripe
        style="width: 100%"
      >
        <el-table-column label="合同名称" width="180">
          <template #default="{ row }">
            <el-link type="primary" @click="viewDetail(row)">
              {{ row.contract_name }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column prop="customer_name" label="客户名称" width="150" />
        <el-table-column prop="stage_name" label="付款阶段" width="120" />
        <el-table-column label="付款金额" width="120">
          <template #default="{ row }">
            <span class="amount">¥{{ formatAmount(row.actual_amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="payment_date" label="付款日期" width="120" />
        <el-table-column prop="created_time" label="登记时间" width="160" />
        <el-table-column prop="notes" label="备注" width="200">
          <template #default="{ row }">
            <span class="notes">{{ row.notes || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" :icon="Check" @click="confirmPayment(row)">
              确认入账
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="pagination.current"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </div>
    </div>

    <el-dialog
      v-model="confirmModalVisible"
      title="确认回款入账"
      width="600px"
    >
      <div v-if="currentRecord" class="confirm-modal-content">
        <el-alert type="info" style="margin-bottom: 16px">
          请核对以下信息，确认后该笔回款将正式入账
        </el-alert>

        <el-descriptions :column="2" border>
          <el-descriptions-item label="合同名称" :span="2">
            {{ currentRecord.contract_name }}
          </el-descriptions-item>
          <el-descriptions-item label="客户名称">
            {{ currentRecord.customer_name }}
          </el-descriptions-item>
          <el-descriptions-item label="付款阶段">
            {{ currentRecord.stage_name }}
          </el-descriptions-item>
          <el-descriptions-item label="付款金额">
            <span class="amount">¥{{ formatAmount(currentRecord.actual_amount) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="付款日期">
            {{ currentRecord.payment_date }}
          </el-descriptions-item>
          <el-descriptions-item label="登记备注" :span="2">
            {{ currentRecord.notes || '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <el-divider />

        <el-form :model="confirmForm" label-position="top">
          <el-form-item label="确认备注（可选）">
            <el-input
              v-model="confirmForm.notes"
              type="textarea"
              placeholder="请输入确认备注"
              :maxlength="500"
              show-word-limit
            />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button size="small" @click="confirmModalVisible = false">取消</el-button>
        <el-button type="primary" size="small" @click="handleConfirmPayment" :loading="confirming">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { showError, showSuccess } from '@/utils/errorMessages'
import { Refresh, Search, Check } from '@element-plus/icons-vue'
import financeApi, { type PendingPaymentConfirmation, type PaymentConfirmationRequest } from '@/api/finance'

const loading = ref(false)
const confirming = ref(false)
const tableData = ref<PendingPaymentConfirmation[]>([])
const confirmModalVisible = ref(false)
const currentRecord = ref<PendingPaymentConfirmation | null>(null)
const confirmForm = reactive<PaymentConfirmationRequest>({
  action: 'confirm',
  notes: ''
})

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

const searchForm = reactive({
  customer_name: '',
  contract_name: '',
  payment_date_range: [] as (Date | undefined)[]
})

const fetchData = async () => {
  loading.value = true
  try {
    const response = await financeApi.getPendingPaymentConfirmations()
    tableData.value = response || []
    pagination.total = response?.length || 0
  } catch (error) {
    console.error('获取待确认回款列表失败', error)
    showError(error, '获取待确认回款列表')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.current = 1
  fetchData()
}

const handleReset = () => {
  searchForm.customer_name = ''
  searchForm.contract_name = ''
  searchForm.payment_date_range = []
  handleSearch()
}

const handlePageChange = (page: number) => {
  pagination.current = page
}

const handlePageSizeChange = (pageSize: number) => {
  pagination.pageSize = pageSize
  pagination.current = 1
}

const viewDetail = (record: PendingPaymentConfirmation) => {
  currentRecord.value = record
  confirmModalVisible.value = true
}

const confirmPayment = (record: PendingPaymentConfirmation) => {
  currentRecord.value = record
  confirmForm.action = 'confirm'
  confirmForm.notes = ''
  confirmModalVisible.value = true
}

const handleConfirmPayment = async () => {
  if (!currentRecord.value) return

  confirming.value = true
  try {
    await financeApi.confirmPayment(currentRecord.value.id, confirmForm)
    showSuccess('确认', '回款')
    confirmModalVisible.value = false
    fetchData()
  } catch (error) {
    console.error('确认回款失败', error)
    showError(error, '确认回款')
  } finally {
    confirming.value = false
  }
}

const formatAmount = (amount: string) => {
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  return num.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

onMounted(() => {
  fetchData()
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
  padding: $wolf-space-md;
  margin-bottom: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
}

.table-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
}

.card-header {
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
  margin-bottom: $wolf-space-md;
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
  color: $wolf-warning-text;
  background: $wolf-warning-bg;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  padding: $wolf-space-md 0;
}

.amount {
  font-weight: $wolf-font-weight-medium;
  color: $wolf-success-text;
}

.notes {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  text-overflow: ellipsis;
  color: $wolf-text-tertiary;
}

.confirm-modal-content {
  padding: $wolf-space-md 0;
}
</style>
