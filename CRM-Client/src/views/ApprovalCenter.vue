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
        :export-enabled="canExportApprovals"
        export-title="审批列表"
        :export-handler="exportApprovalFields"
        :fields="fields"
        :data="rows"
        :total="total"
        :page="page"
        :page-size="pageSize"
        :loading="listLoading"
        :load-error="loadError"
        view-key="approval-center.list"
        :effective-filters="effectiveFilters"
        column-config-enabled
        height="calc(100vh - 108px)"
        height-strategy="fill"
        scroll-mode="contained"
        empty-title="暂无待审批事项"
        :empty-reason="search.trim() !== '' || effectiveFilters.length > 0 ? 'filtered' : 'no-data'"
        empty-description="所有回款与发票申请都已处理完毕"
        mobile-mode="card"
        row-interactive
        detail-column-key="application_number"
        :get-row-label="(row) => `审批单 ${row.application_number || row.id}`"
        :get-row-actions="getRowActions"
        @update:page="page = $event; fetchList()"
        @update:page-size="pageSize = $event; page = 1; fetchList()"
        v-model:search="search"
        search-enabled
        search-placeholder="搜索单号、实体或提交人"
        :search-loading="listLoading"
        @search-apply="handleSearchApply"
        @search-clear="handleSearchClear"
        @filter-apply="handleFilterApply"
        @filter-reset="handleFilterReset"
        @sort-apply="handleSortApply"
        @sort-reset="handleSortReset"
        @row-click="openDetail"
        @retry="reload"
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
              data-action-id="preview"
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
              data-action-id="reject"
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
              data-action-id="approve"
              :loading="quickApprovePendingId === row.id"
              :disabled="quickActionPending"
              @click.stop="handleQuickApprove(row)"
            >
              同意
            </Button>
            <Button
              v-if="!hasAttachment(row)"
              variant="outline"
              size="lg"
              class="approval-mobile-action"
              data-testid="mobile-detail-btn"
              data-action-id="detail"
              @click.stop="openDetail(row, index)"
            >
              查看详情
            </Button>
          </div>
          <div class="approval-mobile-actions" v-else-if="activeTab === 'submitted' && row.status === 'REJECTED' && row.business_type !== 'CONTRACT_CHANGE'">
            <Button
              variant="default"
              size="lg"
              class="approval-mobile-action approval-mobile-action-wide"
              data-testid="mobile-resubmit-btn"
              data-action-id="resubmit"
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
              data-action-id="remind"
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
              data-action-id="preview"
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
              data-action-id="detail"
              @click.stop="openDetail(row, index)"
            >
              查看详情
            </Button>
          </div>
          <div class="approval-mobile-actions" v-else>
            <Button
              v-if="hasAttachment(row)"
              variant="outline"
              size="lg"
              class="approval-mobile-action"
              data-testid="mobile-preview-btn"
              data-action-id="preview"
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
              data-action-id="detail"
              @click.stop="openDetail(row, index)"
            >
              查看详情
            </Button>
          </div>
        </template>
      </DataTable>

    <!-- 详情 Sheet -->
    <Sheet v-model:open="sheetVisible">
      <DetailSheetContent aria-describedby="" @close-auto-focus="restoreListFocus">
        <SheetTitle v-if="drillTarget === 'customer' || drillTarget === 'opportunity'" class="sr-only">{{ drillTarget === 'customer' ? '客户详情' : '商机详情' }}</SheetTitle>
        <div v-show="drillTarget === null" class="flex flex-1 flex-col min-h-0 min-w-0">
        <!-- Header -->
        <SheetHeader class="p-6 pb-4 border-b border-wolf-border-default-v2">
          <SheetTitle v-if="drillTarget === null" class="text-lg font-semibold">审批详情</SheetTitle>
          <p class="font-mono text-sm mt-1">
            {{ selectedApproval?.application_number || '-' }}
          </p>
        </SheetHeader>

        <!-- Content -->
        <ScrollArea class="flex-1 min-h-0 min-w-0">
          <div class="p-6 space-y-6 min-h-[400px]">
            <!-- 申请主体信息：优先展示审批关联业务内容 -->
            <Card v-if="selectedApproval" class="info-card">
              <CardContent class="p-0">
                <div class="p-4 border-b border-wolf-border-light-v2 flex flex-wrap items-center justify-between gap-3">
                  <h3 class="text-sm font-semibold text-wolf-text-primary-v2">{{ approvalSubjectTitle }}</h3>
                  <Button
                    v-if="invoiceBillingType"
                    type="button"
                    variant="outline"
                    size="sm"
                    class="border-primary/20 bg-primary/5 text-primary hover:bg-primary/10"
                    :disabled="invoiceBillingFields.length === 0"
                    @click="copyAllInvoiceBilling"
                  >
                    <Copy class="h-4 w-4 mr-2" aria-hidden="true" />
                    复制全部开票信息
                  </Button>
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
                      <button
                        v-else-if="field.type === 'link' && hasFieldDrilldown(field)"
                        type="button"
                        class="attribute-value attribute-value-link text-left"
                        @click="openFieldDrilldown(field)"
                      >
                        {{ displayFieldValue(field.value) }}
                      </button>
                      <div v-else-if="field.type === 'amount'" class="attribute-value">
                        <AmountText :value="field.value" tone="warning" />
                      </div>
                      <div v-else-if="field.type === 'status'" class="attribute-value">
                        <Badge variant="outline">{{ displayFieldValue(field.value) }}</Badge>
                      </div>
                      <div v-else-if="field.type === 'mono'" class="attribute-value font-mono text-sm">{{ displayFieldValue(field.value) }}</div>
                      <div v-else class="attribute-value">{{ displayFieldValue(field.value) }}</div>
                    </div>
                  </div>
                  <section v-if="invoiceBillingType" class="mt-5 border-t border-dashed border-border pt-5 min-w-0" aria-label="开票信息">
                    <div class="flex flex-wrap items-center gap-x-3 gap-y-1 mb-4">
                      <h4 class="text-sm font-semibold text-foreground">{{ invoiceBillingType === 'INVOICE_REISSUE' ? '新开票信息' : '开票信息' }}</h4>
                      <span class="text-xs text-muted-foreground">点击内容即可复制</span>
                    </div>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4 min-w-0">
                      <div v-for="field in unchangedInvoiceBillingFields" :key="field.key" :class="['min-w-0 space-y-1', field.wide && 'sm:col-span-2']">
                        <div class="text-xs text-muted-foreground">{{ field.label }}</div>
                        <button type="button" class="billing-copy-value" :aria-label="`复制${field.label}：${field.displayValue}`" @click="copyInvoiceBillingField(field)">
                          <AmountText v-if="field.isAmount && field.copyValue !== ''" :value="field.copyValue" tone="primary" class="billing-copy-amount" />
                          <template v-else>{{ field.displayValue }}</template>
                        </button>
                      </div>
                    </div>
                    <div v-if="changedInvoiceBillingFields.length > 0" class="mt-4 space-y-3">
                      <div v-for="field in changedInvoiceBillingFields" :key="field.key" class="min-w-0 rounded-md border border-warning/20 bg-warning/5 p-3">
                        <div class="flex items-center gap-2 mb-1">
                          <span class="text-xs text-muted-foreground">{{ field.label }}</span>
                          <Badge variant="outline" class="border-warning/30 bg-warning/10 text-warning">已改</Badge>
                        </div>
                        <button type="button" class="billing-copy-value" :aria-label="`复制${field.label}：${field.displayValue}`" @click="copyInvoiceBillingField(field)">
                          <AmountText v-if="field.isAmount && field.copyValue !== ''" :value="field.copyValue" tone="primary" class="billing-copy-amount" />
                          <template v-else>{{ field.displayValue }}</template>
                        </button>
                        <div class="mt-1 text-xs text-muted-foreground break-all whitespace-pre-wrap">原：<span class="line-through">{{ field.originalValue }}</span></div>
                      </div>
                    </div>
                  </section>
                </div>
              </CardContent>
            </Card>
            <Card v-if="selectedApproval?.business_type === 'CONTRACT_CHANGE' && contractChangeFiles.length > 0" class="info-card">
              <CardContent class="p-0">
                <div class="p-4 border-b border-wolf-border-light-v2">
                  <h3 class="text-sm font-semibold text-wolf-text-primary-v2">变更附件</h3>
                </div>
                <div class="p-4">
                  <FileAttachment
                    mode="readonly"
                    :files="contractChangeFiles"
                    :preview-in-dialog="false"
                    @preview="handleSelectedAttachmentPreview"
                    @download="handleSelectedAttachmentDownload"
                  />
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
                      <div class="attribute-value"><button type="button" class="attribute-value-link text-left" @click="openDrilldown('customer', approvalCustomerInfo.id)">{{ approvalCustomerInfo.account_name }}</button></div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">客户详情</div>
                      <div class="attribute-value"><button type="button" class="attribute-value-link text-left" @click="openDrilldown('customer', approvalCustomerInfo.id)">查看客户详情</button></div>
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

            <!-- 审批流程卡片（组件内部处理加载/错误/空态） -->
            <Card v-if="selectedApproval && selectedApprovalEntityId !== null" class="info-card">
              <CardContent class="p-0">
                <div class="p-4 border-b border-wolf-border-light-v2">
                  <h3 class="text-sm font-semibold text-wolf-text-primary-v2">审批流程</h3>
                </div>
                <div class="p-4">
                  <ApprovalProcessGeneric
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
              </CardContent>
            </Card>
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
        </div>
        <div v-if="drillTarget !== null" ref="drillSurface" class="flex flex-1 flex-col min-h-0 min-w-0 overflow-hidden">
          <ContractDetailSheet v-if="drillTarget === 'contract'" :contract-id="Number(drillId)" :visible="true" embedded :source-approval="approvalSource" @update:visible="handleDrillVisibleChange" @back="closeDrilldown" />
          <PaymentRecordDetailSheet v-else-if="drillTarget === 'payment'" :record-id="Number(drillId)" :visible="true" embedded :source-approval="approvalSource" @update:visible="handleDrillVisibleChange" @back="closeDrilldown" />
          <InvoiceDetailSheet v-else-if="drillTarget === 'invoice'" :invoice-id="Number(drillId)" :visible="true" embedded :source-approval="approvalSource" @update:visible="handleDrillVisibleChange" @back="closeDrilldown" />
          <OpportunityDetailSheet v-else-if="drillTarget === 'opportunity'" :opportunity-id="String(drillId)" :visible="true" embedded :source-approval="approvalSource" @update:visible="handleDrillVisibleChange" @back="closeDrilldown" />
          <CustomerDetailSheet v-else-if="drillTarget === 'customer'" :customer-id="String(drillId)" :visible="true" embedded :source-approval="approvalSource" @update:visible="handleDrillVisibleChange" @back="closeDrilldown" />
        </div>
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

    <FilePreviewDialog
      :open="attachmentPreviewVisible"
      :file="attachmentPreviewFile"
      :loading="attachmentPreviewPendingId != null"
      @update:open="handleAttachmentPreviewOpenChange"
      @download="handleDownloadAttachment"
    />

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
import { AmountText, DataTable, Badge, FileAttachment, FilePreviewDialog, type ActionConfig, type TableRowActionSet } from '@/components/crmwolf'
import type { ListFieldDefinition } from '@/components/crmwolf/listFieldCatalog'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'
import { Button } from '@/components/ui/button'
import { Sheet, SheetHeader, SheetTitle, SheetFooter } from '@/components/ui/sheet'
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
import ContractDetailSheet from '@/views/ContractDetailSheet.vue'
import PaymentRecordDetailSheet from '@/views/PaymentRecordDetailSheet.vue'
import OpportunityDetailSheet from '@/views/OpportunityDetailSheet.vue'
import CustomerDetailSheet from '@/views/CustomerDetailSheet.vue'
import type { ApprovalSourceContext } from '@/types/approvalSource'
import { useApprovalStore } from '@/stores/approval'
import { usePermissionStore } from '@/stores/permissions'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { useTopBarRegistration } from '@/composables/useTopBarRegistration'
import { useDataTableExport } from '@/composables/useDataTableExport'
import { formatDateRelative } from '@/utils/format'
import { serializeListQuery, withoutFilterFields } from '@/utils/listQuery'
import { buildDataTableExportFileName } from '@/utils/downloadBlob'
import { buildApprovalInvoiceBillingFields, formatApprovalInvoiceBillingCopy, type ApprovalInvoiceBillingField } from '@/utils/approvalInvoiceBilling'
import { createConfirmDialog } from '@/utils/confirmDialogImpl'
import { handleApiError } from '@/utils/errorHandler'
import { toFeedbackError, type FeedbackError } from '@/types/feedback'
import { customerDetailRoute } from '@/utils/customerRoutes'
import approvalGenericApi from '@/api/approvalGeneric'
import { type ListExportPayload } from '@/api/listExport'
import contractApi from '@/api/contract'
import invoiceApi, { type InvoiceApplicationResponse } from '@/api/invoice'
import type { EntityType, ApprovalCustomerInfo, ApprovalDetail, ApprovalListItem, ApprovalListQuery, ApprovalTab } from '@/schemas/approvalGeneric'
import type { FileAttachmentItem } from '@/types/fileAttachment'
import { getAcquisitionSourceDisplayName } from '@/schemas/acquisition-source'
import type { ContractResponse } from '@/api/contract'

