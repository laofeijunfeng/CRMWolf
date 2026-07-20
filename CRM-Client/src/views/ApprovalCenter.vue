<!--
  ApprovalCenter — 审批中心

  基于 V2 设计规范重构：
  - TopBar 集成 ContextTabs（待我审批/我已处理/我提交的，权限驱动）+ Badge 显示待办数
  - DataTable 工具栏筛选（单据类型）
  - DataTable（桌面端表格）+ 键盘快捷键（J/K 上下行、Enter 开 Sheet、Esc 关 Sheet）
  - 移动端卡片列表 + 快速审批按钮（Touch Target ≥44pt）
  - DetailSheetContent（统一详情抽屉样式）
  - V2 Design Tokens 统一样式

  核心功能：
  - 待我审批按 overdue_hours 降序排列
  - 超时徽章（overdue_hours>=48）实时提醒
  - Sheet 关闭焦点回归触发行
  - 单号 mono 字体 + 点击复制
  - 快速审批（同意/驳回）
  - REJECTED 行显示「修改并重新提交」

  权限过滤：列表查询严格按 tab 角色过滤参数传后端。前端不伪造过滤。
  性能优化：列表只调 1 次 listApprovals；详情走单点 getApprovalDetail。
-->
<template>
  <div class="approval-center">
    <!-- 标题 + 全局 ErrorState（403 forbidden / 加载失败） -->
    <ErrorState
      v-if="loadError === 'forbidden'"
      variant="forbidden"
      title="你没有该审批中心的访问权限"
    >
      <template #action>
        <Button data-testid="reload-list-btn" @click="reload">重新加载</Button>
      </template>
    </ErrorState>
    <ErrorState
      v-else-if="loadError === 'error'"
      title="审批列表加载失败"
      description="可点击下方按钮重新加载，若持续失败请联系管理员"
    >
      <template #action>
        <Button data-testid="reload-list-btn" variant="default" @click="reload">重新加载</Button>
      </template>
    </ErrorState>

    <template v-else>
      <!-- DataTable（桌面端） -->
      <DataTable
        v-if="!isMobile"
        v-model:filters="activeFilters"
        :columns="columns"
        :data="rows"
        :total="total"
        :page="page"
        :page-size="pageSize"
        :loading="listLoading"
        :filter-fields="filterFields"
        height="calc(100vh - 248px)"
        empty-title="暂无待审批事项"
        row-interactive
        @update:page="page = $event; fetchList()"
        @update:page-size="pageSize = $event; page = 1; fetchList()"
        @filter-apply="handleFilterApply"
        @filter-reset="handleFilterReset"
        @row-click="openDetail"
      >
        <!-- 单号列：mono font + 点击复制 -->
        <template #cell-application_number="{ row }">
          <Button
            type="button"
            variant="link"
            class="font-mono px-0"
            data-testid="copy-number"
            :aria-label="`复制审批单号 ${row.application_number}`"
            @click.stop="copyNumber(row.application_number)"
          >
            <Copy class="w-4 h-4" aria-hidden="true" />
            {{ row.application_number }}
          </Button>
        </template>

        <!-- 类型列 -->
        <template #cell-business_type="{ row }">
          <span class="text-secondary">{{ businessTypeLabel(row.business_type) }}</span>
        </template>

        <!-- 实体列 -->
        <template #cell-entity_name="{ row }">
          <span>{{ row.entity_name || '-' }}</span>
        </template>

        <!-- 金额列：mono font + 强调 -->
        <template #cell-entity_amount="{ row }">
          <AmountText :value="row.entity_amount" tone="warning" />
        </template>

        <!-- 时间列：relative time -->
        <template #cell-created_time="{ row }">
          <span class="font-mono text-muted-foreground text-sm">
            {{ formatDateRelative(row.created_time) }}
          </span>
        </template>

        <!-- 状态列：ApprovalStatusBadge -->
        <template #cell-status="{ row }">
          <ApprovalStatusBadge :status="row.status" size="small" />
        </template>

        <!-- 超时列：徽章 -->
        <template #cell-overdue_hours="{ row }">
          <Badge
            v-if="row.overdue_hours != null && row.overdue_hours >= 48"
            class="gap-1 overdue-badge-inline"
            role="status"
            :aria-label="`超时 ${row.overdue_hours} 小时`"
          >
            <Clock class="w-3 h-3" />
            超时 {{ row.overdue_hours }} 小时
          </Badge>
          <span v-else class="text-muted-foreground">-</span>
        </template>

        <!-- 操作列 -->
        <template #cell-actions="{ row }">
          <div class="flex gap-2 justify-center">
            <Button
              variant="ghost"
              size="sm"
              data-testid="detail-btn"
              @click.stop="openDetail(row)"
            >
              详情
            </Button>
            <Button
              v-if="activeTab === 'submitted' && row.status === 'REJECTED'"
              variant="ghost"
              size="sm"
              data-testid="resubmit-btn"
              :loading="resubmitPendingId === row.id"
              @click.stop="handleResubmit(row)"
            >
              修改并重新提交
            </Button>
          </div>
        </template>
      </DataTable>

      <!-- 移动端卡片列表 -->
      <div v-if="isMobile" class="space-y-4">
        <div class="approval-mobile-tools">
          <ListFilterPopover
            :model-value="activeFilters"
            :fields="filterFields"
            @update:model-value="activeFilters = $event"
            @apply="handleFilterApply"
            @reset="handleFilterReset"
          />
        </div>

        <div v-if="listLoading" class="approval-mobile-loading">
          加载中...
        </div>

        <Card
          v-for="(row, $index) in rows"
          :key="row.id"
          :class="cn(
            'relative',
            row.overdue_hours != null && row.overdue_hours >= 48 && 'border-warning'
          )"
        >
          <CardContent class="p-4">
            <!-- 卡片头部：单号 + 状态 -->
            <div class="flex justify-between items-center mb-3">
              <span
                class="font-mono text-primary text-base cursor-pointer"
                data-testid="copy-number-mobile"
                @click="copyNumber(row.application_number)"
              >
                {{ row.application_number }}
              </span>
              <ApprovalStatusBadge :status="row.status" size="small" />
            </div>

            <!-- 卡片主体：实体 + 金额 -->
            <div class="flex justify-between items-center mb-3">
              <span class="text-base font-medium max-w-[60%] truncate">
                {{ row.entity_name || '-' }}
              </span>
              <AmountText :value="row.entity_amount" size="lg" tone="warning" />
            </div>

            <!-- 卡片次要信息：提交人 + 时间 -->
            <div class="flex justify-between text-sm text-muted-foreground mb-3">
              <span class="max-w-[50%] truncate">{{ row.submitter_name }} 提交</span>
              <span>{{ formatDateRelative(row.created_time) }}</span>
            </div>

            <!-- 超时提示 -->
            <div v-if="row.overdue_hours != null && row.overdue_hours >= 48" class="mb-3">
              <Badge class="gap-1 bg-warning text-warning-foreground border-transparent">
                <Clock class="w-3 h-3" />
                超时 {{ row.overdue_hours }} 小时
              </Badge>
            </div>

            <Separator class="my-3" />

            <!-- 操作按钮（Touch Target ≥44pt） -->
            <div class="flex gap-2" v-if="activeTab === 'pending'">
              <Button
                variant="default"
                size="lg"
                class="flex-1 min-h-[44px]"
                data-testid="mobile-approve-btn"
                @click="handleQuickApprove(row)"
              >
                同意
              </Button>
              <Button
                variant="destructive"
                size="lg"
                class="flex-1 min-h-[44px]"
                data-testid="mobile-reject-btn"
                @click="handleQuickReject(row)"
              >
                驳回
              </Button>
              <Button
                variant="outline"
                size="lg"
                class="flex-1 min-h-[44px]"
                data-testid="mobile-detail-btn"
                @click="openDetail(row, $index)"
              >
                详情
              </Button>
            </div>
            <div class="flex gap-2" v-else-if="activeTab === 'submitted' && row.status === 'REJECTED'">
              <Button
                variant="default"
                size="lg"
                class="flex-1 min-h-[44px]"
                data-testid="mobile-resubmit-btn"
                :loading="resubmitPendingId === row.id"
                @click="handleResubmit(row)"
              >
                修改并重新提交
              </Button>
            </div>
            <div class="flex gap-2" v-else>
              <Button
                variant="outline"
                size="lg"
                class="flex-1 min-h-[44px]"
                data-testid="mobile-detail-btn"
                @click="openDetail(row, $index)"
              >
                详情
              </Button>
            </div>
          </CardContent>
        </Card>

        <!-- 移动端空态 -->
        <Empty
          v-if="!listLoading && rows.length === 0"
          class="min-h-[220px] border-0"
        >
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Clock class="h-5 w-5" aria-hidden="true" />
            </EmptyMedia>
            <EmptyTitle>暂无待审批事项</EmptyTitle>
            <EmptyDescription>所有回款与发票申请都已处理完毕</EmptyDescription>
          </EmptyHeader>
        </Empty>

        <!-- 移动端分页 -->
        <div v-if="rows.length > 0" class="flex flex-col items-center gap-2 py-4 pb-[env(safe-area-inset-bottom)]">
          <span class="text-sm text-muted-foreground">共 {{ total }} 条</span>
          <Pagination
            v-model:page="page"
            :total="total"
            :items-per-page="pageSize"
            @update:page="fetchList"
          >
            <PaginationContent>
              <PaginationPrevious />
              <PaginationItem
                v-for="item in getPageItems()"
                :key="item"
                :value="item"
              >
                {{ item }}
              </PaginationItem>
              <PaginationNext />
            </PaginationContent>
          </Pagination>
        </div>
      </div>
    </template>

    <!-- 详情 Sheet -->
    <Sheet v-model:open="sheetVisible" @closed="onSheetClosed">
      <DetailSheetContent>
        <!-- Header -->
        <SheetHeader class="p-6 pb-4 border-b border-wolf-border-default-v2">
          <SheetTitle class="text-lg font-semibold">审批详情</SheetTitle>
          <SheetDescription class="font-mono text-sm mt-1">
            {{ selectedApproval?.application_number || '-' }}
          </SheetDescription>
        </SheetHeader>

        <!-- Content -->
        <ScrollArea class="flex-1">
          <div class="p-6 space-y-6 min-h-[400px]">
            <!-- 申请主体信息：优先展示审批关联业务内容 -->
            <Card v-if="selectedApproval" class="info-card">
              <CardContent class="p-0">
                <div class="p-4 border-b border-wolf-border-light-v2">
                  <h3 class="text-sm font-semibold text-wolf-text-primary-v2">{{ approvalSubjectTitle }}</h3>
                </div>
                <div class="p-4">
                  <div class="attributes-grid">
                    <div
                      v-for="field in approvalSubjectFields"
                      :key="field.key"
                      :class="cn('attribute-item', field.wide && 'attribute-item-wide')"
                    >
                      <div class="attribute-label">{{ field.label }}</div>
                      <button
                        v-if="field.type === 'copy'"
                        type="button"
                        class="attribute-value attribute-value-link font-mono text-left"
                        @click="copyNumber(displayFieldValue(field.value))"
                      >
                        {{ displayFieldValue(field.value) }}
                      </button>
                      <div v-else-if="field.type === 'amount'" class="attribute-value">
                        <AmountText :value="typeof field.value === 'number' ? field.value : null" tone="warning" />
                      </div>
                      <div v-else-if="field.type === 'status'" class="attribute-value">
                        <Badge variant="outline">{{ displayFieldValue(field.value) }}</Badge>
                      </div>
                      <div v-else-if="field.type === 'mono'" class="attribute-value font-mono text-sm">{{ displayFieldValue(field.value) }}</div>
                      <div v-else class="attribute-value">{{ displayFieldValue(field.value) }}</div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card v-if="approvalCustomerInfo" class="info-card">
              <CardContent class="p-0">
                <div class="p-4 border-b border-wolf-border-light-v2">
                  <h3 class="text-sm font-semibold text-wolf-text-primary-v2">关联客户</h3>
                </div>
                <div class="p-4">
                  <div class="attributes-grid">
                    <div class="attribute-item">
                      <div class="attribute-label">客户名称</div>
                      <div class="attribute-value">{{ approvalCustomerInfo.account_name }}</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">所在城市</div>
                      <div class="attribute-value">{{ approvalCustomerInfo.city || '-' }}</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">所属行业</div>
                      <div class="attribute-value">{{ approvalCustomerInfo.industry || '-' }}</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">公司规模</div>
                      <div class="attribute-value">{{ approvalCustomerInfo.company_scale || '-' }}</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">客户来源</div>
                      <div class="attribute-value">{{ approvalCustomerInfo.source || '-' }}</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">客户状态</div>
                      <div class="attribute-value">{{ customerStatusLabel(approvalCustomerInfo.status) }}</div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <!-- 审批流程组件（内部处理加载/错误/空态） -->
            <ApprovalProcessGeneric
              v-if="selectedApproval"
              :entity-type="selectedApproval.business_type"
              :entity-id="selectedApproval.business_id"
              :can-approve="activeTab === 'pending'"
              :is-submitter="activeTab === 'submitted'"
              :show-invoice-upload-action="false"
              @approved="onApprovalActionDone"
              @rejected="onApprovalActionDone"
              @withdrawn="onApprovalActionDone"
              @submitted="onApprovalActionDone"
              @resubmit="onResubmit"
            />
          </div>
        </ScrollArea>

        <!-- Footer -->
        <SheetFooter
          v-if="showInvoiceUploadFooter"
          class="p-4 border-t border-wolf-border-default-v2 flex flex-row justify-end gap-2"
        >
          <Button
            data-testid="mark-issued-btn"
            aria-label="上传发票文件，审批已通过"
            @click="markIssuedDialogVisible = true"
          >
            上传发票文件
          </Button>
        </SheetFooter>
      </DetailSheetContent>
    </Sheet>

    <InvoiceMarkIssuedDialog
      v-if="selectedApproval?.business_type === 'INVOICE'"
      v-model:open="markIssuedDialogVisible"
      :application-id="selectedApproval.business_id"
      @issued="handleInvoiceFileUploaded"
    />

    <!-- 移动端快速驳回弹窗 -->
    <Dialog v-model:open="quickRejectVisible">
      <DialogContent class="max-w-[90vw]">
        <DialogHeader>
          <DialogTitle>驳回审批</DialogTitle>
          <DialogDescription>
            请填写驳回理由，提交人将据此修改。
          </DialogDescription>
        </DialogHeader>

        <div class="space-y-4">
          <Textarea
            v-model="quickRejectReason"
            data-testid="quick-reject-reason"
            placeholder="请填写驳回理由"
            :rows="4"
            :maxlength="500"
            class="min-h-[44px]"
          />
          <p class="text-sm text-muted-foreground text-right">
            {{ quickRejectReason.length }} / 500
          </p>
        </div>

        <DialogFooter>
          <Button variant="ghost" @click="quickRejectVisible = false">
            取消
          </Button>
          <Button
            variant="default"
            data-testid="quick-reject-confirm-btn"
            @click="confirmQuickReject"
          >
            确定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- 合同编辑弹窗 -->
    <ContractFormDialog
      v-model:open="contractEditVisible"
      :contract="editingContract"
      @success="handleContractEditSuccess"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, onUnmounted, ref, watch, watchEffect } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { Clock, Copy } from 'lucide-vue-next'
