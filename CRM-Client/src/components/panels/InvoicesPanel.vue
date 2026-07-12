<script setup lang="ts">
/**
 * InvoicesPanel.vue - 发票抬头面板组件
 *
 * 用于 CustomerDetailSheet 中的发票抬头列表展示
 * 支持新建、编辑、删除、设置默认等操作
 *
 * 技术栈：shadcn-vue + variables-v2.scss
 */
import { Plus, Pencil, Trash2, Star, Building2, User } from 'lucide-vue-next'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
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
  <Card class="invoices-panel">
    <CardHeader class="p-4 border-b border-wolf-border-light-v2 flex flex-row items-center justify-between">
      <h3 class="text-sm font-semibold text-wolf-text-primary-v2">发票抬头</h3>
      <Button size="sm" @click="handleAdd">
        <Plus class="w-4 h-4 mr-1" />
        新建抬头
      </Button>
    </CardHeader>
    <CardContent class="p-0">
      <!-- Empty State -->
      <div v-if="invoiceTitles.length === 0" class="p-8 text-center text-wolf-text-tertiary-v2">
        暂无发票抬头
      </div>

      <!-- Invoice Title List -->
      <div v-else class="divide-y divide-wolf-border-light-v2">
        <div
          v-for="title in invoiceTitles"
          :key="title.id"
          class="p-4 hover:bg-wolf-bg-hover-v2 transition-colors"
        >
          <!-- Header -->
          <div class="flex items-start justify-between mb-2">
            <div class="flex-1">
              <div class="flex items-center gap-2 mb-1">
                <component
                  :is="title.title_type === 'COMPANY' ? Building2 : User"
                  class="w-4 h-4 text-wolf-text-secondary-v2"
                />
                <span class="font-medium text-wolf-text-primary-v2">{{ title.title }}</span>
                <Badge
                  :class="getTitleTypeInfo(title.title_type).color"
                  class="text-xs"
                >
                  {{ getTitleTypeInfo(title.title_type).label }}
                </Badge>
                <Badge
                  v-if="title.is_default"
                  variant="secondary"
                  class="text-xs"
                >
                  <Star class="w-3 h-3 mr-1" />
                  默认
                </Badge>
              </div>
            </div>
          </div>

          <!-- Details -->
          <div class="text-sm text-wolf-text-secondary-v2 space-y-1 mb-3">
            <div class="flex items-center gap-2">
              <span class="text-wolf-text-tertiary-v2 w-16">税号:</span>
              <span class="font-mono">{{ maskTaxId(title.taxpayer_id) }}</span>
            </div>
            <div v-if="title.bank_name" class="flex items-center gap-2">
              <span class="text-wolf-text-tertiary-v2 w-16">银行:</span>
              <span>{{ title.bank_name }}</span>
            </div>
            <div v-if="title.bank_account" class="flex items-center gap-2">
              <span class="text-wolf-text-tertiary-v2 w-16">账号:</span>
              <span class="font-mono">{{ title.bank_account }}</span>
            </div>
            <div v-if="title.address" class="flex items-center gap-2">
              <span class="text-wolf-text-tertiary-v2 w-16">地址:</span>
              <span>{{ title.address }}</span>
            </div>
            <div v-if="title.phone" class="flex items-center gap-2">
              <span class="text-wolf-text-tertiary-v2 w-16">电话:</span>
              <span>{{ title.phone }}</span>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex justify-end gap-2">
            <Button
              v-if="!title.is_default"
              variant="ghost"
              size="sm"
              @click="handleSetDefault(title.id)"
            >
              <Star class="w-4 h-4" />
            </Button>
            <Button variant="ghost" size="sm" @click="handleEdit(title)">
              <Pencil class="w-4 h-4" />
            </Button>
            <Button variant="ghost" size="sm" @click="handleDelete(title.id)">
              <Trash2 class="w-4 h-4 text-wolf-danger-text-v2" />
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