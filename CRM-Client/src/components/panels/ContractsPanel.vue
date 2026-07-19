<script setup lang="ts">
/**
 * ContractsPanel.vue - 合同面板组件
 *
 * 使用 ListCard 组件确保风格统一
 * 技术栈：shadcn-vue + variables-v2.scss
 * 无障碍：所有图标按钮均有 aria-label
 *
 * Task 6: 改为 emit 'view' 事件，由父组件决定打开 Sheet 或导航
 */
import { Plus, ExternalLink } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import StatusBadge from '@/components/StatusBadge.vue'
import AmountText from '@/components/crmwolf/AmountText.vue'
import ListCard from '@/components/crmwolf/ListCard.vue'
import type { ContractListResponse, ContractStatus } from '@/api/contract'

interface Props {
  customerId: number
  contracts: ContractListResponse[]
}

defineProps<Props>()

const emit = defineEmits<{
  'add': []
  'view': [contractId: number]
}>()

const handleAdd = (): void => {
  emit('add')
}

const handleView = (contractId: number): void => {
  emit('view', contractId)
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
      <span class="font-medium text-wolf-text-primary-v2 truncate">
        {{ item.contract_name }}
      </span>
    </template>

    <template #itemMeta="{ item }">
      <span>{{ item.contract_number }}</span>
      <span> · </span>
      <AmountText :value="item.total_amount" size="sm" />
      <span> · 签署日期: {{ formatDate(item.signing_date) }}</span>
    </template>

    <template #itemBadges="{ item }">
      <StatusBadge
        :status="mapStatus(item.status)"
        type="contract"
        size="small"
      />
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