import { AmountText, DataTable, Badge, Separator, ListFilterPopover } from '@/components/crmwolf'
import type { ListFilterCondition, ListFilterField } from '@/components/crmwolf/listFilterTypes'
import { Pagination, PaginationContent, PaginationItem, PaginationPrevious, PaginationNext } from '@/components/ui/pagination'
import { Button } from '@/components/ui/button'
import { Sheet, SheetHeader, SheetTitle, SheetDescription, SheetFooter } from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import { Card, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle
} from '@/components/ui/empty'
import { cn } from '@/lib/utils'
import ApprovalStatusBadge from '@/components/ApprovalStatusBadge.vue'
import ApprovalProcessGeneric from '@/components/ApprovalProcessGeneric.vue'
import ErrorState from '@/components/ErrorState.vue'
import ContractFormDialog from '@/components/dialogs/ContractFormDialog.vue'
import InvoiceMarkIssuedDialog from '@/components/dialogs/InvoiceMarkIssuedDialog.vue'
import { useApprovalStore } from '@/stores/approval'
import { usePermissionStore } from '@/stores/permissions'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { formatDateRelative } from '@/utils/format'
import { createConfirmDialog } from '@/utils/confirmDialogImpl'
import contractApi from '@/api/contract'
import type { EntityType, ApprovalCustomerInfo, ApprovalDetail, ApprovalListItem } from '@/schemas/approvalGeneric'
import type { ContractResponse } from '@/api/contract'

