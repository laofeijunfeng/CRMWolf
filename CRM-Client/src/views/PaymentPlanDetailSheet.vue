<script setup lang="ts">
/**
 * PaymentPlanDetailSheet.vue - 回款计划详情抽屉组件
 *
 * 基于 MASTER.md §6.6 布局架构：
 * - 使用 shadcn-vue Sheet 组件 + DetailSheetContent
 * - 宽度：右侧 3/4（75%），最大 1080px
 * - V2 Design Tokens
 *
 * Header 显示：
 * - 回款计划编号
 * - 关联合同
 * - 客户名称
 * - 阶段名称
 * - 状态
 * - 金额
 *
 * Footer 操作：
 * - 编辑
 * - 登记回款
 * - 重新提交审批
 * - 查看合同
 */
import { ref, watch, computed } from 'vue'
import { toast } from 'vue-sonner'
import {
  FileText,
  Calendar,
  Coins,
  User,
  PenLine,
  RefreshCw,
  Eye
} from 'lucide-vue-next'
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
import PaymentPlanDetailContent from './PaymentPlanDetailContent.vue'
import paymentApi, {
  type PaymentPlanResponse,
  type PaymentPlanStatus
} from '@/api/payment'
import { handleApiError } from '@/utils/errorHandler'

// ==================== Props & Emits ====================
interface Props {
  visible: boolean
  planNumber: string | null
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
const planData = ref<PaymentPlanResponse | null>(null)

// ==================== Methods ====================
const fetchPlanDetail = async (): Promise<void> => {
  if (props.recordId === null) return

  loading.value = true
  try {
    const res = await paymentApi.getPaymentPlanDetail(props.recordId)
    planData.value = res
  } catch (error) {
    handleApiError(error, '获取回款计划详情')
    planData.value = null
  } finally {
    loading.value = false
  }
}

const closeSheet = (): void => {
  emit('update:visible', false)
  emit('closed')
}

const handleEdit = (): void => {
  toast.info('编辑功能开发中')
}

const handleRegisterPayment = (): void => {
  toast.info('登记回款功能开发中')
}

const handleResubmitApproval = (): void => {
  toast.info('重新提交审批功能开发中')
}

const handleViewContract = (): void => {
  toast.info('查看合同功能开发中')
}

// ==================== Status Helpers ====================
const getStatusText = (status: PaymentPlanStatus | undefined): string => {
  if (status === undefined) return '-'
  const map: Record<PaymentPlanStatus, string> = {
    'PENDING': '待回款',
    'OVERDUE': '已逾期',
    'PARTIAL': '部分回款',
    'COMPLETED': '已完成'
  }
  const result = map[status]
  return result !== undefined ? result : '未知'
}

const getStatusClass = (status: PaymentPlanStatus | undefined): string => {
  if (status === undefined) return ''
  const map: Record<PaymentPlanStatus, string> = {
    'PENDING': 'status-pending',
    'OVERDUE': 'status-overdue',
    'PARTIAL': 'status-partial',
    'COMPLETED': 'status-completed'
  }
  const result = map[status]
  return result !== undefined ? result : 'status-pending'
}

// ==================== Format Helpers ====================
const formatAmount = (amount: number | undefined): string => {
  if (amount === undefined || amount === null) return '0.00'
  return amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
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
const hasRejectedApproval = computed((): boolean => {
  return planData.value?.latest_approval?.status === 'REJECTED'
})

const isCompleted = computed((): boolean => {
  return planData.value?.status === 'COMPLETED'
})

// ==================== Watch ====================
watch(() => props.visible, (visible): void => {
  if (visible && props.recordId !== null) {
    fetchPlanDetail()
  } else if (!visible) {
    planData.value = null
  }
})
</script>

<template>
  <Sheet :open="visible" @update:open="$emit('update:visible', $event)">
    <DetailSheetContent class="bg-white dark:bg-slate-900">
      <!-- Header -->
      <SheetHeader class="p-6 pb-4 border-b border-wolf-border-default-v2">
        <div class="flex items-center gap-4">
          <div v-if="planData" class="title-avatar">
            {{ planData.stage_name?.charAt(0) || '回' }}
          </div>
          <div class="flex-1 min-w-0">
            <SheetTitle class="text-lg font-semibold truncate">
              {{ planData?.stage_name || '回款计划详情' }}
            </SheetTitle>
            <SheetDescription class="flex items-center gap-2 mt-2 flex-wrap">
              <span class="text-sm text-wolf-text-tertiary-v2">{{ planData?.plan_number || '-' }}</span>
              <Badge v-if="planData" :class="['status-badge', getStatusClass(planData.status)]">
                {{ getStatusText(planData.status) }}
              </Badge>
            </SheetDescription>
          </div>
          <div v-if="planData" class="text-right flex-shrink-0">
            <div class="text-xs text-wolf-text-tertiary-v2">计划金额</div>
            <div class="text-xl font-semibold text-wolf-primary-v2">
              ¥{{ formatAmount(planData.planned_amount) }}
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

          <template v-else-if="planData">
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
                        <span class="attribute-label">计划编号</span>
                      </div>
                      <span class="attribute-value">{{ planData.plan_number || '-' }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <FileText class="attribute-icon" />
                        <span class="attribute-label">关联合同</span>
                      </div>
                      <span class="attribute-value">{{ planData.contract_name || '-' }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <User class="attribute-icon" />
                        <span class="attribute-label">客户名称</span>
                      </div>
                      <span class="attribute-value">{{ planData.customer_name || '-' }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Calendar class="attribute-icon" />
                        <span class="attribute-label">计划日期</span>
                      </div>
                      <span class="attribute-value">{{ formatDate(planData.due_date) }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Coins class="attribute-icon" />
                        <span class="attribute-label">计划金额</span>
                      </div>
                      <span class="attribute-value mono-number">¥{{ formatAmount(planData.planned_amount) }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Coins class="attribute-icon" />
                        <span class="attribute-label">已回款金额</span>
                      </div>
                      <span class="attribute-value mono-number text-wolf-success-text-v2">¥{{ formatAmount(planData.paid_amount) }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Coins class="attribute-icon" />
                        <span class="attribute-label">待回款金额</span>
                      </div>
                      <span class="attribute-value mono-number text-wolf-warning-text-v2">¥{{ formatAmount(planData.remaining_amount) }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <PenLine class="attribute-icon" />
                        <span class="attribute-label">备注</span>
                      </div>
                      <span class="attribute-value" :class="{ 'value-empty': !planData.notes }">
                        {{ planData.notes || '-' }}
                      </span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Separator />

            <!-- 回款进度与记录 -->
            <PaymentPlanDetailContent
              v-if="planData"
              :record-id="planData.id"
              @refresh="fetchPlanDetail"
            />
          </template>

          <!-- Empty State -->
          <template v-else>
            <div class="empty-state">
              <FileText class="w-10 h-10 text-wolf-text-tertiary-v2 mb-2" />
              <p class="text-wolf-text-tertiary-v2">回款计划信息加载失败</p>
            </div>
          </template>
        </div>
      </ScrollArea>

      <!-- Footer -->
      <SheetFooter class="p-4 border-t border-wolf-border-default-v2 flex flex-row gap-2">
        <Button
          v-if="!isCompleted"
          variant="outline"
          @click="handleEdit"
        >
          <PenLine class="w-4 h-4 mr-2" />
          编辑
        </Button>
        <Button
          v-if="!isCompleted"
          @click="handleRegisterPayment"
        >
          <Coins class="w-4 h-4 mr-2" />
          登记回款
        </Button>
        <Button
          v-if="hasRejectedApproval && !isCompleted"
          variant="secondary"
          @click="handleResubmitApproval"
        >
          <RefreshCw class="w-4 h-4 mr-2" />
          重新提交审批
        </Button>
        <Button
          variant="ghost"
          @click="handleViewContract"
        >
          <Eye class="w-4 h-4 mr-2" />
          查看合同
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

.mono-number {
  font-family: $wolf-font-mono-v2;
  font-variant-numeric: tabular-nums lining-nums;
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

.status-pending {
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
}

.status-overdue {
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-text-v2;
}

.status-partial {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-secondary-v2;
}

.status-completed {
  background: $wolf-success-bg-v2;
  color: $wolf-success-text-v2;
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