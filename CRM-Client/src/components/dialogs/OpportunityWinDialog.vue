<script setup lang="ts">
/**
 * OpportunityWinDialog.vue - 赢单表单弹窗
 *
 * 收集实际成交金额和日期，遵循无障碍和动效规范。
 */
import { ref, reactive, watch } from 'vue'
import { toast } from 'vue-sonner'
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
import { DatePicker } from '@/components/ui/date-picker'
import { handleApiError } from '@/utils/errorHandler'
import { getTodayLocalDate, formatLocalDate } from '@/utils/format'
import { opportunityApi, type Opportunity } from '@/api/opportunity'

interface Props {
  opportunityId: number | null
  open: boolean
}

interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// 状态
const loading = ref(false)
const submitting = ref(false)
const opportunity = ref<Opportunity | null>(null)
const form = reactive({
  actual_amount: 0,
  actual_closing_date: getTodayLocalDate()
})

// 监听 open 变化，加载商机详情
watch(() => props.open, async (newOpen) => {
  if (newOpen && props.opportunityId !== null) {
    loading.value = true
    try {
      opportunity.value = await opportunityApi.getOpportunity(props.opportunityId)
      // 预填充预计金额
      form.actual_amount = opportunity.value.total_amount
      form.actual_closing_date = getTodayLocalDate()
    } catch (error) {
      handleApiError(error, '加载商机详情')
      emit('update:open', false)
    } finally {
      loading.value = false
    }
  }
})

// 提交赢单
async function handleSubmit(): Promise<void> {
  // 前端校验
  if (!Number.isFinite(form.actual_amount) || form.actual_amount <= 0) {
    toast.error('实际成交金额必须大于0')
    return
  }

  if (!form.actual_closing_date) {
    toast.error('请选择实际成交日期')
    return
  }

  if (props.opportunityId === null) return

  submitting.value = true
  try {
    await opportunityApi.markAsWon(props.opportunityId, {
      actual_amount: form.actual_amount,
      actual_closing_date: form.actual_closing_date
    })

    toast.success('商机已标记为赢单')
    emit('success')
    emit('update:open', false)
  } catch (error) {
    handleApiError(error, '标记赢单')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Dialog :open="props.open" @update:open="emit('update:open', $event)">
    <DialogContent class="sm:max-w-[425px] max-w-full">
      <DialogHeader>
        <DialogTitle>标记赢单</DialogTitle>
        <DialogDescription>请输入实际成交金额和日期</DialogDescription>
      </DialogHeader>

      <div v-if="loading" class="py-8 text-center text-muted-foreground">
        加载中...
      </div>

      <form v-else class="grid gap-4 py-4">
        <!-- 实际成交金额 -->
        <div class="grid gap-2">
          <Label for="actual_amount">
            实际成交金额 <span class="text-destructive">*</span>
          </Label>
          <Input
            id="actual_amount"
            v-model.number="form.actual_amount"
            type="number"
            step="0.01"
            min="0"
            placeholder="请输入金额"
            :disabled="submitting"
          />
        </div>

        <!-- 实际成交日期 -->
        <div class="grid gap-2">
          <Label for="actual_closing_date">
            实际成交日期 <span class="text-destructive">*</span>
          </Label>
          <DatePicker
            :model-value="form.actual_closing_date ? new Date(form.actual_closing_date) : null"
            placeholder="请选择实际成交日期"
            :disabled="submitting"
            @update:model-value="(date: Date | null) => form.actual_closing_date = date ? formatLocalDate(date) : ''"
          />
        </div>
      </form>

      <DialogFooter class="flex-col gap-2 sm:flex-row">
        <Button
          variant="outline"
          :disabled="submitting"
          class="w-full sm:w-auto"
          @click="emit('update:open', false)"
        >
          取消
        </Button>
        <Button
          type="submit"
          :disabled="submitting || loading"
          :loading="submitting"
          class="w-full sm:w-auto"
          @click="handleSubmit"
        >
          {{ submitting ? '提交中...' : '确认' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>