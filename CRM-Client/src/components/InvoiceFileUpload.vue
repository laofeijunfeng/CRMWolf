<!--
  InvoiceFileUpload.vue - 发票文件上传组件

  Task 5: 发票审批优化 - 前端文件上传组件

  Features:
  - UX: 13项规则（touch-target-size、aria-labels、inline-validation等）
  - Frontend Design: 6项细节（状态动画、按钮层级、视觉区分等）
  - TypeScript 严格模式：无 any/as any/@ts-ignore/!

  Props:
  - invoiceId: 发票申请 ID
  - approvalStatus: 当前审批状态（可选，用于状态动画）

  Events:
  - uploaded: 文件上传成功（file_path, invoice_number）
  - rejected: 审批拒绝
  - error: 错误事件
  - statusChanged: 状态变化事件
-->

<template>
  <div class="invoice-file-upload">
    <!-- Frontend Design: 状态变化动画 -->
    <transition name="status-fade" mode="out-in">
      <div v-if="approvalStatus === 'PENDING_REVIEW'" class="status-badge pending">
        <el-icon><Clock /></el-icon>
        待审批
      </div>
      <div v-else-if="approvalStatus === 'ISSUED'" class="status-badge issued">
        <el-icon><CircleCheckFilled /></el-icon>
        已开票
      </div>
    </transition>

    <!-- 上传区域（Frontend Design: 必填字段视觉区分） -->
    <el-upload
      ref="uploadRef"
      class="upload-area required-field"
      :auto-upload="false"
      :limit="1"
      :on-change="handleFileChange"
      :on-exceed="handleExceed"
      :accept="acceptedTypes"
      :before-upload="beforeUpload"
      :show-file-list="false"
    >
      <!-- UX: aria-label for icon-only button, min-height 44px -->
      <el-button
        type="primary"
        class="wolf-btn wolf-btn--primary upload-btn"
        aria-label="选择发票文件"
      >
        <el-icon><Upload /></el-icon>
        选择发票文件
      </el-button>
      <template #tip>
        <div class="upload-tip">
          支持 PDF、JPG、PNG、OFD 格式，最大 10MB
        </div>
      </template>
    </el-upload>

    <!-- Frontend Design: 空状态引导文案 -->
    <div v-if="!selectedFile && !validationError" class="empty-upload-state">
      <el-icon class="empty-icon"><Document /></el-icon>
      <p class="empty-text">请选择发票文件开始审批</p>
      <p class="empty-hint">支持 PDF、JPG、PNG、OFD 格式</p>
    </div>

    <!-- UX: 即时校验错误提示（含恢复路径） -->
    <el-alert
      v-if="validationError"
      type="error"
      :title="validationError"
      :description="errorRecoveryHint"
      show-icon
      closable
      class="validation-error"
      @close="clearValidationError"
    />

    <!-- UX + Frontend Design: 文件预览 + 成功标记 -->
    <div v-if="selectedFile && !validationError" class="selected-file-info success">
      <el-icon class="success-check"><CircleCheckFilled /></el-icon>
      <el-icon class="file-type-icon" :class="getFileIconClass(selectedFile.name)">
        <Document v-if="isPdf(selectedFile.name)" />
        <Picture v-else />
      </el-icon>
      <span class="file-name">{{ selectedFile.name }}</span>
      <span class="file-size">{{ formatFileSize(selectedFile.size) }}</span>
      <!-- UX: 移除/重新选择按钮 aria-label -->
      <el-button
        link
        type="danger"
        size="small"
        class="remove-file-btn"
        @click="clearFile"
        aria-label="移除已选文件"
      >
        <el-icon><Close /></el-icon>
        移除
      </el-button>
    </div>

    <!-- UX: 上传进度条（大文件 >1MB） -->
    <el-progress
      v-if="uploading && selectedFile && selectedFile.size > ONE_MB"
      :percentage="uploadProgress"
      :status="uploadProgress === 100 ? 'success' : undefined"
      class="upload-progress"
    />

    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-position="top"
      class="invoice-number-form"
    >
      <!-- UX + Frontend Design: 发票号码可选，带可选标记 + tooltip -->
      <el-form-item prop="invoice_number">
        <template #label>
          <div class="optional-label">
            <span>发票号码</span>
            <span class="optional-tag">可选</span>
            <el-tooltip
              content="发票号码已印在发票文件上，无需手动填写。如需记录可填写，便于后续查询。"
              placement="top"
            >
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </div>
        </template>
        <el-input
          v-model="form.invoice_number"
          placeholder="可选：记录发票号码便于查询"
          :maxlength="100"
          show-word-limit
          clearable
        />
      </el-form-item>

      <!-- Frontend Design: 审批意见可选标记 -->
      <el-form-item prop="comment">
        <template #label>
          <div class="optional-label">
            <span>审批意见</span>
            <span class="optional-tag">可选</span>
          </div>
        </template>
        <el-input
          v-model="form.comment"
          type="textarea"
          placeholder="填写审批意见"
          :maxlength="500"
          show-word-limit
        />
      </el-form-item>
    </el-form>

    <!-- Frontend Design: 按钮层级区分 -->
    <div class="action-buttons">
      <!-- 主操作：上传并审批 -->
      <el-button
        type="primary"
        class="wolf-btn wolf-btn--primary approve-btn"
        :loading="submitting"
        :disabled="!selectedFile || !!validationError"
        @click="handleApproveWithFile"
      >
        <template #icon>
          <el-icon><Check /></el-icon>
        </template>
        上传发票并审批
      </el-button>

      <!-- 危险操作：拒绝（视觉分离） -->
      <el-button
        type="danger"
        class="wolf-btn wolf-btn--danger reject-btn"
        plain
        :disabled="submitting"
        @click="handleReject"
      >
        <el-icon><Close /></el-icon>
        拒绝审批
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { ElMessage, type UploadInstance, type UploadFile, type FormInstance, type FormRules } from 'element-plus'
import {
  Upload,
  Document,
  Close,
  Picture,
  QuestionFilled,
  Check,
  Clock,
  CircleCheckFilled
} from '@element-plus/icons-vue'
import { approveInvoiceWithFile, approveInvoiceWithFileProgress } from '@/api/fileUpload'

