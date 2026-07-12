<script setup lang="ts">
/**
 * PaymentsPanel.vue - 回款计划面板组件
 *
 * 用于 CustomerDetailSheet 中的回款计划列表展示
 * 支持新建回款记录等操作
 *
 * 技术栈：shadcn-vue + variables-v2.scss
 */
import { Plus, Receipt } from 'lucide-vue-next'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import StatusBadge from '@/components/StatusBadge.vue'
import type { PaymentPlanResponse, PaymentPlanStatus } from '@/api/payment'

// ==================== Props & Emits ====================
interface Props {
  customerId: number
  payments: PaymentPlanResponse[]
}

defineProps<Props>()

const emit = defineEmits<{
  'add': [planId: number]
  'record': [plan: PaymentPlanResponse]
}>()

// ==================== Methods ====================
const handleAddRecord = (plan: PaymentPlanResponse): void => {
  emit('record', plan)
}

const formatCurrency = (amount: number): string => {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 0
  }).format(amount)
}

const formatDate = (dateStr: string): string => {
  if (dateStr === null || dateStr === undefined || dateStr === '') {
    return '-'
  }
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}

// Map payment status to StatusBadge type
const mapStatus = (status: PaymentPlanStatus): string => {
  const statusMap: Record<PaymentPlanStatus, string> = {
    PENDING: 'pending',
    OVERDUE: 'overdue',
    PARTIAL: 'partial',
    COMPLETED: 'completed'
  }
  return statusMap[status]
}

// Calculate progress percentage
const calculateProgress = (plan: PaymentPlanResponse): number => {
  if (plan.paid_amount === null || plan.paid_amount === undefined || plan.paid_amount === 0) {
    return 0
  }
  return Math.round((plan.paid_amount / plan.planned_amount) * 100)
}
</script>

<template>
  <Card class="payments-panel">
    <CardHeader class="p-4 border-b border-wolf-border-light-v2 flex flex-row items-center justify-between">
      <h3 class="text-sm font-semibold text-wolf-text-primary-v2">回款计划</h3>
      <div class="text-xs text-wolf-text-tertiary-v2">
        共 {{ payments.length }} 条记录
      </div>
    </CardHeader>
    <CardContent class="p-0">
      <!-- Empty State -->
      <div v-if="payments.length === 0" class="p-8 text-center text-wolf-text-tertiary-v2">
        暂无回款计划
      </div>

      <!-- Payment List -->
      <div v-else class="divide-y divide-wolf-border-light-v2">
        <div
          v-for="plan in payments"
          :key="plan.id"
          class="p-4 hover:bg-wolf-bg-hover-v2 transition-colors"
        >
          <!-- Plan Header -->
          <div class="flex items-start justify-between mb-2">
            <div class="flex-1">
              <div class="flex items-center gap-2 mb-1">
                <span class="font-medium text-wolf-text-primary-v2">{{ plan.stage_name }}</span>
                <StatusBadge
                  :status="mapStatus(plan.status)"
                  type="paymentPlan"
                  size="small"
                />
              </div>
              <div class="text-sm text-wolf-text-tertiary-v2">
                {{ plan.contract_name ?? '未关联合同' }}
              </div>
            </div>
            <div class="text-right">
              <div class="font-medium text-wolf-text-primary-v2">
                {{ formatCurrency(plan.planned_amount) }}
              </div>
              <div class="text-xs text-wolf-text-tertiary-v2">
                到期日: {{ formatDate(plan.due_date) }}
              </div>
            </div>
          </div>

          <!-- Progress Bar -->
          <div v-if="plan.status !== 'PENDING'" class="mb-3">
            <div class="flex items-center justify-between text-xs text-wolf-text-tertiary-v2 mb-1">
              <span>回款进度</span>
              <span>{{ calculateProgress(plan) }}%</span>
            </div>
            <div class="h-1.5 bg-wolf-bg-secondary-v2 rounded-full overflow-hidden">
              <div
                class="h-full bg-emerald-500 rounded-full transition-all"
                :style="{ width: `${calculateProgress(plan)}%` }"
              />
            </div>
            <div class="flex justify-between text-xs mt-1">
              <span class="text-emerald-600">
                已回款: {{ formatCurrency(plan.paid_amount ?? 0) }}
              </span>
              <span class="text-wolf-text-tertiary-v2">
                剩余: {{ formatCurrency(plan.remaining_amount ?? plan.planned_amount) }}
              </span>
            </div>
          </div>

          <!-- Payment Records Summary -->
          <div v-if="plan.payment_records && plan.payment_records.length > 0" class="text-xs text-wolf-text-tertiary-v2 mb-3">
            <div class="flex items-center gap-1">
              <Receipt class="w-3 h-3" />
              <span>{{ plan.payment_records.length }} 条回款记录</span>
            </div>
          </div>

          <!-- Notes -->
          <div v-if="plan.notes" class="text-xs text-wolf-text-tertiary-v2 mb-3 p-2 bg-wolf-bg-secondary-v2 rounded">
            {{ plan.notes }}
          </div>

          <!-- Actions -->
          <div class="flex justify-end gap-2">
            <Button
              v-if="plan.status !== 'COMPLETED'"
              size="sm"
              variant="outline"
              @click="handleAddRecord(plan)"
            >
              <Plus class="w-4 h-4 mr-1" />
              登记回款
            </Button>
          </div>
        </div>
      </div>
    </CardContent>
  </Card>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;
</style>