type Tab = 'pending' | 'processed' | 'submitted'
type LoadError = null | 'error' | 'forbidden'
interface ApprovalSubjectField {
  key: string
  label: string
  value: string | number | null | undefined
  type?: 'text' | 'copy' | 'amount' | 'status' | 'mono'
  wide?: boolean
}

// ==================== Stores ====================
usePageTitle()
const store = useApprovalStore()
const permissionStore = usePermissionStore()
const headerStore = useHeaderStore()
const { pendingCount, currentApprovalDetail } = storeToRefs(store)
const router = useRouter()

// ==================== State ====================
const activeTab = ref<Tab>('pending')
const activeFilters = ref<ListFilterCondition[]>([])

const page = ref<number>(1)
const pageSize = ref<number>(20)
const total = ref<number>(0)
const rows = ref<ApprovalListItem[]>([])
const loadError = ref<LoadError>(null)

// 列表加载状态（独立于 Sheet 详情加载）
const listLoading = ref<boolean>(false)

const sheetVisible = ref<boolean>(false)
const selectedApproval = ref<ApprovalListItem | null>(null)
const markIssuedDialogVisible = ref<boolean>(false)
const triggerRowIndex = ref<number>(-1)
const focusedRowEl = ref<HTMLElement | null>(null)

const resubmitPendingId = ref<number | null>(null)

// 合同编辑弹窗状态
const contractEditVisible = ref<boolean>(false)
const editingContract = ref<ContractResponse | null>(null)
const contractLoading = ref<boolean>(false)

