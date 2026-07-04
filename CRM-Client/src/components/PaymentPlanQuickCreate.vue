<!-- CRM-Client/src/components/PaymentPlanQuickCreate.vue -->
<template>
  <el-dialog
    v-model="dialogVisible"
    title="创建回款计划"
    width="700px"
    :close-on-click-modal="false"
    @close="handleClose"
    aria-label="创建回款计划对话框"
    role="dialog"
    aria-modal="true"
  >
    <!-- 合同金额提示 -->
    <div class="contract-summary">
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="合同金额">
          ¥{{ formatAmount(contractInfo?.total_amount ?? 0) }}
        </el-descriptions-item>
        <el-descriptions-item label="已规划金额">
          <span :class="{ 'warning': existingPlansTotal > 0 }">
            ¥{{ formatAmount(existingPlansTotal) }}
          </span>
          <span v-if="remainingAmount > 0" class="remaining-hint" aria-live="polite">
            (剩余可规划 ¥{{ formatAmount(remainingAmount) }})
          </span>
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- 模式切换 -->
    <div class="mode-switch">
      <el-radio-group v-model="mode" size="small">
        <el-radio-button value="quick">快速模式（单阶段）</el-radio-button>
        <el-radio-button value="batch">批量模式（多阶段）</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 快速模式表单 -->
    <div v-if="mode === 'quick'" class="quick-form">
      <el-form
        ref="quickFormRef"
        :model="quickForm"
        :rules="quickRules"
        label-width="120px"
        class="form-content"
      >
        <el-form-item label="阶段名称" prop="stage_name">
          <el-select
            v-model="quickForm.stage_name"
            placeholder="选择或输入阶段名称"
            allow-create
            filterable
            style="width: 100%"
          >
            <el-option
              v-for="preset in STAGE_PRESETS"
              :key="preset.value"
              :label="preset.label"
              :value="preset.value"
            >
              <span>{{ preset.label }}</span>
              <span v-if="preset.suggestedPercentage !== undefined" class="preset-hint">
                (建议 {{ preset.suggestedPercentage }}%)
              </span>
            </el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="计划金额" prop="planned_amount">
          <el-input-number
            v-model="quickForm.planned_amount"
            :min="0"
            :max="remainingAmount"
            :precision="2"
            :step="1000"
            style="width: 200px"
          />
          <span class="amount-hint" aria-live="polite" aria-atomic="true">
            {{ percentageHint }}
          </span>
          <div class="quick-allocate">
            <el-button
              size="small"
              @click="quickAllocate(30)"
              aria-label="快速分配30%金额（常见首付比例）"
            >
              30%
            </el-button>
            <el-button
              size="small"
              @click="quickAllocate(50)"
              aria-label="快速分配50%金额（平均分配）"
            >
              50%
            </el-button>
            <el-button
              size="small"
              @click="quickAllocate(70)"
              aria-label="快速分配70%金额"
            >
              70%
            </el-button>
            <el-button
              size="small"
              @click="quickAllocate(100)"
              aria-label="快速分配100%金额（全额付款）"
            >
              100%
            </el-button>
          </div>
        </el-form-item>

        <el-form-item label="计划日期" prop="due_date">
          <el-date-picker
            v-model="quickForm.due_date"
            type="date"
            placeholder="选择计划回款日期"
            style="width: 200px"
            value-format="YYYY-MM-DD"
            :disabled-date="disabledDate"
          />
          <span v-if="suggestedDate !== ''" class="date-hint">
            建议: {{ suggestedDate }}
          </span>
        </el-form-item>

        <el-form-item label="备注">
          <el-input
            v-model="quickForm.notes"
            type="textarea"
            placeholder="备注信息（可选）"
            :maxlength="200"
            show-word-limit
          />
        </el-form-item>
      </el-form>
    </div>

    <!-- 批量模式表单 -->
    <div v-else class="batch-form">
      <div class="batch-header">
        <el-button size="small" @click="addBatchPlan">
          <el-icon><Plus /></el-icon>
          添加阶段
        </el-button>
      </div>

      <div class="batch-plans">
        <div
          v-for="(plan, index) in batchForm.plans"
          :key="index"
          class="batch-plan-item"
        >
          <div class="plan-header">
            <span class="plan-index">第 {{ index + 1 }} 阶段</span>
            <el-button
              v-if="batchForm.plans.length > 1"
              size="small"
              type="danger"
              @click="removeBatchPlan(index)"
            >
              删除
            </el-button>
          </div>

          <el-form :model="plan" label-width="120px">
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="阶段名称" prop="stage_name">
                  <el-input v-model="plan.stage_name" placeholder="阶段名称" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="计划金额" prop="planned_amount">
                  <el-input-number
                    v-model="plan.planned_amount"
                    :min="0"
                    :precision="2"
                    style="width: 100%"
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="计划日期" prop="due_date">
              <el-date-picker
                v-model="plan.due_date"
                type="date"
                value-format="YYYY-MM-DD"
                style="width: 100%"
              />
            </el-form-item>
          </el-form>
        </div>
      </div>

      <div v-if="batchForm.plans.length > 0" class="batch-summary">
        <span>
          计划总金额: ¥{{ formatAmount(batchTotalAmount) }}
          (合同金额的 {{ batchPercentage }}%)
        </span>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <div class="footer-hints">
          <span class="hint">Ctrl+Enter 快速创建</span>
          <span class="hint">Esc 关闭</span>
        </div>
        <div class="footer-actions">
          <el-button @click="handleClose">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="handleSubmit">
            {{ mode === 'quick' ? '创建' : '批量创建' }}
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import paymentApi, { type PaymentPlanResponse } from '@/api/payment'
import { STAGE_PRESETS, suggestNextStage, type StagePreset } from '@/constants/payment-stage-presets'
import { showError, showSuccess } from '@/utils/errorMessages'

