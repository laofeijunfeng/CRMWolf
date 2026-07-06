<script setup lang="ts">
import { useRouter } from 'vue-router'
import type { PaymentRecordInfo } from '@/api/payment'
import type { PaymentConfirmationStatus } from '@/api/payment'

const router = useRouter()

defineProps<{
  records: PaymentRecordInfo[]
}>()

const getStatusType = (status: PaymentConfirmationStatus | undefined): string => {
  if (status === undefined) return 'info'
  switch (status) {
    case 'CONFIRMED': return 'success'
    case 'PENDING': return 'warning'
    case 'DISPUTED': return 'danger'
    default: return 'info'
  }
}

const getStatusLabel = (status: PaymentConfirmationStatus | undefined): string => {
  if (status === undefined) return '未知'
  switch (status) {
    case 'CONFIRMED': return '已确认'
    case 'PENDING': return '待确认'
    case 'DISPUTED': return '有争议'
    default: return status
  }
}

const formatAmount = (amount: number): string => {
  return amount.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

const formatDate = (dateStr: string): string => {
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}

const viewApprovalDetail = (recordId: number): void => {
  // Navigate to approval detail for this payment record
  router.push(`/approvals?business_type=PAYMENT&business_id=${recordId}`)
}
</script>

<template>
  <el-table :data="records" v-if="records.length > 0" stripe>
    <el-table-column prop="actual_amount" label="回款金额" min-width="120">
      <template #default="{ row }">
        <span class="amount">{{ formatAmount(row.actual_amount) }}</span>
      </template>
    </el-table-column>

    <el-table-column prop="payment_date" label="回款日期" min-width="120">
      <template #default="{ row }">
        {{ formatDate(row.payment_date) }}
      </template>
    </el-table-column>

    <el-table-column prop="creator_name" label="登记人" min-width="100">
      <template #default="{ row }">
        {{ row.creator_name || '未知' }}
      </template>
    </el-table-column>

    <el-table-column prop="confirmation_status" label="状态" min-width="100">
      <template #default="{ row }">
        <el-tag :type="getStatusType(row.confirmation_status)" size="small">
          {{ getStatusLabel(row.confirmation_status) }}
        </el-tag>
      </template>
    </el-table-column>

    <el-table-column prop="notes" label="备注" min-width="150">
      <template #default="{ row }">
        {{ row.notes || '-' }}
      </template>
    </el-table-column>

    <el-table-column label="审批详情" min-width="100">
      <template #default="{ row }">
        <el-button
          v-if="row.confirmation_status === 'PENDING'"
          link
          type="primary"
          size="small"
          @click="viewApprovalDetail(row.id)"
        >
          查看
        </el-button>
        <span v-else class="text-muted">-</span>
      </template>
    </el-table-column>
  </el-table>

  <el-empty v-else description="暂无回款记录" />
</template>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.amount {
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-primary;
}

.text-muted {
  color: $wolf-text-tertiary;
}
</style>