// 移动端检测（响应式）
const isMobile = ref<boolean>(false)
const checkMobile = (): void => {
  isMobile.value = typeof window !== 'undefined' && window.innerWidth < 768
}

// 快速驳回弹窗
const quickRejectVisible = ref<boolean>(false)
const quickRejectReason = ref<string>('')
const quickRejectRow = ref<ApprovalListItem | null>(null)

// ==================== 计算属性 ====================
const activeApprovalDetail = computed<ApprovalDetail | null>(() => {
  const selected = selectedApproval.value
  const detail = currentApprovalDetail.value
  if (!selected || !detail) return null
  return detail.business_type === selected.business_type && detail.business_id === selected.business_id
    ? detail
    : null
})

const showInvoiceUploadFooter = computed<boolean>(() =>
  selectedApproval.value?.business_type === 'INVOICE' &&
  activeApprovalDetail.value?.business_type === 'INVOICE' &&
  activeApprovalDetail.value.status === 'APPROVED' &&
  (activeApprovalDetail.value.invoice_file_path == null || activeApprovalDetail.value.invoice_file_path.length === 0) &&
  permissionStore.hasPermission('invoice:mark_issued')
)

const subjectNumber = computed<string>(() =>
  activeApprovalDetail.value?.application_number ?? selectedApproval.value?.application_number ?? '-'
)

const subjectName = computed<string | null | undefined>(() =>
  activeApprovalDetail.value?.entity_name ?? selectedApproval.value?.entity_name
)

const subjectAmount = computed<number | null | undefined>(() =>
  activeApprovalDetail.value?.entity_amount ?? selectedApproval.value?.entity_amount
)

const subjectActualPayerName = computed<string | null | undefined>(() =>
  activeApprovalDetail.value?.actual_payer_name ?? selectedApproval.value?.actual_payer_name
)

const approvalCustomerInfo = computed<ApprovalCustomerInfo | null>(() =>
  activeApprovalDetail.value?.customer_info ?? selectedApproval.value?.customer_info ?? null
)

const approvalSubjectTitle = computed<string>(() => {
  const type = selectedApproval.value?.business_type
  const map: Partial<Record<EntityType, string>> = {
    CONTRACT: '合同信息',
    PAYMENT: '回款信息',
    INVOICE: '发票申请信息',
    LICENSE: 'License 申请信息',
    OPPORTUNITY: '商机信息'
  }
  return type ? map[type] ?? '申请信息' : '申请信息'
})

const licenseStatusLabel = (status?: string | null): string => {
  const map: Record<string, string> = {
    DRAFT: '草稿',
    PENDING_REVIEW: '审批中',
    APPROVED: '已通过',
    REJECTED: '已驳回',
    ISSUED: '已签发'
  }
  return status == null ? '-' : (map[status] ?? status)
}

const licenseTypeLabel = (type?: string | null): string => {
  const map: Record<string, string> = {
    TRIAL: '试用版',
    OFFICIAL: '正式版',
    SUBSCRIPTION: '订阅',
    PERPETUAL: '买断'
  }
  return type == null ? '-' : (map[type] ?? type)
}

const purchaseTypeLabel = (type?: string | null): string => {
  const map: Record<string, string> = {
    NEW: '新购',
    RENEWAL: '续购',
    EXPANSION: '增购'
  }
  return type == null ? '-' : (map[type] ?? type)
}

const paymentConfirmStatusLabel = (status?: string | null): string => {
  const map: Record<string, string> = {
    DRAFT: '草稿',
    PENDING: '待确认',
    CONFIRMED: '已确认',
    DISPUTED: '有争议'
  }
  return status == null ? '-' : (map[status] ?? status)
}

const paymentStatusLabel = (status?: string | null): string => {
  const map: Record<string, string> = {
    UNPAID: '未回款',
    PARTIAL: '部分回款',
    COMPLETED: '已完成',
    OVERDUE: '已逾期'
  }
  return status == null ? '-' : (map[status] ?? status)
}

const contractStatusLabel = (status?: string | null): string => {
  const map: Record<string, string> = {
    DRAFT: '草稿',
    PENDING_REVIEW: '审批中',
    SIGNED: '已签署',
    EFFECTIVE: '已生效',
    EXPIRED: '已到期',
    TERMINATED: '已终止'
  }
  return status == null ? '-' : (map[status] ?? status)
}

const invoiceStatusLabel = (status?: string | null): string => {
  const map: Record<string, string> = {
    DRAFT: '草稿',
    PENDING_REVIEW: '审批中',
    APPROVED: '已通过',
    REJECTED: '已驳回',
    ISSUED: '已开票'
  }
  return status == null ? '-' : (map[status] ?? status)
}

const invoiceTypeLabel = (type?: string | null): string => {
  const map: Record<string, string> = {
    VAT_SPECIAL: '增值税专用发票',
    VAT_NORMAL: '普通发票'
  }
  return type == null ? '-' : (map[type] ?? type)
}

const opportunityStatusLabel = (status?: number | string | null): string => {
  const map: Record<string, string> = {
    '0': '跟进中',
    '1': '已赢单',
    '2': '已输单'
  }
  return status == null ? '-' : (map[String(status)] ?? String(status))
}

const entityDetailValue = (key: string): string | number | null | undefined => {
  const detail = activeApprovalDetail.value?.entity_detail
  const value = detail?.[key]
  if (typeof value === 'string' || typeof value === 'number') return value
  if (value == null) return null
  return String(value)
}

const formatDateValue = (value: string | number | null | undefined): string | null => {
  if (value == null || value === '') return null
  return String(value).split('T')[0] ?? String(value)
}

const displayFieldValue = (value: string | number | null | undefined): string => {
  if (value == null || value === '') return '-'
  return String(value)
}

