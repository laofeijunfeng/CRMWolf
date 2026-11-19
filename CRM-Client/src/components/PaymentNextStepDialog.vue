<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { Clock, Eye, ReceiptText, Send } from 'lucide-vue-next'
import ActionOptionCard from '@/components/crmwolf/ActionOptionCard.vue'
import AmountText from '@/components/crmwolf/AmountText.vue'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
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

const submitting = ref(false)

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
      toast.success('回款已直接确认（无需审批）')
    } else {
      toast.success('已提交审批，等待审批人处理')
    }
    emit('submitted')
    emit('update:visible', false)
  } catch (error: unknown) {
    const err = error as Error & { response?: { data?: { message?: string } } }
    const responseMessage = err.response?.data?.message
    const errorMessage = err.message
    const errorMsg = responseMessage ?? errorMessage ?? '提交审批失败'
    toast.error(`${errorMsg}，请检查网络连接后重试`)
  } finally {
    submitting.value = false
  }
}

const handleLater = (): void => {
  if (submitting.value) return
  emit('update:visible', false)
}

const handleViewDetail = (): void => {
  if (!props.record || submitting.value) return
  router.push({
    path: '/payments/plans',
    query: { planId: String(props.record.payment_plan_id) }
  })
  emit('update:visible', false)
}
</script>

<template>
  <Dialog :open="visible" @update:open="!submitting && emit('update:visible', $event)">
    <DialogContent
      size="sm"
      :hide-close="submitting"
      @escape-key-down="(event) => submitting && event.preventDefault()"
      @interact-outside="(event) => event.preventDefault()"
    >
      <DialogHeader>
        <DialogTitle>登记成功</DialogTitle>
        <DialogDescription>
          回款记录已保存，可继续提交审批或稍后处理。
        </DialogDescription>
      </DialogHeader>

      <div class="rounded-md border bg-muted/30 p-4">
        <div class="flex items-center gap-3">
          <div class="flex size-10 shrink-0 items-center justify-center rounded-md bg-brand/10 text-brand">
            <ReceiptText class="size-5" aria-hidden="true" />
          </div>
          <div class="min-w-0 flex-1">
            <div class="text-sm text-muted-foreground">回款金额</div>
            <AmountText :value="record?.actual_amount ?? 0" size="xl" />
          </div>
        </div>
        <div class="mt-3 border-t pt-3 text-sm text-muted-foreground">
          回款日期：{{ formatDate(record?.payment_date ?? '') }}
        </div>
      </div>

      <div class="space-y-2">
        <ActionOptionCard
          variant="primary"
          :icon="Send"
          :title="submitting ? '提交中...' : '立即提交审批'"
          description="提交后审批人将收到待办提醒"
          :loading="submitting"
          :disabled="!record"
          @click="handleSubmitApproval"
        />

        <ActionOptionCard
          :icon="Clock"
          title="稍后提交"
          description="先关闭弹窗，之后可在回款记录中处理"
          :disabled="submitting"
          @click="handleLater"
        />

        <Button
          type="button"
          variant="ghost"
          class="w-full justify-center gap-2"
          :disabled="submitting || !record"
          @click="handleViewDetail"
        >
          <Eye class="size-4" aria-hidden="true" />
          查看详情
        </Button>
      </div>
    </DialogContent>
  </Dialog>
</template>
