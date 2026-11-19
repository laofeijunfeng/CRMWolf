<script setup lang="ts">
/**
 * InvoicesPanel.vue - 客户发票面板组件
 *
 * 使用 ListCard 组件确保风格统一
 * 技术栈：shadcn-vue + base.css 设计令牌
 * 无障碍：所有图标按钮均有 aria-label
 */
import { Plus, Pencil, Trash2, Star, Building2, User, ReceiptText, Download, Loader2 } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import ListCard from '@/components/crmwolf/ListCard.vue'
import { HoverInfo } from '@/components/crmwolf'
import type { InvoiceApplicationResponse, InvoiceApplicationStatus, InvoiceTitleResponse, InvoiceType, TitleType } from '@/api/invoice'
import { hasDownloadableInvoiceFile } from '@/utils/invoiceDownload'
import { getStatusPresentation, type StatusPresentation, type StatusTone } from '@/utils/statusPresentation'

// ==================== Props & Emits ====================
interface Props {
  customerId: string
  invoiceTitles: InvoiceTitleResponse[]
  invoiceApplications: InvoiceApplicationResponse[]
  downloadingApplicationId?: number | null
  showInvoiceTitles?: boolean
  showInvoiceApplications?: boolean
  showAddTitle?: boolean
  showAddApplication?: boolean
  showTitleApplyAction?: boolean
  canEditTitle?: boolean
  canDeleteTitle?: boolean
  canSetDefaultTitle?: boolean
}

withDefaults(defineProps<Props>(), {
  downloadingApplicationId: null,
  showInvoiceTitles: true,
  showInvoiceApplications: true,
  showAddTitle: true,
  showAddApplication: false,
  showTitleApplyAction: true,
  canEditTitle: true,
  canDeleteTitle: true,
  canSetDefaultTitle: true
})

const emit = defineEmits<{
  'add': []
  'add-application': []
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

const handleAddApplication = (): void => {
  emit('add-application')
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
const getTitleTypeInfo = (type: TitleType): { label: string; tone: StatusTone } => {
  const typeMap: Record<TitleType, { label: string; tone: StatusTone }> = {
    COMPANY: { label: '企业', tone: 'info' },
    PERSONAL: { label: '个人', tone: 'neutral' }
  }
  return typeMap[type] ?? { label: type, tone: 'neutral' }
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

const getStatusInfo = (status: InvoiceApplicationStatus): StatusPresentation => getStatusPresentation('invoiceApplication', status)

const canDownloadApplication = hasDownloadableInvoiceFile

const getApplicationCompanyName = (application: InvoiceApplicationResponse): string => {
  const customerName = application.customer_name?.trim()
  if (customerName !== undefined && customerName !== '') {
    return customerName
  }
  return application.invoice_title_text
}

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
      v-if="showInvoiceTitles"
      title="发票抬头"
      :items="invoiceTitles"
      empty-text="暂无发票抬头"
    >
      <template #headerActions>
        <Button v-if="showAddTitle" size="sm" @click="handleAdd">
          <Plus class="w-4 h-4 mr-1" />
          新建抬头
        </Button>
      </template>

      <template #itemMain="{ item }">
        <div class="flex items-center gap-2 min-w-0">
          <component
            :is="item.title_type === 'COMPANY' ? Building2 : User"
            class="w-4 h-4 shrink-0 text-muted-foreground"
          />
          <span class="font-medium text-foreground truncate">{{ item.title }}</span>
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
        <Badge variant="status" :data-tone="getTitleTypeInfo(item.title_type).tone" class="text-xs">
          {{ getTitleTypeInfo(item.title_type).label }}
        </Badge>
        <Badge v-if="item.is_default" variant="secondary" class="text-xs">
          <Star class="w-3 h-3 mr-1" />
          默认
        </Badge>
      </template>

      <template #itemActions="{ item }">
        <Button
          v-if="showTitleApplyAction"
          variant="ghost"
          size="sm"
          :aria-label="`使用 ${item.title} 申请发票`"
          @click.stop="handleApply(item)"
        >
          <ReceiptText class="w-4 h-4" />
          申请发票
        </Button>
        <Button
          v-if="canSetDefaultTitle && !item.is_default"
          variant="ghost"
          size="sm"
          :aria-label="`将 ${item.title} 设为默认发票抬头`"
          @click.stop="handleSetDefault(item.id)"
        >
          <Star class="w-4 h-4" />
        </Button>
        <Button
          v-if="canEditTitle"
          variant="ghost"
          size="sm"
          :aria-label="`编辑发票抬头 ${item.title}`"
          @click.stop="handleEdit(item)"
        >
          <Pencil class="w-4 h-4" />
        </Button>
        <Button
          v-if="canDeleteTitle"
          variant="ghost"
          size="sm"
          :aria-label="`删除发票抬头 ${item.title}`"
          @click.stop="handleDelete(item.id)"
        >
          <Trash2 class="w-4 h-4 text-danger" />
        </Button>
      </template>
    </ListCard>

    <ListCard
      v-if="showInvoiceApplications"
      title="发票申请"
      :items="invoiceApplications"
      empty-text="暂无发票申请"
    >
      <template #headerActions>
        <Button v-if="showAddApplication" size="sm" @click="handleAddApplication">
          <Plus class="w-4 h-4 mr-1" />
          申请发票
        </Button>
      </template>

      <template #itemMain="{ item }">
        <div class="invoice-application-main">
          <span class="invoice-application-title">{{ getApplicationCompanyName(item) }}</span>
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
        <Badge
          variant="status"
          :data-tone="getStatusInfo(item.status).tone"
          data-status-domain="invoiceApplication"
          :data-status-value="item.status"
          :title="getStatusInfo(item.status).traceValue === undefined ? undefined : `invoiceApplication: ${item.status}`"
          class="text-xs"
        >
          {{ getStatusInfo(item.status).label }}
        </Badge>
      </template>

      <template #itemActions="{ item }">
        <HoverInfo
          v-if="canDownloadApplication(item)"
          side="top"
          align="center"
          content-class="invoice-action-hover-card"
        >
          <template #trigger>
            <Button
              variant="ghost"
              size="icon"
              class="invoice-action-button invoice-action-button--primary"
              :aria-label="`下载发票申请 ${item.application_number} 的发票文件`"
              :disabled="downloadingApplicationId !== null"
              @click.stop="handleDownloadApplication(item)"
            >
              <Loader2 v-if="downloadingApplicationId === item.id" class="w-4 h-4 animate-spin" />
              <Download v-else class="w-4 h-4" />
            </Button>
          </template>
          <span class="invoice-action-hover-text">下载发票</span>
        </HoverInfo>
      </template>
    </ListCard>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.invoices-panel {
  display: flex;
  flex-direction: column;
  gap: $space-6;

  :deep(.list-card) {
    height: auto;
  }
}

.invoice-application-main {
  display: flex;
  align-items: center;
  gap: $space-2;
  min-width: 0;
}

.invoice-application-title {
  min-width: 0;
  overflow: hidden;
  color: hsl(var(--foreground));
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}


.invoice-action-button {
  width: 32px;
  height: 32px;
  color: hsl(var(--muted-foreground));
}

.invoice-action-button--primary {
  &:hover {
    color: hsl(var(--brand));
  }
}

:global(.invoice-action-hover-card) {
  width: auto;
  padding: 6px 10px;
}

.invoice-action-hover-text {
  display: inline-flex;
  color: hsl(var(--foreground));
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}
</style>