const approvalSubjectFields = computed<ApprovalSubjectField[]>(() => {
  const selected = selectedApproval.value
  if (!selected) return []

  const commonCustomerField: ApprovalSubjectField = {
    key: 'customer_name',
    label: '关联客户',
    value: approvalCustomerInfo.value?.account_name
  }

  switch (selected.business_type) {
    case 'CONTRACT':
      return [
        { key: 'number', label: '合同编号', value: entityDetailValue('contract_number') ?? subjectNumber.value, type: 'copy' },
        { key: 'name', label: '合同名称', value: entityDetailValue('contract_name') ?? subjectName.value, wide: true },
        commonCustomerField,
        { key: 'opportunity', label: '关联商机', value: entityDetailValue('opportunity_name') },
        { key: 'amount', label: '合同金额', value: entityDetailValue('total_amount') ?? subjectAmount.value, type: 'amount' },
        { key: 'user_count', label: '用户数', value: entityDetailValue('user_count') },
        { key: 'license_type', label: '授权模式', value: licenseTypeLabel(entityDetailValue('license_type')?.toString()) },
        { key: 'subscription_years', label: '订阅年限', value: entityDetailValue('subscription_years') },
        { key: 'unit_price', label: '标准单价', value: entityDetailValue('standard_unit_price'), type: 'amount' },
        { key: 'status', label: '合同状态', value: contractStatusLabel(entityDetailValue('status')?.toString()), type: 'status' },
        { key: 'payment_status', label: '回款状态', value: paymentStatusLabel(entityDetailValue('payment_status')?.toString()), type: 'status' },
        { key: 'signing_date', label: '签署日期', value: formatDateValue(entityDetailValue('signing_date')) },
        { key: 'effective_date', label: '生效日期', value: formatDateValue(entityDetailValue('effective_date')) },
        { key: 'expiry_date', label: '到期日期', value: formatDateValue(entityDetailValue('expiry_date')) },
        { key: 'signing_contact', label: '签约人', value: entityDetailValue('signing_contact_name') },
        { key: 'contract_file', label: '合同文件', value: activeApprovalDetail.value?.contract_file_name ?? entityDetailValue('contract_file_name'), wide: true }
      ]
    case 'INVOICE':
      return [
        { key: 'number', label: '申请编号', value: entityDetailValue('application_number') ?? subjectNumber.value, type: 'copy' },
        { key: 'title', label: '发票抬头', value: entityDetailValue('invoice_title_text') ?? subjectName.value, wide: true },
        commonCustomerField,
        { key: 'amount', label: '开票金额', value: entityDetailValue('invoice_amount') ?? subjectAmount.value, type: 'amount' },
        { key: 'invoice_type', label: '发票类型', value: invoiceTypeLabel(entityDetailValue('invoice_type')?.toString()) },
        { key: 'status', label: '发票状态', value: invoiceStatusLabel(entityDetailValue('status')?.toString()), type: 'status' },
        { key: 'taxpayer_id', label: '纳税人识别号', value: entityDetailValue('invoice_taxpayer_id'), type: 'mono', wide: true },
        { key: 'bank', label: '开户行', value: entityDetailValue('invoice_bank_name') },
        { key: 'bank_account', label: '银行账号', value: entityDetailValue('invoice_bank_account'), type: 'mono' },
        { key: 'invoice_address', label: '地址', value: entityDetailValue('invoice_address'), wide: true },
        { key: 'invoice_phone', label: '电话', value: entityDetailValue('invoice_phone') },
        { key: 'contract', label: '关联合同', value: entityDetailValue('contract_name') },
        { key: 'payment_plan', label: '回款阶段', value: entityDetailValue('payment_plan_stage_name') },
        { key: 'invoice_number', label: '发票号码', value: activeApprovalDetail.value?.invoice_number ?? entityDetailValue('invoice_number') },
        {
          key: 'invoice_file',
          label: '发票文件',
          value: activeApprovalDetail.value?.invoice_file_path != null && activeApprovalDetail.value.invoice_file_path.length > 0
            ? '已上传'
            : null
        }
      ]
    case 'PAYMENT':
      return [
        { key: 'number', label: '回款编号', value: entityDetailValue('record_number') ?? subjectNumber.value, type: 'copy' },
        { key: 'amount', label: '回款金额', value: entityDetailValue('actual_amount') ?? subjectAmount.value, type: 'amount' },
        { key: 'payer', label: '实际付款方', value: entityDetailValue('actual_payer_name') ?? subjectActualPayerName.value },
        { key: 'payment_date', label: '回款日期', value: formatDateValue(entityDetailValue('payment_date')) },
        { key: 'confirm_status', label: '确认状态', value: paymentConfirmStatusLabel(entityDetailValue('confirmation_status')?.toString()), type: 'status' },
        commonCustomerField,
        { key: 'contract', label: '关联合同', value: entityDetailValue('contract_name') ?? subjectName.value, wide: true },
        { key: 'contract_number', label: '合同编号', value: entityDetailValue('contract_number'), type: 'copy' },
        { key: 'opportunity', label: '关联商机', value: entityDetailValue('opportunity_name') },
        { key: 'plan_number', label: '计划编号', value: entityDetailValue('plan_number'), type: 'copy' },
        { key: 'stage_name', label: '回款阶段', value: entityDetailValue('stage_name') },
        { key: 'planned_amount', label: '计划金额', value: entityDetailValue('planned_amount'), type: 'amount' },
        { key: 'due_date', label: '计划日期', value: formatDateValue(entityDetailValue('due_date')) },
        { key: 'proof', label: '回款凭证', value: entityDetailValue('proof_attachment'), wide: true },
        { key: 'notes', label: '备注', value: entityDetailValue('notes'), wide: true }
      ]
    case 'LICENSE':
      return [
        { key: 'number', label: '申请编号', value: entityDetailValue('application_number') ?? subjectNumber.value, type: 'copy' },
        { key: 'type', label: 'License 类型', value: licenseTypeLabel(entityDetailValue('license_type')?.toString() ?? subjectName.value?.toString()) },
        {
          key: 'license_status',
          label: '签发状态',
          value: licenseStatusLabel(activeApprovalDetail.value?.license_status ?? selected.license_status),
          type: 'status'
        },
        commonCustomerField,
        { key: 'deployment_name', label: '部署名称', value: entityDetailValue('deployment_name') },
        { key: 'server_address', label: '服务器地址', value: entityDetailValue('server_address'), type: 'mono', wide: true },
        { key: 'authorized_users', label: '授权人数', value: entityDetailValue('authorized_users') },
        { key: 'expiry_date', label: '到期时间', value: formatDateValue(entityDetailValue('expiry_date')) },
        { key: 'contract', label: '关联合同', value: entityDetailValue('contract_name'), wide: true },
        { key: 'remark', label: '申请备注', value: entityDetailValue('remark'), wide: true },
        { key: 'enterprise_id', label: '企业编号', value: entityDetailValue('enterprise_id'), type: 'mono' },
        { key: 'supported_modules', label: '支持模块', value: entityDetailValue('supported_modules'), wide: true }
      ]
    case 'OPPORTUNITY':
      return [
        { key: 'number', label: '商机编号', value: subjectNumber.value, type: 'copy' },
        { key: 'name', label: '商机名称', value: entityDetailValue('opportunity_name') ?? subjectName.value, wide: true },
        commonCustomerField,
        { key: 'amount', label: '预计金额', value: entityDetailValue('total_amount') ?? subjectAmount.value, type: 'amount' },
        { key: 'user_count', label: '用户数', value: entityDetailValue('user_count') },
        { key: 'unit_price', label: '标准单价', value: entityDetailValue('unit_price'), type: 'amount' },
        { key: 'license_type', label: '授权模式', value: licenseTypeLabel(entityDetailValue('license_type')?.toString()) },
        { key: 'subscription_years', label: '订阅年限', value: entityDetailValue('subscription_years') },
        { key: 'purchase_type', label: '采购类型', value: purchaseTypeLabel(entityDetailValue('purchase_type')?.toString()) },
        { key: 'decision_maker_count', label: '决策人数', value: entityDetailValue('decision_maker_count') },
        { key: 'expected_closing_date', label: '预计成交', value: formatDateValue(entityDetailValue('expected_closing_date')) },
        { key: 'stage', label: '当前阶段', value: entityDetailValue('current_stage_name') },
        { key: 'win_probability', label: '赢率', value: entityDetailValue('win_probability') != null ? `${entityDetailValue('win_probability')}%` : null },
        { key: 'status', label: '商机状态', value: opportunityStatusLabel(entityDetailValue('status')) }
      ]
    default:
      return [
        { key: 'number', label: '单号', value: subjectNumber.value, type: 'copy' },
        { key: 'name', label: '申请内容', value: subjectName.value },
        { key: 'amount', label: '金额', value: subjectAmount.value, type: 'amount' },
        commonCustomerField
      ]
  }
})

