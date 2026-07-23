<script setup lang="ts">
/**
 * OpportunityWinDialog.vue - 赢单表单弹窗
 *
 * 收集实际成交金额和日期，遵循无障碍和动效规范。
 * 使用 vee-validate + Zod 进行表单校验。
 */
import { ref, watch } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { toast } from 'vue-sonner'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter
} from '@/components/ui/dialog'
import {
  FormField,
  FormItem,
  FormMessage,
} from '@/components/ui/form'
import { Button } from '@/components/ui/button'
import {
  DateField,
  InputField,
} from '@/components/crmwolf'
import { handleApiError } from '@/utils/errorHandler'
import { getTodayLocalDate, formatLocalDate } from '@/utils/format'
import { opportunityApi, type Opportunity } from '@/api/opportunity'

// Zod schema for form validation
const schema = toTypedSchema(
  z.object({
    actual_amount: z.number().min(0.01, '实际成交金额必须大于0'),
    actual_closing_date: z.string().min(1, '请选择实际成交日期')
  })
)

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

// VeeValidate form setup
const { handleSubmit, setFieldValue } = useForm({
  validationSchema: schema,
  initialValues: {
    actual_amount: 0,
    actual_closing_date: getTodayLocalDate()
  }
})

// State
const loading = ref(false)
const submitting = ref(false)
const opportunity = ref<Opportunity | null>(null)

// Watch for dialog open to load opportunity details
watch(() => props.open, async (newOpen) => {
  if (newOpen && props.opportunityId !== null) {
    loading.value = true
    try {
      opportunity.value = await opportunityApi.getOpportunity(props.opportunityId)
      // Pre-fill with estimated amount
      setFieldValue('actual_amount', opportunity.value.total_amount)
      setFieldValue('actual_closing_date', getTodayLocalDate())
    } catch (error) {
      handleApiError(error, '加载商机详情')
      emit('update:open', false)
    } finally {
      loading.value = false
    }
  }
})

// Form submission
const onSubmit = handleSubmit(async (formValues) => {
  if (props.opportunityId === null) return

  submitting.value = true
  try {
    await opportunityApi.markAsWon(props.opportunityId, {
      actual_amount: formValues.actual_amount,
      actual_closing_date: formValues.actual_closing_date
    })

    toast.success('商机已标记为赢单')
    emit('success')
    emit('update:open', false)
  } catch (error) {
    handleApiError(error, '标记赢单')
  } finally {
    submitting.value = false
  }
})
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

      <form v-else class="grid gap-4 py-4" @submit="onSubmit">
        <!-- 实际成交金额 -->
        <FormField v-slot="{ value, handleChange }" name="actual_amount">
          <FormItem>
            <InputField
              id="opportunity-win-amount"
              :model-value="Number(value ?? 0)"
              label="实际成交金额"
              required
              type="number"
              step="0.01"
              min="0"
              placeholder="请输入金额"
              :disabled="submitting"
              @update:model-value="handleChange(Number($event))"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- 实际成交日期 -->
        <FormField v-slot="{ value, handleChange }" name="actual_closing_date">
          <FormItem>
            <DateField
              id="opportunity-win-date"
              :model-value="value ? new Date(String(value)) : null"
              label="实际成交日期"
              required
              placeholder="请选择实际成交日期"
              :disabled="submitting"
              @update:model-value="(date: Date | null) => handleChange(date ? formatLocalDate(date) : '')"
            />
            <FormMessage />
          </FormItem>
        </FormField>
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
          @click="onSubmit"
        >
          {{ submitting ? '提交中...' : '确认' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
