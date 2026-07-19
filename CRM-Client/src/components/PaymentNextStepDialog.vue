<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { DocumentChecked, Clock, View, ArrowRight } from '@element-plus/icons-vue'
import AmountText from '@/components/crmwolf/AmountText.vue'
import { useApprovalStore } from '@/stores/approval'
import type { PaymentRecordResponse } from '@/api/payment'

const props = defineProps<{
  visible: boolean
  record: PaymentRecordResponse | null
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'submitted': []
}>()

const router = useRouter()
const approvalStore = useApprovalStore()

// Task 6.1: Loading state for async button
const submitting = ref(false)

// Task 7.5: Format helpers
const formatDate = (date: string): string => {
  return date ?? ''
}

const handleSubmitApproval = async (): Promise<void> => {
  if (!props.record) return
  if (submitting.value) return

  submitting.value = true
  try {
    const result = await approvalStore.submitEntity('PAYMENT', props.record.id)
    if (result.approval_id === 0 && result.status === 'APPROVED') {
      ElMessage.success('回款已直接确认（无需审批）')
    } else {
      ElMessage.success('已提交审批，等待审批人处理')
    }
    emit('submitted')
    emit('update:visible', false)
  } catch (error: unknown) {
    // Task 6.2: Error recovery path with clear message
    const err = error as Error & { response?: { data?: { message?: string } } }
    const responseMessage = err.response?.data?.message
    const errorMessage = err.message
    const errorMsg = responseMessage ?? errorMessage ?? '提交审批失败'
    ElMessage({
      type: 'error',
      message: `${errorMsg}，请检查网络连接后重试`,
      duration: 5000,
      showClose: true
    })
  } finally {
    submitting.value = false
  }
}

const handleLater = (): void => {
  emit('update:visible', false)
}

const handleViewDetail = (): void => {
  if (!props.record) return
  // 修复：使用 payment_plan_id（与后端 schema 一致）
  router.push(`/payments/${props.record.payment_plan_id}`)
  emit('update:visible', false)
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="emit('update:visible', $event)"
    title="登记成功"
    width="420px"
    :close-on-click-modal="false"
  >
    <!-- Task 7.5: Signature design - Amount hero display -->
    <div class="success-content">
      <!-- Signature: Payment amount large number display -->
      <div class="amount-hero">
        <div class="amount-label">回款金额</div>
        <!-- Task 7.1: Mono font for amount -->
        <AmountText class="amount-value" :value="record?.actual_amount ?? 0" size="xl" />
        <div class="amount-date">
          回款日期：{{ formatDate(record?.payment_date ?? '') }}
        </div>
      </div>

      <!-- Visual separator -->
      <div class="divider"></div>

      <!-- Next step option cards -->
      <div class="next-steps">
        <!-- Primary action: Submit approval -->
        <div
          class="step-card primary"
          @click="handleSubmitApproval"
          :class="{ disabled: submitting }"
        >
          <div class="step-icon">
            <el-icon><DocumentChecked /></el-icon>
          </div>
          <div class="step-content">
            <div class="step-label">立即提交审批</div>
            <div class="step-desc">快速进入审批流程</div>
          </div>
          <el-icon class="step-arrow"><ArrowRight /></el-icon>
        </div>

        <!-- Secondary action: Submit later -->
        <div class="step-card" @click="handleLater">
          <div class="step-icon">
            <el-icon><Clock /></el-icon>
          </div>
          <div class="step-content">
            <div class="step-label">稍后提交</div>
            <div class="step-desc">等待准备更多资料</div>
          </div>
          <el-icon class="step-arrow"><ArrowRight /></el-icon>
        </div>

        <!-- Text action: View detail -->
        <div class="step-card text" @click="handleViewDetail">
          <el-icon><View /></el-icon>
          <span class="step-label">查看详情</span>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

// Task 7.5: Signature design - Amount hero display
.success-content {
  display: flex;
  flex-direction: column;
}

// Signature: Amount large number display with gradient background
.amount-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: $wolf-space-lg;
  background: linear-gradient(135deg, rgba($wolf-primary, 0.08) 0%, rgba($wolf-warning-text, 0.05) 100%);
  border-radius: $wolf-radius-md;
  margin-bottom: $wolf-space-md;
}

.amount-label {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  margin-bottom: $wolf-space-xs;
}

.amount-value {
  margin-bottom: $wolf-space-xs;
}

.amount-date {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-secondary;
}

// Visual separator (gradient line)
.divider {
  height: 1px;
  background: linear-gradient(90deg, transparent 0%, $wolf-border-default 50%, transparent 100%);
  margin: $wolf-space-md 0;
}

// Next step option cards
.next-steps {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm;
}

.step-card {
  display: flex;
  align-items: center;
  padding: $wolf-space-md;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  background: $wolf-bg-card;
  margin-bottom: $wolf-space-sm;
  border: 1px solid $wolf-border-light;
}

.step-card.primary {
  background: $wolf-primary;
  color: $wolf-text-inverse;
  border-color: $wolf-primary;
}

.step-card.text {
  background: transparent;
  border-color: transparent;
  padding: $wolf-space-sm;
  justify-content: center;
  gap: $wolf-space-xs;
}

.step-card:hover:not(.disabled) {
  transform: translateY(-2px);
  box-shadow: $wolf-shadow-hover;
}

.step-card.disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.step-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: $wolf-bg-hover;
  border-radius: 8px;
  margin-right: $wolf-space-md;
}

.step-card.primary .step-icon {
  background: rgba($wolf-text-inverse, 0.2);
}

.step-content {
  flex: 1;
}

.step-label {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  margin-bottom: $wolf-space-xs;
}

.step-desc {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.step-card.primary .step-desc {
  color: rgba($wolf-text-inverse, 0.8);
}

.step-arrow {
  font-size: 16px;
  color: $wolf-text-tertiary;
}

.step-card.primary .step-arrow {
  color: rgba($wolf-text-inverse, 0.8);
}

// Task 7.1: Mono-number style
.mono-number {
  font-family: $wolf-font-mono;
  font-variant-numeric: tabular-nums lining-nums;
}
</style>