// ==================== ContextTabs 配置 ====================
const tabs = computed(() => {
  const pendingTab: { key: string; label: string; badge?: number } = {
    key: 'pending',
    label: '待我审批'
  }
  if (pendingCount.value > 0) {
    pendingTab.badge = pendingCount.value
  }
  return [
    pendingTab,
    { key: 'processed', label: '我已处理' },
    { key: 'submitted', label: '我提交的' }
  ]
})

// ==================== 筛选配置 ====================
const filterFields: ListFilterField[] = [
  {
    key: 'business_type',
    type: 'enum',
    label: '单据类型',
    options: [
      { value: 'PAYMENT', label: '回款' },
      { value: 'INVOICE', label: '发票' },
      { value: 'CONTRACT', label: '合同' },
      { value: 'LICENSE', label: 'License' },
      { value: 'OPPORTUNITY', label: '商机' }
    ]
  }
]

// ==================== DataTable Columns 配置 ====================
const columns = [
  {
    key: 'application_number',
    title: '单号',
    width: '180px',
    fixed: 'left' as const
  },
  {
    key: 'business_type',
    title: '类型',
    width: '90px',
    align: 'center' as const
  },
  {
    key: 'entity_name',
    title: '实体',
    width: '160px'
  },
  {
    key: 'entity_amount',
    title: '金额',
    width: '130px',
    align: 'right' as const
  },
  {
    key: 'submitter_name',
    title: '提交人',
    width: '110px'
  },
  {
    key: 'created_time',
    title: '提交时间',
    width: '150px'
  },
  {
    key: 'status',
    title: '状态',
    width: '120px',
    align: 'center' as const
  },
  {
    key: 'overdue_hours',
    title: '超时',
    width: '130px',
    align: 'center' as const
  },
  {
    key: 'actions',
    title: '操作',
    width: '200px',
    align: 'center' as const,
    fixed: 'right' as const
  }
]

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', checkMobile)
})
onUnmounted(() => {
  headerStore.clear()
})

// TopBar 配置（Tabs）
watchEffect(() => {
  headerStore.setTabs(tabs.value, activeTab.value)
})

// 监听 headerStore.activeTab 变化
watchEffect(() => {
  if (headerStore.activeTab && headerStore.activeTab !== activeTab.value) {
    activeTab.value = headerStore.activeTab as Tab
    page.value = 1
    fetchList()
  }
})

// ===== 方法 =====
const isAxiosStatus = (err: unknown, code: number): boolean => {
  const r = (err as { response?: { status?: number } } | null)?.response
  return typeof r?.status === 'number' && r.status === code
}

const businessTypeLabel = (t: EntityType): string => {
  const map: Record<EntityType, string> = {
    PAYMENT: '回款',
    INVOICE: '发票',
    CONTRACT: '合同',
    LICENSE: 'License',
    OPPORTUNITY: '商机'
  }
  return map[t] ?? t
}

const customerStatusLabel = (status?: number | null): string => {
  const map: Record<number, string> = {
    0: '跟进中',
    1: '已成交',
    2: '已流失',
    3: '非激活'
  }
  return status == null ? '-' : (map[status] ?? String(status))
}

const fetchList = async (): Promise<void> => {
  loadError.value = null
  listLoading.value = true
  try {
    const businessType = getBusinessTypeFilter()
    const businessTypeExclude = getBusinessTypeExcludeFilter()
    const query = {
      tab: activeTab.value,
      page: page.value,
      page_size: pageSize.value,
      ...(businessType !== null ? { business_type: businessType } : {}),
      ...(businessTypeExclude !== null ? { business_type_exclude: businessTypeExclude } : {})
    }
    const res = await store.fetchList(query)
    rows.value = activeTab.value === 'pending'
      ? [...res.items].sort(byOverdueDesc)
      : res.items
    total.value = res.total
  } catch (err) {
    if (isAxiosStatus(err, 403)) {
      loadError.value = 'forbidden'
    } else {
      loadError.value = 'error'
    }
  } finally {
    listLoading.value = false
  }
}

