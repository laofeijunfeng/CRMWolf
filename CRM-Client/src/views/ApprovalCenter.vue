<!--
  ApprovalCenter — 审批中心

  基于 V2 设计规范重构：
  - TopBar 集成 ContextTabs（待我审批/我已处理/我提交的，权限驱动）+ Badge 显示待办数
  - FilterPanel（单据类型筛选）
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
  <div class="approval-center" v-loading="listLoading">
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
      <!-- FilterPanel -->
      <FilterPanel
        :fields="filterFields"
        v-model:values="filterValues"
        @search="handleFilterChange"
        @reset="resetFilter"
      />

      <!-- DataTable（桌面端） -->
      <DataTable
        v-if="!isMobile"
        :columns="columns"
        :data="rows"
        :total="total"
        :page="page"
        :page-size="pageSize"
        :loading="listLoading"
        height="calc(100vh - 248px)"
        empty-title="暂无待审批事项"
        row-interactive
        @update:page="page = $event; fetchList()"
        @update:page-size="pageSize = $event; page = 1; fetchList()"
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
          <span class="font-mono font-semibold text-warning">
            {{ formatCurrency(row.entity_amount) }}
          </span>
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
              <span class="font-mono font-semibold text-lg text-warning">
                {{ formatCurrency(row.entity_amount) }}
              </span>
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
          v-if="rows.length === 0"
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
            <!-- 基本信息卡（来自列表行数据，无需额外请求） -->
            <Card v-if="selectedApproval" class="info-card">
              <CardContent class="p-0">
                <div class="p-4 border-b border-wolf-border-light-v2">
                  <h3 class="text-sm font-semibold text-wolf-text-primary-v2">基本信息</h3>
                </div>
                <div class="p-4">
                  <div class="attributes-grid">
                    <div class="attribute-item">
                      <div class="attribute-label">单号</div>
                      <div
                        class="attribute-value font-mono text-wolf-primary-v2 cursor-pointer hover:underline"
                        @click="copyNumber(selectedApproval.application_number)"
                      >
                        {{ selectedApproval.application_number }}
                      </div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">单据类型</div>
                      <div class="attribute-value">{{ businessTypeLabel(selectedApproval.business_type) }}</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">客户/实体</div>
                      <div class="attribute-value">{{ selectedApproval.entity_name || '-' }}</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">金额</div>
                      <div class="attribute-value font-mono font-semibold text-wolf-warning-text-v2">
                        {{ formatCurrency(selectedApproval.entity_amount) }}
                      </div>
                    </div>
                    <div v-if="selectedApproval.business_type === 'PAYMENT'" class="attribute-item">
                      <div class="attribute-label">实际付款方</div>
                      <div class="attribute-value">{{ selectedApproval.actual_payer_name || '-' }}</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">提交人</div>
                      <div class="attribute-value">{{ selectedApproval.submitter_name }}</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">提交时间</div>
                      <div class="attribute-value font-mono text-sm">{{ formatDateRelative(selectedApproval.created_time) }}</div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card v-if="selectedApproval?.customer_info" class="info-card">
              <CardContent class="p-0">
                <div class="p-4 border-b border-wolf-border-light-v2">
                  <h3 class="text-sm font-semibold text-wolf-text-primary-v2">公司信息</h3>
                </div>
                <div class="p-4">
                  <div class="attributes-grid">
                    <div class="attribute-item">
                      <div class="attribute-label">客户名称</div>
                      <div class="attribute-value">{{ selectedApproval.customer_info.account_name }}</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">所在城市</div>
                      <div class="attribute-value">{{ selectedApproval.customer_info.city || '-' }}</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">所属行业</div>
                      <div class="attribute-value">{{ selectedApproval.customer_info.industry || '-' }}</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">公司规模</div>
                      <div class="attribute-value">{{ selectedApproval.customer_info.company_scale || '-' }}</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">客户来源</div>
                      <div class="attribute-value">{{ selectedApproval.customer_info.source || '-' }}</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">客户状态</div>
                      <div class="attribute-value">{{ customerStatusLabel(selectedApproval.customer_info.status) }}</div>
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
import { computed, nextTick, onMounted, onBeforeUnmount, onUnmounted, ref, watch, watchEffect, reactive } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { Clock, Copy } from 'lucide-vue-next'
import { FilterPanel, DataTable, Badge, Separator } from '@/components/crmwolf'
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
// Element Plus components for remaining template sections (none remaining after refactor)
import ApprovalStatusBadge from '@/components/ApprovalStatusBadge.vue'
import ApprovalProcessGeneric from '@/components/ApprovalProcessGeneric.vue'
import ErrorState from '@/components/ErrorState.vue'
import ContractFormDialog from '@/components/dialogs/ContractFormDialog.vue'
import InvoiceMarkIssuedDialog from '@/components/dialogs/InvoiceMarkIssuedDialog.vue'
import { useApprovalStore } from '@/stores/approval'
import { usePermissionStore } from '@/stores/permissions'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { formatCurrency, formatDateRelative } from '@/utils/format'
import { createConfirmDialog } from '@/utils/confirmDialogImpl'
import contractApi from '@/api/contract'
import type { EntityType, ApprovalListItem } from '@/schemas/approvalGeneric'
import type { ContractResponse } from '@/api/contract'

type Tab = 'pending' | 'processed' | 'submitted'
type LoadError = null | 'error' | 'forbidden'

// ==================== Stores ====================
usePageTitle()
const store = useApprovalStore()
const permissionStore = usePermissionStore()
const headerStore = useHeaderStore()
const { pendingCount, currentApprovalDetail } = storeToRefs(store)
const router = useRouter()

// ==================== State ====================
const activeTab = ref<Tab>('pending')
const filterValues = reactive({
  business_type: '' as EntityType | ''
})

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
const showInvoiceUploadFooter = computed<boolean>(() =>
  selectedApproval.value?.business_type === 'INVOICE' &&
  currentApprovalDetail.value?.business_type === 'INVOICE' &&
  currentApprovalDetail.value.status === 'APPROVED' &&
  (currentApprovalDetail.value.invoice_file_path == null || currentApprovalDetail.value.invoice_file_path.length === 0) &&
  permissionStore.hasPermission('invoice:mark_issued')
)

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

// ==================== FilterPanel 配置 ====================
const filterFields = [
  {
    key: 'business_type',
    type: 'select' as const,
    label: '单据类型',
    placeholder: '全部类型',
    options: [
      { value: 'PAYMENT', label: '回款' },
      { value: 'INVOICE', label: '发票' },
      { value: 'CONTRACT', label: '合同' },
      { value: 'LICENSE', label: 'License' }
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
    LICENSE: 'License'
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
    const query = {
      tab: activeTab.value,
      page: page.value,
      page_size: pageSize.value,
      ...(filterValues.business_type ? { business_type: filterValues.business_type } : {})
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

const handleFilterChange = (): void => {
  page.value = 1
  fetchList()
}

const resetFilter = (): void => {
  filterValues.business_type = ''
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
        : '/customers'
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
</style>