// Props
interface Props {
  visible: boolean
  contractId: number
  contractInfo?: {
    contract_name: string
    contract_number: string
    total_amount: number
    customer_info?: { account_name: string }
    effective_date?: string
    signing_date?: string
  }
  existingPlans?: PaymentPlanResponse[]
}

const props = defineProps<Props>()

// Emits
const emit = defineEmits<{
  close: []
  success: []
}>()

// 对话框可见性
const dialogVisible = computed({
  get: (): boolean => props.visible,
  set: (val: boolean): void => {
    if (val === false) emit('close')
  }
})

// 模式切换
const mode = ref<'quick' | 'batch'>('quick')

// 快速模式表单
const quickFormRef = ref<FormInstance | undefined>(undefined)
const quickForm = ref({
  stage_name: '',
  planned_amount: 0,
  due_date: '',
  notes: ''
})

const quickRules: FormRules = {
  stage_name: [{ required: true, message: '请选择阶段名称', trigger: 'change' }],
  planned_amount: [
    { required: true, message: '请输入计划金额', trigger: 'blur' },
    { type: 'number', min: 0.01, message: '金额必须大于0', trigger: 'blur' }
  ],
  due_date: [{ required: true, message: '请选择计划日期', trigger: 'change' }]
}

// 批量模式表单（应用 ENG Review D3：添加 prop 属性）
interface BatchPlanItem {
  stage_name: string
  planned_amount: number
  due_date: string
}

const batchForm = ref<{ plans: BatchPlanItem[] }>({
  plans: [{ stage_name: '', planned_amount: 0, due_date: '' }]
})

// 计算属性
const existingPlansTotal = computed((): number => {
  const plans = props.existingPlans ?? []
  return plans.reduce((sum: number, p): number => sum + Number(p.planned_amount), 0)
})

const remainingAmount = computed((): number => {
  const total = props.contractInfo?.total_amount ?? 0
  return total - existingPlansTotal.value
})

const percentageHint = computed((): string => {
  const total = props.contractInfo?.total_amount
  if (total === undefined || total === 0) return ''
  const pct = (quickForm.value.planned_amount / total) * 100
  return `(${pct.toFixed(1)}%)`
})

const suggestedDate = computed((): string => {
  const baseDate = props.contractInfo?.effective_date ?? props.contractInfo?.signing_date
  if (baseDate === undefined || baseDate === '') return ''

  const stageIndex = props.existingPlans?.length ?? 0
  const daysToAdd = [30, 90, 180][stageIndex] ?? 30

  const date = new Date(baseDate)
  date.setDate(date.getDate() + daysToAdd)
return date.toISOString().split('T')[0] ?? ''
})

const batchTotalAmount = computed((): number => {
  return batchForm.value.plans.reduce((sum: number, p): number => sum + (p.planned_amount ?? 0), 0)
})

const batchPercentage = computed((): string => {
  const total = props.contractInfo?.total_amount
  if (total === undefined || total === 0) return '0'
  return ((batchTotalAmount.value / total) * 100).toFixed(1)
})

// 提交状态
const submitting = ref<boolean>(false)