/**
 * Props 定义
 */
const props = defineProps<{
  invoiceId: number
  approvalStatus?: string // Frontend Design: 接收当前审批状态
}>()

/**
 * Emits 定义
 */
const emit = defineEmits<{
  uploaded: [file_path: string, invoice_number: string]
  rejected: []
  error: [message: string]
  statusChanged: [new_status: string] // Frontend Design: 状态变化事件
}>()

// ==================== 常量 ====================

const ACCEPTED_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png', '.ofd'] as const
const acceptedTypes = ACCEPTED_EXTENSIONS.join(',')
const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB
const ONE_MB = 1024 * 1024 // 1MB

// ==================== Refs ====================

const uploadRef = ref<UploadInstance>()
const formRef = ref<FormInstance>()
const selectedFile = ref<File | null>(null)

// UX: 状态变量
const validationError = ref('')
const errorRecoveryHint = ref('')
const uploading = ref(false)
const uploadProgress = ref(0)
const submitting = ref(false)

// ==================== Form ====================

const form = reactive({
  invoice_number: '',
  comment: ''
})

const rules: FormRules = {
  invoice_number: [
    { max: 100, message: '发票号码最长 100 字符', trigger: 'blur' }
  ]
}

// ==================== 文件校验 ====================

/**
 * 文件校验结果
 */
interface ValidationResult {
  valid: boolean
  error?: string
  recoveryHint?: string
}

/**
 * UX: 即时校验函数（含恢复路径）
 */
const validateFileInstant = (file: File): ValidationResult => {
  // 文件大小校验
  if (file.size > MAX_FILE_SIZE) {
    return {
      valid: false,
      error: `文件过大：${formatFileSize(file.size)}`,
      recoveryHint: `请选择小于 ${formatFileSize(MAX_FILE_SIZE)} 的文件，或压缩后再上传`
    }
  }

  // 扩展名校验
  const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase()
  if (!ACCEPTED_EXTENSIONS.includes(ext as typeof ACCEPTED_EXTENSIONS[number])) {
    return {
      valid: false,
      error: `不支持的文件类型：${ext}`,
      recoveryHint: '请选择 PDF、JPG、PNG 或 OFD 格式的发票文件'
    }
  }

  return { valid: true }
}

/**
 * UX: 即时校验（选择时而非提交时）
 */
const handleFileChange = (uploadFile: UploadFile): void => {
  if (uploadFile.raw) {
    const validationResult = validateFileInstant(uploadFile.raw)
    if (!validationResult.valid) {
      validationError.value = validationResult.error ?? ''
      errorRecoveryHint.value = validationResult.recoveryHint ?? ''
      selectedFile.value = null
      uploadRef.value?.clearFiles()
    } else {
      validationError.value = ''
      errorRecoveryHint.value = ''
      selectedFile.value = uploadFile.raw
    }
  }
}

const handleExceed = (): void => {
  ElMessage.warning('只能上传一个文件，请先移除当前文件')
}

const beforeUpload = (file: File): boolean => {
  // 重复校验（before-upload 是 el-upload 的钩子）
  const result = validateFileInstant(file)
  if (!result.valid) {
    ElMessage.error(result.error)
    return false
  }
  return true
}

