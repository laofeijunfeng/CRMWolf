<script setup lang="ts">
/**
 * ContractsPanel.vue - 合同面板组件
 *
 * 使用 ListCard 组件确保风格统一
 * 技术栈：shadcn-vue + variables-v2.scss
 * 无障碍：所有图标按钮均有 aria-label
 */
import { Plus, ExternalLink } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { Button } from '@/components/ui/button'
import StatusBadge from '@/components/StatusBadge.vue'
import ListCard from '@/components/crmwolf/ListCard.vue'
import type { ContractListResponse, ContractStatus } from '@/api/contract'

interface Props {
  customerId: number
  contracts: ContractListResponse[]
}

defineProps<Props>()

const emit = defineEmits<{
  'add': []
}>()

const router = useRouter()

const handleAdd = (): void => {
  emit('add')
}

const handleView = (contractId: number): void => {
  router.push(`/contracts/${contractId}`)
}

const mapStatus = (status: ContractStatus): string => {
  const statusMap: Record<ContractStatus, string> = {
    'DRAFT': 'draft',
    'PENDING_REVIEW': 'pending_review',
    'SIGNED': 'signed',
    'EFFECTIVE': 'effective',
    'EXPIRED': 'expired',
    'TERMINATED': 'terminated'
  }
  return statusMap[status]
}

const formatCurrency = (amount: string | number): string => {
  const numAmount = typeof amount === 'string' ? parseFloat(amount) : amount
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 0
  }).format(numAmount)
}

const formatDate = (dateStr: string | null): string => {
  if (dateStr === null || dateStr === '') {
    return '-'
  }
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}
</script>

<template>
  <ListCard
    title="合同"
    :items="contracts"
    empty-text="暂无合同"
  >
    <template #headerActions>
      <Button size="sm" @click="handleAdd">
        <Plus class="w-4 h-4 mr-1" />
        新建合同
      </Button>
    </template>

    <template #itemMain="{ item }">
      <div class="flex items-center gap-2">
        <span class="font-medium text-wolf-text-primary-v2">
          {{ item.contract_name }}
        </span>
        <StatusBadge
          :status="mapStatus(item.status)"
          type="contract"
          size="small"
        />
      </div>
      <div class="text-sm text-wolf-text-tertiary-v2 mt-1">
        {{ item.contract_number }} · {{ formatCurrency(item.total_amount) }}
        · 签署日期: {{ formatDate(item.signing_date) }}
      </div>
    </template>

    <template #itemActions="{ item }">
      <Button
        variant="ghost"
        size="sm"
        :aria-label="`查看合同 ${item.contract_name} 详情`"
        @click.stop="handleView(item.id)"
      >
        <ExternalLink class="w-4 h-4" />
      </Button>
    </template>
  </ListCard>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;
</style>