// 格式化函数
const formatAmount = (amount: number): string => {
  return amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// 禁用过去日期
const disabledDate = (date: Date): boolean => {
  return date < new Date(new Date().setHours(0, 0, 0, 0))
}

// 快速分配百分比
const quickAllocate = (percentage: number): void => {
  const total = props.contractInfo?.total_amount
  if (total === undefined) return
  quickForm.value.planned_amount = total * percentage / 100
}

// 添加批量阶段
const addBatchPlan = (): void => {
  batchForm.value.plans.push({ stage_name: '', planned_amount: 0, due_date: '' })
}

// 删除批量阶段
const removeBatchPlan = (index: number): void => {
  batchForm.value.plans.splice(index, 1)
}

// 智能预填充
const initQuickForm = (): void => {
  const existingStages: string[] = props.existingPlans?.map((p): string => p.stage_name) ?? []
  const suggested: StagePreset = suggestNextStage(existingStages)

  // 1. 阶段名称
  quickForm.value.stage_name = suggested.value

  // 2. 金额
  const suggestedPct = suggested.suggestedPercentage
  const total = props.contractInfo?.total_amount
  if (suggestedPct !== undefined && total !== undefined) {
    const calculated = total * suggestedPct / 100
    quickForm.value.planned_amount = Math.min(remainingAmount.value, calculated)
  } else {
    quickForm.value.planned_amount = remainingAmount.value > 0 ? remainingAmount.value : 0
  }

  // 3. 日期
  const suggestedDt = suggestedDate.value
  quickForm.value.due_date = suggestedDt !== '' ? suggestedDt : ''
}

// 监听 visible 变化，初始化表单
watch(() => props.visible, (val: boolean): void => {
  if (val === true) {
    initQuickForm()
    batchForm.value.plans = [{ stage_name: '', planned_amount: 0, due_date: '' }]
  }
})

// 键盘快捷键（应用 ENG Review 和 P1 改进）
const handleKeydown = (e: KeyboardEvent): void => {
  // Ctrl+Enter 或 Cmd+Enter（Mac）快速提交
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault()
    handleSubmit()
  }

  // Esc 关闭 Modal
  if (e.key === 'Escape') {
    e.preventDefault()
    handleClose()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})

// 关闭对话框
const handleClose = (): void => {
  emit('close')
}

// 提交表单（应用 ENG Review D2：提前设置 submitting 防双击）
const handleSubmit = async (): Promise<void> => {
  // D2: 立即设置 submitting 防止双击
  submitting.value = true

  try {
    if (mode.value === 'quick') {
      // 快速模式验证
      const formRef = quickFormRef.value
      const valid = formRef !== undefined ? await formRef.validate().catch(() => false) : false
      if (valid === false) {
        submitting.value = false
        return
      }

      await paymentApi.createPaymentPlans(props.contractId, {
        plans: [quickForm.value]
      })
      showSuccess('创建', '回款计划')
      emit('success')
      emit('close')
    } else {
      // 批量模式验证（应用 ENG Review D1：前端校验总金额）
      const isValid = batchForm.value.plans.every((p): boolean =>
        p.stage_name !== '' && p.planned_amount > 0 && p.due_date !== ''
      )
      if (isValid === false) {
        ElMessage.error('请填写完整的计划信息')
        submitting.value = false
        return
      }

      // D1: 校验总金额不超过合同金额
      const contractTotalAmount = props.contractInfo?.total_amount ?? 0
      if (batchTotalAmount.value > contractTotalAmount) {
        ElMessage.error('计划总金额超过合同金额，无法创建')
        submitting.value = false
        return
      }

      await paymentApi.createPaymentPlans(props.contractId, batchForm.value)
      showSuccess('批量创建', '回款计划')
      emit('success')
      emit('close')
    }
  } catch (error: unknown) {
    showError(error, '创建回款计划')
    submitting.value = false
  }
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.contract-summary {
  margin-bottom: $wolf-space-md;
  padding: $wolf-space-sm;
  background: $wolf-bg-soft;
  border-radius: $wolf-radius-md;

  .warning {
    color: $wolf-warning-text;
    font-weight: $wolf-font-weight-semibold;
  }

  .remaining-hint {
    color: $wolf-text-tertiary;
    font-size: $wolf-font-size-small;
    margin-left: $wolf-space-xs;
  }
}

.mode-switch {
  margin-bottom: $wolf-space-md;
  display: flex;
  justify-content: center;
}

.quick-form,
.batch-form {
  min-height: 200px;
}

.form-content {
  .amount-hint {
    color: $wolf-text-tertiary;
    font-size: $wolf-font-size-small;
    margin-left: $wolf-space-sm;
  }

  .quick-allocate {
    margin-top: $wolf-space-xs;
    display: flex;
    gap: $wolf-space-xs;
  }

  .date-hint {
    color: $wolf-text-tertiary;
    font-size: $wolf-font-size-small;
    margin-left: $wolf-space-sm;
  }

  .preset-hint {
    color: $wolf-text-tertiary;
    font-size: $wolf-font-size-small;
    margin-left: $wolf-space-xs;
  }
}

.batch-header {
  margin-bottom: $wolf-space-sm;
}

.batch-plans {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md;
}

.batch-plan-item {
  padding: $wolf-space-md;
  background: $wolf-bg-page;
  border-radius: $wolf-radius-md;
  border: 1px solid $wolf-border-default;

  .plan-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: $wolf-space-sm;

    .plan-index {
      font-weight: $wolf-font-weight-semibold;
      color: $wolf-text-primary;
    }
  }
}

