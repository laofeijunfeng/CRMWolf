<script setup lang="ts">
import { ExternalLink } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import StatusBadge from '@/components/StatusBadge.vue'
import AmountText from '@/components/crmwolf/AmountText.vue'
import ListCard from '@/components/crmwolf/ListCard.vue'
import type { PaymentConfirmationStatus, PaymentRecordWithDetails } from '@/api/payment'

interface Props {
  records: PaymentRecordWithDetails[]
  loading?: boolean
}

withDefaults(defineProps<Props>(), {
  loading: false
})

const emit = defineEmits<{
  'view': [record: PaymentRecordWithDetails]
}>()

const handleView = (record: PaymentRecordWithDetails): void => {
  emit('view', record)
}

const formatDate = (value: string | null | undefined): string => {
  if (value === undefined || value === null || value.trim() === '') return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleDateString('zh-CN')
}

const mapStatus = (status: PaymentConfirmationStatus | undefined): 'pending' | 'confirmed' | 'rejected' => {
  if (status === 'CONFIRMED') return 'confirmed'
  if (status === 'DISPUTED') return 'rejected'
  return 'pending'
}
</script>

<template>
  <ListCard
    title="回款记录"
    :items="records"
    empty-text="暂无回款记录"
    :loading="loading === true"
    row-interactive
    @row-click="handleView"
  >
    <template #itemMain="{ item }">
      <span class="font-medium text-wolf-text-primary-v2 truncate">
        {{ item.record_number ?? `回款记录 #${item.id}` }}
      </span>
    </template>

    <template #itemMeta="{ item }">
      <span>{{ item.stage_name ?? '未关联阶段' }}</span>
      <span> · 回款日期: {{ formatDate(item.payment_date) }}</span>
      <span> · 金额: </span>
      <AmountText :value="item.actual_amount" size="sm" />
      <span v-if="item.actual_payer_name"> · 付款方: {{ item.actual_payer_name }}</span>
    </template>

    <template #itemBadges="{ item }">
      <StatusBadge
        :status="mapStatus(item.confirmation_status)"
        type="paymentRecord"
        size="small"
      />
    </template>

    <template #itemActions="{ item }">
      <Button
        variant="ghost"
        size="sm"
        :aria-label="`查看回款记录 ${item.record_number ?? item.id} 详情`"
        @click.stop="handleView(item)"
      >
        <ExternalLink class="w-4 h-4" />
      </Button>
    </template>
  </ListCard>
</template>