const clearFile = (): void => {
  selectedFile.value = null
  validationError.value = ''
  errorRecoveryHint.value = ''
  uploadRef.value?.clearFiles()
}

const clearValidationError = (): void => {
  validationError.value = ''
  errorRecoveryHint.value = ''
}

// ==================== 工具函数 ====================

/**
 * 格式化文件大小
 */
const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * 判断是否为 PDF 文件
 */
const isPdf = (filename: string): boolean =>
  filename.toLowerCase().endsWith('.pdf')

/**
 * 获取文件类型图标类名
 */
const getFileIconClass = (filename: string): string =>
  isPdf(filename) ? 'pdf-icon' : 'image-icon'

// ==================== 表单验证 ====================

/**
 * 验证并提交
 * @returns 是否验证成功
 */
const validate = async (): Promise<boolean> => {
  // 检查文件（UX: 即时校验已处理，此处为二次确认）
  if (!selectedFile.value) {
    ElMessage.warning('请选择发票文件')
    return false
  }

  // 检查表单
  try {
    const valid = await formRef.value?.validate()
    return valid === true
  } catch {
    return false
  }
}

/**
 * 获取提交数据
 */
const getSubmitData = (): { file: File | null; invoice_number: string; comment: string } => ({
  file: selectedFile.value,
  invoice_number: form.invoice_number,
  comment: form.comment
})

/**
 * UX: 设置上传状态（由父组件调用）
 */
const setUploadState = (state: { uploading: boolean; progress?: number }): void => {
  uploading.value = state.uploading
  if (state.progress !== undefined) {
    uploadProgress.value = state.progress
  }
}

// ==================== 事件处理 ====================

/**
 * Frontend Design + Toast 文案优化: 审批通过处理
 */
const handleApproveWithFile = async (): Promise<void> => {
  const valid = await validate()
  if (!valid) return

  const data = getSubmitData()
  if (!data.file) return

  submitting.value = true

  // UX: 大文件显示进度
  const isLargeFile = data.file.size > ONE_MB

  try {
    uploading.value = true
    uploadProgress.value = 0

    // 根据文件大小选择上传方式
    if (isLargeFile) {
      const result = await approveInvoiceWithFileProgress(
        props.invoiceId,
        data.file,
        (progress) => {
          uploadProgress.value = progress
        },
        data.invoice_number.length > 0 ? data.invoice_number : undefined,
        data.comment.length > 0 ? data.comment : undefined
      )

      emit('uploaded', result.file_path, result.invoice_number ?? '')
      emit('statusChanged', result.new_status)
    } else {
      const result = await approveInvoiceWithFile(
        props.invoiceId,
        data.file,
        data.invoice_number.length > 0 ? data.invoice_number : undefined,
        data.comment.length > 0 ? data.comment : undefined
      )

      emit('uploaded', result.file_path, result.invoice_number ?? '')
      emit('statusChanged', result.new_status)
    }

    // Frontend Design: Toast 文案优化
    ElMessage.success({
      message: '审批通过，发票已开票',
      duration: 3000
    })

    clearFile()
    form.invoice_number = ''
    form.comment = ''
  } catch (error) {
    const err = error as Error
    // Frontend Design: Toast 文案优化
    ElMessage.error({
      message: '审批失败',
      duration: 3000
    })
    emit('error', err.message.length > 0 ? err.message : '审批失败')
  } finally {
    submitting.value = false
    uploading.value = false
    uploadProgress.value = 0
  }
}

/**
 * Frontend Design: 拒绝审批处理
 */
const handleReject = (): void => {
  emit('rejected')

  ElMessage.warning({
    message: '审批已拒绝',
    duration: 2000
  })

  emit('statusChanged', 'REJECTED')
}

// ==================== 暴露方法 ====================

