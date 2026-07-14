<script setup lang="ts">
/**
 * ContractDetailSheet.vue - 合同详情抽屉组件
 *
 * 基于 MASTER.md §6.6 布局架构：
 * - 使用 shadcn-vue Sheet 组件 + DetailSheetContent
 * - 宽度：右侧 3/4（75%），最大 1080px
 * - V2 Design Tokens
 *
 * 包含：
 * - 合同基本信息
 * - 状态展示
 * - 授权类型展示
 * - 金额展示
 * - ContractDetailContent 业务内容委托
 */
import { ref, watch, computed } from 'vue'
import { handleApiError } from '@/utils/errorHandler'
import { toast } from 'vue-sonner'
import { FileText, Calendar, Coins, User, TrendingUp, PenLine, Users } from 'lucide-vue-next'
import {
  Sheet,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter
} from '@/components/ui/sheet'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import DetailSheetContent from '@/components/ui/detail-sheet/DetailSheetContent.vue'
import contractApi, { type ContractResponse, type ContractStatus, type LicenseType } from '@/api/contract'

// ==================== Props & Emits ====================
interface Props {
  visible: boolean
  contractNumber: string | null
  recordId: number | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:visible': [value: boolean]
  'refresh': []
  'deleted': []
  'closed': []
}>()

// ==================== State ====================
const loading = ref(false)
const contractData = ref<ContractResponse | null>(null)

// ==================== Methods ====================
const fetchContractDetail = async (): Promise<void> => {
  if (props.recordId === null) return

  loading.value = true
  try {
    const res = await contractApi.getContract(props.recordId)
    contractData.value = res
  } catch (error) {
    handleApiError(error, '获取合同详情')
    contractData.value = null
  } finally {
    loading.value = false
  }
}

const closeSheet = (): void => {
  emit('update:visible', false)
  emit('closed')
}

const handleEdit = (): void => {
  // TODO: Navigate to edit page or open edit dialog
  toast.info('编辑功能开发中')
}

// ==================== Status Helpers ====================
const getStatusText = (status: ContractStatus | undefined): string => {
  if (!status) return '-'
  const map: Record<ContractStatus, string> = {
    DRAFT: '草稿',
    PENDING_REVIEW: '审批中',
    SIGNED: '已签署',
    EFFECTIVE: '生效中',
    EXPIRED: '已到期',
    TERMINATED: '已终止'
  }
  return map[status] || '未知'
}

const getStatusClass = (status: ContractStatus | undefined): string => {
  if (!status) return ''
  const map: Record<ContractStatus, string> = {
    DRAFT: 'status-draft',
    PENDING_REVIEW: 'status-pending',
    SIGNED: 'status-signed',
    EFFECTIVE: 'status-effective',
    EXPIRED: 'status-expired',
    TERMINATED: 'status-terminated'
  }
  return map[status] || 'status-draft'
}

const getLicenseTypeText = (licenseType: LicenseType | undefined): string => {
  if (!licenseType) return '-'
  return licenseType === 'SUBSCRIPTION' ? '订阅' : '买断'
}

const getLicenseTypeClass = (licenseType: LicenseType | undefined): string => {
  if (!licenseType) return ''
  return licenseType === 'SUBSCRIPTION' ? 'license-subscription' : 'license-perpetual'
}