type Tab = 'pending' | 'processed' | 'submitted'
type ApprovalSubjectLinkTarget = 'contract' | 'payment' | 'invoice' | 'opportunity' | 'customer'
interface ApprovalSubjectField {
  key: string
  label: string
  value: string | number | null | undefined
  type?: 'text' | 'copy' | 'amount' | 'status' | 'mono' | 'link'
  linkTarget?: ApprovalSubjectLinkTarget
  linkId?: number | string | null
  wide?: boolean
}

// ==================== Stores ====================
usePageTitle()
const store = useApprovalStore()
const permissionStore = usePermissionStore()
const headerStore = useHeaderStore()
const { pendingCount, currentApprovalDetail } = storeToRefs(store)
const router = useRouter()
const canExportApprovals = computed(() => permissionStore.hasPermission('approval:export'))
const activeTab = ref<Tab>('pending')

interface ApprovalListExportContext {
  tab: ApprovalTab
  search: string | undefined
  filters: ListFilterCondition[]
  sorts: ListSortCondition[]
}

const currentApprovalListContext = (): ApprovalListExportContext => ({
  tab: activeTab.value,
  search: search.value.trim() || undefined,
  filters: [...activeFilters.value],
  sorts: [...activeSorts.value],
})

const { exportFields: exportApprovalFields } = useDataTableExport({
  request: (fields) => {
    const { tab, search, filters, sorts } = currentApprovalListContext()
    const payload: ListExportPayload<ApprovalTab> = { fields, tab, filters, sorts }
    if (search !== undefined) {
      payload.search = search
    }
    return approvalGenericApi.exportApprovals(payload)
  },
  fileName: () => buildDataTableExportFileName(
    '审批列表',
    tabs.value.find((tab) => tab.key === activeTab.value)?.label ?? '待我审批',
    new Date(),
  ),
})


