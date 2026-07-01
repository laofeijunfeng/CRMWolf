<template>
  <div class="payment-records">
    <div v-loading="loading">
      <el-empty v-if="!records || records.length === 0" description="暂无回款记录" />

      <div v-else class="records-list">
        <div
          v-for="record in records"
          :key="record.id"
          class="record-item"
        >
          <div class="record-header">
            <div class="record-amount">
              <span class="amount">¥{{ formatAmount(record.actual_amount) }}</span>
              <el-tag type="success" size="small">已回款</el-tag>
            </div>
            <div class="record-date">{{ formatDate(record.payment_date) }}</div>
          </div>

          <div class="record-details">
            <div v-if="record.creator_name" class="detail-row">
              <span class="label">登记人：</span>
              <span class="value">{{ record.creator_name }}</span>
            </div>
            <div v-if="record.proof_attachment" class="detail-row">
              <span class="label">凭证：</span>
              <el-link :href="record.proof_attachment" target="_blank" :underline="false">
                <el-icon class="link-icon"><Link /></el-icon>
                查看凭证
              </el-link>
            </div>
            <div v-if="(record as any).notes" class="detail-row">
              <span class="label">备注：</span>
              <span class="value">{{ (record as any).notes }}</span>
            </div>
            <div class="detail-row">
              <span class="label">登记时间：</span>
              <span class="value">{{ formatDateTime(record.created_time) }}</span>
            </div>
          </div>

          <div class="record-actions">
            <el-button size="small" @click="editRecord(record)">
              <el-icon class="mr-1"><Edit /></el-icon>
              编辑
            </el-button>
            <el-button size="small" type="danger" @click="deleteRecord(record)">
              <el-icon class="mr-1"><Delete /></el-icon>
              删除
            </el-button>
          </div>
        </div>
      </div>

      <div class="records-summary">
        <div class="summary-item">
          <span class="label">总回款金额：</span>
          <span class="value total">¥{{ formatAmount(totalAmount) }}</span>
        </div>
        <div class="summary-item">
          <span class="label">回款次数：</span>
          <span class="value">{{ records.length }} 次</span>
        </div>
      </div>
    </div>

    <el-dialog
      v-model="editModalVisible"
      title="编辑回款记录"
      width="500px"
      @close="editModalVisible = false"
    >
      <el-form :model="editForm" label-position="top">
        <el-form-item label="回款金额" required>
          <el-input-number v-model="editForm.actual_amount" placeholder="请输入回款金额" :min="0" :precision="2" :controls="false" style="width: 100%">
            <template #prepend>¥</template>
          </el-input-number>
        </el-form-item>
        <el-form-item label="回款日期" required>
          <el-date-picker v-model="editForm.payment_date" type="date" placeholder="请选择回款日期" style="width: 100%" />
        </el-form-item>
        <el-form-item label="凭证附件">
          <el-input v-model="editForm.proof_attachment" placeholder="附件URL（可选）" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editForm.notes" type="textarea" placeholder="备注信息（可选）" :maxlength="200" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleUpdateRecord">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Link, Edit, Delete } from '@element-plus/icons-vue'
import paymentApi, { type PaymentRecordInfo, type PaymentRecordUpdate } from '@/api/payment'

interface Props {
  planId: number
}

const props = defineProps<Props>()
const emit = defineEmits(['record-updated'])

const loading = ref(false)
const records = ref<PaymentRecordInfo[]>([])

const editModalVisible = ref(false)
const editForm = ref<PaymentRecordUpdate>({
  actual_amount: 0,
  payment_date: '',
  proof_attachment: '',
  notes: ''
})
const editingRecord = ref<PaymentRecordInfo | null>(null)

const totalAmount = computed(() => {
  return records.value.reduce((sum, record) => sum + record.actual_amount, 0)
})

const fetchRecords = async () => {
  loading.value = true
  try {
    const response = await paymentApi.getPaymentRecords(props.planId) as any
    records.value = response.data || response
  } catch (error) {
    console.error('获取回款记录失败', error)
  } finally {
    loading.value = false
  }
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

const formatDateTime = (dateStr: string) => {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const editRecord = (record: PaymentRecordInfo) => {
  editingRecord.value = record
  editForm.value = {
    actual_amount: record.actual_amount,
    payment_date: record.payment_date,
    proof_attachment: record.proof_attachment,
    notes: (record as any).notes
  }
  editModalVisible.value = true
}

const handleUpdateRecord = async () => {
  if (!editingRecord.value) return
  
  if (!editForm.value.actual_amount || editForm.value.actual_amount <= 0) {
    ElMessage.error('请输入有效的回款金额')
    return
  }
  
  if (!editForm.value.payment_date) {
    ElMessage.error('请选择回款日期')
    return
  }

  try {
    await paymentApi.updatePaymentRecord(editingRecord.value.id, editForm.value)
    ElMessage.success('更新成功')
    editModalVisible.value = false
    fetchRecords()
    emit('record-updated')
  } catch (error: unknown) {
    console.error('更新回款记录失败', error)
    ElMessage.error(error.response?.data?.detail || '更新失败')
  }
}

const deleteRecord = (record: PaymentRecordInfo) => {
  ElMessageBox.confirm(
    `确定要删除这条回款记录吗？金额：¥${formatAmount(record.actual_amount)}`,
    '确认删除',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    try {
      await paymentApi.deletePaymentRecord(record.id)
      ElMessage.success('删除成功')
      fetchRecords()
      emit('record-updated')
    } catch (error: unknown) {
      console.error('删除回款记录失败', error)
      ElMessage.error(error.response?.data?.detail || '删除失败')
    }
  }).catch(() => {
  })
}

const refresh = () => {
  fetchRecords()
}

defineExpose({
  refresh
})

watch(() => props.planId, () => {
  fetchRecords()
}, { immediate: true })

onMounted(() => {
  fetchRecords()
})
</script>

<style scoped>
.payment-records {
  width: 100%;
}

.records-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}

.record-item {
  padding: 16px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  transition: all 0.3s;
}

.record-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.record-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.record-amount {
  display: flex;
  align-items: center;
  gap: 8px;
}

.record-amount .amount {
  font-size: 20px;
  font-weight: 600;
  color: var(--el-color-success);
}

.record-date {
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.record-details {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}

.detail-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.detail-row .label {
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}

.detail-row .value {
  color: var(--el-text-color-regular);
  word-break: break-all;
}

.link-icon {
  margin-right: 4px;
}

.record-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.mr-1 {
  margin-right: 4px;
}

.records-summary {
  padding: 16px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  display: flex;
  justify-content: space-around;
}

.summary-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.summary-item .label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.summary-item .value {
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.summary-item .value.total {
  font-size: 20px;
  color: var(--el-color-success);
}
</style>