.batch-summary {
  margin-top: $wolf-space-md;
  padding: $wolf-space-sm;
  background: $wolf-info-bg;
  border-radius: $wolf-radius-md;
  color: $wolf-text-secondary;
}

.dialog-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: $wolf-space-md;

  .footer-hints {
    display: flex;
    gap: $wolf-space-sm;
    font-size: $wolf-font-size-xs;
    color: $wolf-text-tertiary;
  }

  .footer-actions {
    display: flex;
    gap: $wolf-space-sm;
  }
}

// ==================== P0: Modal 动画 ====================
// 进入动画：200ms ease-out（符合 Material Design 标准）
.el-dialog {
  animation: modal-enter 200ms ease-out;
}

// 退出动画：更快（120ms），避免用户等待
.el-dialog.is-close {
  animation: modal-exit 120ms ease-in;
}

@keyframes modal-enter {
  from {
    opacity: 0;
    transform: scale(0.95) translateY(-20px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

@keyframes modal-exit {
  from {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
  to {
    opacity: 0;
    transform: scale(0.95) translateY(-20px);
  }
}

// P0: 支持 prefers-reduced-motion（WCAG 2.1 AA）
@media (prefers-reduced-motion: reduce) {
  .el-dialog,
  .el-dialog.is-close {
    animation: none;
  }
}

// ==================== P2: 微交互状态 ====================
// 快速分配按钮微交互（克制的 Wolf 风格）
.quick-allocate {
  .el-button {
    transition: all 150ms ease-out;

    // Hover: 轻微提升
    &:hover {
      transform: translateY(-1px);
      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    }

    // Active: 回弹（更快，80ms）
    &:active {
      transform: translateY(0);
      transition-duration: 80ms;
    }

    // Focus-visible: 保持可见性（WCAG 2.1 AA）
    &:focus-visible {
      outline: 2px solid $wolf-primary;
      outline-offset: 2px;
    }
  }
}

// 批量模式卡片 hover
.batch-plan-item {
  transition: all 150ms ease-out;

  &:hover {
    border-color: $wolf-border-hover;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  }
}

// ==================== P2: 响应式布局 ====================
// 平板（768px）
@media (max-width: 768px) {
  .el-dialog {
    width: 90% !important;
    max-width: 600px;
    margin: 5vh auto;
  }

  .contract-summary {
    :deep(.el-descriptions) {
      .el-descriptions-item {
        display: block;
        width: 100%;
        margin-bottom: $wolf-space-xs;
      }
    }
  }

  .quick-form {
    .el-form-item {
      :deep(.el-form-item__label) {
        width: 100px !important;
        text-align: left;
      }

      :deep(.el-form-item__content) {
        flex: 1;
      }
    }

    .el-input-number,
    .el-date-picker {
      width: 100% !important;
      max-width: 200px;
    }

    .quick-allocate {
      flex-wrap: wrap;
      gap: $wolf-space-xs;

      .el-button {
        flex: 1 1 calc(50% - 4px);
        min-width: 70px;
      }
    }
  }

  .batch-form {
    .batch-plan-item {
      padding: $wolf-space-sm;

      .el-row {
        flex-direction: column;
        gap: $wolf-space-sm;

        .el-col {
          width: 100%;
        }
      }
    }
  }
}

// 小手机（375px）
@media (max-width: 375px) {
  .el-dialog {
    width: 100% !important;
    max-width: 100%;
    margin: 0;
    border-radius: 0;
    min-height: 100vh;

    :deep(.el-dialog__header) {
      padding: $wolf-space-md;
      border-bottom: 1px solid $wolf-border-light;
    }

    :deep(.el-dialog__body) {
      padding: $wolf-space-md;
    }

    :deep(.el-dialog__footer) {
      padding: $wolf-space-md;
      border-top: 1px solid $wolf-border-light;
    }
  }

  .contract-summary {
    padding: $wolf-space-sm;
    background: $wolf-bg-page;
    border-radius: 0;
  }

  .mode-switch {
    margin-bottom: $wolf-space-sm;

    :deep(.el-radio-button__inner) {
      padding: 8px 12px;
      font-size: $wolf-font-size-small;
    }
  }

  .quick-form,
  .batch-form {
    min-height: auto;
  }

  .dialog-footer {
    flex-direction: column-reverse;
    gap: $wolf-space-sm;

    .footer-hints {
      order: 1;
      width: 100%;
      justify-content: center;
      font-size: $wolf-font-size-caption;
    }

    .footer-actions {
      width: 100%;
      display: flex;
      flex-direction: column;
      gap: $wolf-space-sm;

      .el-button {
        width: 100%;
        margin: 0;
      }
    }
  }
}
</style>
