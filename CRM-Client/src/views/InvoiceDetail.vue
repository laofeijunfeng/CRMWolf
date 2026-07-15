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
                  <User aria-hidden="true" class="attribute-icon w-3.5 h-3.5" />
                  <span class="attribute-label">客户名称</span>
                </div>
                <span class="attribute-value">{{ invoiceInfo?.customer_name || '-' }}</span>
              </div>
              <div class="attribute-item">
                <div class="attribute-header">
                  <FileText aria-hidden="true" class="attribute-icon w-3.5 h-3.5" />
                  <span class="attribute-label">关联合同</span>
                </div>
                <span class="attribute-value">{{ invoiceInfo?.contract_name || '-' }}</span>
              </div>
              <div class="attribute-item">
                <div class="attribute-header">
                  <Clock aria-hidden="true" class="attribute-icon w-3.5 h-3.5" />
                  <span class="attribute-label">回款阶段</span>
                </div>
                <span class="attribute-value">{{ invoiceInfo?.payment_plan_stage_name || '-' }}</span>
              </div>
              <div class="attribute-item">
                <div class="attribute-header">
                  <UserCircle aria-hidden="true" class="attribute-icon w-3.5 h-3.5" />
                  <span class="attribute-label">申请人</span>
                </div>
                <span class="attribute-value">{{ invoiceInfo?.applicant_name || '-' }}</span>
              </div>
              <div class="attribute-item">
                <div class="attribute-header">
                  <Calendar aria-hidden="true" class="attribute-icon w-3.5 h-3.5" />
                  <span class="attribute-label">申请时间</span>
                </div>
                <span class="attribute-value secondary">{{ formatDateTime(invoiceInfo?.created_time) }}</span>
              </div>
              <div class="attribute-item">
                <div class="attribute-header">
                  <UserCircle aria-hidden="true" class="attribute-icon w-3.5 h-3.5" />
                  <span class="attribute-label">审批人</span>
                </div>
                <span class="attribute-value" :class="{ 'not-filled': !invoiceInfo?.reviewer_name }">{{ invoiceInfo?.reviewer_name || '-' }}</span>
              </div>
              <div class="attribute-item" v-if="invoiceInfo?.invoice_number">
                <div class="attribute-header">
                  <Ticket aria-hidden="true" class="attribute-icon w-3.5 h-3.5" />
                  <span class="attribute-label">发票号码</span>
                </div>
                <span class="attribute-value">{{ invoiceInfo?.invoice_number }}</span>
              </div>
              <div class="attribute-item" v-if="invoiceInfo?.reviewed_time">
                <div class="attribute-header">
                  <Calendar aria-hidden="true" class="attribute-icon w-3.5 h-3.5" />
                  <span class="attribute-label">审批时间</span>
                </div>
                <span class="attribute-value secondary">{{ formatDateTime(invoiceInfo?.reviewed_time) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ISSUED 状态专属：已开票文件高亮区域 -->
      <div
        v-if="invoiceInfo?.status === 'ISSUED' && invoiceInfo?.invoice_file_path"
        class="issued-file-highlight"
      >
        <div class="highlight-header">
          <CheckCircle2 aria-hidden="true" class="success-icon w-5 h-5" />
          <span class="highlight-title">已开票</span>
          <span v-if="invoiceInfo?.invoice_number" class="invoice-number-badge">
            {{ invoiceInfo.invoice_number }}
          </span>
        </div>
        <div class="file-download-area">
          <FileText
            v-if="isPdf(invoiceInfo.invoice_file_path)"
            aria-hidden="true"
            :class="['file-type-icon', getFileIconClass(invoiceInfo.invoice_file_path), 'w-5 h-5']"
          />
          <Image
            v-else
            aria-hidden="true"
            :class="['file-type-icon', getFileIconClass(invoiceInfo.invoice_file_path), 'w-5 h-5']"
          />
          <span class="file-type-label">{{ getFileTypeLabel(invoiceInfo.invoice_file_path) }}</span>
          <Button
            class="download-btn"
            aria-label="下载发票文件"
            @click="handleDownloadWithFeedback"
          >
            <Download class="w-4 h-4" aria-hidden="true" />
            下载发票文件
          </Button>
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
                    <Building2 aria-hidden="true" class="attribute-icon w-3.5 h-3.5" />
                    <span class="attribute-label">抬头类型</span>
                  </div>
                  <el-tag :class="['wolf-tag', invoiceInfo?.invoice_title_type === 'COMPANY' ? 'wolf-tag--info' : 'wolf-tag--gray']" size="small">
                    {{ invoiceInfo?.invoice_title_type === 'COMPANY' ? '单位' : '个人' }}
                  </el-tag>
                </div>
                <div class="attribute-item">
                  <div class="attribute-header">
                    <FileText aria-hidden="true" class="attribute-icon w-3.5 h-3.5" />
                    <span class="attribute-label">开票抬头</span>
                  </div>
                  <span class="attribute-value">{{ invoiceInfo?.invoice_title_text || '-' }}</span>
                </div>
                <div class="attribute-item">
                  <div class="attribute-header">
                    <Key aria-hidden="true" class="attribute-icon w-3.5 h-3.5" />
                    <span class="attribute-label">纳税人识别号</span>
                  </div>
                  <span class="attribute-value">{{ invoiceInfo?.invoice_taxpayer_id || '-' }}</span>
                </div>
                <div class="attribute-item">
                  <div class="attribute-header">
                    <CreditCard aria-hidden="true" class="attribute-icon w-3.5 h-3.5" />
                    <span class="attribute-label">开户行</span>
                  </div>
                  <span class="attribute-value" :class="{ 'not-filled': !invoiceInfo?.invoice_bank_name }">{{ invoiceInfo?.invoice_bank_name || '-' }}</span>
                </div>
                <div class="attribute-item">
                  <div class="attribute-header">
                    <Wallet aria-hidden="true" class="attribute-icon w-3.5 h-3.5" />
                    <span class="attribute-label">开户账号</span>
                  </div>
                  <span class="attribute-value" :class="{ 'not-filled': !invoiceInfo?.invoice_bank_account }">{{ invoiceInfo?.invoice_bank_account || '-' }}</span>
                </div>
                <div class="attribute-item">
                  <div class="attribute-header">
                    <MapPin aria-hidden="true" class="attribute-icon w-3.5 h-3.5" />
                    <span class="attribute-label">开票地址</span>
                  </div>
                  <span class="attribute-value" :class="{ 'not-filled': !invoiceInfo?.invoice_address }">{{ invoiceInfo?.invoice_address || '-' }}</span>
                </div>
                <div class="attribute-item">
                  <div class="attribute-header">
                    <Phone aria-hidden="true" class="attribute-icon w-3.5 h-3.5" />
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
            <FileText aria-hidden="true" class="file-icon w-4 h-4" />
            <span v-if="invoiceInfo?.invoice_number" class="invoice-number">
              发票号码：{{ invoiceInfo.invoice_number }}
            </span>
            <Button
              variant="link"
              size="sm"
              aria-label="下载发票文件"
              @click="downloadInvoiceFile"
            >
              <Download class="w-4 h-4" aria-hidden="true" />
              下载发票文件
            </Button>
          </div>
        </div>
      </div>
    </div>

    <Dialog v-model:open="invoicedModalVisible">
      <DialogContent class="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>标记开票</DialogTitle>
          <DialogDescription>
            请输入发票号码以完成开票标记
          </DialogDescription>
        </DialogHeader>

        <div class="space-y-4">
          <div class="space-y-2">
            <Label for="invoice-number">发票号码 <span class="text-destructive">*</span></Label>
            <Input
              id="invoice-number"
              v-model="invoicedForm.invoice_number"
              placeholder="请输入发票号码"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" @click="invoicedModalVisible = false">取消</Button>
          <Button @click="handleConfirmInvoiced" :disabled="marking">
            <Loader2 v-if="marking" aria-hidden="true" class="w-4 h-4 mr-2 animate-spin" />
            确定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { toast } from 'vue-sonner'
import {
  User,
  FileText,
  Clock,
  UserCircle,
  Calendar,
  Ticket,
  Building2,
  Key,
  CreditCard,
  Wallet,
  MapPin,
  Phone,
  Download,
  CheckCircle2,
  Image,
  Loader2
} from 'lucide-vue-next'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
  const invoiceId = String(route.params['id'] ?? '')
  loading.value = true
  try {
    const data = await invoiceApi.getInvoiceApplication(Number(invoiceId))
    invoiceInfo.value = data
    // 设置动态标题
    setTitle(data.application_number || '发票申请详情')
  } catch (error) {
    logger.error('[InvoiceDetail]', '获取发票申请详情失败', { error })
    handleApiError(error, '获取发票申请详情')
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
    toast.success('发票申请删除成功')
    router.push('/invoices')
  } catch (error: unknown) {
    if (error !== 'cancel') {
      logger.error('[InvoiceDetail]', '删除失败', { error })
      handleApiError(error, '删除发票申请')
    }
  }
}

const handleMarkInvoiced = (): void => {
  invoicedModalVisible.value = true
}

const handleConfirmInvoiced = async (): Promise<void> => {
  if (invoicedForm.value.invoice_number.trim().length === 0) {
    toast.warning('请输入发票号码')
    return
  }

  if (!invoiceInfo.value) return

  try {
    marking.value = true
    await invoiceApi.markAsInvoiced(invoiceInfo.value.id, invoicedForm.value.invoice_number)
    toast.success('发票申请已标记开票')
    invoicedModalVisible.value = false
    invoicedForm.value.invoice_number = ''
    fetchInvoiceDetail()
  } catch (error) {
    logger.error('[InvoiceDetail]', '标记开票失败', { error })
    handleApiError(error, '标记开票')
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

/**
 * 判断是否为 PDF 文件
 */
const isPdf = (filePath: string | null): boolean => {
  if (filePath === null) return false
  return filePath.toLowerCase().endsWith('.pdf')
}

/**
 * 获取文件图标类名
 */
const getFileIconClass = (filePath: string | null): string => {
  if (filePath === null) return 'default-icon'
  const ext = filePath.toLowerCase().split('.').pop()
  const classMap: Record<string, string> = {
    'pdf': 'pdf-icon',
    'jpg': 'image-icon',
    'jpeg': 'image-icon',
    'png': 'image-icon',
    'ofd': 'ofd-icon',
  }
  return classMap[ext ?? ''] ?? 'default-icon'
}

/**
 * 获取文件类型标签
 */
const getFileTypeLabel = (filePath: string | null): string => {
  if (filePath === null) return '发票文件'
  const ext = filePath.toLowerCase().split('.').pop()
  const labelMap: Record<string, string> = {
    'pdf': 'PDF 发票',
    'jpg': '图片发票 (JPG)',
    'jpeg': '图片发票 (JPEG)',
    'png': '图片发票 (PNG)',
    'ofd': 'OFD 电子发票',
  }
  return labelMap[ext ?? ''] ?? '发票文件'
}

/**
 * 下载发票文件（带 Toast 反馈）
 * UX: success-feedback - 下载成功有提示
 */
const handleDownloadWithFeedback = (): void => {
  if (!invoiceInfo.value) return

  toast.success('发票文件下载成功')

  downloadInvoiceFile()
}

// Configure header on mount
onMounted(() => {
  headerStore.setBack(true)
  fetchInvoiceDetail()
})

// Watch invoiceInfo to update actions
watch(invoiceInfo, () => {
  const actions: { id: string; label: string; type?: 'primary' | 'success' | 'danger' | 'default'; handler: () => void }[] = []

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
@use '@/styles/variables-v2.scss' as *;

.invoice-detail-container {
  padding: 0;
  min-height: 0;
  flex: 1;
  background: $wolf-bg-page-v2;
}

.invoice-content {
  padding: $wolf-page-padding-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-section-gap-v2;
}

.invoice-info-card {
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-lg-v2;
  padding: $wolf-card-padding-v2;
  box-shadow: $wolf-shadow-card-v2;
}

.invoice-basic-info {
  padding: 0;
}

.info-top {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: $wolf-space-lg-v2;
  margin-bottom: 0;
}

.info-left {
  .invoice-title-section {
    display: flex;
    gap: $wolf-card-padding-v2;
    align-items: flex-start;
  }

  .invoice-avatar {
    width: 48px;
    height: 48px;
    border-radius: $wolf-radius-full-v2;
    background: $wolf-primary-v2;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    font-weight: $wolf-font-weight-semibold-v2;
    color: $wolf-text-inverse-v2;
    flex-shrink: 0;
  }

  .invoice-title-content {
    flex: 1;

    .invoice-name {
      margin: 0 0 $wolf-space-sm-v2 0;
      font-size: $wolf-font-size-body-v2;
      font-weight: $wolf-font-weight-semibold-v2;
      color: $wolf-text-primary-v2;
      line-height: $wolf-line-height-title-v2;
    }

    .invoice-tags {
      display: flex;
      gap: $wolf-space-sm-v2;
      flex-wrap: wrap;
    }
  }
}

.info-divider {
  height: 1px;
  background: $wolf-border-divider-v2;
  margin: $wolf-space-lg-v2 0;
}

.info-bottom {
  .attributes-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: $wolf-card-padding-v2 $wolf-space-lg-v2;
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
    font-size: 14px;
    color: $wolf-text-tertiary-v2;
    flex-shrink: 0;
  }

  .attribute-label {
    font-size: $wolf-font-size-caption-v2;
    color: $wolf-text-tertiary-v2;
    font-weight: $wolf-font-weight-normal-v2;
  }

  .attribute-value {
    font-size: $wolf-font-size-body-v2;
    color: $wolf-text-primary-v2;
    font-weight: $wolf-font-weight-medium-v2;
    line-height: $wolf-line-height-body-v2;

    &.secondary {
      color: $wolf-text-secondary-v2;
    }

    &.not-filled {
      color: $wolf-text-placeholder-v2;
    }
  }
}

.info-right {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: flex-end;
  gap: $wolf-card-padding-v2;

  .amount-section {
    text-align: right;

    .amount-label {
      font-size: $wolf-font-size-caption-v2;
      color: $wolf-text-tertiary-v2;
      margin-bottom: $wolf-space-xs-v2;
      font-weight: $wolf-font-weight-normal-v2;
    }

    .amount-value {
      font-size: 24px;
      font-weight: $wolf-font-weight-semibold-v2;
      color: $wolf-primary-v2;
      line-height: $wolf-line-height-title-v2;
    }
  }
}

.core-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $wolf-section-gap-v2;
}

.section-card {
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-v2;
  padding: $wolf-card-padding-v2;
  box-shadow: $wolf-shadow-card-v2;
  min-height: 300px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: $wolf-space-md-v2;
}

.card-title {
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
}

.invoice-title-content-detail {
  .attributes-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: $wolf-card-padding-v2 $wolf-space-lg-v2;
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
    font-size: 14px;
    color: $wolf-text-tertiary-v2;
    flex-shrink: 0;
  }

  .attribute-label {
    font-size: $wolf-font-size-caption-v2;
    color: $wolf-text-tertiary-v2;
    font-weight: $wolf-font-weight-normal-v2;
  }

  .attribute-value {
    font-size: $wolf-font-size-body-v2;
    color: $wolf-text-primary-v2;
    font-weight: $wolf-font-weight-medium-v2;
    line-height: $wolf-line-height-body-v2;

    &.not-filled {
      color: $wolf-text-placeholder-v2;
    }
  }
}

// Element Plus tag compatibility while the template still uses el-tag.
.wolf-tag {
  height: auto !important;
  padding: $wolf-space-xs-v2 $wolf-space-sm-v2 !important;
  border-width: $wolf-focus-ring-width-subtle-v2 !important;
  border-radius: $wolf-radius-sm-v2 !important;
  font-size: $wolf-font-size-caption-v2 !important;
  font-weight: $wolf-font-weight-medium-v2 !important;
  line-height: $wolf-line-height-body-v2 !important;
}

.wolf-tag--primary,
.wolf-tag--info {
  color: $wolf-primary-v2 !important;
  background-color: $wolf-primary-light-v2 !important;
  border-color: $wolf-primary-v2 !important;
}

.wolf-tag--success {
  color: $wolf-success-text-v2 !important;
  background-color: $wolf-success-bg-v2 !important;
  border-color: $wolf-success-v2 !important;
}

.wolf-tag--warning {
  color: $wolf-warning-text-v2 !important;
  background-color: $wolf-warning-bg-v2 !important;
  border-color: $wolf-warning-v2 !important;
}

.wolf-tag--danger {
  color: $wolf-danger-text-v2 !important;
  background-color: $wolf-danger-bg-v2 !important;
  border-color: $wolf-danger-v2 !important;
}

.wolf-tag--gray,
.wolf-tag--purple {
  color: $wolf-text-secondary-v2 !important;
  background-color: $wolf-bg-hover-v2 !important;
  border-color: $wolf-border-default-v2 !important;
}

// Task 6: 发票文件显示区域样式
.invoice-file-section {
  .file-info {
    display: flex;
    align-items: center;
    gap: $wolf-space-md-v2;
    padding: $wolf-space-md-v2;
    background: $wolf-bg-hover-v2;
    border-radius: $wolf-radius-sm-v2;
  }

  .file-icon {
    font-size: 24px;
    color: $wolf-primary-v2;
  }

  .invoice-number {
    font-size: $wolf-font-size-body-v2;
    color: $wolf-text-secondary-v2;
    font-weight: $wolf-font-weight-medium-v2;
  }
}

// Task 7: ISSUED 状态高亮文件区域样式
.issued-file-highlight {
  margin-top: $wolf-space-lg-v2;
  padding: $wolf-card-padding-v2;
  background: linear-gradient(135deg, $wolf-success-bg-v2 0%, $wolf-bg-card-v2 100%);
  border: 2px solid $wolf-success-v2;
  border-radius: $wolf-radius-v2;

  .highlight-header {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm-v2;
    margin-bottom: $wolf-space-md-v2;

    .success-icon {
      font-size: 20px;
      color: $wolf-success-text-v2;
    }

    .highlight-title {
      font-size: $wolf-font-size-body-v2;
      font-weight: $wolf-font-weight-semibold-v2;
      color: $wolf-success-text-v2;
    }

    .invoice-number-badge {
      font-size: $wolf-font-size-caption-v2;
      padding: $wolf-space-xs-v2 $wolf-space-sm-v2;
      background: $wolf-success-text-v2;
      color: $wolf-text-inverse-v2;
      border-radius: $wolf-radius-sm-v2;
      font-weight: $wolf-font-weight-medium-v2;
    }
  }

  .file-download-area {
    display: flex;
    align-items: center;
    gap: $wolf-space-md-v2;
    padding: $wolf-space-md-v2;
    background: $wolf-bg-card-v2;
    border-radius: $wolf-radius-sm-v2;

    .file-type-icon {
      font-size: 32px;

      &.pdf-icon { color: $wolf-danger-v2; }
      &.image-icon { color: $wolf-success-v2; }
      &.ofd-icon { color: $wolf-primary-v2; }  // OFD 蓝色
      &.default-icon { color: $wolf-text-tertiary-v2; }
    }

    .file-type-label {
      font-size: $wolf-font-size-body-v2;
      color: $wolf-text-secondary-v2;
      font-weight: $wolf-font-weight-medium-v2;
    }

    // UX: touch-target-size (CRITICAL) - 最小 44px
    .download-btn {
      margin-left: auto;
      min-width: 140px;
      min-height: 44px;  // 确保满足 touch-target 要求
    }
  }

  // UX: reduced-motion (MEDIUM)
  @media (prefers-reduced-motion: reduce) {
    * {
      transition: none;
    }
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
