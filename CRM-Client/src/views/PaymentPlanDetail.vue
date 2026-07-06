<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, InfoFilled } from '@element-plus/icons-vue'
import paymentApi, {
  type PaymentPlanResponse,
  type PaymentRecordCreate,
  type PaymentPlanStatus
} from '@/api/payment'
import { useApprovalStore } from '@/stores/approval'
import PaymentRecordList from '@/components/PaymentRecordList.vue'
import { formatCurrency } from '@/utils/format'
import { showError, showSuccess } from '@/utils/errorMessages'
import { logger } from '@/utils/logger'

const route = useRoute()
const router = useRouter()
const approvalStore = useApprovalStore()

const planId = Number(route.params['id'])
const plan = ref<PaymentPlanResponse | null>(null)
const loading = ref(true)

// Payment dialog state
const paymentModalVisible = ref(false)
const paymentForm = ref<PaymentRecordCreate>({
  actual_amount: 0,
  payment_date: ''
})

// Approval submission loading state
const submittingApproval = ref(false)

// Computed: has pending payment record (confirmation_status === 'PENDING' and no approval submitted)
const hasPendingRecord = computed(() => {
  if (!plan.value?.payment_records || plan.value.payment_records.length === 0) return false
  const latestRecord = plan.value.payment_records[plan.value.payment_records.length - 1]
  return latestRecord?.confirmation_status === 'PENDING'
})

// Computed: has approval in progress (submitted but not confirmed)
const hasPendingApproval = computed(() => {
  if (!plan.value?.payment_records || plan.value.payment_records.length === 0) return false
  // Check if any record has pending approval
  return plan.value.payment_records.some(record =>
    record.confirmation_status === 'PENDING' && record.id !== undefined
  )
})

// Fetch plan detail
const fetchPlanDetail = async (): Promise<void> => {
  loading.value = true
  try {
    plan.value = await paymentApi.getPaymentPlanDetail(planId)
  } catch (error) {
    logger.error('[PaymentPlanDetail]', '获取计划详情失败', { error })
    showError(error, '获取计划详情')
    router.push('/payments')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchPlanDetail()
})

// Status helpers
const getStatusType = (status: PaymentPlanStatus): string => {
  const statusMap: Record<PaymentPlanStatus, string> = {
    'PENDING': 'info',
    'OVERDUE': 'danger',
    'PARTIAL': 'warning',
    'COMPLETED': 'success'
  }
  return statusMap[status] ?? 'info'
}

const getStatusLabel = (status: PaymentPlanStatus): string => {
  const statusMap: Record<PaymentPlanStatus, string> = {
    'PENDING': '待回款',
    'OVERDUE': '已逾期',
    'PARTIAL': '部分回款',
    'COMPLETED': '已完成'
  }
  return statusMap[status] ?? status
}

// Format date
const formatDate = (dateStr: string): string => {
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}

// Open register payment dialog
const handleRegisterPayment = (): void => {
  paymentForm.value = {
    actual_amount: 0,
    payment_date: ''
  }
  paymentModalVisible.value = true
}

// Create payment record
const handleCreatePayment = async (): Promise<void> => {
  if (paymentForm.value.actual_amount === null || paymentForm.value.actual_amount <= 0) {
    ElMessage.error('请输入有效的回款金额')
    return
  }

  if (paymentForm.value.payment_date.length === 0) {
    ElMessage.error('请选择回款日期')
    return
  }

  try {
    await paymentApi.createPaymentRecord(planId, paymentForm.value)
    showSuccess('登记', '回款')
    paymentModalVisible.value = false
    fetchPlanDetail()
  } catch (error: unknown) {
    logger.error('[PaymentPlanDetail]', '登记回款失败', { error })
    showError(error, '登记回款')
  }
}

// Submit approval for the latest payment record
const handleSubmitApproval = async (): Promise<void> => {
  if (submittingApproval.value) return
  submittingApproval.value = true

  try {
    // Get the latest payment record ID (assuming the last one needs approval)
    const latestRecord = plan.value?.payment_records[plan.value.payment_records.length - 1]
    if (!latestRecord) {
      ElMessage.error('没有可提交审批的回款记录')
      return
    }

    const res = await approvalStore.submitEntity('PAYMENT', latestRecord.id)
    if (res.approval_id === 0) {
      // No approval flow configured, direct to finance confirmation
      ElMessage.success('未配置审批流，已转为财务确认')
    } else {
      ElMessage.success('已提交审批，等待审批人处理')
    }
    fetchPlanDetail()
  } catch {
    // Error toast handled by request interceptor
  } finally {
    submittingApproval.value = false
  }
}

// Navigate to contract detail
const viewContract = (): void => {
  if (plan.value?.contract_id !== undefined && plan.value.contract_id > 0) {
    router.push(`/contracts/${plan.value.contract_id}`)
  }
}

