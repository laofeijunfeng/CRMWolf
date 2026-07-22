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
import { CreditCard, Pencil, Plus, Trash2 } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import AmountText from '@/components/crmwolf/AmountText.vue'
import { HoverInfo } from '@/components/crmwolf'
import ListCard from '@/components/crmwolf/ListCard.vue'
import type { PaymentPlanResponse } from '@/api/payment'

type PaymentPlanActionPredicate = (plan: PaymentPlanResponse) => boolean

interface Props {
  customerId: number
  payments: PaymentPlanResponse[]
  loading?: boolean
  showAdd?: boolean
  canRecord?: PaymentPlanActionPredicate | null
  canEdit?: PaymentPlanActionPredicate | null
  canDelete?: PaymentPlanActionPredicate | null
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  showAdd: false,
  canRecord: null,
  canEdit: null,
  canDelete: null
})

const emit = defineEmits<{
  'add': []
  'record': [plan: PaymentPlanResponse]
  'view': [planId: number]
  'edit': [plan: PaymentPlanResponse]
  'delete': [plan: PaymentPlanResponse]
}>()

const handleAdd = (): void => {
  emit('add')
}

const handleRecord = (plan: PaymentPlanResponse): void => {
  emit('record', plan)
}

const handleView = (plan: PaymentPlanResponse): void => {
  emit('view', plan.id)
}

const handleEdit = (plan: PaymentPlanResponse): void => {
  emit('edit', plan)
}

const handleDelete = (plan: PaymentPlanResponse): void => {
  emit('delete', plan)
}

const formatDate = (dateStr: string): string => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}

const getPaymentStateText = (plan: PaymentPlanResponse): string => {
  const paidAmount = Number(plan.paid_amount ?? 0)
  const plannedAmount = Number(plan.planned_amount ?? 0)
  if (plan.status === 'COMPLETED' || (plannedAmount > 0 && paidAmount >= plannedAmount)) {
    return '已回款'
  }
  if (paidAmount > 0) {
    return '部分回款'
  }
  if (plan.latest_approval?.status === 'PENDING' || plan.payment_records.some(record => record.approval?.status === 'PENDING')) {
    return '审批中'
  }
  if (plan.payment_records.length > 0) {
    return '已登记'
  }
  if (plan.status === 'OVERDUE') {
    return '已逾期'
  }
  return '未登记'
}

const getPaymentStateClass = (plan: PaymentPlanResponse): string => {
  const state = getPaymentStateText(plan)
  if (state === '已回款') return 'payment-state--completed'
  if (state === '部分回款') return 'payment-state--partial'
  if (state === '审批中') return 'payment-state--reviewing'
  if (state === '已登记') return 'payment-state--registered'
  if (state === '已逾期') return 'payment-state--overdue'
  return 'payment-state--pending'
}

const calculateProgress = (plan: PaymentPlanResponse): number => {
  if (plan.paid_amount === null || plan.paid_amount === undefined || plan.paid_amount === 0) {
    return 0
  }
  return Math.round((plan.paid_amount / plan.planned_amount) * 100)
}

const shouldShowAction = (
  predicate: PaymentPlanActionPredicate | null | undefined,
  plan: PaymentPlanResponse
): boolean => predicate?.(plan) === true

const hasActions = (plan: PaymentPlanResponse): boolean =>
  shouldShowAction(props.canRecord, plan)
  || shouldShowAction(props.canEdit, plan)
  || shouldShowAction(props.canDelete, plan)
</script>

<template>
  <ListCard
    title="回款计划"
    :items="payments"
    empty-text="暂无回款计划"
    :loading="loading === true"
    row-interactive
    @row-click="handleView"
  >
    <template #headerActions>
      <Button v-if="showAdd" size="sm" @click="handleAdd">
        <Plus class="w-4 h-4 mr-1" />
        新建计划
      </Button>
    </template>

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
      <span :class="['payment-state-badge', getPaymentStateClass(item)]">
        {{ getPaymentStateText(item) }}
      </span>
    </template>

    <template #itemActions="{ item }">
      <div v-if="hasActions(item)" class="payment-plan-actions" @click.stop>
        <HoverInfo
          v-if="shouldShowAction(canRecord, item)"
          side="top"
          align="center"
          content-class="payment-plan-action-hover-card"
        >
          <template #trigger>
            <Button
              variant="ghost"
              size="icon"
              class="payment-plan-action-button payment-plan-action-button--primary"
              :aria-label="`为 ${item.stage_name} 登记回款`"
              @click="handleRecord(item)"
            >
              <CreditCard class="w-4 h-4" />
            </Button>
          </template>
          <span class="payment-plan-action-hover-text">登记回款</span>
        </HoverInfo>

        <HoverInfo
          v-if="shouldShowAction(canEdit, item)"
          side="top"
          align="center"
          content-class="payment-plan-action-hover-card"
        >
          <template #trigger>
            <Button
              variant="ghost"
              size="icon"
              class="payment-plan-action-button payment-plan-action-button--primary"
              :aria-label="`编辑回款计划 ${item.stage_name}`"
              @click="handleEdit(item)"
            >
              <Pencil class="w-4 h-4" />
            </Button>
          </template>
          <span class="payment-plan-action-hover-text">编辑</span>
        </HoverInfo>

        <HoverInfo
          v-if="shouldShowAction(canDelete, item)"
          side="top"
          align="center"
          content-class="payment-plan-action-hover-card"
        >
          <template #trigger>
            <Button
              variant="ghost"
              size="icon"
              class="payment-plan-action-button payment-plan-action-button--danger"
              :aria-label="`删除回款计划 ${item.stage_name}`"
              @click="handleDelete(item)"
            >
              <Trash2 class="w-4 h-4" />
            </Button>
          </template>
          <span class="payment-plan-action-hover-text">删除</span>
        </HoverInfo>
      </div>
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

.payment-state-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: $wolf-radius-full-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  white-space: nowrap;
}

.payment-state--pending {
  background: $wolf-bg-muted-v2;
  color: $wolf-text-tertiary-v2;
}

.payment-state--registered {
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
}

.payment-state--reviewing,
.payment-state--partial {
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
}

.payment-state--completed {
  background: $wolf-success-bg-v2;
  color: $wolf-success-text-v2;
}

.payment-state--overdue {
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-text-v2;
}

.payment-plan-actions {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  min-width: 0;
}

.payment-plan-action-button {
  width: 32px;
  height: 32px;
  color: $wolf-text-secondary-v2;
}

.payment-plan-action-button--primary {
  &:hover {
    color: $wolf-primary-v2;
  }
}

.payment-plan-action-button--danger {
  &:hover {
    color: $wolf-danger-v2;
  }
}

:global(.payment-plan-action-hover-card) {
  width: auto;
  padding: 6px 10px;
}

.payment-plan-action-hover-text {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  white-space: nowrap;
}
</style>
