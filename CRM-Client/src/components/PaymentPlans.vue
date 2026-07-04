<template>
  <el-card shadow="never" class="payment-plans-card" v-loading="loading">
    <template #header>
      <div class="card-header">
        <span>回款计划</span>
        <div class="card-header-actions">
          <el-button type="primary" class="wolf-btn wolf-btn--primary" @click="showCreateModal">
            <el-icon><Plus /></el-icon>
            新建计划
          </el-button>
        </div>
      </div>
    </template>

    <el-empty v-if="!plans || plans.length === 0" description="暂无回款计划" />

    <div v-else class="plans-list">
      <div
        v-for="plan in plans"
        :key="plan.id"
        class="plan-item"
        :class="{ 'overdue': plan.status === 'OVERDUE', 'completed': plan.status === 'COMPLETED' }"
      >
        <div class="plan-header">
          <div class="plan-title">
            <span class="stage-name">{{ plan.stage_name }}</span>
            <el-tag :type="getStatusType(plan.status)" size="small" class="wolf-tag">
              {{ getStatusText(plan.status) }}
            </el-tag>
          </div>
          <div v-if="plan.status !== 'COMPLETED'" class="plan-actions">
            <el-button size="small" class="wolf-btn wolf-btn--primary-sm" @click="showRecords(plan)">
              <el-icon><Document /></el-icon>
              回款记录
            </el-button>
            <el-button size="small" type="success" class="wolf-btn wolf-btn--primary-sm" @click="showPaymentModal(plan)">
              <el-icon><CircleCheckFilled /></el-icon>
              登记回款
            </el-button>
            <el-dropdown>
              <el-button size="small" class="wolf-btn wolf-btn--primary-sm">
                <el-icon><MoreFilled /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="editPlan(plan)">
                    <el-icon><Edit /></el-icon>
                    编辑
                  </el-dropdown-item>
                  <el-dropdown-item @click="deletePlan(plan)" :disabled="plan.payment_records && plan.payment_records.length > 0">
                    <el-icon><Delete /></el-icon>
                      删除
                    </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>

        <div class="plan-info">
          <div class="attributes-grid">
            <div class="attribute-item">
              <div class="attribute-header">
                <el-icon class="attribute-icon"><Coin /></el-icon>
                <span class="attribute-label">计划金额</span>
              </div>
              <span class="attribute-value">¥{{ formatAmount(plan.planned_amount) }}</span>
            </div>
            <div class="attribute-item">
              <div class="attribute-header">
                <el-icon class="attribute-icon"><CircleCheckFilled /></el-icon>
                <span class="attribute-label">已回款</span>
              </div>
              <span class="attribute-value">¥{{ formatAmount(plan.paid_amount || 0) }}</span>
            </div>
            <div class="attribute-item">
              <div class="attribute-header">
                <el-icon class="attribute-icon"><Clock /></el-icon>
                <span class="attribute-label">待回款</span>
              </div>
              <span class="attribute-value">¥{{ formatAmount(plan.remaining_amount || 0) }}</span>
            </div>
            <div class="attribute-item">
              <div class="attribute-header">
                <el-icon class="attribute-icon"><Calendar /></el-icon>
                <span class="attribute-label">计划日期</span>
              </div>
              <span class="attribute-value">{{ formatDate(plan.due_date) }}</span>
            </div>
          </div>
        </div>

        <div v-if="plan.notes" class="plan-notes">
          <span class="notes-label">备注：</span>
          <span class="notes-content">{{ plan.notes }}</span>
        </div>
      </div>
    </div>

    <el-dialog
      v-model="paymentModalVisible"
      title="登记回款"
      width="500px"
      @close="paymentModalVisible = false"
    >
      <el-form :model="paymentForm" label-position="top">
        <el-form-item label="回款金额" required>
          <el-input-number v-model="paymentForm.actual_amount" placeholder="请输入回款金额" :min="0" :precision="2" :controls="false" style="width: 100%">
            <template #prepend>¥</template>
          </el-input-number>
          <template v-if="currentPlan" #footer>
            <span class="form-extra">
              待回款：¥{{ formatAmount(currentPlan.remaining_amount || 0) }}
            </span>
          </template>
        </el-form-item>
        <el-form-item label="回款日期" required>
          <el-date-picker v-model="paymentForm.payment_date" type="date" placeholder="请选择回款日期" style="width: 100%" />
        </el-form-item>
        <el-form-item label="凭证附件">
          <el-input v-model="paymentForm.proof_attachment" placeholder="附件URL（可选）" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="paymentForm.notes" type="textarea" placeholder="备注信息（可选）" :maxlength="200" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button class="wolf-btn wolf-btn--default" @click="paymentModalVisible = false">取消</el-button>
        <el-button type="primary" class="wolf-btn wolf-btn--primary" @click="handleCreatePayment">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="recordsModalVisible"
      :title="`${currentPlan?.stage_name} - 回款记录`"
      width="800px"
      @close="recordsModalVisible = false"
    >
      <PaymentRecords v-if="currentPlan" :plan-id="currentPlan.id" @record-updated="handleRecordUpdated" />
    </el-dialog>

    <el-dialog
      v-model="editModalVisible"
      title="编辑回款计划"
      width="500px"
      @close="editModalVisible = false"
    >
      <el-form :model="editForm" label-position="top">
        <el-form-item label="阶段名称" required>
          <el-input v-model="editForm.stage_name" placeholder="阶段名称" />
        </el-form-item>
        <el-form-item label="计划金额" required>
          <el-input-number v-model="editForm.planned_amount" placeholder="计划金额" :min="0" :precision="2" :controls="false" style="width: 100%">
            <template #prepend>¥</template>
          </el-input-number>
        </el-form-item>
        <el-form-item label="计划日期" required>
          <el-date-picker v-model="editForm.due_date" type="date" placeholder="计划回款日期" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editForm.notes" type="textarea" placeholder="备注（可选）" :maxlength="200" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button class="wolf-btn wolf-btn--default" @click="editModalVisible = false">取消</el-button>
        <el-button type="primary" class="wolf-btn wolf-btn--primary" @click="handleUpdatePlan">确定</el-button>
      </template>
    </el-dialog>

    <!-- 快速创建 Modal -->
    <PaymentPlanQuickCreate
      v-model:visible="quickCreateVisible"
      :contract-id="contractId"
