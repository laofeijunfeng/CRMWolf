<script setup lang="ts">
/**
 * InvoicesPanel.vue - 发票抬头面板组件
 *
 * 使用 ListCard 组件确保风格统一
 * 技术栈：shadcn-vue + variables-v2.scss
 * 无障碍：所有图标按钮均有 aria-label
 */
import { Plus, Pencil, Trash2, Star, Building2, User, ReceiptText } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import ListCard from '@/components/crmwolf/ListCard.vue'
import type { InvoiceTitleResponse, TitleType } from '@/api/invoice'

// ==================== Props & Emits ====================
interface Props {
  customerId: number
  invoiceTitles: InvoiceTitleResponse[]
}

defineProps<Props>()

const emit = defineEmits<{
  'add': []
  'edit': [invoiceTitle: InvoiceTitleResponse]
  'delete': [titleId: number]
  'set-default': [titleId: number]
  'apply': [invoiceTitle: InvoiceTitleResponse]
}>()

// ==================== Methods ====================
const handleAdd = (): void => {
  emit('add')
}

const handleEdit = (invoiceTitle: InvoiceTitleResponse): void => {
  emit('edit', invoiceTitle)
}

const handleDelete = (titleId: number): void => {
  emit('delete', titleId)
}

const handleSetDefault = (titleId: number): void => {
  emit('set-default', titleId)
}

const handleApply = (invoiceTitle: InvoiceTitleResponse): void => {
  emit('apply', invoiceTitle)
}

// Get title type label and icon
const getTitleTypeInfo = (type: TitleType): { label: string; color: string } => {
  const typeMap: Record<TitleType, { label: string; color: string }> = {
    COMPANY: { label: '企业', color: 'bg-blue-100 text-blue-700' },
    PERSONAL: { label: '个人', color: 'bg-purple-100 text-purple-700' }
  }
  return typeMap[type] ?? { label: type, color: 'bg-gray-100 text-gray-700' }
}

// Mask sensitive info (show first 4 and last 4 chars)
const maskTaxId = (taxId: string): string => {
  if (taxId.length <= 8) {
    return taxId
  }
  return `${taxId.slice(0, 4)}****${taxId.slice(-4)}`
}
</script>

<template>
  <ListCard
    title="发票抬头"
    :items="invoiceTitles"
    empty-text="暂无发票抬头"
  >
    <template #headerActions>
      <Button size="sm" @click="handleAdd">
        <Plus class="w-4 h-4 mr-1" />
        新建抬头
      </Button>
    </template>

    <template #itemMain="{ item }">
      <!-- Title header with type and default badge -->
      <div class="flex items-center gap-2 mb-2">
        <component
          :is="item.title_type === 'COMPANY' ? Building2 : User"
          class="w-4 h-4 text-wolf-text-secondary-v2"
        />
        <span class="font-medium text-wolf-text-primary-v2">{{ item.title }}</span>
        <Badge :class="getTitleTypeInfo(item.title_type).color" class="text-xs">
          {{ getTitleTypeInfo(item.title_type).label }}
        </Badge>
        <Badge v-if="item.is_default" variant="secondary" class="text-xs">
          <Star class="w-3 h-3 mr-1" />
          默认
        </Badge>
      </div>

      <!-- Details -->
      <div class="text-sm text-wolf-text-secondary-v2 space-y-1">
        <div class="flex items-center gap-2">
          <span class="text-wolf-text-tertiary-v2 w-16">税号:</span>
          <span class="font-mono">{{ maskTaxId(item.taxpayer_id) }}</span>
        </div>
        <div v-if="item.bank_name" class="flex items-center gap-2">
          <span class="text-wolf-text-tertiary-v2 w-16">银行:</span>
          <span>{{ item.bank_name }}</span>
        </div>
        <div v-if="item.bank_account" class="flex items-center gap-2">
          <span class="text-wolf-text-tertiary-v2 w-16">账号:</span>
          <span class="font-mono">{{ item.bank_account }}</span>
        </div>
        <div v-if="item.address" class="flex items-center gap-2">
          <span class="text-wolf-text-tertiary-v2 w-16">地址:</span>
          <span>{{ item.address }}</span>
        </div>
        <div v-if="item.phone" class="flex items-center gap-2">
          <span class="text-wolf-text-tertiary-v2 w-16">电话:</span>
          <span>{{ item.phone }}</span>
        </div>
      </div>
    </template>

    <template #itemActions="{ item }">
      <Button
        variant="ghost"
        size="sm"
        :aria-label="`使用 ${item.title} 申请发票`"
        @click.stop="handleApply(item)"
      >
        <ReceiptText class="w-4 h-4" />
        申请发票
      </Button>
      <Button
        v-if="!item.is_default"
        variant="ghost"
        size="sm"
        :aria-label="`将 ${item.title} 设为默认发票抬头`"
        @click.stop="handleSetDefault(item.id)"
      >
        <Star class="w-4 h-4" />
      </Button>
      <Button
        variant="ghost"
        size="sm"
        :aria-label="`编辑发票抬头 ${item.title}`"
        @click.stop="handleEdit(item)"
      >
        <Pencil class="w-4 h-4" />
      </Button>
      <Button
        variant="ghost"
        size="sm"
        :aria-label="`删除发票抬头 ${item.title}`"
        @click.stop="handleDelete(item.id)"
      >
        <Trash2 class="w-4 h-4 text-wolf-danger-text-v2" />
      </Button>
    </template>
  </ListCard>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;
</style>