// 待我审批按 overdue_hours 降序（积压最久顶；null 视为 0）
const byOverdueDesc = (a: ApprovalListItem, b: ApprovalListItem): number => {
  const ah = a.overdue_hours ?? 0
  const bh = b.overdue_hours ?? 0
  return bh - ah
}

// 移动端分页页码计算
const getPageItems = (): number[] => {
  const totalPages = Math.ceil(total.value / pageSize.value)
  const current = page.value
  const items: number[] = []

  // 显示最多 5 个页码
  const maxItems = 5
  const half = Math.floor(maxItems / 2)

  let start = Math.max(1, current - half)
  let end = Math.min(totalPages, start + maxItems - 1)

  // 调整起点以确保显示足够的页码
  if (end - start < maxItems - 1) {
    start = Math.max(1, end - maxItems + 1)
  }

  for (let i = start; i <= end; i++) {
    items.push(i)
  }

  return items
}

const reload = (): void => {
  fetchList()
}

const getBusinessTypeFilterValue = (operators: ListFilterCondition['op'][]): string | null => {
  const values = activeFilters.value
    .filter((item) => item.field === 'business_type' && operators.includes(item.op))
    .flatMap((condition) => {
      const value = condition.value
      if (Array.isArray(value)) return value.map(String)
      if (value === undefined || value === null || value === '') return []
      return [String(value)]
    })
    .filter((value, index, list) => value !== '' && list.indexOf(value) === index)

  return values.length > 0 ? values.join(',') : null
}

const getBusinessTypeFilter = (): string | null =>
  getBusinessTypeFilterValue(['contains', 'eq'])

const getBusinessTypeExcludeFilter = (): string | null =>
  getBusinessTypeFilterValue(['not_contains', 'neq'])

const handleFilterApply = (filters: ListFilterCondition[]): void => {
  activeFilters.value = filters
  page.value = 1
  fetchList()
}

const handleFilterReset = (): void => {
  activeFilters.value = []
  page.value = 1
  fetchList()
}