:contract-info="contractInfo ?? undefined"
      :existing-plans="plans ?? undefined"
      @close="quickCreateVisible = false"
      @success="handleQuickCreateSuccess"
    />
  </el-card>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus,
  CircleCheckFilled,
  MoreFilled,
  Edit,
  Delete,
  Document,
  Coin,
  Clock,
  Calendar
} from '@element-plus/icons-vue'
import paymentApi, { type PaymentPlanResponse, type PaymentPlanStatus, type PaymentRecordCreate } from '@/api/payment'
import PaymentRecords from './PaymentRecords.vue'
import PaymentPlanQuickCreate from './PaymentPlanQuickCreate.vue'

interface Props {
  contractId: number
  contractStatus?: string
  contractInfo?: {
    contract_name: string
    contract_number: string
    total_amount: number
    customer_info?: { account_name: string }
    effective_date?: string
    signing_date?: string
  }
}

const props = defineProps<Props>()
const emit = defineEmits(['plan-updated'])

const loading = ref(false)
const plans = ref<PaymentPlanResponse[]>([])
const statusFilter = ref<string>('')
const quickCreateVisible = ref(false)

const paymentModalVisible = ref(false)
const paymentForm = ref<PaymentRecordCreate>({
  actual_amount: 0,
  payment_date: ''
})
const currentPlan = ref<PaymentPlanResponse | null>(null)

const recordsModalVisible = ref(false)

const editModalVisible = ref(false)
const editForm = ref<{
  stage_name: string
  planned_amount: number
  due_date: string
  notes?: string
}>({
  stage_name: '',
  planned_amount: 0,
  due_date: '',
  notes: ''
})
const editingPlan = ref<PaymentPlanResponse | null>(null)

const fetchPlans = async () => {
  loading.value = true
  try {
    const response = await paymentApi.getPaymentPlans(props.contractId, statusFilter.value as PaymentPlanStatus)
    plans.value = response
  } catch (error: unknown) {
    console.error('获取回款计划失败', error)
  } finally {
    loading.value = false
  }
}

const getStatusText = (status: PaymentPlanStatus) => {
  const statusMap: Record<PaymentPlanStatus, string> = {
    'PENDING': '待回款',
    'OVERDUE': '已逾期',
    'PARTIAL': '部分回款',
    'COMPLETED': '已完成'
  }
  return statusMap[status] || status
}

const getStatusType = (status: PaymentPlanStatus) => {
  const typeMap: Record<PaymentPlanStatus, string> = {
    'PENDING': '',
    'OVERDUE': 'danger',
    'PARTIAL': 'warning',
    'COMPLETED': 'success'
  }
  return typeMap[status] || 'info'
}

