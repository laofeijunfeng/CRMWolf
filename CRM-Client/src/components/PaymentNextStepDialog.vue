<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { CircleCheckFilled } from '@element-plus/icons-vue'
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
  router.push(`/payments/${props.record.plan_id}`)
  emit('update:visible', false)
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="emit('update:visible', $event)"
    title="登记成功"
    width="400px"
    :close-on-click-modal="false"
  >
    <div class="success-content">
      <el-icon class="success-icon" color="#67C23A" :size="48">
        <CircleCheckFilled />
      </el-icon>

      <h3>回款登记成功！</h3>

      <el-descriptions v-if="record" :column="1" border size="small">
        <el-descriptions-item label="回款金额">
          ¥{{ record.actual_amount.toLocaleString() }}
        </el-descriptions-item>
        <el-descriptions-item label="回款日期">
          {{ record.payment_date }}
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <div class="next-step">
      <h4>下一步操作：</h4>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="submitting"
        @click="handleSubmitApproval"
      >
        {{ submitting ? '提交中...' : '立即提交审批' }}
      </el-button>
      <el-button @click="handleLater">
        稍后提交
      </el-button>
      <el-button text @click="handleViewDetail">
        查看详情
      </el-button>
    </div>
  </el-dialog>
</template>

<style scoped>
.success-content {
  text-align: center;
  margin-bottom: 24px;
}

.success-icon {
  margin-bottom: 16px;
}

.next-step {
  border-top: 1px solid var(--el-border-color);
  padding-top: 16px;
}

.next-step h4 {
  margin-bottom: 12px;
}

.next-step .el-button {
  margin-right: 8px;
}
</style>