// ==================== Format Helpers ====================
const formatAmount = (amount: string | number | undefined): string => {
  if (amount === undefined || amount === null) return '0.00'
  if (amount === '') return '0.00'
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const formatDate = (dateStr: string | null | undefined): string => {
  if (dateStr === undefined || dateStr === null || dateStr === '') return '-'
  const date = new Date(dateStr)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

// ==================== Computed ====================
const signingContactName = computed((): string => {
  const name = contractData.value?.contact_info?.name
  return name !== undefined && name !== '' ? name : '-'
})

// ==================== Watch ====================
watch(() => props.visible, (visible): void => {
  if (visible && props.recordId !== null) {
    fetchContractDetail()
  } else if (!visible) {
    // Clear state when closed
    contractData.value = null
  }
})
</script>

<template>
  <Sheet :open="visible" @update:open="$emit('update:visible', $event)">
    <DetailSheetContent class="bg-white dark:bg-slate-900">
      <!-- Header -->
      <SheetHeader class="p-6 pb-4 border-b border-wolf-border-default-v2">
        <div class="flex items-center gap-4">
          <div v-if="contractData" class="title-avatar">
            {{ contractData.contract_name?.charAt(0) || '合' }}
          </div>
          <div class="flex-1 min-w-0">
            <SheetTitle class="text-lg font-semibold truncate">
              {{ contractData?.contract_name || '合同详情' }}
            </SheetTitle>
            <SheetDescription class="flex items-center gap-2 mt-2 flex-wrap">
              <span class="text-sm text-wolf-text-tertiary-v2">{{ contractData?.contract_number || '-' }}</span>
              <Badge v-if="contractData" :class="['status-badge', getStatusClass(contractData.status)]">
                {{ getStatusText(contractData.status) }}
              </Badge>
              <Badge v-if="contractData" :class="['license-badge', getLicenseTypeClass(contractData.license_type)]">
                {{ getLicenseTypeText(contractData.license_type) }}
              </Badge>
            </SheetDescription>
          </div>
          <div v-if="contractData" class="text-right flex-shrink-0">
            <div class="text-xs text-wolf-text-tertiary-v2">合同总金额</div>
            <div class="text-xl font-semibold text-wolf-primary-v2">
              ¥{{ formatAmount(contractData.total_amount) }}
            </div>
          </div>
        </div>
      </SheetHeader>

      <!-- Content -->
      <ScrollArea class="flex-1">
        <div class="p-6 space-y-6 min-h-[600px] transition-opacity duration-200">
          <!-- Loading Skeleton -->
          <template v-if="loading">
            <div class="space-y-4">
              <Skeleton class="h-32 w-full" />
              <Skeleton class="h-24 w-full" />
              <Skeleton class="h-48 w-full" />
            </div>
          </template>

          <template v-else-if="contractData">
            <!-- 基本信息 -->
            <Card class="info-card">
              <CardContent class="p-0">
                <div class="p-4 border-b border-wolf-border-light-v2">
                  <h3 class="text-sm font-semibold text-wolf-text-primary-v2">基本信息</h3>
                </div>
                <div class="p-4">
                  <div class="attributes-grid">
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <FileText class="attribute-icon" />
                        <span class="attribute-label">合同编号</span>
                      </div>
                      <span class="attribute-value">{{ contractData.contract_number || '-' }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <User class="attribute-icon" />
                        <span class="attribute-label">关联客户</span>
                      </div>
                      <span class="attribute-value">{{ contractData.customer_info?.account_name || '-' }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <TrendingUp class="attribute-icon" />
                        <span class="attribute-label">关联商机</span>
                      </div>
                      <span class="attribute-value">{{ contractData.opportunity_info?.opportunity_name || '-' }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <PenLine class="attribute-icon" />
                        <span class="attribute-label">签约人</span>
                      </div>
                      <span class="attribute-value" :class="{ 'value-empty': !signingContactName || signingContactName === '-' }">
                        {{ signingContactName }}
                      </span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Users class="attribute-icon" />
                        <span class="attribute-label">采购用户数</span>
                      </div>
                      <span class="attribute-value">{{ contractData.user_count || '-' }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Coins class="attribute-icon" />
                        <span class="attribute-label">标准单价</span>
                      </div>
                      <span class="attribute-value">¥{{ formatAmount(contractData.standard_unit_price) }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Calendar class="attribute-icon" />
                        <span class="attribute-label">订阅年限</span>
                      </div>
                      <span class="attribute-value">{{ contractData.subscription_years ? contractData.subscription_years + '年' : '-' }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Users class="attribute-icon" />
                        <span class="attribute-label">创建人</span>
                      </div>
                      <span class="attribute-value" :class="{ 'value-empty': !contractData.creator_info?.name }">
                        {{ contractData.creator_info?.name || '-' }}
                      </span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Calendar class="attribute-icon" />
                        <span class="attribute-label">签约日期</span>
                      </div>
                      <span class="attribute-value">{{ formatDate(contractData.signing_date) }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Calendar class="attribute-icon" />
                        <span class="attribute-label">生效日期</span>
                      </div>
                      <span class="attribute-value">{{ formatDate(contractData.effective_date) }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Calendar class="attribute-icon" />
                        <span class="attribute-label">到期日期</span>
                      </div>
                      <span class="attribute-value">{{ formatDate(contractData.expiry_date) }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Calendar class="attribute-icon" />
                        <span class="attribute-label">创建时间</span>
                      </div>
                      <span class="attribute-value">{{ formatDate(contractData.created_time) }}</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Separator />

            <!-- TODO: ContractDetailContent 组件（稍后创建） -->
            <!-- 业务内容区域预留 -->
            <div class="content-placeholder">
              <p class="text-wolf-text-tertiary-v2 text-sm text-center py-8">
                合同详细内容区域（ContractDetailContent 组件待实现）
              </p>
            </div>
          </template>

          <!-- Empty State -->
          <template v-else>
            <div class="empty-state">
              <FileText class="w-10 h-10 text-wolf-text-tertiary-v2 mb-2" />
              <p class="text-wolf-text-tertiary-v2">合同信息加载失败</p>
            </div>
          </template>
        </div>
      </ScrollArea>

      <!-- Footer -->
      <SheetFooter class="p-4 border-t border-wolf-border-default-v2 flex flex-row gap-2">
        <Button variant="outline" @click="handleEdit">
          <PenLine class="w-4 h-4 mr-2" />
          编辑
        </Button>
        <Button variant="outline" @click="closeSheet">
          关闭
        </Button>
      </SheetFooter>
    </DetailSheetContent>
  </Sheet>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.title-avatar {
  width: 48px;
  height: 48px;
  border-radius: $wolf-radius-full-v2;
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: $wolf-font-weight-semibold-v2;
  flex-shrink: 0;
}

.attributes-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: $wolf-space-md-v2 $wolf-space-lg-v2;

  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    grid-template-columns: repeat(2, 1fr);
  }

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
  }
}

.attribute-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.attribute-header {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
}

.attribute-icon {
  width: 14px;
  height: 14px;
  color: $wolf-text-tertiary-v2;
  flex-shrink: 0;
}

.attribute-label {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.attribute-value {
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-primary-v2;
  font-weight: $wolf-font-weight-medium-v2;
  word-break: break-all;

  &.value-empty {
    color: $wolf-text-placeholder-v2;
  }
}

// Status Badge
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  border-radius: $wolf-radius-full-v2;
  white-space: nowrap;
}

.status-draft {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-tertiary-v2;
}

.status-pending {
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
}

.status-signed {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-secondary-v2;
}

.status-effective {
  background: $wolf-success-bg-v2;
  color: $wolf-success-text-v2;
}

.status-expired {
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-text-v2;
}

.status-terminated {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-placeholder-v2;
}

// License Type Badge
.license-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  border-radius: $wolf-radius-full-v2;
  white-space: nowrap;
}

.license-subscription {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-tertiary-v2;
}

.license-perpetual {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-secondary-v2;
}

// Content Placeholder
.content-placeholder {
  background: $wolf-bg-muted-v2;
  border-radius: $wolf-radius-v2;
  border: 1px dashed $wolf-border-default-v2;
}

// Empty State
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

// Reduced Motion 支持
@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>