const search = ref('')

watch(activeTab, () => {
  search.value = ''
}, { flush: 'sync' })
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

const drillTarget = ref<ApprovalSubjectLinkTarget | null>(null)
const drillSurface = ref<HTMLElement | null>(null)
const drillId = ref<number | string | null>(null)
const approvalSource = computed<ApprovalSourceContext | null>(() => {
  const approval = selectedApproval.value
  if (!approval) return null
  return {
    approvalLabel: `${businessTypeLabel(approval.business_type)}审批`,
    applicationNumber: approval.application_number,
  }
})
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


const attachmentPreviewVisible = ref<boolean>(false)
const attachmentPreviewPendingId = ref<number | null>(null)
const attachmentPreviewRow = ref<ApprovalListItem | null>(null)
const attachmentPreviewUrl = ref<string>('')

// ==================== 计算属性 ====================
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
    CONTRACT_CHANGE: '合同变更审批',
    PAYMENT: '回款信息',
    INVOICE: '发票申请信息',
    INVOICE_REISSUE: '发票重开申请信息',
    LICENSE: 'License 申请信息',
    OPPORTUNITY: '商机信息'
  }
  return type ? map[type] ?? '申请信息' : '申请信息'
})
const invoiceBillingType = computed<'INVOICE' | 'INVOICE_REISSUE' | null>(() => {
  const type = selectedApproval.value?.business_type
  return type === 'INVOICE' || type === 'INVOICE_REISSUE' ? type : null
})
const invoiceBillingFields = computed(() => {
  const type = invoiceBillingType.value
  const detail = activeApprovalDetail.value?.entity_detail
  return type && detail ? buildApprovalInvoiceBillingFields(type, detail) : []
})
const unchangedInvoiceBillingFields = computed(() => invoiceBillingFields.value.filter(field => !field.changed))
const changedInvoiceBillingFields = computed(() => invoiceBillingFields.value.filter(field => field.changed))


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


