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
          ¥{{ formatAmount(contractInfo?.total_amount || 0) }}
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
              <span v-if="preset.suggestedPercentage" class="preset-hint">
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
          <span v-if="suggestedDate" class="date-hint">
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
import { STAGE_PRESETS, suggestNextStage } from '@/constants/payment-stage-presets'
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
  get: () => props.visible,
  set: (val) => {
    if (!val) emit('close')
  }
})

// 模式切换
const mode = ref<'quick' | 'batch'>('quick')

// 快速模式表单
const quickFormRef = ref<FormInstance>()
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
const existingPlansTotal = computed(() => {
  return props.existingPlans?.reduce((sum, p) => sum + Number(p.planned_amount), 0) || 0
})

const remainingAmount = computed(() => {
  return (props.contractInfo?.total_amount || 0) - existingPlansTotal.value
})

const percentageHint = computed(() => {
  if (!props.contractInfo?.total_amount) return ''
  const pct = (quickForm.value.planned_amount / props.contractInfo.total_amount) * 100
  return `(${pct.toFixed(1)}%)`
})

const suggestedDate = computed(() => {
  const baseDate = props.contractInfo?.effective_date || props.contractInfo?.signing_date
  if (!baseDate) return ''

  const stageIndex = props.existingPlans?.length || 0
  const daysToAdd = [30, 90, 180][stageIndex] || 30

  const date = new Date(baseDate)
  date.setDate(date.getDate() + daysToAdd)
  return date.toISOString().split('T')[0]
})

const batchTotalAmount = computed(() => {
  return batchForm.value.plans.reduce((sum, p) => sum + (p.planned_amount || 0), 0)
})

const batchPercentage = computed(() => {
  if (!props.contractInfo?.total_amount) return '0'
  return ((batchTotalAmount.value / props.contractInfo.total_amount) * 100).toFixed(1)
})

// 提交状态
const submitting = ref(false)

// 格式化函数
const formatAmount = (amount: number) => {
  return amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// 禁用过去日期
const disabledDate = (date: Date) => {
  return date < new Date(new Date().setHours(0, 0, 0, 0))
}

// 快速分配百分比
const quickAllocate = (percentage: number) => {
  if (!props.contractInfo?.total_amount) return
  quickForm.value.planned_amount = props.contractInfo.total_amount * percentage / 100
}

// 添加批量阶段
const addBatchPlan = () => {
  batchForm.value.plans.push({ stage_name: '', planned_amount: 0, due_date: '' })
}

// 删除批量阶段
const removeBatchPlan = (index: number) => {
  batchForm.value.plans.splice(index, 1)
}

// 智能预填充
const initQuickForm = () => {
  const existingStages = props.existingPlans?.map(p => p.stage_name) || []
  const suggested = suggestNextStage(existingStages)

  // 1. 阶段名称
  quickForm.value.stage_name = suggested.value

  // 2. 金额
  if (suggested.suggestedPercentage && props.contractInfo?.total_amount) {
    quickForm.value.planned_amount = Math.min(
      remainingAmount.value,
      props.contractInfo.total_amount * suggested.suggestedPercentage / 100
    )
  } else {
    quickForm.value.planned_amount = remainingAmount.value > 0 ? remainingAmount.value : 0
  }

  // 3. 日期
  quickForm.value.due_date = suggestedDate.value || ''
}

// 监听 visible 变化，初始化表单
watch(() => props.visible, (val) => {
  if (val) {
    initQuickForm()
    batchForm.value.plans = [{ stage_name: '', planned_amount: 0, due_date: '' }]
  }
})

// 键盘快捷键（应用 ENG Review 和 P1 改进）
const handleKeydown = (e: KeyboardEvent) => {
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
const handleClose = () => {
  emit('close')
}

// 提交表单（应用 ENG Review D2：提前设置 submitting 防双击）
const handleSubmit = async () => {
  // D2: 立即设置 submitting 防止双击
  submitting.value = true

  try {
    if (mode.value === 'quick') {
      // 快速模式验证
      const valid = await quickFormRef.value?.validate().catch(() => false)
      if (!valid) {
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
      const valid = batchForm.value.plans.every(p =>
        p.stage_name && p.planned_amount > 0 && p.due_date
      )
      if (!valid) {
        ElMessage.error('请填写完整的计划信息')
        submitting.value = false
        return
      }

      // D1: 校验总金额不超过合同金额
      const contractTotalAmount = props.contractInfo?.total_amount || 0
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
    console.error('创建回款计划失败', error)
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
</style>