// Navigate to approval center
const viewApprovalDetail = (): void => {
  router.push(`/approvals?business_type=PAYMENT&business_id=${planId}`)
}
</script>

<template>
  <div class="payment-plan-detail" v-loading="loading">
    <!-- Plan info card -->
    <el-card class="plan-info-card">
      <template #header>
        <div class="card-header">
          <span>回款计划详情</span>
          <el-button text @click="router.push('/payments')">返回列表</el-button>
        </div>
      </template>

      <el-descriptions :column="2" border>
        <el-descriptions-item label="客户名称">
          <span class="link-text" @click="viewContract">{{ plan?.customer_name || '未知' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="合同名称">
          <span class="link-text" @click="viewContract">{{ plan?.contract_name || '未知' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="回款阶段">{{ plan?.stage_name }}</el-descriptions-item>
        <el-descriptions-item label="计划金额">
          <span class="amount">{{ formatCurrency(plan?.planned_amount ?? 0) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="计划日期">{{ formatDate(plan?.due_date ?? '') }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusType(plan?.status ?? 'PENDING')" size="small">
            {{ getStatusLabel(plan?.status ?? 'PENDING') }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="待回款金额">
          <span class="remaining">{{ formatCurrency(plan?.remaining_amount ?? 0) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="累计回款">
          <span class="paid">{{ formatCurrency(plan?.paid_amount ?? 0) }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- Payment records list -->
    <el-card class="records-card">
      <template #header>
        <div class="card-header">
          <span>回款记录</span>
          <el-button
            v-if="plan?.status !== 'COMPLETED'"
            type="primary"
            size="small"
            @click="handleRegisterPayment"
          >
            <el-icon><Plus /></el-icon>
            登记回款
          </el-button>
        </div>
      </template>

      <PaymentRecordList :records="plan?.payment_records || []" @register="handleRegisterPayment" />
    </el-card>

    <!-- Approval progress (if there are pending records) -->
    <el-card v-if="hasPendingApproval" class="approval-card">
      <template #header>
        <div class="card-header">
          <span>审批进度</span>
          <el-button text type="primary" @click="viewApprovalDetail">查看详情</el-button>
        </div>
      </template>

      <!-- Task 6.7: Approval status visual hierarchy -->
      <el-descriptions :column="1" border>
        <el-descriptions-item label="审批状态">
          <el-tag type="warning" size="small">审批中</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="审批人">
          <div class="approver-info">
            <el-avatar :size="24" />
            <span class="approver-name">待分配</span>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="说明">该回款记录已提交审批，等待审批人处理</el-descriptions-item>
      </el-descriptions>

      <!-- Task 6.7: Current approver highlight -->
      <div class="current-approver-hint">
        <el-icon><InfoFilled /></el-icon>
        <span>审批通过后，回款状态将自动更新为"已确认"</span>
      </div>
    </el-card>

    <!-- Action buttons -->
    <div class="action-buttons">
      <el-button
        v-if="plan?.status !== 'COMPLETED' && hasPendingRecord"
        type="primary"
        :loading="submittingApproval"
        :disabled="submittingApproval"
        @click="handleSubmitApproval"
      >
        提交审批
      </el-button>
      <el-button @click="router.push('/payments')">返回列表</el-button>
    </div>

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
          <div v-if="plan" class="form-extra">
            待回款：{{ formatCurrency(plan.remaining_amount ?? 0) }}
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

.payment-plan-detail {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

.plan-info-card,
.records-card,
.approval-card {
  margin-bottom: $wolf-space-md;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.link-text {
  color: $wolf-text-link;
  cursor: pointer;
  font-weight: $wolf-font-weight-medium;
  &:hover {
    color: $wolf-text-link-hover;
  }
}

.amount {
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-primary;
}

.paid {
  color: $wolf-success-text;
  font-weight: $wolf-font-weight-medium;
}

.remaining {
  color: $wolf-warning-text;
  font-weight: $wolf-font-weight-medium;
}

.action-buttons {
  margin-top: $wolf-space-lg;
  display: flex;
  gap: $wolf-space-sm;
}

.form-extra {
  color: $wolf-text-secondary;
  font-size: $wolf-font-size-caption;
  margin-top: $wolf-space-xs;
}

// Task 6.7: Approver visual hierarchy styles
.approver-info {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.approver-name {
  font-weight: $wolf-font-weight-medium;
}

.current-approver-hint {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  margin-top: $wolf-space-md;
  padding: $wolf-space-md;
  background: $wolf-bg-soft;
  border-radius: $wolf-radius-sm;
  color: $wolf-text-secondary;
  font-size: $wolf-font-size-caption;
}

// Responsive
@media (max-width: 768px) {
  .payment-plan-detail {
    padding: $wolf-space-md;
  }
}
</style>