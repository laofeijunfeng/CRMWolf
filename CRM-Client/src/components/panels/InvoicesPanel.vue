<script setup lang="ts">
/**
 * InvoicesPanel.vue - 客户发票面板组件
 *
 * 使用 ListCard 组件确保风格统一
 * 技术栈：shadcn-vue + variables-v2.scss
 * 无障碍：所有图标按钮均有 aria-label
 */
import { Plus, Pencil, Trash2, Star, Building2, User, ReceiptText, Download, Loader2 } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import ListCard from '@/components/crmwolf/ListCard.vue'
import type { InvoiceApplicationResponse, InvoiceApplicationStatus, InvoiceTitleResponse, InvoiceType, TitleType } from '@/api/invoice'

// ==================== Props & Emits ====================
interface Props {
  customerId: number
  invoiceTitles: InvoiceTitleResponse[]
  invoiceApplications: InvoiceApplicationResponse[]
  downloadingApplicationId?: number | null
}

withDefaults(defineProps<Props>(), {
  downloadingApplicationId: null
})

const emit = defineEmits<{
  'add': []
  'edit': [invoiceTitle: InvoiceTitleResponse]
  'delete': [titleId: number]
  'set-default': [titleId: number]
  'apply': [invoiceTitle: InvoiceTitleResponse]
  'download-application': [application: InvoiceApplicationResponse]
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

const handleDownloadApplication = (application: InvoiceApplicationResponse): void => {
  emit('download-application', application)
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

const getInvoiceTypeLabel = (type: InvoiceType): string => {
  const typeMap: Record<InvoiceType, string> = {
    VAT_SPECIAL: '增值税专用发票',
    VAT_NORMAL: '增值税普通发票'
  }
  return typeMap[type] ?? type
}

const getStatusInfo = (status: InvoiceApplicationStatus): { label: string; className: string } => {
  const statusMap: Record<InvoiceApplicationStatus, { label: string; className: string }> = {
    DRAFT: { label: '草稿', className: 'invoice-status invoice-status--draft' },
    PENDING_REVIEW: { label: '审批中', className: 'invoice-status invoice-status--pending' },
    APPROVED: { label: '已审批', className: 'invoice-status invoice-status--approved' },
    REJECTED: { label: '已驳回', className: 'invoice-status invoice-status--rejected' },
    ISSUED: { label: '已开票', className: 'invoice-status invoice-status--issued' },
    CANCELLED: { label: '已取消', className: 'invoice-status invoice-status--cancelled' }
  }
  return statusMap[status] ?? { label: status, className: 'invoice-status invoice-status--draft' }
}

const canDownloadApplication = (application: InvoiceApplicationResponse): boolean =>
  application.status === 'ISSUED' &&
  application.invoice_file_path !== null &&
  application.invoice_file_path.trim() !== ''

const formatCurrency = (value: string): string => {
  const amount = Number(value)
  if (!Number.isFinite(amount)) return '-'
  return amount.toLocaleString('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

const formatDate = (value: string | null): string => {
  if (value === null || value.trim() === '') return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  })
}
</script>

<template>
  <div class="invoices-panel">
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
        <div class="flex items-center gap-2 min-w-0">
          <component
            :is="item.title_type === 'COMPANY' ? Building2 : User"
            class="w-4 h-4 shrink-0 text-wolf-text-secondary-v2"
          />
          <span class="font-medium text-wolf-text-primary-v2 truncate">{{ item.title }}</span>
        </div>
      </template>

      <template #itemMeta="{ item }">
        <span>税号: </span>
        <span class="font-mono">{{ maskTaxId(item.taxpayer_id) }}</span>
        <span v-if="item.bank_name"> · {{ item.bank_name }}</span>
        <span v-if="item.bank_account"> · {{ item.bank_account }}</span>
        <span v-if="item.phone"> · {{ item.phone }}</span>
        <span v-if="item.address"> · {{ item.address }}</span>
      </template>

      <template #itemBadges="{ item }">
        <Badge :class="getTitleTypeInfo(item.title_type).color" class="text-xs">
          {{ getTitleTypeInfo(item.title_type).label }}
        </Badge>
        <Badge v-if="item.is_default" variant="secondary" class="text-xs">
          <Star class="w-3 h-3 mr-1" />
          默认
        </Badge>
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

    <ListCard
      title="发票申请"
      :items="invoiceApplications"
      empty-text="暂无发票申请"
    >
      <template #itemMain="{ item }">
        <div class="invoice-application-main">
          <span class="invoice-application-number">{{ item.application_number }}</span>
          <span class="invoice-application-title">{{ item.invoice_title_text }}</span>
        </div>
      </template>

      <template #itemMeta="{ item }">
        <span>{{ getInvoiceTypeLabel(item.invoice_type) }}</span>
        <span> · {{ formatCurrency(item.invoice_amount) }}</span>
        <span v-if="item.contract_name"> · {{ item.contract_name }}</span>
        <span> · 申请于 {{ formatDate(item.created_time) }}</span>
        <span v-if="item.invoice_number"> · 发票号 {{ item.invoice_number }}</span>
      </template>

      <template #itemBadges="{ item }">
        <Badge :class="getStatusInfo(item.status).className" class="text-xs">
          {{ getStatusInfo(item.status).label }}
        </Badge>
      </template>

      <template #itemActions="{ item }">
        <Button
          v-if="canDownloadApplication(item)"
          variant="ghost"
          size="sm"
          :aria-label="`下载发票申请 ${item.application_number} 的发票文件`"
          :disabled="downloadingApplicationId !== null"
          @click.stop="handleDownloadApplication(item)"
        >
          <Loader2 v-if="downloadingApplicationId === item.id" class="w-4 h-4 animate-spin" />
          <Download v-else class="w-4 h-4" />
          下载
        </Button>
      </template>
    </ListCard>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.invoices-panel {
  display: flex;
  flex-direction: column;
  gap: $wolf-section-gap-v2;

  :deep(.list-card) {
    height: auto;
  }
}

.invoice-application-main {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  min-width: 0;
}

.invoice-application-number {
  font-family: $wolf-font-mono-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
  white-space: nowrap;
}

.invoice-application-title {
  min-width: 0;
  overflow: hidden;
  color: $wolf-text-secondary-v2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.invoice-status {
  border: 1px solid transparent;
}

.invoice-status--draft {
  background: $wolf-bg-muted-v2;
  color: $wolf-text-secondary-v2;
}

.invoice-status--pending {
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
}

.invoice-status--approved,
.invoice-status--issued {
  background: $wolf-success-bg-v2;
  color: $wolf-success-text-v2;
}

.invoice-status--rejected,
.invoice-status--cancelled {
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-text-v2;
}
</style>