const formatAmount = (amount: number) => {
  return amount.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

const formatDate = (dateStr: string) => {
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}

const showCreateModal = () => {
  quickCreateVisible.value = true
}

const handleQuickCreateSuccess = () => {
  fetchPlans()
  emit('plan-updated')
}

const showPaymentModal = (plan: PaymentPlanResponse) => {
  currentPlan.value = plan
  const today = new Date().toISOString().split('T')[0] ?? ''
  paymentForm.value = {
    actual_amount: plan.remaining_amount ?? plan.planned_amount,
    payment_date: today
  }
  paymentModalVisible.value = true
}

const handleCreatePayment = async () => {
  if (!paymentForm.value.actual_amount || paymentForm.value.actual_amount <= 0) {
    ElMessage.error('请输入有效的回款金额')
    return
  }
  
  if (!paymentForm.value.payment_date) {
    ElMessage.error('请选择回款日期')
    return
  }

  if (currentPlan.value) {
    try {
      await paymentApi.createPaymentRecord(currentPlan.value.id, paymentForm.value)
      ElMessage.success('登记成功')
      paymentModalVisible.value = false
      fetchPlans()
      emit('plan-updated')
    } catch (error: unknown) {
      console.error('登记回款失败', error)
      const err = error as Error
      ElMessage.error(err.message || '登记失败')
    }
  }
}

const showRecords = (plan: PaymentPlanResponse) => {
  currentPlan.value = plan
  recordsModalVisible.value = true
}

const handleRecordUpdated = () => {
  fetchPlans()
  emit('plan-updated')
}

const editPlan = (plan: PaymentPlanResponse) => {
  editingPlan.value = plan
  editForm.value = {
    stage_name: plan.stage_name,
    planned_amount: plan.planned_amount,
    due_date: plan.due_date,
    notes: plan.notes ?? undefined ?? undefined
  }
  editModalVisible.value = true
}

const handleUpdatePlan = async () => {
  if (!editingPlan.value) return
  
  if (!editForm.value.stage_name || editForm.value.planned_amount <= 0 || !editForm.value.due_date) {
    ElMessage.error('请填写完整的计划信息')
    return
  }

  try {
    await paymentApi.updatePaymentPlan(editingPlan.value.id, editForm.value)
    ElMessage.success('更新成功')
    editModalVisible.value = false
    fetchPlans()
    emit('plan-updated')
  } catch (error: unknown) {
    console.error('更新回款计划失败', error)
    const err = error as Error
    ElMessage.error(err.message || '更新失败')
  }
}

const deletePlan = (plan: PaymentPlanResponse) => {
  if (plan.payment_records && plan.payment_records.length > 0) {
    ElMessage.warning('存在回款记录的计划不能删除')
    return
  }

  ElMessageBox.confirm(
    `确定要删除回款计划"${plan.stage_name}"吗？`,
    '确认删除',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    try {
      await paymentApi.deletePaymentPlan(plan.id)
      ElMessage.success('删除成功')
      fetchPlans()
      emit('plan-updated')
    } catch (error: unknown) {
      console.error('删除回款计划失败', error)
      ElMessage.error(error.response?.data?.detail || '删除失败')
    }
  }).catch(() => {
  })
}

const refresh = () => {
  fetchPlans()
}

defineExpose({
  refresh
})

watch(() => props.contractId, () => {
  fetchPlans()
}, { immediate: true })

onMounted(() => {
  fetchPlans()
})
</script>

<style scoped>
.payment-plans-card {
  height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--wolf-space-4);
  font-size: var(--wolf-font-size-card-title);
  font-weight: var(--wolf-font-weight-semibold);
  color: var(--wolf-text-primary);
}

.card-header-actions {
  display: flex;
  gap: var(--wolf-button-gap);
}

.plans-list {
  display: flex;
  flex-direction: column;
  gap: var(--wolf-space-4);
}

.plan-item {
  padding: var(--wolf-card-padding);
  background: var(--wolf-bg-card);
  border-radius: var(--wolf-radius-lg);
  border: 1px solid var(--wolf-border-color);
  transition: all 0.2s ease;
}

.plan-item:hover {
  border-color: var(--wolf-primary);
  box-shadow: var(--wolf-shadow-card);
}

.plan-item.overdue {
  border-color: var(--wolf-danger);
  background: var(--wolf-danger-bg);
}

.plan-item.completed {
  border-color: var(--wolf-success);
  background: var(--wolf-success-bg);
}

.plan-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--wolf-space-4);
  padding-bottom: var(--wolf-space-3);
  border-bottom: 1px solid var(--wolf-border-light);
}

.plan-title {
  display: flex;
  align-items: center;
  gap: var(--wolf-space-2);
}

.stage-name {
  font-weight: var(--wolf-font-weight-semibold);
  font-size: var(--wolf-font-size-body);
  color: var(--wolf-text-primary);
}

.plan-actions {
  display: flex;
  gap: var(--wolf-space-2);
}

.plan-info {
  margin-bottom: var(--wolf-space-3);
}

.attributes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--wolf-space-4);
}

.attribute-item {
  display: flex;
  flex-direction: column;
  gap: var(--wolf-space-1);
}

.attribute-header {
  display: flex;
  align-items: center;
  gap: var(--wolf-space-1);
}

.attribute-icon {
  font-size: 16px;
  color: var(--wolf-text-tertiary);
}

.attribute-label {
  font-size: var(--wolf-font-size-small);
  color: var(--wolf-text-tertiary);
}

.attribute-value {
  font-size: var(--wolf-font-size-body);
  font-weight: var(--wolf-font-weight-medium);
  color: var(--wolf-text-primary);
}

.plan-notes {
  padding: var(--wolf-space-3);
  background: var(--wolf-bg-soft);
  border-radius: var(--wolf-radius-md);
  font-size: var(--wolf-font-size-body);
  line-height: var(--wolf-line-height-normal);
}

.notes-label {
  color: var(--wolf-text-tertiary);
  margin-right: var(--wolf-space-2);
}

.notes-content {
  color: var(--wolf-text-secondary);
}

.form-extra {
  font-size: var(--wolf-font-size-label);
  color: var(--wolf-text-tertiary);
}
</style>