const copyNumber = async (num: string): Promise<void> => {
  try {
    if (typeof navigator?.clipboard?.writeText === 'function') {
      await navigator.clipboard.writeText(num)
    } else {
      // 降级：document.execCommand
      const ta = document.createElement('textarea')
      ta.value = num
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    toast.success('已复制单号')
  } catch {
    toast.error('复制失败，请手动选择单号复制')
  }
}

const openDetail = (row: ApprovalListItem, index?: number): void => {
  // Find index if not provided (DataTable row-click doesn't provide index)
  const rowIndex = index ?? rows.value.findIndex(r => r.id === row.id)
  selectedApproval.value = row
  triggerRowIndex.value = rowIndex
  focusedRowEl.value = (document.querySelectorAll('.data-table-row')[rowIndex] as HTMLElement) ?? null
  sheetVisible.value = true
}

const onSheetClosed = (): void => {
  // 条13：抽屉关闭焦点回触发发行（或下一行）
  const target = focusedRowEl.value ?? null
  if (target && typeof target.focus === 'function') {
    target.focus()
  }
  selectedApproval.value = null
  store.clearDetail()
  markIssuedDialogVisible.value = false
  triggerRowIndex.value = -1
}

const onApprovalActionDone = (): void => {
  // 审批完成（同意/驳回/撤回/提交）后刷新列表 + 关抽屉
  sheetVisible.value = false
  fetchList()
}

const handleInvoiceFileUploaded = (): void => {
  markIssuedDialogVisible.value = false
  sheetVisible.value = false
  fetchList()
}

// 条4：REJECTED 行修改并重新提交（先 update 回 DRAFT 再 submitApproval）
// 注：update 回 DRAFT 由各实体编辑页负责；审批中心 entry 仅 router.push 跳
// 对应编辑页（PAYMENT 无独立编辑页，跳列表页 + info 提示），避免审批中心耦合
// 各实体的 update API（COMPONENTS.md「视图不直接发业务 update」亦不在此处内嵌
// 多条合同/回款/发票的 update 调用，保持中心单一职责）。
// 修复：合同编辑使用弹窗而非路由跳转
const handleResubmit = async (row: ApprovalListItem): Promise<void> => {
  resubmitPendingId.value = row.id
  try {
    // 合同类型：直接打开编辑弹窗
    if (row.business_type === 'CONTRACT') {
      contractLoading.value = true
      try {
        const contract = await contractApi.getContract(row.business_id)
        editingContract.value = contract
        contractEditVisible.value = true
      } catch {
        toast.error('获取合同信息失败')
      } finally {
        contractLoading.value = false
      }
      return
    }

    // 其他实体类型：路由跳转
    const confirmed = await createConfirmDialog({
      title: '修改并重新提交',
      message: `将跳转到 ${businessTypeLabel(row.business_type)} 编辑页修改后重新提交审批。是否继续？`,
      confirmText: '确定',
      cancelText: '取消',
      variant: 'default'
    })
    if (!confirmed) return
    // 跳转到对应实体编辑页
    const route: Record<Exclude<EntityType, 'CONTRACT'>, string> = {
      INVOICE: `/invoices/${row.business_id}`,
      // 回款无独立编辑页（/payments 为列表页）：跳列表页 + info 提示，
      // 保证不白屏/不断旅程；用户在列表内修改后重新提交审批。
      PAYMENT: `/payments`,
      // License 申请在客户详情页的 License 管理 Tab 编辑
      LICENSE: row.customer_info?.id !== undefined
        ? `/customers/${row.customer_info.id}?tab=license-management`
        : '/customers',
      OPPORTUNITY: `/opportunities?opportunityId=${row.business_id}`
    }
    const target = route[row.business_type as Exclude<EntityType, 'CONTRACT'>]
    await router.push(target)
    // PAYMENT 目标是列表页，无法直接进入驳回回款的编辑入口——补 info 引导，
    // 旅程不断（比原 window.location.assign hash bug 强）。
    if (row.business_type === 'PAYMENT') {
      toast.info('请修改回款记录后重新提交审批')
    }
    if (row.business_type === 'INVOICE') {
      toast.info('请在发票详情页编辑后重新提交审批')
    }
    if (row.business_type === 'LICENSE') {
      toast.info('请修改 License 申请后重新提交审批')
    }
    if (row.business_type === 'OPPORTUNITY') {
      toast.info('请在商机详情中处理审批')
    }
  } catch {
    // router.push 失败
  } finally {
    resubmitPendingId.value = null
  }
}

// 合同编辑成功回调
const handleContractEditSuccess = (): void => {
  contractEditVisible.value = false
  editingContract.value = null
  toast.success('合同已修改，请重新提交审批')
  fetchList()
}

// 移动端快速审批：同意（单条，无抽屉）
const handleQuickApprove = async (row: ApprovalListItem): Promise<void> => {
  try {
    const confirmed = await createConfirmDialog({
      title: '快速审批',
      message: '确定同意该审批？',
      confirmText: '确定',
      cancelText: '取消',
      variant: 'default'
    })
    if (!confirmed) return
    // 调 store.approveEntity（单条审批，updated_time 用当前行）
    await store.approveEntity(
      row.business_type,
      row.business_id,
      'APPROVE',
      '审批通过',
      row.updated_time
    )
    toast.success('已同意')
    // 刷新列表（移除该行）
    fetchList()
  } catch {
    // 审批失败（拦截器已 toast）
  }
}

// 移动端快速审批：驳回（单条，弹窗输入理由）
const handleQuickReject = (row: ApprovalListItem): void => {
  quickRejectReason.value = ''
  quickRejectRow.value = row
  quickRejectVisible.value = true
}

const confirmQuickReject = async (): Promise<void> => {
  const reason = quickRejectReason.value.trim()
  if (!reason) {
    toast.warning('请填写驳回理由，提交人将据此修改')
    return
  }
  if (!quickRejectRow.value) return
  try {
    await store.approveEntity(
      quickRejectRow.value.business_type,
      quickRejectRow.value.business_id,
      'REJECT',
      reason,
      quickRejectRow.value.updated_time
    )
    toast.success('已驳回，申请人可修改后重新提交')
    quickRejectVisible.value = false
    fetchList()
  } catch {
    // 审批失败（拦截器已 toast）
  }
}

// 抽屉侧 ApprovalProcessGeneric REJECTED 态「修改并重新提交」CTA（Important #2）
// 事件无 payload，目标行取 selectedApproval（抽屉当前展示行）。
const onResubmit = (): void => {
  if (selectedApproval.value == null) return
  handleResubmit(selectedApproval.value)
}

// 键盘快捷键（条9）：J/K 上下行、Enter 开抽屉、Esc 关抽屉
// 通过全局 keydown 监听，避免每行绑定；仅当焦点不在输入/弹窗内时生效。
const onKeydown = (e: KeyboardEvent): void => {
  const target = e.target as HTMLElement | null
  if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return
  if (sheetVisible.value) {
    if (e.key === 'Escape') {
      sheetVisible.value = false
    }
    return
  }
  if (rows.value.length === 0) return
  if (e.key === 'Enter') {
    const row = rows.value[focusIndex.value] ?? null
    if (row) openDetail(row, focusIndex.value)
  } else if (e.key === 'j' || e.key === 'J') {
    focusIndex.value = Math.min(rows.value.length - 1, focusIndex.value + 1)
    focusCurrentRow()
  } else if (e.key === 'k' || e.key === 'K') {
    focusIndex.value = Math.max(0, focusIndex.value - 1)
    focusCurrentRow()
  }
}

const focusIndex = ref<number>(0)

const focusCurrentRow = (): void => {
  const els = document.querySelectorAll('.data-table-row')
  const el = els[focusIndex.value] as HTMLElement | undefined
  if (el && typeof el.focus === 'function') {
    el.focus()
  }
}

const setupKeyboard = (): void => {
  window.addEventListener('keydown', onKeydown)
}

const teardownKeyboard = (): void => {
  window.removeEventListener('keydown', onKeydown)
}

// ===== 生命周期 =====
onMounted((): void => {
  setupKeyboard()
  fetchList()
})
onBeforeUnmount((): void => {
  teardownKeyboard()
  store.clearList()
})

// 行可聚焦（条9 键盘导航 + 条13 焦点回归）：每次列表刷新后给行加 tabindex=0
watch(rows, async () => {
  await nextTick()
  document.querySelectorAll<HTMLElement>('.data-table-row').forEach((el) => {
    el.setAttribute('tabindex', '0')
  })
}, { flush: 'post' })
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.approval-center {
  padding: $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-section-gap-v2;
  min-height: 0;
  flex: 1;
}

// 超时徽章（DataTable 内使用 Badge 组件）
.overdue-badge-inline {
  display: inline-flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
  padding: $wolf-space-xs-v2 $wolf-space-sm-v2;
  border-radius: $wolf-radius-sm-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  color: $wolf-warning-text-v2;
  background: $wolf-warning-bg-v2;
  border: none;
}

.approval-mobile-tools {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  min-height: 36px;
}

.approval-mobile-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-body-v2;
}

// 行级聚焦态（键盘导航 + 抽屉关闭后焦点回归）
:deep(.data-table-row) {
  outline: none;

  &:focus,
  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-primary-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
    background: $wolf-bg-hover-v2;
  }
}

// 移动端卡片警告边框样式
@media (max-width: 768px) {
  .approval-center {
    padding: $wolf-page-padding-mobile-v2;
  }

  // 超时卡片边框警告样式（配合 :class="row.overdue_hours >= 48 && 'border-warning'"）
  :deep(.border-warning) {
    border-color: $wolf-warning-v2;
    border-width: 1px;
  }
}

// ===== Sheet 内部样式（参考 LeadDetailSheet） =====

// 信息卡片
.info-card {
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-lg-v2;
  border: 1px solid $wolf-border-light-v2;
}

// 属性网格
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

.attribute-item-wide {
  grid-column: span 2;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-column: span 1;
  }
}

.attribute-label {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.attribute-value {
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-secondary-v2;
  font-weight: $wolf-font-weight-medium-v2;
  word-break: break-all;
}

.attribute-value-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: $wolf-primary-v2;
  cursor: pointer;

  &:hover {
    text-decoration: underline;
  }
}
</style>
