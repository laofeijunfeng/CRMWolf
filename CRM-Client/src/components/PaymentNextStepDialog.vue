<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { ArrowRight, Clock, Eye, Loader2, ReceiptText, Send } from 'lucide-vue-next'
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
  emit('update:visible', false)
}

const handleViewDetail = (): void => {
  if (!props.record) return
  router.push({
    path: '/payments/plans',
    query: { planId: String(props.record.payment_plan_id) }
  })
  emit('update:visible', false)
}
</script>

<template>
  <Dialog :open="visible" @update:open="emit('update:visible', $event)">
    <DialogContent
      class="sm:max-w-[440px]"
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
          <div class="flex size-10 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
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
        <button
          type="button"
          class="flex w-full items-center gap-3 rounded-md border bg-primary px-3 py-3 text-left text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="submitting"
          @click="handleSubmitApproval"
        >
          <span class="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary-foreground/15">
            <Loader2 v-if="submitting" class="size-4 animate-spin" aria-hidden="true" />
            <Send v-else class="size-4" aria-hidden="true" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block text-sm font-medium">
              {{ submitting ? '提交中...' : '立即提交审批' }}
            </span>
            <span class="block text-xs text-primary-foreground/80">提交后审批人将收到待办提醒</span>
          </span>
          <ArrowRight class="size-4 shrink-0 opacity-80" aria-hidden="true" />
        </button>

        <button
          type="button"
          class="flex w-full items-center gap-3 rounded-md border bg-background px-3 py-3 text-left transition-colors hover:bg-muted/60"
          @click="handleLater"
        >
          <span class="flex size-9 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
            <Clock class="size-4" aria-hidden="true" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block text-sm font-medium text-foreground">稍后提交</span>
            <span class="block text-xs text-muted-foreground">先关闭弹窗，之后可在回款记录中处理</span>
          </span>
          <ArrowRight class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        </button>

        <Button
          type="button"
          variant="ghost"
          class="w-full justify-center gap-2"
          @click="handleViewDetail"
        >
          <Eye class="size-4" aria-hidden="true" />
          查看详情
        </Button>
      </div>
    </DialogContent>
  </Dialog>
</template>