const paymentConfirmStatusLabel = (status?: string | null): string => {
  const map: Record<string, string> = {
    DRAFT: '草稿',
    PENDING: '待确认',
    CONFIRMED: '已确认',
    DISPUTED: '有争议'
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
  if (row.business_type === 'CONTRACT_CHANGE') {
    const name = row.attachment_name?.trim() ?? ''
    return name.length > 0 ? name : '合同变更附件'
  }
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
  (row.business_type === 'CONTRACT_CHANGE' && (row.attachment_name?.trim() ?? '').length > 0) ||
  (row.business_type === 'CONTRACT' && row.contract_file_path != null && row.contract_file_path.length > 0) ||
  (row.business_type === 'INVOICE' && row.invoice_file_path != null && row.invoice_file_path.length > 0)

const selectedAttachmentRow = computed<ApprovalListItem | null>(() => {
  const row = selectedApproval.value
  if (row?.business_type !== 'CONTRACT_CHANGE') return null
  const detail = activeApprovalDetail.value
  return {
    ...row,
    attachment_name: detail?.attachment_name ?? detail?.entity_detail?.attachment_name ?? row.attachment_name,
    attachment_size: detail?.attachment_size ?? detail?.entity_detail?.attachment_size ?? row.attachment_size,
    attachment_mime_type: detail?.attachment_mime_type ?? detail?.entity_detail?.attachment_mime_type ?? row.attachment_mime_type
  }
})

const contractChangeFiles = computed<FileAttachmentItem[]>(() => {
  const row = selectedAttachmentRow.value
  if (row === null || !hasAttachment(row)) return []
  const file: FileAttachmentItem = {
    id: row.business_id,
    name: getAttachmentFileName(row)
  }
  if (row.attachment_size != null) file.size = row.attachment_size
  if (row.attachment_mime_type != null) file.mimeType = row.attachment_mime_type
  return [file]
})

const attachmentPreviewFile = computed<FileAttachmentItem | null>(() => {
  const row = attachmentPreviewRow.value
  if (!row) return null
  return { id: row.id, name: getAttachmentFileName(row), url: attachmentPreviewUrl.value }
})

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
  const customer = approvalCustomerInfo.value
  const customerField: ApprovalSubjectField = { key: 'customer_name', label: '关联客户', value: customer?.account_name, type: 'link', linkTarget: 'customer', linkId: customer?.id ?? null }
  const detail = (key: string): string | number | null => entityDetailValue(key) ?? null
  const entityDetail = activeApprovalDetail.value?.entity_detail
  switch (selected.business_type) {
    case 'CONTRACT_CHANGE': {
      const item = (entityDetail?.change_items ?? activeApprovalDetail.value?.change_items ?? selected.change_items)?.[0]
      return [
        { key: 'contract', label: '关联合同', value: entityDetail?.contract_name ?? subjectName.value, type: 'link', linkTarget: 'contract', linkId: entityDetail?.contract_id ?? null },
        { key: 'old_amount', label: '原合同金额', value: item?.old_value ?? null, type: 'amount' },
        { key: 'new_amount', label: '变更后金额', value: item?.new_value ?? selected.entity_amount ?? null, type: 'amount' },
        { key: 'reason', label: '变更原因', value: entityDetail?.reason ?? activeApprovalDetail.value?.reason ?? selected.reason ?? null, wide: true }
      ]
    }
    case 'CONTRACT': return [
      { key: 'number', label: '合同编号', value: detail('contract_number') ?? subjectNumber.value, type: 'copy' },
      { key: 'name', label: '合同名称', value: detail('contract_name') ?? subjectName.value }, customerField,
      { key: 'amount', label: '合同金额', value: detail('total_amount') ?? subjectAmount.value, type: 'amount' },
      { key: 'status', label: '合同状态', value: contractStatusLabel(detail('status')?.toString()), type: 'status' },
    ]
    case 'PAYMENT': return [
      { key: 'number', label: '回款编号', value: detail('record_number') ?? subjectNumber.value, type: 'copy' },
      { key: 'amount', label: '回款金额', value: detail('actual_amount') ?? subjectAmount.value, type: 'amount' },
      { key: 'payer', label: '实际付款方', value: detail('actual_payer_name') ?? subjectActualPayerName.value },
      { key: 'payment_date', label: '回款日期', value: formatDateValue(detail('payment_date')) },
      { key: 'contract', label: '关联合同', value: detail('contract_name') ?? subjectName.value, type: 'link', linkTarget: 'contract', linkId: detail('contract_id') as number | null },
      { key: 'opportunity', label: '关联商机', value: detail('opportunity_name'), type: 'link', linkTarget: 'opportunity', linkId: detail('opportunity_public_id') },
      { key: 'confirm_status', label: '确认状态', value: paymentConfirmStatusLabel(detail('confirmation_status')?.toString()), type: 'status' },
    ]
    case 'INVOICE': return [
      { key: 'number', label: '申请编号', value: detail('application_number') ?? subjectNumber.value, type: 'copy' },
      customerField,
      { key: 'amount', label: '开票金额', value: detail('invoice_amount') ?? subjectAmount.value, type: 'amount' },
      { key: 'status', label: '发票状态', value: invoiceStatusLabel(detail('status')?.toString()), type: 'status' },
    ]
    case 'INVOICE_REISSUE': return [
      { key: 'number', label: '重开申请编号', value: detail('application_number') ?? subjectNumber.value, type: 'copy' },
      { key: 'original_number', label: '原发票申请', value: detail('original_invoice_application_number'), type: 'link', linkTarget: 'invoice', linkId: getOriginalInvoiceApplicationId(selected) },
      { key: 'reason', label: '重开原因', value: detail('reason') },
      customerField,
      { key: 'status', label: '重开状态', value: invoiceReissueStatusLabel(detail('status')?.toString()), type: 'status' },
    ]
    case 'LICENSE': return [
      { key: 'number', label: '申请编号', value: detail('application_number') ?? subjectNumber.value, type: 'copy' },
      { key: 'type', label: 'License 类型', value: licenseTypeLabel(detail('license_type')?.toString() ?? subjectName.value?.toString()) },
      { key: 'status', label: '签发状态', value: licenseStatusLabel(activeApprovalDetail.value?.license_status ?? selected.license_status), type: 'status' }, customerField,
      { key: 'deployment', label: '部署名称', value: detail('deployment_name') },
      { key: 'users', label: '使用人数', value: detail('authorized_users') },
      { key: 'expiry', label: '到期时间', value: formatDateValue(detail('expiry_date')) },
    ]
    case 'OPPORTUNITY': return [
      { key: 'number', label: '商机编号', value: detail('opportunity_number') ?? subjectNumber.value, type: 'copy' },
      { key: 'name', label: '商机名称', value: detail('opportunity_name') ?? subjectName.value }, customerField,
      { key: 'product', label: '产品', value: detail('product_name') },
      { key: 'amount', label: '预计金额', value: detail('total_amount') ?? subjectAmount.value, type: 'amount' },
      { key: 'stage', label: '当前阶段', value: detail('stage_name') },
      { key: 'status', label: '商机状态', value: opportunityStatusLabel(detail('status')?.toString()), type: 'status' },
    ]
    default: return []
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
  { value: 'CONTRACT_CHANGE', label: '合同变更' },
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
    CONTRACT_CHANGE: '合同变更',
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

const fetchList = async (): Promise<boolean> => {
  const requestId = ++listRequestId.value
  loadError.value = null
  listLoading.value = true
  try {
    const effectiveFilters = activeTab.value === 'pending'
      ? withoutFilterFields(activeFilters.value, ['status'])
      : activeFilters.value
    const query: ApprovalListQuery = {
      tab: activeTab.value,
      page: page.value,
      page_size: pageSize.value,
      ...(search.value.trim() !== '' ? { search: search.value.trim() } : {}),
      ...serializeListQuery({ filters: effectiveFilters, sorts: activeSorts.value })
    }
    const res = await store.fetchList(query)
    if (requestId !== listRequestId.value) return false
    rows.value = res.items
    total.value = res.total
    return true
  } catch (err) {
    if (requestId !== listRequestId.value) return false
    loadError.value = toFeedbackError(err, '审批中心')
    return false
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

const handleSearchApply = (value: string): void => {
  search.value = value.trim()
  page.value = 1
  void fetchList()
}

const handleSearchClear = (): void => {
  search.value = ''
  page.value = 1
  void fetchList()
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

const copyText = async (value: string, successMessage: string): Promise<void> => {
  try {
    if (typeof navigator?.clipboard?.writeText === 'function') {
      await navigator.clipboard.writeText(value)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = value
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      try {
        textarea.select()
        if (!document.execCommand('copy')) throw new Error('Clipboard copy rejected')
      } finally {
        textarea.remove()
      }
    }
    toast.success(successMessage)
  } catch {
    toast.error('复制失败，请手动选择内容复制')
  }
}

const copyNumber = (num: string): Promise<void> => copyText(num, '已复制单号')
const copyInvoiceBillingField = (field: ApprovalInvoiceBillingField): Promise<void> =>
  copyText(field.copyValue, `已复制${field.label}`)
const copyAllInvoiceBilling = (): Promise<void> | undefined => {
  if (invoiceBillingFields.value.length === 0) return
  return copyText(formatApprovalInvoiceBillingCopy(invoiceBillingFields.value), '已复制全部开票信息')
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
let drillTrigger: HTMLElement | null = null

const openDrilldown = (target: ApprovalSubjectLinkTarget, id: string | number): void => {
  if (!sheetVisible.value || !selectedApproval.value || id === '') return
  drillTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
  drillId.value = id
  drillTarget.value = target
  void nextTick(() => {
    drillSurface.value?.querySelector<HTMLElement>('[data-testid="approval-source-back-top"]')?.focus({ preventScroll: true })
  })
}

const hasFieldDrilldown = (field: ApprovalSubjectField): boolean =>
  field.linkTarget !== undefined && field.linkId !== undefined && field.linkId !== null && field.linkId !== ''

const openFieldDrilldown = (field: ApprovalSubjectField): void => {
  if (field.linkTarget === undefined || field.linkId === undefined || field.linkId === null) return
  openDrilldown(field.linkTarget, field.linkId)
}

const closeDrilldown = (): void => {
  const trigger = drillTrigger
  drillTarget.value = null
  drillId.value = null
  drillTrigger = null
  void nextTick(() => {
    if (sheetVisible.value && trigger?.isConnected === true) trigger.focus({ preventScroll: true })
  })
}

const handleDrillVisibleChange = (visible: boolean): void => {
  if (!visible) closeDrilldown()
}

watch([sheetVisible, (): number | undefined => selectedApproval.value?.id], (): void => {
  drillTarget.value = null
  drillId.value = null
  drillTrigger = null
})

const openDetail = (row: ApprovalListItem, index?: number): void => {
  const rowIndex = index ?? rows.value.findIndex(r => r.id === row.id)
  selectedApproval.value = row
  triggerRowIndex.value = rowIndex
  focusedRowEl.value = getDetailTrigger(rowIndex)
  sheetVisible.value = true
}

watch(sheetVisible, (open): void => {
  if (!open) void nextTick(onSheetClosed)
})

const restoreListFocus = (event: Event): void => {
  event.preventDefault()
  getDetailTrigger(triggerRowIndex.value)?.focus({ preventScroll: true })
}

const onSheetClosed = (): void => {
  closeDrilldown()
  const target = focusedRowEl.value?.isConnected === true ? focusedRowEl.value : getDetailTrigger(triggerRowIndex.value)
  target?.focus({ preventScroll: true })
  selectedApproval.value = null
  store.clearDetail()
  markIssuedDialogVisible.value = false
  reissueCompleteDialogVisible.value = false
  licenseIssueDialogVisible.value = false
  // Keep the list index until the dialog finishes its close-focus lifecycle.
}

const onApprovalActionDone = async (): Promise<void> => {
  // 审批完成（同意/驳回/撤回/提交）后刷新列表 + 关抽屉
  sheetVisible.value = false
  const refreshed = await fetchList()
  if (!refreshed) {
    toast.warning('审批操作已提交，但列表刷新失败，请稍后重试。')
  }
}

const handleInvoiceFileUploaded = async (): Promise<void> => {
  markIssuedDialogVisible.value = false
  sheetVisible.value = false
  const refreshed = await fetchList()
  if (!refreshed) {
    toast.warning('发票操作已完成，但审批列表刷新失败，请稍后重试。')
  }
}

const handleInvoiceReissueCompleted = async (): Promise<void> => {
  reissueCompleteDialogVisible.value = false
  sheetVisible.value = false
  const refreshed = await fetchList()
  if (!refreshed) {
    toast.warning('发票重开已完成，但审批列表刷新失败，请稍后重试。')
  }
}

const handleLicenseIssued = async (): Promise<void> => {
  licenseIssueDialogVisible.value = false
  sheetVisible.value = false
  const refreshed = await fetchList()
  if (!refreshed) {
    toast.warning('License 发放已完成，但审批列表刷新失败，请稍后重试。')
  }
}

// 条4：REJECTED 行修改并重新提交。
// 合同、发票在审批中心内打开既有编辑弹窗；其他业务仍进入对应业务页面处理。
const handleResubmit = async (row: ApprovalListItem): Promise<void> => {
  if (row.business_type === 'CONTRACT_CHANGE') return
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
    const route: Record<Exclude<EntityType, 'CONTRACT' | 'CONTRACT_CHANGE' | 'INVOICE' | 'INVOICE_REISSUE'>, string | ReturnType<typeof customerDetailRoute>> = {
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
    const target = route[row.business_type as Exclude<EntityType, 'CONTRACT' | 'CONTRACT_CHANGE' | 'INVOICE' | 'INVOICE_REISSUE'>]
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
const handleContractEditSuccess = async (): Promise<void> => {
  contractEditVisible.value = false
  editingContract.value = null
  const refreshed = await fetchList()
  toast.success('合同已修改，请重新提交审批', refreshed ? undefined : {
    description: '合同已修改，但审批列表刷新失败，请稍后重试。',
  })
}

const handleInvoiceEditDialogOpenChange = (open: boolean): void => {
  invoiceEditDialogVisible.value = open
  if (!open) {
    editingInvoiceApplication.value = null
  }
}

const handleInvoiceEditSuccess = async (): Promise<void> => {
  invoiceEditDialogVisible.value = false
  editingInvoiceApplication.value = null
  sheetVisible.value = false
  const refreshed = await fetchList()
  toast.success('发票申请已修改，请重新提交审批', refreshed ? undefined : {
    description: '发票申请已修改，但审批列表刷新失败，请稍后重试。',
  })
}

const handleInvoiceDetailSheetVisibleChange = (visible: boolean): void => {
  invoiceDetailSheetVisible.value = visible
  if (!visible) {
    selectedInvoiceDetailId.value = null
  }
}

const handleInvoiceDetailRefresh = async (): Promise<void> => {
  const refreshed = await fetchList()
  if (!refreshed) {
    toast.warning('发票详情已更新，但审批列表刷新失败，请稍后重试。')
  }
}

const getOriginalInvoiceApplicationId = (row: ApprovalListItem): number | null => {
  const listValue = row.original_invoice_application_id
  if (typeof listValue === 'number') return listValue

  const detailValue = activeApprovalDetail.value?.entity_detail?.['original_invoice_application_id']
  return typeof detailValue === 'number' ? detailValue : null
}

const handleRemind = async (row: ApprovalListItem): Promise<void> => {
  if (remindPendingId.value === row.id) return
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

const handleSelectedAttachmentPreview = (file: FileAttachmentItem): void => {
  const row = selectedAttachmentRow.value
  if (row === null || file.id !== row.business_id) return
  void handlePreviewAttachment(row)
}

const handleSelectedAttachmentDownload = (file: FileAttachmentItem): void => {
  const row = selectedAttachmentRow.value
  if (row === null || file.id !== row.business_id) return
  attachmentPreviewRow.value = row
  void handleDownloadAttachment()
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
      id: 'detail',
      label: '查看详情',
      kind: 'detail',
      handler: () => openDetail(row)
    }
  ]
  if (hasAttachment(row)) {
    primaryActions.push({
      id: 'preview',
      label: '预览',
      desktopPrimary: true,
      handler: () => { void handlePreviewAttachment(row) },
      disabled: attachmentPreviewPendingId.value === row.id,
      disabledReason: attachmentPreviewPendingId.value === row.id ? '预览处理中' : undefined,
      resultType: 'none'
    })
  }
  if (activeTab.value === 'submitted' && row.status === 'REJECTED' && row.business_type !== 'CONTRACT_CHANGE') {
    primaryActions.push({
      id: 'resubmit',
      label: '修改并重新提交',
      desktopPrimary: true,
      handler: () => { void handleResubmit(row) },
      disabled: resubmitPendingId.value === row.id,
      disabledReason: resubmitPendingId.value === row.id ? '提交处理中' : undefined,
      risk: 'approval',
      resultType: 'status-changed'
    })
  }
  if (activeTab.value === 'submitted' && row.status === 'PENDING') {
    primaryActions.push({
      id: 'remind',
      label: '催办',
      desktopPrimary: true,
      icon: BellRing,
      handler: () => { void handleRemind(row) },
      disabled: remindPendingId.value === row.id,
      disabledReason: remindPendingId.value === row.id ? '催办处理中' : undefined,
      risk: 'approval',
      resultType: 'none'
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
    const refreshed = await fetchList()
    toast.success('已同意', refreshed ? undefined : {
      description: '审批已同意，但列表刷新失败，请稍后重试。',
    })
    // 刷新列表（移除该行）
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
    quickRejectVisible.value = false
    quickRejectRow.value = null
    quickRejectReason.value = ''
    quickRejectReasonError.value = ''
    quickActionError.value = null
    const refreshed = await fetchList()
    toast.success('已驳回，申请人可修改后重新提交', refreshed ? undefined : {
      description: '审批已驳回，但列表刷新失败，请稍后重试。',
    })
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
.billing-copy-value {
  max-width: 100%;
  padding: 2px 0;
  color: hsl(var(--primary));
  text-align: left;
  font-size: 0.875rem;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  text-decoration-line: underline;
  text-decoration-style: dashed;
  text-decoration-color: hsl(var(--primary) / 0.35);
  text-underline-offset: 5px;
  border-radius: 2px;

  &:hover { background: hsl(var(--primary) / 0.05); }
  &:focus-visible { outline: 2px solid hsl(var(--ring)); outline-offset: 3px; }
}

.billing-copy-amount {
  text-decoration: inherit;
  text-underline-offset: inherit;
}
</style>