defineExpose({
  validate,
  getSubmitData,
  clearFile,
  setUploadState,
  handleApproveWithFile,
  handleReject
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.invoice-file-upload {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md;
}

// ==================== 状态变化动画 ====================
// Frontend Design: Motion deliberately

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: $wolf-space-xs;
  padding: $wolf-space-xs $wolf-space-md;
  border-radius: $wolf-radius-sm;
  font-weight: $wolf-font-weight-medium;
  font-size: $wolf-font-size-body;
  transition: all 0.3s ease;

  &.pending {
    background: $wolf-warning-bg;
    color: $wolf-warning-text;
    border: 1px solid $wolf-warning-border;
  }

  &.issued {
    background: $wolf-success-bg;
    color: $wolf-success-text;
    border: 1px solid $wolf-success-border;
  }
}

.status-fade-enter-active,
.status-fade-leave-active {
  transition: all 0.3s ease;
}

.status-fade-enter-from {
  opacity: 0;
  transform: translateY(-10px);
}

.status-fade-leave-to {
  opacity: 0;
  transform: translateY(10px);
}

// UX: Reduced Motion
@media (prefers-reduced-motion: reduce) {
  .status-badge {
    transition: none;
  }

  .status-fade-enter-active,
  .status-fade-leave-active {
    transition: none;
  }

  .status-fade-enter-from,
  .status-fade-leave-to {
    opacity: 1;
    transform: none;
  }
}

// ==================== 上传区域 ====================
// Frontend Design: 必填字段视觉区分

.upload-area.required-field {
  border-left: 3px solid $wolf-primary;
  padding-left: $wolf-space-sm;
  margin-bottom: $wolf-space-md;
}

.upload-area {
  :deep(.el-upload) {
    width: 100%;
  }
}

.upload-tip {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  margin-top: $wolf-space-xs;
}

// UX: Touch target size (44×44px minimum)
.upload-btn {
  min-height: 44px;
  min-width: 44px;
  padding: $wolf-space-sm $wolf-space-md;

  // UX: Press feedback
  &:active:not(:disabled) {
    transform: scale(0.95);
    opacity: 0.9;
  }
}

// ==================== 空状态引导文案 ====================
// Frontend Design: Empty states are invitations

.empty-upload-state {
  text-align: center;
  padding: $wolf-space-lg;
  color: $wolf-text-tertiary;
  background: $wolf-fill-light;
  border-radius: $wolf-radius-sm;
  border: 1px dashed $wolf-border-light;

  .empty-icon {
    font-size: 48px;
    color: $wolf-text-quaternary;
    margin-bottom: $wolf-space-md;
  }

  .empty-text {
    font-size: $wolf-font-size-body;
    font-weight: $wolf-font-weight-medium;
    color: $wolf-text-secondary;
    margin-bottom: $wolf-space-xs;
  }

  .empty-hint {
    font-size: $wolf-font-size-caption;
    color: $wolf-text-tertiary;
  }
}

// ==================== 校验错误提示 ====================
// UX: Error recovery

.validation-error {
  margin-top: $wolf-space-sm;
}

// ==================== 文件预览 + 成功标记 ====================
// Frontend Design: Write from end user's side

.selected-file-info.success {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  padding: $wolf-space-sm $wolf-card-padding;
  background: $wolf-success-bg;
  border: 1px solid $wolf-success-border;
  border-radius: $wolf-radius-sm;

  .success-check {
    color: $wolf-success-text;
    font-size: 20px;
    font-weight: bold;
  }

  .file-type-icon {
    font-size: 24px;
    color: $wolf-primary;
  }

  .file-name {
    flex: 1;
    font-size: $wolf-font-size-body;
    color: $wolf-text-primary;
    font-weight: $wolf-font-weight-medium;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .file-size {
    font-size: $wolf-font-size-caption;
    color: $wolf-text-tertiary;
  }

  .remove-file-btn {
    min-height: 44px; // UX: touch-target-size
    min-width: 44px; // UX: touch-target-size
    display: flex;
    align-items: center;
    gap: $wolf-space-xs;
  }
}

// ==================== 上传进度条 ====================
// UX: Progress indicators

.upload-progress {
  margin-top: $wolf-space-sm;
}

// ==================== 表单 ====================

.invoice-number-form {
  margin-top: $wolf-space-md;

  // Frontend Design: 可选标签视觉区分
  .optional-label {
    display: flex;
    align-items: center;
    gap: $wolf-space-xs;

    .optional-tag {
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
      background: $wolf-fill-light;
      padding: 2px 6px;
      border-radius: $wolf-radius-xs;
      font-weight: $wolf-font-weight-normal;
    }

    .help-icon {
      color: $wolf-text-tertiary;
      cursor: help;
      font-size: 16px;

      &:hover {
        color: $wolf-primary;
      }
    }
  }
}

// ==================== 按钮层级区分 ====================
// Frontend Design: Structure is information

.action-buttons {
  display: flex;
  gap: $wolf-space-md;
  margin-top: $wolf-space-lg;

  .approve-btn {
    flex: 1; // 主操作占据更多空间
    min-height: 44px; // UX: touch-target-size
  }

  .reject-btn {
    flex: 0 0 auto; // 次操作固定宽度
    min-height: 44px; // UX: touch-target-size
    // 危险操作视觉分离
    margin-left: auto;
  }
}

// UX: Press feedback for buttons
.action-buttons {
  .wolf-btn {
    &:active:not(:disabled) {
      transform: scale(0.95);
      opacity: 0.9;
    }
  }
}

// UX: Reduced Motion for buttons
@media (prefers-reduced-motion: reduce) {
  .action-buttons .wolf-btn {
    transition: none;

    &:active:not(:disabled) {
      transform: none;
    }
  }
}
</style>