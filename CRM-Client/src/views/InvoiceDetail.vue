<template>
  <div class="invoice-detail-container">
    <div v-loading="loading" class="invoice-content">
      <div v-if="!invoiceInfo" class="invoice-info-card">
        <el-empty description="发票信息加载失败" />
      </div>

      <div v-else class="invoice-info-card">
        <div class="invoice-basic-info">
          <div class="info-top">
            <div class="info-left">
              <div class="invoice-title-section">
                <div class="invoice-avatar">{{ invoiceInfo?.application_number?.charAt(0) || '发' }}</div>
                <div class="invoice-title-content">
                  <h2 class="invoice-name">{{ invoiceInfo?.application_number }}</h2>
                  <div class="invoice-tags">
                    <el-tag :class="['wolf-tag', getStatusTagClass(invoiceInfo?.status)]" size="small">
                      {{ getStatusText(invoiceInfo?.status) }}
                    </el-tag>
                    <el-tag :class="['wolf-tag', 'wolf-tag--purple']" size="small">
                      {{ getInvoiceTypeText(invoiceInfo?.invoice_type) }}
                    </el-tag>
                  </div>
                </div>
              </div>
            </div>

            <div class="info-right">
              <div class="amount-section">
                <div class="amount-label">开票金额</div>
                <div class="amount-value">¥{{ formatAmount(invoiceInfo?.invoice_amount || '0') }}</div>
              </div>
            </div>
          </div>

          <div class="info-divider"></div>

          <div class="info-bottom">
            <div class="attributes-grid">
              <div class="attribute-item">
                <div class="attribute-header">
                  <el-icon class="attribute-icon"><User /></el-icon>
                  <span class="attribute-label">客户名称</span>
                </div>
                <span class="attribute-value">{{ invoiceInfo?.customer_name || '-' }}</span>
              </div>
              <div class="attribute-item">
                <div class="attribute-header">
                  <el-icon class="attribute-icon"><Document /></el-icon>
                  <span class="attribute-label">关联合同</span>
                </div>
                <span class="attribute-value">{{ invoiceInfo?.contract_name || '-' }}</span>
              </div>
              <div class="attribute-item">
                <div class="attribute-header">
                  <el-icon class="attribute-icon"><Clock /></el-icon>
                  <span class="attribute-label">回款阶段</span>
                </div>
                <span class="attribute-value">{{ invoiceInfo?.payment_plan_stage_name || '-' }}</span>
              </div>
              <div class="attribute-item">
                <div class="attribute-header">
                  <el-icon class="attribute-icon"><Avatar /></el-icon>
                  <span class="attribute-label">申请人</span>
                </div>
                <span class="attribute-value">{{ invoiceInfo?.applicant_name || '-' }}</span>
              </div>
              <div class="attribute-item">
                <div class="attribute-header">
                  <el-icon class="attribute-icon"><Calendar /></el-icon>
                  <span class="attribute-label">申请时间</span>
                </div>
                <span class="attribute-value secondary">{{ formatDateTime(invoiceInfo?.created_time) }}</span>
              </div>
              <div class="attribute-item">
                <div class="attribute-header">
                  <el-icon class="attribute-icon"><Avatar /></el-icon>
                  <span class="attribute-label">审批人</span>
                </div>
                <span class="attribute-value" :class="{ 'not-filled': !invoiceInfo?.reviewer_name }">{{ invoiceInfo?.reviewer_name || '-' }}</span>
              </div>
              <div class="attribute-item" v-if="invoiceInfo?.invoice_number">
                <div class="attribute-header">
                  <el-icon class="attribute-icon"><Ticket /></el-icon>
                  <span class="attribute-label">发票号码</span>
                </div>
                <span class="attribute-value">{{ invoiceInfo?.invoice_number }}</span>
              </div>
              <div class="attribute-item" v-if="invoiceInfo?.reviewed_time">
                <div class="attribute-header">
                  <el-icon class="attribute-icon"><Calendar /></el-icon>
                  <span class="attribute-label">审批时间</span>
                </div>
                <span class="attribute-value secondary">{{ formatDateTime(invoiceInfo?.reviewed_time) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="core-section">
        <div class="invoice-title-section-card section-card">
          <div class="card-header">
            <span class="card-title">开票抬头信息</span>
          </div>
          <div class="invoice-title-content-detail">
            <div class="attributes-grid">
                <div class="attribute-item">
                  <div class="attribute-header">
                    <el-icon class="attribute-icon"><OfficeBuilding /></el-icon>
                    <span class="attribute-label">抬头类型</span>
                  </div>
                  <el-tag :class="['wolf-tag', invoiceInfo?.invoice_title_type === 'COMPANY' ? 'wolf-tag--info' : 'wolf-tag--gray']" size="small">
                    {{ invoiceInfo?.invoice_title_type === 'COMPANY' ? '单位' : '个人' }}
                  </el-tag>
                </div>
                <div class="attribute-item">
                  <div class="attribute-header">
                    <el-icon class="attribute-icon"><Document /></el-icon>
                    <span class="attribute-label">开票抬头</span>
                  </div>
                  <span class="attribute-value">{{ invoiceInfo?.invoice_title_text || '-' }}</span>
                </div>
                <div class="attribute-item">
                  <div class="attribute-header">
                    <el-icon class="attribute-icon"><Key /></el-icon>
                    <span class="attribute-label">纳税人识别号</span>
                  </div>
                  <span class="attribute-value">{{ invoiceInfo?.invoice_taxpayer_id || '-' }}</span>
                </div>
                <div class="attribute-item">
                  <div class="attribute-header">
                    <el-icon class="attribute-icon"><CreditCard /></el-icon>
                    <span class="attribute-label">开户行</span>
                  </div>
                  <span class="attribute-value" :class="{ 'not-filled': !invoiceInfo?.invoice_bank_name }">{{ invoiceInfo?.invoice_bank_name || '-' }}</span>
                </div>
                <div class="attribute-item">
                  <div class="attribute-header">
                    <el-icon class="attribute-icon"><Wallet /></el-icon>
                    <span class="attribute-label">开户账号</span>
                  </div>
                  <span class="attribute-value" :class="{ 'not-filled': !invoiceInfo?.invoice_bank_account }">{{ invoiceInfo?.invoice_bank_account || '-' }}</span>
                </div>
                <div class="attribute-item">
                  <div class="attribute-header">
                    <el-icon class="attribute-icon"><Location /></el-icon>
                    <span class="attribute-label">开票地址</span>
                  </div>
                  <span class="attribute-value" :class="{ 'not-filled': !invoiceInfo?.invoice_address }">{{ invoiceInfo?.invoice_address || '-' }}</span>
                </div>
                <div class="attribute-item">
                  <div class="attribute-header">
                    <el-icon class="attribute-icon"><Phone /></el-icon>
                    <span class="attribute-label">电话</span>
                  </div>
                  <span class="attribute-value" :class="{ 'not-filled': !invoiceInfo?.invoice_phone }">{{ invoiceInfo?.invoice_phone || '-' }}</span>
                </div>
              </div>
          </div>
        </div>

        <div class="approval-section section-card">
          <div class="card-header">
            <span class="card-title">审批进度</span>
          </div>
          <!-- Phase C / Task C3：嵌入通用审批组件 ApprovalProcessGeneric，
               取代原合同专属 ApprovalProcess 的硬编码 timeline。
               canApprove/isSubmitter 由当前发票状态 + 权限 + 申请人 ID 推导。 -->
          <ApprovalProcessGeneric
            v-if="invoiceInfo"
            :entity-type="invoiceEntityType"
            :entity-id="invoiceInfo.id"
            :can-approve="canApproveGeneric"
            :is-submitter="isSubmitterGeneric"
            @submitted="fetchInvoiceDetail"
            @approved="fetchInvoiceDetail"
            @rejected="fetchInvoiceDetail"
            @withdrawn="fetchInvoiceDetail"
            @uploaded="fetchInvoiceDetail"
          />
        </div>

        <!-- Task 6: 已上传发票文件显示 -->
        <div v-if="invoiceInfo?.invoice_file_path" class="invoice-file-section section-card">
          <div class="card-header">
            <span class="card-title">发票文件</span>
          </div>
          <div class="file-info">
            <el-icon class="file-icon"><Document /></el-icon>
            <span v-if="invoiceInfo?.invoice_number" class="invoice-number">
              发票号码：{{ invoiceInfo.invoice_number }}
            </span>
            <el-button link type="primary" size="small" @click="downloadInvoiceFile">
              <el-icon><Download /></el-icon>
              下载发票文件
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="invoicedModalVisible" title="标记开票" width="480px" :close-on-click-modal="false" class="wolf-modal">
      <el-form :model="invoicedForm" label-position="top">
        <el-form-item label="发票号码" required>
          <el-input v-model="invoicedForm.invoice_number" placeholder="请输入发票号码" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button class="wolf-btn wolf-btn--default" @click="invoicedModalVisible = false">取消</el-button>
        <el-button type="primary" class="wolf-btn wolf-btn--primary" @click="handleConfirmInvoiced" :loading="marking">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { showError, showSuccess } from '@/utils/errorMessages'
import {
  User,
  Document,
  Clock,
  Avatar,
  Calendar,
  Ticket,
  OfficeBuilding,
  Key,
  CreditCard,
  Wallet,
  Location,
  Phone,
  Download
} from '@element-plus/icons-vue'
import invoiceApi, { type InvoiceApplicationResponse } from '@/api/invoice'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'
import ApprovalProcessGeneric from '@/components/ApprovalProcessGeneric.vue'
import { logger } from '@/utils/logger'
import { usePageTitle } from '@/composables/usePageTitle'
import { useHeaderStore } from '@/stores/header'
import { getInvoiceFileUrl } from '@/api/fileUpload'

const { setTitle } = usePageTitle()

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const permissionStore = usePermissionStore()
const headerStore = useHeaderStore()

const currentUserId = computed<string>(() => userStore.userInfo?.id != null ? String(userStore.userInfo.id) : '')

// 通用审批组件入参（Phase C / Task C3）
const invoiceEntityType = 'INVOICE' as const
const isSubmitterGeneric = computed<boolean>(() =>
  invoiceInfo.value?.applicant_id === currentUserId.value
)
// canApproveGeneric：发票处于待审批状态 + 当前用户持有 invoice:approve
// （草稿/已通过/已驳回/已开票态不再展示同意/驳回按钮，由 ApprovalProcessGeneric 内部按 detail.status 处理）
const canApproveGeneric = computed<boolean>(() =>
  invoiceInfo.value?.status === 'PENDING_REVIEW' &&
  permissionStore.hasPermission('invoice:approve')
)

const invoiceInfo = ref<InvoiceApplicationResponse | null>(null)
const loading = ref(false)
const marking = ref(false)
const invoicedModalVisible = ref(false)

const invoicedForm = ref({
  invoice_number: ''
})

const canEdit = computed<boolean>(() => {
  if (!invoiceInfo.value) return false
  const status = invoiceInfo.value.status
  return (status === 'DRAFT' || status === 'REJECTED') &&
         invoiceInfo.value.applicant_id === currentUserId.value
})

const canDelete = computed<boolean>(() => {
  if (!invoiceInfo.value) return false
  const status = invoiceInfo.value.status
  return (status === 'DRAFT' || status === 'REJECTED') &&
         invoiceInfo.value.applicant_id === currentUserId.value
})

const canMarkInvoiced = computed<boolean>(() => {
  return invoiceInfo.value?.status === 'APPROVED'
})

const getStatusTagClass = (status: string | undefined): string => {
  const statusMap: Record<string, string> = {
    'DRAFT': 'wolf-tag--gray',
    'PENDING_REVIEW': 'wolf-tag--warning',
    'APPROVED': 'wolf-tag--success',
    'REJECTED': 'wolf-tag--danger',
    'ISSUED': 'wolf-tag--primary'
  }
  return statusMap[status ?? ''] ?? 'wolf-tag--gray'
}

const getStatusText = (status: string | undefined): string => {
  const statusMap: Record<string, string> = {
    'DRAFT': '草稿',
    'PENDING_REVIEW': '待审批',
    'APPROVED': '已批准',
    'REJECTED': '已拒绝',
    'ISSUED': '已开票'
  }
  return statusMap[status ?? ''] ?? '未知'
}

const getInvoiceTypeText = (type: string | undefined): string => {
  const typeMap: Record<string, string> = {
    'VAT_SPECIAL': '增值税专用发票',
    'VAT_NORMAL': '普通发票'
  }
  return typeMap[type ?? ''] ?? type ?? '未知'
}

const fetchInvoiceDetail = async (): Promise<void> => {
  const invoiceId = route.params.id as string
  loading.value = true
  try {
    const data = await invoiceApi.getInvoiceApplication(Number(invoiceId))
    invoiceInfo.value = data
    // 设置动态标题
    setTitle(data.application_number || '发票申请详情')
  } catch (error) {
    logger.error('[InvoiceDetail]', '获取发票申请详情失败', { error })
    showError(error, '获取发票申请详情')
  } finally {
    loading.value = false
  }
}

const handleEdit = (): void => {
  if (invoiceInfo.value) {
    router.push(`/invoices/edit/${invoiceInfo.value.id}`)
  }
}

const handleDelete = async (): Promise<void> => {
  if (!invoiceInfo.value) return

  try {
    await ElMessageBox.confirm(
      `确定要删除发票申请"${invoiceInfo.value.application_number}"吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    await invoiceApi.deleteInvoiceApplication(invoiceInfo.value.id)
    showSuccess('删除', '发票申请')
    router.push('/invoices')
  } catch (error: unknown) {
    if (error !== 'cancel') {
      logger.error('[InvoiceDetail]', '删除失败', { error })
      showError(error, '删除发票申请')
    }
  }
}

const handleMarkInvoiced = (): void => {
  invoicedModalVisible.value = true
}

const handleConfirmInvoiced = async (): Promise<void> => {
  if (invoicedForm.value.invoice_number.trim().length === 0) {
    ElMessage.warning('请输入发票号码')
    return
  }

  if (!invoiceInfo.value) return

  try {
    marking.value = true
    await invoiceApi.markAsInvoiced(invoiceInfo.value.id, invoicedForm.value.invoice_number)
    showSuccess('标记开票', '发票申请')
    invoicedModalVisible.value = false
    invoicedForm.value.invoice_number = ''
    fetchInvoiceDetail()
  } catch (error) {
    logger.error('[InvoiceDetail]', '标记开票失败', { error })
    showError(error, '标记开票')
  } finally {
    marking.value = false
  }
}

const formatAmount = (amount: number | string): string => {
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const formatDateTime = (dateStr: string | undefined): string => {
  if (dateStr === undefined || dateStr.length === 0) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// Task 6: 发票文件下载
const downloadInvoiceFile = (): void => {
  if (!invoiceInfo.value) return
  const url = getInvoiceFileUrl(invoiceInfo.value.id)
  window.open(url, '_blank')
}

// Configure header on mount
onMounted(() => {
  headerStore.setBack(true)
  fetchInvoiceDetail()
})

// Watch invoiceInfo to update actions
watch(invoiceInfo, () => {
  const actions: Array<{ id: string; label: string; type?: 'primary' | 'success' | 'danger' | 'default'; handler: () => void }> = []

  if (canEdit.value) {
    actions.push({ id: 'edit', label: '编辑', type: 'primary', handler: handleEdit })
  }
  if (canDelete.value) {
    actions.push({ id: 'delete', label: '删除', type: 'danger', handler: handleDelete })
  }
  if (canMarkInvoiced.value) {
    actions.push({ id: 'mark-invoiced', label: '标记开票', type: 'primary', handler: handleMarkInvoiced })
  }

  headerStore.setActions(actions)
}, { immediate: true })

// Clear header on unmount
onUnmounted(() => {
  headerStore.clear()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.invoice-detail-container {
  padding: 0;
  min-height: calc(100vh - 48px);
  background: $wolf-bg-page;
}

.invoice-content {
  padding: $wolf-page-padding;
  display: flex;
  flex-direction: column;
  gap: $wolf-section-gap;
}

.invoice-info-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-card-padding;
  box-shadow: $wolf-shadow-card;
}

.invoice-basic-info {
  padding: 0;
}

.info-top {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: $wolf-space-lg;
  margin-bottom: 0;
}

.info-left {
  .invoice-title-section {
    display: flex;
    gap: $wolf-card-padding;
    align-items: flex-start;
  }

  .invoice-avatar {
    width: 48px;
    height: 48px;
    border-radius: $wolf-radius-full;
    background: $wolf-primary;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    font-weight: $wolf-font-weight-semibold;
    color: $wolf-text-inverse;
    flex-shrink: 0;
  }

  .invoice-title-content {
    flex: 1;

    .invoice-name {
      margin: 0 0 $wolf-space-sm 0;
      font-size: $wolf-font-size-body;
      font-weight: $wolf-font-weight-semibold;
      color: $wolf-text-primary;
      line-height: $wolf-line-height-title;
    }

    .invoice-tags {
      display: flex;
      gap: $wolf-space-sm;
      flex-wrap: wrap;
    }
  }
}

.info-divider {
  height: 1px;
  background: $wolf-border-divider;
  margin: $wolf-space-lg 0;
}

.info-bottom {
  .attributes-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: $wolf-card-padding $wolf-space-lg;
  }

  .attribute-item {
    display: flex;
    flex-direction: column;
    gap: $wolf-space-xs;
  }

  .attribute-header {
    display: flex;
    align-items: center;
    gap: $wolf-space-xs;
  }

  .attribute-icon {
    font-size: 14px;
    color: $wolf-text-tertiary;
    flex-shrink: 0;
  }

  .attribute-label {
    font-size: $wolf-font-size-caption;
    color: $wolf-text-tertiary;
    font-weight: $wolf-font-weight-normal;
  }

  .attribute-value {
    font-size: $wolf-font-size-body;
    color: $wolf-text-primary;
    font-weight: $wolf-font-weight-medium;
    line-height: $wolf-line-height-body;

    &.secondary {
      color: $wolf-text-secondary;
    }

    &.not-filled {
      color: $wolf-text-placeholder;
    }
  }
}

.info-right {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: flex-end;
  gap: $wolf-card-padding;

  .amount-section {
    text-align: right;

    .amount-label {
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
      margin-bottom: $wolf-space-xs;
      font-weight: $wolf-font-weight-normal;
    }

    .amount-value {
      font-size: 24px;
      font-weight: $wolf-font-weight-semibold;
      color: $wolf-primary;
      line-height: $wolf-line-height-title;
    }
  }
}

.core-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $wolf-section-gap;
}

.section-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-card-padding;
  box-shadow: $wolf-shadow-card;
  min-height: 300px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: $wolf-space-md;
}

.card-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
}

.invoice-title-content-detail {
  .attributes-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: $wolf-card-padding $wolf-space-lg;
  }

  .attribute-item {
    display: flex;
    flex-direction: column;
    gap: $wolf-space-xs;
  }

  .attribute-header {
    display: flex;
    align-items: center;
    gap: $wolf-space-xs;
  }

  .attribute-icon {
    font-size: 14px;
    color: $wolf-text-tertiary;
    flex-shrink: 0;
  }

  .attribute-label {
    font-size: $wolf-font-size-caption;
    color: $wolf-text-tertiary;
    font-weight: $wolf-font-weight-normal;
  }

  .attribute-value {
    font-size: $wolf-font-size-body;
    color: $wolf-text-primary;
    font-weight: $wolf-font-weight-medium;
    line-height: $wolf-line-height-body;

    &.not-filled {
      color: $wolf-text-placeholder;
    }
  }
}

.approval-timeline {
  padding: $wolf-space-sm 0;
}

.wolf-timeline {
  position: relative;
}

.wolf-timeline__item {
  position: relative;
  padding-left: 40px;
  padding-bottom: $wolf-space-lg;
}

.wolf-timeline__item:last-child {
  padding-bottom: 0;
}

.wolf-timeline__line {
  position: absolute;
  left: 15px;
  top: 32px;
  bottom: 0;
  width: 2px;
  background: $wolf-border-default;
}

.wolf-timeline__item:last-child .wolf-timeline__line {
  display: none;
}

.wolf-timeline__dot {
  position: absolute;
  left: 0;
  top: 2px;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 14px;
  font-weight: $wolf-font-weight-medium;
}

.wolf-timeline__dot--primary {
  background-color: $wolf-primary;
}

.wolf-timeline__dot--success {
  background-color: $wolf-success-text;
}

.wolf-timeline__dot--info {
  background-color: $wolf-info;
}

.wolf-timeline__dot--danger {
  background-color: $wolf-danger-text;
}

.wolf-timeline__dot--gray {
  background-color: $wolf-purple;
}

.wolf-timeline__content {
  padding-top: $wolf-space-xs;
}

.wolf-timeline__header {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  margin-bottom: $wolf-space-xs;
}

.wolf-timeline__title {
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
  font-size: $wolf-font-size-body;
}

.wolf-timeline__meta {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  font-size: $wolf-font-size-auxiliary;
  color: $wolf-text-tertiary;
}

.wolf-timeline__result {
  margin-top: $wolf-space-sm;
}

.wolf-tag {
  border-radius: $wolf-radius-sm !important;
  padding: 2px 8px !important;
  font-size: $wolf-font-size-caption !important;
  font-weight: $wolf-font-weight-medium !important;
  height: auto !important;
  line-height: 1.5 !important;
  border-width: 1px !important;
}

.wolf-tag--primary {
  background-color: $wolf-info-bg !important;
  border-color: $wolf-info-border !important;
  color: $wolf-info !important;
}

.wolf-tag--success {
  background-color: $wolf-success-bg !important;
  border-color: $wolf-success-border !important;
  color: $wolf-success-text !important;
}

.wolf-tag--warning {
  background-color: $wolf-warning-bg !important;
  border-color: $wolf-warning-border !important;
  color: $wolf-warning-text !important;
}

.wolf-tag--danger {
  background-color: $wolf-danger-bg !important;
  border-color: $wolf-danger-border !important;
  color: $wolf-danger-text !important;
}

.wolf-tag--gray {
  background-color: $wolf-purple-bg !important;
  border-color: $wolf-purple-border !important;
  color: $wolf-purple !important;
}

.wolf-tag--purple {
  background-color: $wolf-purple-bg !important;
  border-color: $wolf-purple-border !important;
  color: $wolf-purple !important;
}

.wolf-tag--info {
  background-color: $wolf-info-bg !important;
  border-color: $wolf-info-border !important;
  color: $wolf-info !important;
}

// Task 6: 发票文件显示区域样式
.invoice-file-section {
  .file-info {
    display: flex;
    align-items: center;
    gap: $wolf-space-md;
    padding: $wolf-space-md;
    background: $wolf-bg-hover;
    border-radius: $wolf-radius-sm;
  }

  .file-icon {
    font-size: 24px;
    color: $wolf-primary;
  }

  .invoice-number {
    font-size: $wolf-font-size-body;
    color: $wolf-text-secondary;
    font-weight: $wolf-font-weight-medium;
  }
}

@media (max-width: 1200px) {
  .info-top {
    grid-template-columns: 1fr;
  }

  .info-left {
    .invoice-title-section {
      flex-direction: column;
      text-align: center;
    }
  }

  .info-right {
    align-items: center;

    .amount-section {
      text-align: center;
    }
  }

  .info-bottom {
    .attributes-grid {
      grid-template-columns: repeat(2, 1fr);
    }
  }

  .core-section {
    grid-template-columns: 1fr;
  }

  .invoice-title-content-detail {
    .attributes-grid {
      grid-template-columns: 1fr;
    }
  }
}

@media (max-width: 768px) {
  .info-bottom {
    .attributes-grid {
      grid-template-columns: 1fr;
    }
  }
}
</style>
