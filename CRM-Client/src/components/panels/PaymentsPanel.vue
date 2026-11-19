<script setup lang="ts">
/**
 * PaymentsPanel.vue - 回款计划面板组件
 *
 * 使用 ListCard 组件确保风格统一
 * 技术栈：shadcn-vue + base.css 设计令牌
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
  customerId: string
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
  'view': [planId: number, plan: PaymentPlanResponse]
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
  emit('view', plan.id, plan)
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
        <span class="font-medium text-foreground truncate">
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
@use '@/styles/tokens.scss' as *;

.payment-plan-main {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: $space-1;
}

.payment-plan-progress {
  width: min(160px, 100%);
  height: 6px;
}

.payment-state-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

.payment-state--pending {
  background: hsl(var(--muted));
  color: hsl(var(--muted-foreground));
}

.payment-state--registered {
  background: var(--wash-hover);
  color: hsl(var(--brand));
}

.payment-state--reviewing,
.payment-state--partial {
  background: color-mix(in srgb, hsl(var(--status-warning)) var(--status-bg-mix), transparent);
  color: hsl(var(--status-warning));
}

.payment-state--completed {
  background: color-mix(in srgb, hsl(var(--status-success)) var(--status-bg-mix), transparent);
  color: hsl(var(--status-success));
}

.payment-state--overdue {
  background: color-mix(in srgb, hsl(var(--status-danger)) var(--status-bg-mix), transparent);
  color: hsl(var(--status-danger));
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
  color: hsl(var(--muted-foreground));
}

.payment-plan-action-button--primary {
  &:hover {
    color: hsl(var(--brand));
  }
}

.payment-plan-action-button--danger {
  &:hover {
    color: hsl(var(--status-danger));
  }
}

:global(.payment-plan-action-hover-card) {
  width: auto;
  padding: 6px 10px;
}

.payment-plan-action-hover-text {
  color: hsl(var(--foreground));
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}
</style>
