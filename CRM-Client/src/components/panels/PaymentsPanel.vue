<script setup lang="ts">
/**
 * PaymentsPanel.vue - 回款计划面板组件
 *
 * 使用 ListCard 组件确保风格统一
 * 技术栈：shadcn-vue + variables-v2.scss
 * 无障碍：所有图标按钮均有 aria-label
 *
 * Task 6: 添加 'view' 事件用于查看回款计划详情
 */
import { Plus, ExternalLink } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import StatusBadge from '@/components/StatusBadge.vue'
import AmountText from '@/components/crmwolf/AmountText.vue'
import ListCard from '@/components/crmwolf/ListCard.vue'
import type { PaymentPlanResponse, PaymentPlanStatus } from '@/api/payment'

interface Props {
  customerId: number
  payments: PaymentPlanResponse[]
}

defineProps<Props>()

const emit = defineEmits<{
  'record': [plan: PaymentPlanResponse]
  'view': [planId: number]
}>()

const handleRecord = (plan: PaymentPlanResponse): void => {
  emit('record', plan)
}

const handleView = (planId: number): void => {
  emit('view', planId)
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
      <div class="payment-plan-main">
        <span class="font-medium text-wolf-text-primary-v2 truncate">
          {{ item.stage_name }}
        </span>

        <Progress
          v-if="item.status !== 'PENDING'"
          :model-value="calculateProgress(item)"
          class="payment-plan-progress"
          :aria-label="`${item.stage_name} 回款进度 ${calculateProgress(item)}%`"
        />
      </div>
    </template>

    <template #itemMeta="{ item }">
      <span>{{ item.contract_name ?? '未关联合同' }}</span>
      <span> · 到期: {{ formatDate(item.due_date) }}</span>
      <span> · 计划: </span>
      <AmountText :value="item.planned_amount" size="sm" tone="warning" />
      <template v-if="item.status !== 'PENDING'">
        <span> · 已回款: </span>
        <AmountText :value="item.paid_amount ?? 0" size="sm" />
      </template>
    </template>

    <template #itemBadges="{ item }">
      <StatusBadge
        :status="mapStatus(item.status)"
        type="paymentPlan"
        size="small"
      />
    </template>

    <template #itemActions="{ item }">
      <Button
        variant="ghost"
        size="sm"
        :aria-label="`查看 ${item.stage_name} 详情`"
        @click.stop="handleView(item.id)"
      >
        <ExternalLink class="w-4 h-4" />
      </Button>
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

.payment-plan-main {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.payment-plan-progress {
  width: min(160px, 100%);
  height: 6px;
}
</style>
