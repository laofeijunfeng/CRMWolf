<template>
  <el-card title="回款汇总" shadow="never" class="payment-summary-card" v-loading="loading">
    <div class="summary-grid">
      <div class="summary-item">
        <div class="summary-label">合同总额</div>
        <AmountText class="summary-amount-value" :value="summary?.total_amount || 0" size="lg" tone="warning" />
      </div>
      
      <div class="summary-item">
        <div class="summary-label">已回款金额</div>
        <AmountText class="summary-amount-value" :value="summary?.total_paid_amount || 0" size="lg" />
      </div>
      
      <div class="summary-item">
        <div class="summary-label">待回款金额</div>
        <AmountText class="summary-amount-value" :value="summary?.remaining_amount || 0" size="lg" tone="primary" />
      </div>
      
      <div class="summary-item">
        <div class="summary-label">回款进度</div>
        <div class="summary-value progress">
          <el-progress 
            :percentage="paymentProgress" 
            :color="progressColor"
          />
        </div>
      </div>
      
      <div class="summary-item">
        <div class="summary-label">回款状态</div>
        <div class="summary-value status">
          <el-tag :type="statusType" size="default">
            {{ statusText }}
          </el-tag>
        </div>
      </div>
      
      <div class="summary-item">
        <div class="summary-label">完成进度</div>
        <div class="summary-value plans">
          <span class="completed">{{ summary?.completed_plans_count || 0 }}</span>
          <span class="separator">/</span>
          <span class="total">{{ summary?.payment_plans_count || 0 }}</span>
          <span class="label">计划</span>
        </div>
      </div>
      
      <div v-if="summary && summary.overdue_plans_count > 0" class="summary-item warning">
        <div class="summary-label">逾期计划</div>
        <div class="summary-value overdue">
          <el-icon class="warning-icon" :size="20"><WarningFilled /></el-icon>
          <span>{{ summary.overdue_plans_count }} 个</span>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'
import AmountText from '@/components/crmwolf/AmountText.vue'
import paymentApi, { type ContractPaymentSummary } from '@/api/payment'

interface Props {
  contractId: number
}

const props = defineProps<Props>()

const loading = ref(false)
const summary = ref<ContractPaymentSummary | null>(null)

type StatusTagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

const paymentProgress = computed((): number => {
  if (!summary.value || summary.value.total_amount === 0) return 0
  return Math.round((summary.value.total_paid_amount / summary.value.total_amount) * 100)
})

const statusText = computed((): string => {
  if (!summary.value) return '-'
  const statusMap: Record<string, string> = {
    'UNPAID': '未回款',
    'PARTIAL': '部分回款',
    'COMPLETED': '已回完',
    'OVERDUE': '有逾期'
  }
  return statusMap[summary.value.payment_status] ?? '-'
})

const statusType = computed((): StatusTagType => {
  if (!summary.value) return 'info'
  const typeMap: Record<string, StatusTagType> = {
    'UNPAID': 'info',
    'PARTIAL': 'primary',
    'COMPLETED': 'success',
    'OVERDUE': 'danger'
  }
  return typeMap[summary.value.payment_status] ?? 'info'
})

const progressColor = computed((): string => {
  const progress = paymentProgress.value
  if (progress === 100) return '#67c23a'
  if (progress >= 50) return '#409eff'
  if (progress >= 25) return '#e6a23c'
  return '#f56c6c'
})

const fetchSummary = async (): Promise<void> => {
  loading.value = true
  try {
    summary.value = await paymentApi.getPaymentSummary(props.contractId)
  } catch {
    summary.value = null
  } finally {
    loading.value = false
  }
}

const refresh = (): void => {
  fetchSummary()
}

defineExpose({
  refresh
})

watch(() => props.contractId, () => {
  fetchSummary()
}, { immediate: true })

onMounted(() => {
  fetchSummary()
})
</script>

<style scoped>
.payment-summary-card {
  margin-bottom: 16px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.summary-item {
  padding: 16px;
  background: var(--el-bg-color);
  border-radius: 8px;
  border: 1px solid var(--el-border-color-light);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.summary-item.warning {
  background: rgba(245, 108, 108, 0.1);
  border-color: var(--el-color-danger-light-3);
}

.summary-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.summary-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.summary-value.progress {
  display: flex;
  align-items: center;
}

.summary-value.plans {
  display: flex;
  align-items: center;
  gap: 4px;
}

.summary-value.plans .completed {
  color: var(--el-color-success);
  font-weight: 600;
}

.summary-value.plans .separator {
  color: var(--el-text-color-secondary);
}

.summary-value.plans .total {
  color: var(--el-text-color-regular);
}

.summary-value.plans .label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-weight: 400;
  margin-left: 4px;
}

.summary-value.overdue {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--el-color-danger);
}

.warning-icon {
  font-size: 20px;
}

@media (max-width: 768px) {
  .summary-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
