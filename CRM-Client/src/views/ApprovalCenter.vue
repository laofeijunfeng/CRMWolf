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
    <!-- DataTable 负责列表读取错误、空状态和刷新状态；失败时保留已成功加载的数据 -->
    <!-- DataTable（桌面 + 移动端卡片） -->
      <DataTable
        v-model:filters="activeFilters"
        v-model:sorts="activeSorts"
        :fields="fields"
        :data="rows"
        :total="total"
        :page="page"
        :page-size="pageSize"
        :loading="listLoading"
        :load-error="loadError"
        :selectable="activeTab === 'pending'"
        :selected-row-keys="selectedRowKeys"
        :get-row-selectable="isRowSelectable"
        view-key="approval-center.list"
        :view-label="activeViewLabel"
        :effective-filters="effectiveFilters"
        column-config-enabled
        height="calc(100vh - 108px)"
        height-strategy="fill"
        scroll-mode="contained"
        empty-title="暂无待审批事项"
        empty-description="所有回款与发票申请都已处理完毕"
        mobile-mode="card"
        row-interactive
        detail-column-key="application_number"
        :get-row-label="(row) => `审批单 ${row.application_number || row.id}`"
        :get-row-actions="getRowActions"
        @update:page="page = $event; fetchList()"
        @update:page-size="pageSize = $event; page = 1; fetchList()"
        @filter-apply="handleFilterApply"
        @filter-reset="handleFilterReset"
        @sort-apply="handleSortApply"
        @sort-reset="handleSortReset"
        @row-click="openDetail"
        @retry="reload"
      >
        <template #tableTools>
          <div v-if="selectedApprovals.length > 0" class="approval-bulk-toolbar" role="region" aria-label="批量审批操作">
            <span class="approval-bulk-toolbar__count">已选 {{ selectedApprovals.length }} 条{{ selectedBusinessType ? `（${businessTypeLabel(selectedBusinessType)}）` : '' }}</span>
            <Button
              size="sm"
              data-testid="bulk-approve-btn"
              :loading="bulkPending"
              :disabled="bulkPending"
              @click="openBulkAction('APPROVE')"
            >
              批量同意
            </Button>
            <Button
              variant="destructive"
              size="sm"
              data-testid="bulk-reject-btn"
              :disabled="bulkPending"
              @click="openBulkAction('REJECT')"
            >
              批量驳回
            </Button>
            <Button variant="ghost" size="sm" :disabled="bulkPending" @click="clearSelection">
              清除选择
            </Button>
          </div>
        </template>

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


        <template #mobile-card="{ row }">
          <div :class="cn('approval-mobile-card', row.overdue_hours != null && row.overdue_hours >= 48 && 'is-overdue')">
            <div class="flex justify-between items-center mb-3">
              <span
                class="font-mono text-primary text-base cursor-pointer"
                data-testid="copy-number-mobile"
                @click.stop="copyNumber(row.application_number)"
              >
                {{ row.application_number }}
              </span>
              <ApprovalStatusBadge :status="row.status" size="small" />
            </div>

            <div class="flex justify-between items-center mb-3 gap-3">
              <span class="text-base font-medium min-w-0 flex-1 truncate">
                {{ row.entity_name || '-' }}
              </span>
              <AmountText :value="row.entity_amount" size="lg" tone="warning" />
            </div>

            <div class="flex justify-between text-sm text-muted-foreground mb-3 gap-3">
              <span class="min-w-0 flex-1 truncate">{{ row.submitter_name }} 提交</span>
              <span class="shrink-0">{{ formatDateRelative(row.created_time) }}</span>
            </div>

            <div v-if="row.overdue_hours != null && row.overdue_hours >= 48">
              <Badge class="gap-1 bg-warning text-warning-foreground border-transparent">
                <Clock class="w-3 h-3" />
                超时 {{ row.overdue_hours }} 小时
              </Badge>
            </div>
          </div>
        </template>

        <template #mobile-actions="{ row, index }">
          <div class="approval-mobile-actions" v-if="activeTab === 'pending'">
            <Button
              v-if="hasAttachment(row)"
              variant="outline"
              size="lg"
              class="approval-mobile-action"
              data-testid="mobile-preview-btn"
              :loading="attachmentPreviewPendingId === row.id"
              @click.stop="handlePreviewAttachment(row)"
            >
              预览
            </Button>
            <Button
              variant="destructive"
              size="lg"
              class="approval-mobile-action"
              data-testid="mobile-reject-btn"
              :loading="quickRejectPendingId === row.id"
              :disabled="quickActionPending"
              @click.stop="handleQuickReject(row)"
            >
              驳回
            </Button>
            <Button
              variant="default"
              size="lg"
              class="approval-mobile-action"
              data-testid="mobile-approve-btn"
              :loading="quickApprovePendingId === row.id"
              :disabled="quickActionPending"
              @click.stop="handleQuickApprove(row)"
            >
              通过
            </Button>
            <Button
              v-if="!hasAttachment(row)"
              variant="outline"
              size="lg"
              class="approval-mobile-action"
              data-testid="mobile-detail-btn"
              @click.stop="openDetail(row, index)"
            >
              详情
            </Button>
          </div>
          <div class="approval-mobile-actions" v-else-if="activeTab === 'submitted' && row.status === 'REJECTED'">
            <Button
              variant="default"
              size="lg"
              class="approval-mobile-action approval-mobile-action-wide"
              data-testid="mobile-resubmit-btn"
              :loading="resubmitPendingId === row.id"
              @click.stop="handleResubmit(row)"
            >
              修改并重新提交
            </Button>
          </div>
          <div class="approval-mobile-actions" v-else-if="activeTab === 'submitted' && row.status === 'PENDING'">
            <Button
              variant="outline"
              size="lg"
              class="approval-mobile-action"
              data-testid="mobile-remind-btn"
              :loading="remindPendingId === row.id"
              @click.stop="handleRemind(row)"
            >
              <BellRing class="w-4 h-4" aria-hidden="true" />
              催办
            </Button>
            <Button
              v-if="hasAttachment(row)"
              variant="outline"
              size="lg"
              class="approval-mobile-action"
              data-testid="mobile-preview-btn"
              :loading="attachmentPreviewPendingId === row.id"
              @click.stop="handlePreviewAttachment(row)"
            >
              预览
            </Button>
            <Button
              variant="outline"
              size="lg"
              class="approval-mobile-action"
              data-testid="mobile-detail-btn"
              @click.stop="openDetail(row, index)"
            >
              详情
            </Button>
          </div>
          <div class="approval-mobile-actions" v-else>
            <Button
              v-if="hasAttachment(row)"
              variant="outline"
              size="lg"
              class="approval-mobile-action"
              data-testid="mobile-preview-btn"
              :loading="attachmentPreviewPendingId === row.id"
              @click.stop="handlePreviewAttachment(row)"
            >
              预览
            </Button>
            <Button
              variant="outline"
              size="lg"
              class="approval-mobile-action"
              data-testid="mobile-detail-btn"
              @click.stop="openDetail(row, index)"
            >
              详情
            </Button>
          </div>
        </template>
      </DataTable>

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
                      <div class="attribute-value">{{ getAcquisitionSourceDisplayName(approvalCustomerInfo) }}</div>
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
              v-if="selectedApproval && selectedApprovalEntityId !== null"
              :entity-type="selectedApproval.business_type"
              :entity-id="selectedApprovalEntityId"
              :can-approve="activeTab === 'pending'"
              :is-submitter="activeTab === 'submitted'"
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
          v-if="showBusinessActionFooter"
          class="p-4 border-t border-wolf-border-default-v2 flex flex-row justify-end gap-2"
        >
          <Button
            :data-testid="businessActionTestId"
            :aria-label="uploadFooterAriaLabel"
            @click="openUploadFooterDialog"
          >
            {{ uploadFooterLabel }}
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

    <InvoiceReissueCompleteDialog
      v-if="selectedApproval?.business_type === 'INVOICE_REISSUE'"
      v-model:open="reissueCompleteDialogVisible"
      :reissue-id="selectedApproval.business_id"
      @completed="handleInvoiceReissueCompleted"
    />

    <InvoiceApplicationFormDialog
      :open="invoiceEditDialogVisible"
      mode="edit"
      :application="editingInvoiceApplication"
      @update:open="handleInvoiceEditDialogOpenChange"
      @success="handleInvoiceEditSuccess"
    />

    <InvoiceDetailSheet
      :invoice-id="selectedInvoiceDetailId"
      :visible="invoiceDetailSheetVisible"
      :auto-edit-reissue-id="selectedApproval?.business_type === 'INVOICE_REISSUE' ? selectedApproval.business_id : null"
      @update:visible="handleInvoiceDetailSheetVisibleChange"
      @refresh="handleInvoiceDetailRefresh"
    />

    <LicenseIssueDialog
      v-if="selectedApproval?.business_type === 'LICENSE'"
      v-model:open="licenseIssueDialogVisible"
      :application-id="selectedApproval.business_id"
      @issued="handleLicenseIssued"
    />

    <Dialog :open="attachmentPreviewVisible" @update:open="handleAttachmentPreviewOpenChange">
      <DialogContent class="max-w-[92vw] sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>{{ attachmentPreviewTitle }}</DialogTitle>
          <DialogDescription>审批附件预览</DialogDescription>
        </DialogHeader>

        <div class="approval-attachment-preview">
          <div v-if="attachmentPreviewPendingId != null" class="approval-attachment-preview__loading">
            加载中...
          </div>
          <img
            v-else-if="attachmentPreviewIsImage && attachmentPreviewUrl"
            :src="attachmentPreviewUrl"
            :alt="attachmentPreviewTitle"
            class="approval-attachment-preview__image"
          >
          <iframe
            v-else-if="attachmentPreviewIsPdf && attachmentPreviewUrl"
            :src="attachmentPreviewUrl"
            :title="attachmentPreviewTitle"
            class="approval-attachment-preview__frame"
          />
          <div v-else class="approval-attachment-preview__fallback">
            当前文件格式不支持直接预览，请下载后查看。
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" @click="closeAttachmentPreview">关闭</Button>
          <Button @click="handleDownloadAttachment">下载</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- 批量审批确认与结果弹窗：保留失败项，允许单独重试 -->
    <Dialog v-model:open="bulkDialogVisible">
      <DialogContent class="max-w-[560px]">
        <DialogHeader>
          <DialogTitle>{{ bulkAction === 'REJECT' ? '批量驳回审批' : '批量同意审批' }}</DialogTitle>
          <DialogDescription v-if="bulkResult === null">
            将处理 {{ selectedApprovals.length }} 条{{ selectedBusinessType ? businessTypeLabel(selectedBusinessType) : '' }}审批；每条记录独立处理，部分失败不会回滚已成功项。
          </DialogDescription>
          <DialogDescription v-else>
            本次已成功处理 {{ bulkResult.success_count }} 条，失败 {{ bulkResult.failed.length }} 条。
          </DialogDescription>
        </DialogHeader>

        <template v-if="bulkResult === null">
          <Textarea
            v-if="bulkAction === 'REJECT'"
            v-model="bulkComment"
            data-testid="bulk-reject-reason"
            placeholder="请填写驳回理由，提交人将据此修改"
            :rows="4"
            :maxlength="500"
          />
          <p v-if="bulkAction === 'REJECT'" class="text-sm text-muted-foreground text-right">
            {{ bulkComment.length }} / 500
          </p>
          <ErrorState
            v-if="bulkError"
            :variant="bulkError.variant ?? 'error'"
            :title="bulkError.title"
            :description="bulkError.description"
          />
        </template>
        <template v-else>
          <div v-if="bulkResult.failed.length > 0" class="approval-bulk-result" role="alert">
            <p class="font-medium">以下记录未处理成功：</p>
            <ul class="approval-bulk-result__list">
              <li v-for="item in bulkResult.failed" :key="item.id">
                <span>{{ bulkFailureLabel(item.id) }}</span>
                <span class="text-muted-foreground">{{ item.reason }}</span>
              </li>
            </ul>
          </div>
          <p v-else class="text-sm text-muted-foreground">全部记录已处理成功。</p>
        </template>

        <DialogFooter>
          <Button variant="ghost" :disabled="bulkPending" @click="bulkDialogVisible = false">
            {{ bulkResult === null ? '取消' : '关闭' }}
          </Button>
          <Button
            v-if="bulkResult === null"
            :variant="bulkAction === 'REJECT' ? 'destructive' : 'default'"
            data-testid="bulk-confirm-btn"
            :loading="bulkPending"
            :disabled="bulkPending || (bulkAction === 'REJECT' && !bulkComment.trim())"
            @click="confirmBulkAction"
          >
            确定处理
          </Button>
          <Button
            v-else-if="bulkResult.failed.length > 0"
            data-testid="bulk-retry-btn"
            :loading="bulkPending"
            :disabled="bulkPending"
            @click="retryBulkFailures"
          >
            重试失败项
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- 移动端快速驳回弹窗 -->
    <Dialog :open="quickRejectVisible" @update:open="handleQuickRejectOpenChange">
      <DialogContent class="max-w-[90vw]">
        <DialogHeader>
          <DialogTitle>驳回审批</DialogTitle>
          <DialogDescription>
            {{ quickRejectDescription }}请填写驳回理由，提交人将据此修改。
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
            id="quick-reject-reason"
            :aria-invalid="quickRejectReasonError ? 'true' : undefined"
            :aria-describedby="quickRejectReasonError ? 'quick-reject-reason-error' : undefined"
            @update:model-value="quickRejectReasonError = ''"
          />
          <p
            v-if="quickRejectReasonError"
            id="quick-reject-reason-error"
            class="text-sm text-destructive"
            role="alert"
          >
            {{ quickRejectReasonError }}
          </p>
          <p class="text-sm text-muted-foreground text-right">
            {{ quickRejectReason.length }} / 500
          </p>
        </div>

        <ErrorState
          v-if="quickActionError"
          :variant="quickActionError.variant ?? 'error'"
          :title="quickActionError.title"
          :description="quickActionError.description"
        />

        <DialogFooter>
          <Button variant="ghost" :disabled="quickActionPending" @click="handleQuickRejectOpenChange(false)">
            取消
          </Button>
          <Button
            variant="default"
            data-testid="quick-reject-confirm-btn"
            :loading="quickRejectPendingId === quickRejectRow?.id"
            :disabled="quickActionPending || !quickRejectReason.trim()"
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
import { BellRing, Clock, Copy } from 'lucide-vue-next'
import { AmountText, DataTable, Badge, type ActionConfig, type TableRowActionSet } from '@/components/crmwolf'
import type { ListFieldDefinition } from '@/components/crmwolf/listFieldCatalog'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'
import { Button } from '@/components/ui/button'
import { Sheet, SheetHeader, SheetTitle, SheetDescription, SheetFooter } from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import { Card, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import ApprovalStatusBadge from '@/components/ApprovalStatusBadge.vue'
import ApprovalProcessGeneric from '@/components/ApprovalProcessGeneric.vue'
import ErrorState from '@/components/ErrorState.vue'
import ContractFormDialog from '@/components/dialogs/ContractFormDialog.vue'
import InvoiceApplicationFormDialog from '@/components/dialogs/InvoiceApplicationFormDialog.vue'
import InvoiceMarkIssuedDialog from '@/components/dialogs/InvoiceMarkIssuedDialog.vue'
import InvoiceReissueCompleteDialog from '@/components/dialogs/InvoiceReissueCompleteDialog.vue'
import LicenseIssueDialog from '@/components/dialogs/LicenseIssueDialog.vue'
import InvoiceDetailSheet from '@/views/InvoiceDetailSheet.vue'
import { useApprovalStore } from '@/stores/approval'
import { usePermissionStore } from '@/stores/permissions'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { useTopBarRegistration } from '@/composables/useTopBarRegistration'
import { formatDateRelative } from '@/utils/format'
import { serializeListQuery, withoutFilterFields } from '@/utils/listQuery'
import { createConfirmDialog } from '@/utils/confirmDialogImpl'
import { handleApiError } from '@/utils/errorHandler'
import { toFeedbackError, type FeedbackError } from '@/types/feedback'
import { customerDetailRoute } from '@/utils/customerRoutes'
import approvalGenericApi from '@/api/approvalGeneric'
import contractApi from '@/api/contract'
import invoiceApi, { type InvoiceApplicationResponse } from '@/api/invoice'
import type { EntityType, ApprovalCustomerInfo, ApprovalDetail, ApprovalListItem, ApprovalListQuery, ApprovalAction, BulkApproveResponse } from '@/schemas/approvalGeneric'
import { getAcquisitionSourceDisplayName } from '@/schemas/acquisition-source'
import type { ContractResponse } from '@/api/contract'

type Tab = 'pending' | 'processed' | 'submitted'
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
const activeSorts = ref<ListSortCondition[]>([])

const page = ref<number>(1)
const pageSize = ref<number>(20)
const total = ref<number>(0)
const rows = ref<ApprovalListItem[]>([])
const loadError = ref<FeedbackError | null>(null)
const listRequestId = ref<number>(0)

// 列表加载状态（独立于 Sheet 详情加载）
const listLoading = ref<boolean>(false)

const sheetVisible = ref<boolean>(false)
const selectedApproval = ref<ApprovalListItem | null>(null)
const markIssuedDialogVisible = ref<boolean>(false)
const reissueCompleteDialogVisible = ref<boolean>(false)
const licenseIssueDialogVisible = ref<boolean>(false)
const triggerRowIndex = ref<number>(-1)
const focusedRowEl = ref<HTMLElement | null>(null)

const resubmitPendingId = ref<number | null>(null)
const remindPendingId = ref<number | null>(null)

// 合同编辑弹窗状态
const contractEditVisible = ref<boolean>(false)
const editingContract = ref<ContractResponse | null>(null)
const contractLoading = ref<boolean>(false)
const invoiceEditDialogVisible = ref<boolean>(false)
const editingInvoiceApplication = ref<InvoiceApplicationResponse | null>(null)
const invoiceDetailSheetVisible = ref<boolean>(false)
const selectedInvoiceDetailId = ref<number | null>(null)

// 快速驳回弹窗
const quickRejectVisible = ref<boolean>(false)
const quickRejectReason = ref<string>('')
const quickRejectRow = ref<ApprovalListItem | null>(null)
const quickApprovePendingId = ref<number | null>(null)
const quickRejectPendingId = ref<number | null>(null)
const quickRejectReasonError = ref<string>('')
const quickActionError = ref<FeedbackError | null>(null)

// 批量审批状态：只允许同一业务类型，避免后端将不同实体混在一次事务中
const selectedRowKeys = ref<(string | number)[]>([])
const bulkDialogVisible = ref<boolean>(false)
const bulkAction = ref<ApprovalAction | null>(null)
const bulkComment = ref<string>('')
const bulkPending = ref<boolean>(false)
const bulkError = ref<FeedbackError | null>(null)
const bulkResult = ref<BulkApproveResponse | null>(null)
// 保存批量结果中的失败项快照，失败项不应受当前页/筛选变化影响而丢失重试入口。
const bulkRetryItems = ref<ApprovalListItem[]>([])

const attachmentPreviewVisible = ref<boolean>(false)
const attachmentPreviewPendingId = ref<number | null>(null)
const attachmentPreviewRow = ref<ApprovalListItem | null>(null)
const attachmentPreviewUrl = ref<string>('')

// ==================== 计算属性 ====================
const selectedApprovals = computed<ApprovalListItem[]>(() => rows.value.filter((row) => selectedRowKeys.value.includes(row.id)))
const selectedBusinessType = computed<EntityType | null>(() => {
  const first = selectedApprovals.value[0]
  return first?.business_type ?? null
})
const quickActionPending = computed<boolean>(() =>
  quickApprovePendingId.value !== null || quickRejectPendingId.value !== null
)
const quickRejectDescription = computed<string>(() => {
  const row = quickRejectRow.value
  if (!row) return ''
  return `确定驳回“${getApprovalSubjectLabel(row)}”吗？当前状态：审批中。`
})

const activeApprovalDetail = computed<ApprovalDetail | null>(() => {
  const selected = selectedApproval.value
  const detail = currentApprovalDetail.value
  if (!selected || !detail) return null
  return detail.business_type === selected.business_type && detail.business_id === selected.business_id
    ? detail
    : null
})

const approvalEntityRouteId = (row: ApprovalListItem): number | string | null => {
  if (row.business_type !== 'OPPORTUNITY') return row.business_id
  return row.business_public_id ?? null
}

const requireApprovalEntityRouteId = (row: ApprovalListItem): number | string | null => {
  const entityId = approvalEntityRouteId(row)
  if (entityId === null) {
    toast.error('商机审批缺少对外ID，请刷新后重试')
  }
  return entityId
}

const selectedApprovalEntityId = computed<number | string | null>(() => {
  const selected = selectedApproval.value
  if (selected == null) return null
  return approvalEntityRouteId(selected)
})

const showInvoiceUploadFooter = computed<boolean>(() =>
  selectedApproval.value?.business_type === 'INVOICE' &&
  activeApprovalDetail.value?.business_type === 'INVOICE' &&
  activeApprovalDetail.value.status === 'APPROVED' &&
  (activeApprovalDetail.value.invoice_file_path == null || activeApprovalDetail.value.invoice_file_path.length === 0) &&
  permissionStore.hasPermission('invoice:mark_issued')
)

const showReissueCompleteFooter = computed<boolean>(() =>
  selectedApproval.value?.business_type === 'INVOICE_REISSUE' &&
  activeApprovalDetail.value?.business_type === 'INVOICE_REISSUE' &&
  activeApprovalDetail.value.status === 'APPROVED' &&
  entityDetailValue('status') !== 'COMPLETED' &&
  permissionStore.hasPermission('invoice:mark_issued')
)

const showLicenseIssueFooter = computed<boolean>(() =>
  selectedApproval.value?.business_type === 'LICENSE' &&
  activeApprovalDetail.value?.business_type === 'LICENSE' &&
  activeApprovalDetail.value.status === 'APPROVED' &&
  activeApprovalDetail.value.license_status !== 'ISSUED' &&
  permissionStore.hasPermission('license:issue')
)

const showBusinessActionFooter = computed<boolean>(() =>
  showInvoiceUploadFooter.value || showReissueCompleteFooter.value || showLicenseIssueFooter.value
)

const uploadFooterLabel = computed<string>(() =>
  showReissueCompleteFooter.value
    ? '上传重开发票'
    : showLicenseIssueFooter.value
      ? '发放 License'
      : '上传发票文件'
)

const uploadFooterAriaLabel = computed<string>(() =>
  showReissueCompleteFooter.value
    ? '上传红字发票和新发票，审批已通过'
    : showLicenseIssueFooter.value
      ? '发放 License，审批已通过'
      : '上传发票文件，审批已通过'
)

const businessActionTestId = computed<string>(() =>
  showReissueCompleteFooter.value
    ? 'complete-reissue-btn'
    : showLicenseIssueFooter.value
      ? 'issue-license-btn'
      : 'mark-issued-btn'
)

const openUploadFooterDialog = (): void => {
  if (showReissueCompleteFooter.value) {
    reissueCompleteDialogVisible.value = true
    return
  }
  if (showLicenseIssueFooter.value) {
    licenseIssueDialogVisible.value = true
    return
  }
  markIssuedDialogVisible.value = true
}

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
    INVOICE_REISSUE: '发票重开申请信息',
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
    EFFECTIVE: '已签署',
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

const invoiceReissueStatusLabel = (status?: string | null): string => {
  const map: Record<string, string> = {
    DRAFT: '草稿',
    PENDING_REVIEW: '审批中',
    APPROVED: '待财务重开',
    REJECTED: '已驳回',
    COMPLETED: '已重开'
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

const getFileExtension = (fileNameOrPath?: string | null): string => {
  if (fileNameOrPath == null || fileNameOrPath === '') return ''
  return fileNameOrPath.toLowerCase().split('?')[0]?.split('.').pop() ?? ''
}

const getAttachmentFileName = (row: ApprovalListItem | null): string => {
  if (!row) return '审批附件'
  if (row.business_type === 'CONTRACT') {
    const configured = row.contract_file_name?.trim()
    if (configured != null && configured.length > 0) return configured
    const ext = getFileExtension(row.contract_file_path)
    return ext.length > 0 ? `合同附件.${ext}` : '合同附件'
  }
  if (row.business_type === 'INVOICE') {
    const ext = getFileExtension(row.invoice_file_path)
    const normalizedInvoiceNumber = row.invoice_number?.trim() ?? ''
    const prefix = normalizedInvoiceNumber.length > 0 ? normalizedInvoiceNumber : '发票文件'
    return ext.length > 0 ? `${prefix}.${ext}` : prefix
  }
  return '审批附件'
}

const hasAttachment = (row: ApprovalListItem): boolean =>
  row.has_attachment === true ||
  (row.business_type === 'CONTRACT' && row.contract_file_path != null && row.contract_file_path.length > 0) ||
  (row.business_type === 'INVOICE' && row.invoice_file_path != null && row.invoice_file_path.length > 0)

const attachmentPreviewExtension = computed<string>(() =>
  getFileExtension(getAttachmentFileName(attachmentPreviewRow.value))
)

const attachmentPreviewIsImage = computed<boolean>(() =>
  ['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(attachmentPreviewExtension.value)
)

const attachmentPreviewIsPdf = computed<boolean>(() => attachmentPreviewExtension.value === 'pdf')

const attachmentPreviewTitle = computed<string>(() => getAttachmentFileName(attachmentPreviewRow.value))

const revokeAttachmentPreviewUrl = (): void => {
  if (attachmentPreviewUrl.value.length > 0) {
    window.URL.revokeObjectURL(attachmentPreviewUrl.value)
    attachmentPreviewUrl.value = ''
  }
}

const closeAttachmentPreview = (): void => {
  attachmentPreviewVisible.value = false
  attachmentPreviewRow.value = null
  revokeAttachmentPreviewUrl()
}

const handleAttachmentPreviewOpenChange = (open: boolean): void => {
  if (open) {
    attachmentPreviewVisible.value = true
    return
  }
  closeAttachmentPreview()
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
    case 'INVOICE_REISSUE':
      return [
        { key: 'number', label: '重开申请编号', value: entityDetailValue('application_number') ?? subjectNumber.value, type: 'copy' },
        { key: 'original_number', label: '原发票申请', value: entityDetailValue('original_invoice_application_number'), type: 'copy' },
        { key: 'reason', label: '重开原因', value: entityDetailValue('reason'), wide: true },
        { key: 'title', label: '新开票抬头', value: entityDetailValue('invoice_title_text') ?? subjectName.value, wide: true },
        commonCustomerField,
        { key: 'amount', label: '新开票金额', value: entityDetailValue('invoice_amount') ?? subjectAmount.value, type: 'amount' },
        { key: 'invoice_type', label: '新发票类型', value: invoiceTypeLabel(entityDetailValue('invoice_type')?.toString()) },
        { key: 'status', label: '重开状态', value: invoiceReissueStatusLabel(entityDetailValue('status')?.toString()), type: 'status' },
        { key: 'taxpayer_id', label: '新纳税人识别号', value: entityDetailValue('invoice_taxpayer_id'), type: 'mono', wide: true },
        { key: 'bank', label: '开户行', value: entityDetailValue('invoice_bank_name') },
        { key: 'bank_account', label: '银行账号', value: entityDetailValue('invoice_bank_account'), type: 'mono' },
        { key: 'invoice_address', label: '地址', value: entityDetailValue('invoice_address'), wide: true },
        { key: 'invoice_phone', label: '电话', value: entityDetailValue('invoice_phone') },
        { key: 'red_invoice_number', label: '红字发票号码', value: entityDetailValue('red_invoice_number'), type: 'mono' },
        { key: 'red_issued_time', label: '红字发票时间', value: formatDateValue(entityDetailValue('red_issued_time')) },
        {
          key: 'red_invoice_file',
          label: '红字发票文件',
          value: entityDetailValue('red_invoice_file_path') != null ? '已上传' : null
        },
        { key: 'new_invoice_number', label: '新发票号码', value: entityDetailValue('new_invoice_number'), type: 'mono' },
        { key: 'new_issued_time', label: '新发票时间', value: formatDateValue(entityDetailValue('new_issued_time')) },
        {
          key: 'new_invoice_file',
          label: '新发票文件',
          value: entityDetailValue('new_invoice_file_path') != null ? '已上传' : null
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
        { key: 'authorized_users', label: '使用人数', value: entityDetailValue('authorized_users') },
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
const activeViewLabel = computed(() =>
  tabs.value.find((tab) => tab.key === activeTab.value)?.label ?? '审批列表'
)
const effectiveFilters = computed(() => activeTab.value === 'pending'
  ? withoutFilterFields(activeFilters.value, ['status'])
  : activeFilters.value
)

// ==================== 列表字段注册表 ====================
const approvalBusinessTypeOptions = [
  { value: 'PAYMENT', label: '回款' },
  { value: 'INVOICE', label: '发票' },
  { value: 'INVOICE_REISSUE', label: '发票重开' },
  { value: 'CONTRACT', label: '合同' },
  { value: 'LICENSE', label: 'License' },
  { value: 'OPPORTUNITY', label: '商机' }
]
const approvalStatusOptions = [
  { value: 'PENDING', label: '审批中' },
  { value: 'APPROVED', label: '已通过' },
  { value: 'REJECTED', label: '已驳回' },
  { value: 'CANCELLED', label: '已撤回' }
]

const fields: ListFieldDefinition[] = [
  {
    key: 'application_number',
    label: '单号',
    type: 'text',
    column: { width: '180px', fixed: 'left' },
    filter: true
  },
  {
    key: 'business_type',
    label: '类型',
    type: 'enum',
    options: approvalBusinessTypeOptions,
    column: { width: '90px', align: 'center' },
    filter: { label: '单据类型' }
  },
  { key: 'entity_name', label: '实体', type: 'text', column: { width: '160px' }, filter: true },
  { key: 'entity_amount', label: '金额', type: 'number', column: { width: '130px', align: 'right' }, filter: true },
  { key: 'submitter_name', label: '提交人', type: 'text', column: { width: '110px' }, filter: true },
  { key: 'created_time', label: '提交时间', type: 'date', column: { width: '150px' }, filter: true },
  {
    key: 'status',
    label: '状态',
    type: 'enum',
    options: approvalStatusOptions,
    column: { width: '120px', align: 'center' },
    filter: { label: '审批状态' }
  },
  { key: 'overdue_hours', label: '超时', type: 'number', column: { width: '130px', align: 'center' } },
]

onUnmounted(() => {
  headerStore.clear()
})

useTopBarRegistration({
  tabs,
  activeTab: () => activeTab.value
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
const businessTypeLabel = (t: EntityType): string => {
  const map: Record<EntityType, string> = {
    PAYMENT: '回款',
    INVOICE: '发票',
    INVOICE_REISSUE: '发票重开',
    CONTRACT: '合同',
    LICENSE: 'License',
    OPPORTUNITY: '商机'
  }
  return map[t] ?? t
}

const getApprovalSubjectLabel = (row: ApprovalListItem): string => {
  const type = businessTypeLabel(row.business_type)
  const number = row.application_number?.trim()
  const name = row.entity_name?.trim()
  const subject = name !== undefined && name.length > 0 && number !== undefined && number.length > 0
    ? `${number} · ${name}`
    : name !== undefined && name.length > 0
      ? name
      : number !== undefined && number.length > 0
        ? number
        : `#${row.business_id}`
  return `${type}审批单 ${subject}`
}

const bulkFailureLabel = (businessId: number): string => {
  const row = bulkRetryItems.value.find((item) => item.business_id === businessId)
    ?? rows.value.find((item) => item.business_id === businessId)
  return row ? getApprovalSubjectLabel(row) : `业务单据 #${businessId}`
}

const isAxiosStatus = (error: unknown, code: number): boolean => {
  const response = (error as { response?: { status?: number } } | null)?.response
  return response?.status === code
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
  const requestId = ++listRequestId.value
  loadError.value = null
  selectedRowKeys.value = []
  listLoading.value = true
  try {
    const effectiveFilters = activeTab.value === 'pending'
      ? withoutFilterFields(activeFilters.value, ['status'])
      : activeFilters.value
    const query: ApprovalListQuery = {
      tab: activeTab.value,
      page: page.value,
      page_size: pageSize.value,
      ...serializeListQuery({ filters: effectiveFilters, sorts: activeSorts.value })
    }
    const res = await store.fetchList(query)
    if (requestId !== listRequestId.value) return
    rows.value = res.items
    total.value = res.total
  } catch (err) {
    if (requestId !== listRequestId.value) return
    loadError.value = toFeedbackError(err, '审批中心')
  } finally {
    if (requestId === listRequestId.value) {
      listLoading.value = false
    }
  }
}
const reload = (): void => {
  fetchList()
}

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

const handleSortApply = (sorts: ListSortCondition[]): void => {
  activeSorts.value = sorts
  page.value = 1
  fetchList()
}

const handleSortReset = (): void => {
  activeSorts.value = []
  page.value = 1
  fetchList()
}

const isRowSelectable = (row: ApprovalListItem): boolean => {
  if (activeTab.value !== 'pending' || row.status !== 'PENDING') return false
  if (selectedBusinessType.value !== null && row.business_type !== selectedBusinessType.value) return false
  return true
}

const clearSelection = (): void => {
  selectedRowKeys.value = []
}

const openBulkAction = (action: ApprovalAction): void => {
  if (selectedApprovals.value.length === 0 || selectedBusinessType.value === null) return
  bulkAction.value = action
  bulkComment.value = ''
  bulkError.value = null
  bulkResult.value = null
  bulkRetryItems.value = []
  bulkDialogVisible.value = true
}

const getBulkUpdatedTimes = (items: ApprovalListItem[]): Record<string, string> => Object.fromEntries(
  items
    .filter((item): item is ApprovalListItem & { updated_time: string } => typeof item.updated_time === 'string')
    .map((item) => [String(item.business_id), item.updated_time])
)

const executeBulkAction = async (items: ApprovalListItem[], action: ApprovalAction, comment: string): Promise<BulkApproveResponse | null> => {
  const entityType = items[0]?.business_type
  if (!entityType || items.some((item) => item.business_type !== entityType)) return null
  bulkPending.value = true
  bulkError.value = null
  try {
    return await store.bulkApprove(
      entityType,
      items.map((item) => item.business_id),
      action,
      comment,
      getBulkUpdatedTimes(items)
    )
  } catch (error: unknown) {
    bulkError.value = toFeedbackError(error, '批量审批', { operation: 'write' })
    handleApiError(error, '批量审批')
    return null
  } finally {
    bulkPending.value = false
  }
}

const updateBulkRetryItems = (sourceItems: ApprovalListItem[], result: BulkApproveResponse): void => {
  const failedIds = new Set(result.failed.map((item) => item.id))
  const latestByBusinessId = new Map(rows.value.map((row) => [row.business_id, row]))
  bulkRetryItems.value = sourceItems
    .filter((item) => failedIds.has(item.business_id))
    .map((item) => latestByBusinessId.get(item.business_id) ?? item)
}

const syncBulkSelection = (items: ApprovalListItem[]): void => {
  const visibleIds = new Set(items.map((item) => item.id))
  selectedRowKeys.value = rows.value
    .filter((row) => visibleIds.has(row.id))
    .map((row) => row.id)
}

const confirmBulkAction = async (): Promise<void> => {
  if (bulkAction.value === null) return
  if (bulkAction.value === 'REJECT' && !bulkComment.value.trim()) {
    toast.warning('请填写驳回理由，提交人将据此修改')
    return
  }
  const items = [...selectedApprovals.value]
  const result = await executeBulkAction(items, bulkAction.value, bulkComment.value.trim())
  if (result === null) return
  bulkResult.value = result
  await fetchList()
  updateBulkRetryItems(items, result)
  syncBulkSelection(bulkRetryItems.value)
  if (result.failed.length === 0) {
    bulkDialogVisible.value = false
  }
}

const retryBulkFailures = async (): Promise<void> => {
  if (bulkAction.value === null || bulkResult.value === null) return
  const items = [...bulkRetryItems.value]
  if (items.length === 0) return
  const result = await executeBulkAction(items, bulkAction.value, bulkComment.value.trim())
  if (result === null) return
  bulkResult.value = result
  await fetchList()
  updateBulkRetryItems(items, result)
  syncBulkSelection(bulkRetryItems.value)
  if (result.failed.length === 0) bulkDialogVisible.value = false
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

const getVisibleDetailTriggers = (): HTMLElement[] => {
  const desktopTriggers = Array.from(document.querySelectorAll<HTMLElement>(
    'table.data-table .data-table-row-detail-trigger'
  ))
  const desktopTable = document.querySelector<HTMLTableElement>('table.data-table')
  const desktopVisible = desktopTable === null
    || typeof window === 'undefined'
    || window.getComputedStyle(desktopTable).display !== 'none'
  if (desktopVisible && desktopTriggers.length > 0) return desktopTriggers
  return Array.from(document.querySelectorAll<HTMLElement>(
    '.data-table-mobile-list .data-table-mobile-detail-trigger'
  ))
}

const getDetailTrigger = (index: number): HTMLElement | null => {
  const triggers = getVisibleDetailTriggers()
  return triggers[index] ?? triggers[Math.min(Math.max(index, 0), triggers.length - 1)] ?? null
}

const openDetail = (row: ApprovalListItem, index?: number): void => {
  const rowIndex = index ?? rows.value.findIndex(r => r.id === row.id)
  selectedApproval.value = row
  triggerRowIndex.value = rowIndex
  focusedRowEl.value = getDetailTrigger(rowIndex)
  sheetVisible.value = true
}

const onSheetClosed = (): void => {
  // Sheet 关闭后回到真实详情按钮，而不是把 table row 变成伪按钮。
  const target = focusedRowEl.value?.isConnected === true
    ? focusedRowEl.value
    : getDetailTrigger(triggerRowIndex.value)
  target?.focus({ preventScroll: true })
  selectedApproval.value = null
  store.clearDetail()
  markIssuedDialogVisible.value = false
  reissueCompleteDialogVisible.value = false
  licenseIssueDialogVisible.value = false
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

const handleInvoiceReissueCompleted = (): void => {
  reissueCompleteDialogVisible.value = false
  sheetVisible.value = false
  fetchList()
}

const handleLicenseIssued = (): void => {
  licenseIssueDialogVisible.value = false
  sheetVisible.value = false
  fetchList()
}

// 条4：REJECTED 行修改并重新提交。
// 合同、发票在审批中心内打开既有编辑弹窗；其他业务仍进入对应业务页面处理。
const handleResubmit = async (row: ApprovalListItem): Promise<void> => {
  resubmitPendingId.value = row.id
  try {
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

    if (row.business_type === 'INVOICE') {
      try {
        editingInvoiceApplication.value = await invoiceApi.getInvoiceApplication(row.business_id)
        invoiceEditDialogVisible.value = true
      } catch (error: unknown) {
        handleApiError(error, '获取发票申请')
      }
      return
    }

    if (row.business_type === 'INVOICE_REISSUE') {
      const originalInvoiceApplicationId = getOriginalInvoiceApplicationId(row)
      if (originalInvoiceApplicationId === null) {
        toast.error('未找到原发票申请，无法修改重开申请')
        return
      }
      selectedInvoiceDetailId.value = originalInvoiceApplicationId
      invoiceDetailSheetVisible.value = true
      return
    }

    const confirmed = await createConfirmDialog({
      title: '修改并重新提交',
      message: `将跳转到 ${businessTypeLabel(row.business_type)} 编辑页修改后重新提交审批。是否继续？`,
      confirmText: '确定',
      cancelText: '取消',
      variant: 'default'
    })
    if (!confirmed) return
    // 跳转到对应实体编辑页
    const route: Record<Exclude<EntityType, 'CONTRACT' | 'INVOICE' | 'INVOICE_REISSUE'>, string | ReturnType<typeof customerDetailRoute>> = {
      // 回款无独立编辑页（/payments 为列表页）：跳列表页 + info 提示，
      // 保证不白屏/不断旅程；用户在列表内修改后重新提交审批。
      PAYMENT: `/payments`,
      // License 申请在客户详情页的 License 管理 Tab 编辑
      LICENSE: row.customer_info?.id !== undefined
        ? customerDetailRoute(row.customer_info.id, { tab: 'license-management' })
        : '/customers',
      OPPORTUNITY: row.business_public_id !== undefined && row.business_public_id !== null
        ? `/opportunities?opportunityId=${row.business_public_id}`
        : '/opportunities'
    }
    const target = route[row.business_type as Exclude<EntityType, 'CONTRACT' | 'INVOICE' | 'INVOICE_REISSUE'>]
    await router.push(target)
    // PAYMENT 目标是列表页，无法直接进入驳回回款的编辑入口——补 info 引导，
    // 旅程不断（比原 window.location.assign hash bug 强）。
    if (row.business_type === 'PAYMENT') {
      toast.info('请修改回款记录后重新提交审批')
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

const handleInvoiceEditDialogOpenChange = (open: boolean): void => {
  invoiceEditDialogVisible.value = open
  if (!open) {
    editingInvoiceApplication.value = null
  }
}

const handleInvoiceEditSuccess = (): void => {
  invoiceEditDialogVisible.value = false
  editingInvoiceApplication.value = null
  sheetVisible.value = false
  fetchList()
}

const handleInvoiceDetailSheetVisibleChange = (visible: boolean): void => {
  invoiceDetailSheetVisible.value = visible
  if (!visible) {
    selectedInvoiceDetailId.value = null
  }
}

const handleInvoiceDetailRefresh = (): void => {
  fetchList()
}

const getOriginalInvoiceApplicationId = (row: ApprovalListItem): number | null => {
  const listValue = row.original_invoice_application_id
  if (typeof listValue === 'number') return listValue

  const detailValue = activeApprovalDetail.value?.entity_detail?.['original_invoice_application_id']
  return typeof detailValue === 'number' ? detailValue : null
}

const handleRemind = async (row: ApprovalListItem): Promise<void> => {
  const entityId = requireApprovalEntityRouteId(row)
  if (entityId === null) return

  remindPendingId.value = row.id
  try {
    const res = await store.remindEntity(row.business_type, entityId)
    toast.success(res.message)
  } catch (error) {
    handleApiError(error, '催办')
  } finally {
    remindPendingId.value = null
  }
}

const handlePreviewAttachment = async (row: ApprovalListItem): Promise<void> => {
  if (!hasAttachment(row)) return
  const entityId = requireApprovalEntityRouteId(row)
  if (entityId === null) return

  attachmentPreviewPendingId.value = row.id
  attachmentPreviewRow.value = row
  attachmentPreviewVisible.value = true
  revokeAttachmentPreviewUrl()
  try {
    attachmentPreviewUrl.value = await approvalGenericApi.createApprovalAttachmentObjectUrl(
      row.business_type,
      entityId
    )
  } catch (error) {
    attachmentPreviewVisible.value = false
    attachmentPreviewRow.value = null
    handleApiError(error, '预览附件')
  } finally {
    attachmentPreviewPendingId.value = null
  }
}

const getRowActions = (row: ApprovalListItem): TableRowActionSet => {
  const primaryActions: ActionConfig[] = [
    {
      label: '详情',
      kind: 'detail',
      handler: () => openDetail(row)
    }
  ]
  if (hasAttachment(row)) {
    primaryActions.push({
      label: '预览',
      desktopPrimary: true,
      handler: () => { void handlePreviewAttachment(row) },
      disabled: attachmentPreviewPendingId.value === row.id
    })
  }
  if (activeTab.value === 'submitted' && row.status === 'REJECTED') {
    primaryActions.push({
      label: '修改并重新提交',
      desktopPrimary: true,
      handler: () => { void handleResubmit(row) },
      disabled: resubmitPendingId.value === row.id
    })
  }
  if (activeTab.value === 'submitted' && row.status === 'PENDING') {
    primaryActions.push({
      label: '催办',
      desktopPrimary: true,
      icon: BellRing,
      handler: () => { void handleRemind(row) },
      disabled: remindPendingId.value === row.id
    })
  }
  return { primaryActions, secondaryActions: [] }
}

const handleDownloadAttachment = async (): Promise<void> => {
  const row = attachmentPreviewRow.value
  if (!row) return
  const entityId = requireApprovalEntityRouteId(row)
  if (entityId === null) return

  try {
    await approvalGenericApi.downloadApprovalAttachment(
      row.business_type,
      entityId,
      getAttachmentFileName(row)
    )
  } catch (error) {
    handleApiError(error, '下载附件')
  }
}

// 移动端快速审批：同意（单条，无抽屉）
const handleQuickApprove = async (row: ApprovalListItem): Promise<void> => {
  if (quickActionPending.value || row.status !== 'PENDING') return
  const entityId = requireApprovalEntityRouteId(row)
  if (entityId === null) return

  quickApprovePendingId.value = row.id
  quickActionError.value = null
  try {
    const confirmed = await createConfirmDialog({
      title: '同意审批',
      message: `确定同意“${getApprovalSubjectLabel(row)}”吗？当前状态：审批中。同意后将进入已通过状态。`,
      confirmText: '确定',
      cancelText: '取消',
      variant: 'default'
    })
    if (!confirmed) return
    // 调 store.approveEntity（单条审批，updated_time 用当前行）
    await store.approveEntity(
      row.business_type,
      entityId,
      'APPROVE',
      '审批通过',
      row.updated_time
    )
    toast.success('已同意')
    // 刷新列表（移除该行）
    await fetchList()
  } catch (error: unknown) {
    if (isAxiosStatus(error, 409)) {
      await fetchList()
      toast.warning('该审批已被他人处理，列表已刷新')
    } else {
      quickActionError.value = toFeedbackError(error, '同意审批', { operation: 'write' })
      handleApiError(error, '同意审批')
    }
  } finally {
    quickApprovePendingId.value = null
  }
}

// 移动端快速审批：驳回（单条，弹窗输入理由）
const handleQuickReject = (row: ApprovalListItem): void => {
  if (quickActionPending.value || row.status !== 'PENDING') return
  quickRejectReason.value = ''
  quickRejectReasonError.value = ''
  quickActionError.value = null
  quickRejectRow.value = row
  quickRejectVisible.value = true
}

const handleQuickRejectOpenChange = (open: boolean): void => {
  if (!open && quickActionPending.value) return
  quickRejectVisible.value = open
  if (!open) {
    quickRejectRow.value = null
    quickRejectReasonError.value = ''
    quickActionError.value = null
  }
}

const confirmQuickReject = async (): Promise<void> => {
  const reason = quickRejectReason.value.trim()
  if (!reason) {
    quickRejectReasonError.value = '请填写驳回理由'
    toast.warning('请填写驳回理由，提交人将据此修改')
    return
  }
  if (!quickRejectRow.value) return
  if (quickActionPending.value) return
  const row = quickRejectRow.value
  const entityId = requireApprovalEntityRouteId(row)
  if (entityId === null) return

  quickRejectReasonError.value = ''
  quickActionError.value = null
  quickRejectPendingId.value = row.id
  try {
    await store.approveEntity(
      row.business_type,
      entityId,
      'REJECT',
      reason,
      row.updated_time
    )
    toast.success('已驳回，申请人可修改后重新提交')
    quickRejectVisible.value = false
    quickRejectRow.value = null
    quickRejectReason.value = ''
    quickRejectReasonError.value = ''
    quickActionError.value = null
    await fetchList()
  } catch (error: unknown) {
    if (isAxiosStatus(error, 409)) {
      await fetchList()
      toast.warning('该审批已被他人处理，你的填写已保留')
    } else {
      quickActionError.value = toFeedbackError(error, '驳回审批', { operation: 'write' })
      handleApiError(error, '驳回审批')
      const input = document.querySelector<HTMLElement>('#quick-reject-reason')
      input?.focus()
    }
  } finally {
    quickRejectPendingId.value = null
  }
}

// 抽屉侧 ApprovalProcessGeneric REJECTED 态「修改并重新提交」CTA（Important #2）
// 事件无 payload，目标行取 selectedApproval（抽屉当前展示行）。
const onResubmit = (): void => {
  if (selectedApproval.value == null) return
  handleResubmit(selectedApproval.value)
}

// 键盘快捷键（条9）：J/K 上下移动；Enter 仅作为页面级增强。
// 详情按钮本身使用原生 Enter/Space，避免页面级监听再次打开详情。
const isKeyboardScopeBlocked = (target: EventTarget | null): boolean => {
  if (!(target instanceof HTMLElement)) return false
  return target.closest(
    'input, textarea, select, button, a, [contenteditable="true"], [role="dialog"], [role="menu"]'
  ) !== null
}

const onKeydown = (e: KeyboardEvent): void => {
  if (sheetVisible.value || isKeyboardScopeBlocked(e.target)) return
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
  const target = getDetailTrigger(focusIndex.value)
  target?.focus({ preventScroll: false })
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
  revokeAttachmentPreviewUrl()
})

watch(rows, async () => {
  focusIndex.value = Math.min(Math.max(focusIndex.value, 0), Math.max(rows.value.length - 1, 0))
  await nextTick()
  if (focusedRowEl.value?.isConnected !== true && sheetVisible.value === false) {
    focusedRowEl.value = getDetailTrigger(focusIndex.value)
  }
}, { flush: 'post' })
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.approval-center {
  padding: $wolf-list-page-padding-top-v2 $wolf-page-padding-v2 $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-section-gap-v2;
  min-height: 0;
  flex: 1;
}

.approval-bulk-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: $wolf-space-sm-v2;
  margin-left: auto;
}

.approval-bulk-toolbar__count {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  white-space: nowrap;
}

.approval-bulk-result {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm-v2;
  max-height: 280px;
  overflow-y: auto;
  padding: $wolf-space-md-v2;
  border: 1px solid $wolf-border-light-v2;
  border-radius: $wolf-radius-surface-v2;
  background: $wolf-bg-page-v2;
}

.approval-bulk-result__list {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  margin: 0;
  padding-left: $wolf-space-lg-v2;
  font-size: $wolf-font-size-caption-v2;
}

.approval-bulk-result__list li {
  display: flex;
  justify-content: space-between;
  gap: $wolf-space-md-v2;
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

.approval-mobile-card {
  min-width: 0;
}

.approval-mobile-actions {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-sm-v2;
  width: 100%;
}

.approval-mobile-action {
  flex: 1 1 30%;
  min-width: 0;
  min-height: $wolf-touch-target-min-v2;
}

.approval-mobile-action-wide {
  flex-basis: 100%;
}

.approval-attachment-preview {
  min-height: 55vh;
  max-height: 70vh;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: auto;
  border: 1px solid $wolf-border-light-v2;
  border-radius: $wolf-radius-surface-v2;
  background: $wolf-bg-page-v2;
}

.approval-attachment-preview__loading,
.approval-attachment-preview__fallback {
  padding: $wolf-space-xl-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-body-v2;
  text-align: center;
}

.approval-attachment-preview__image {
  display: block;
  max-width: 100%;
  max-height: 70vh;
  object-fit: contain;
}

.approval-attachment-preview__frame {
  width: 100%;
  height: 70vh;
  border: 0;
  background: $wolf-bg-card-v2;
}

// 移动端卡片警告边框样式
@media (max-width: 768px) {
  .approval-center {
    padding: $wolf-page-padding-mobile-v2;
  }

  :deep(.data-table-mobile-card:has(.approval-mobile-card.is-overdue)) {
    border-color: $wolf-warning-v2;
    border-width: 1px;
  }
}

// ===== Sheet 内部样式（参考 LeadDetailSheet） =====

// 信息卡片
.info-card {
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-surface-v2;
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
