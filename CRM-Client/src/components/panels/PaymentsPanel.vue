<script setup lang="ts">
/**
 * PaymentsPanel.vue - 回款计划面板组件
 *
 * 使用 ListCard 组件确保风格统一
 * 技术栈：shadcn-vue + variables-v2.scss
 * 无障碍：所有图标按钮均有 aria-label
 */
import { Plus } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import StatusBadge from '@/components/StatusBadge.vue'
import ListCard from '@/components/crmwolf/ListCard.vue'
import type { PaymentPlanResponse, PaymentPlanStatus } from '@/api/payment'

interface Props {
  customerId: number
  payments: PaymentPlanResponse[]
}

defineProps<Props>()

const emit = defineEmits<{
  'record': [plan: PaymentPlanResponse]
}>()

const handleRecord = (plan: PaymentPlanResponse): void => {
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
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}

const mapStatus = (status: PaymentPlanStatus): string => {
  const statusMap: Record<PaymentPlanStatus, string> = {
    PENDING: 'pending',
    OVERDUE: 'overdue',
    PARTIAL: 'partial',
    COMPLETED: 'completed'
  }
  return statusMap[status]
}

const calculateProgress = (plan: PaymentPlanResponse): number => {
  if (plan.paid_amount === null || plan.paid_amount === undefined || plan.paid_amount === 0) {
    return 0
  }
  return Math.round((plan.paid_amount / plan.planned_amount) * 100)
}
</script>

<template>
  <ListCard
    title="回款计划"
    :items="payments"
    empty-text="暂无回款计划"
  >
    <template #itemMain="{ item }">
      <div class="flex items-center justify-between mb-2">
        <div>
          <div class="flex items-center gap-2">
            <span class="font-medium text-wolf-text-primary-v2">
              {{ item.stage_name }}
            </span>
            <StatusBadge
              :status="mapStatus(item.status)"
              type="paymentPlan"
              size="small"
            />
          </div>
          <div class="text-sm text-wolf-text-tertiary-v2 mt-1">
            {{ item.contract_name ?? '未关联合同' }} ·
            到期: {{ formatDate(item.due_date) }}
          </div>
        </div>
        <div class="text-right">
          <div class="font-medium text-wolf-text-primary-v2">
            {{ formatCurrency(item.planned_amount) }}
          </div>
          <div v-if="item.status !== 'PENDING'" class="text-xs text-wolf-text-tertiary-v2 mt-1">
            已回款: {{ formatCurrency(item.paid_amount ?? 0) }}
          </div>
        </div>
      </div>

      <!-- Progress bar for partial/completed -->
      <div v-if="item.status !== 'PENDING'" class="mt-2">
        <Progress
          :model-value="calculateProgress(item)"
          class="h-1.5"
          :aria-label="`${item.stage_name} 回款进度 ${calculateProgress(item)}%`"
        />
      </div>
    </template>

    <template #itemActions="{ item }">
      <Button
        v-if="item.status !== 'COMPLETED'"
        size="sm"
        variant="outline"
        :aria-label="`为 ${item.stage_name} 登记回款`"
        @click.stop="handleRecord(item)"
      >
        <Plus class="w-4 h-4 mr-1" />
        登记回款
      </Button>
    </template>
  </ListCard>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;
</style>