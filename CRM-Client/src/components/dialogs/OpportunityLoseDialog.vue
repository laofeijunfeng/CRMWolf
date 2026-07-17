<script setup lang="ts">
/**
 * OpportunityLoseDialog.vue - 输单表单弹窗
 *
 * 收集输单原因，遵循无障碍和动效规范。
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
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { handleApiError } from '@/utils/errorHandler'
import { opportunityApi, type Opportunity } from '@/api/opportunity'

// Zod schema for form validation
const schema = toTypedSchema(
  z.object({
    loss_reason: z
      .string()
      .min(1, '请输入输单原因')
      .max(500, '输单原因不能超过500个字符')
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
    loss_reason: ''
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
      // Clear loss_reason field
      setFieldValue('loss_reason', '')
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
    await opportunityApi.markAsLost(props.opportunityId, {
      loss_reason: formValues.loss_reason
    })

    toast.success('商机已标记为输单')
    emit('success')
    emit('update:open', false)
  } catch (error) {
    handleApiError(error, '标记输单')
  } finally {
    submitting.value = false
  }
})
</script>

<template>
  <Dialog :open="props.open" @update:open="emit('update:open', $event)">
    <DialogContent class="sm:max-w-[425px] max-w-full">
      <DialogHeader>
        <DialogTitle>标记输单</DialogTitle>
        <DialogDescription>请输入输单原因</DialogDescription>
      </DialogHeader>

      <div v-if="loading" class="py-8 text-center text-muted-foreground">
        加载中...
      </div>

      <form v-else class="grid gap-4 py-4" @submit="onSubmit">
        <!-- 输单原因 -->
        <FormField v-slot="{ componentField }" name="loss_reason">
          <FormItem>
            <FormLabel>
              输单原因 <span class="text-destructive">*</span>
            </FormLabel>
            <FormControl>
              <Textarea
                v-bind="componentField as any"
                :rows="4"
                placeholder="请输入输单原因"
                :disabled="submitting"
                class="resize-none"
              />
            </FormControl>
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