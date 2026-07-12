<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useForm, useField } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { toast } from 'vue-sonner'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import customerFollowUpApi from '@/api/customerFollowUp'

// Compute default date: 3 days from now
function getDefaultNextFollowTime(): string {
  const date = new Date()
  date.setDate(date.getDate() + 3)
  const parts = date.toISOString().split('T')
  return parts[0] ?? ''
}

// Zod schema for form validation
const schema = toTypedSchema(
  z.object({
    method: z.string().min(1, '请选择跟进方式'),
    content: z.string().min(1, '请输入跟进内容').max(500, '内容不能超过500字'),
    next_follow_time: z.string().optional(),
    next_action: z.string().max(200, '动作不能超过200字').optional()
  })
)

interface Props {
  customerId: number
  open: boolean
}

interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// VeeValidate form setup
const { handleSubmit, resetForm, values } = useForm({
  validationSchema: schema,
  initialValues: {
    method: '',
    content: '',
    next_follow_time: getDefaultNextFollowTime(),
    next_action: ''
  }
})

// Use useField for RadioGroup to handle type compatibility
const { value: methodValue, errorMessage: methodError } = useField<string>('method')

// State
const submitting = ref(false)
const isDirty = ref(false)
const showConfirmDialog = ref(false)

// Computed property for dialog visibility
const visible = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val)
})

// Follow-up method options
const methodOptions: { value: string; label: string }[] = [
  { value: '电话', label: '电话' },
  { value: '微信', label: '微信' },
  { value: '拜访', label: '拜访' },
  { value: '邮件', label: '邮件' },
  { value: '其他', label: '其他' }
]

// Watch for form changes
watch(values, () => {
  isDirty.value = true
}, { deep: true })

// Reset form when dialog opens
watch(() => props.open, (newOpen) => {
  if (newOpen) {
    resetForm({
      values: {
        method: '',
        content: '',
        next_follow_time: getDefaultNextFollowTime(),
        next_action: ''
      }
    })
    isDirty.value = false
  }
})

// Form submission
const onSubmit = handleSubmit(async (formValues) => {
  submitting.value = true
  try {
    await customerFollowUpApi.createFollowUp(props.customerId, {
      method: formValues['method'],
      content: formValues['content'],
      next_follow_time: formValues['next_follow_time'] ?? null,
      next_action: formValues['next_action'] ?? null
    })
    toast.success('跟进记录添加成功')
    isDirty.value = false
    visible.value = false
    emit('success')
  } catch {
    toast.error('添加跟进记录失败')
  } finally {
    submitting.value = false
  }
})

// Cancel operation
function handleCancel(): void {
  if (isDirty.value) {
    showConfirmDialog.value = true
  } else {
    visible.value = false
  }
}

// Confirm discard changes
function confirmCancel(): void {
  showConfirmDialog.value = false
  visible.value = false
}

// Continue editing
function continueEditing(): void {
  showConfirmDialog.value = false
}
</script>

<template>
  <Dialog v-model:open="visible">
    <DialogContent class="sm:max-w-[500px]">
      <DialogHeader>
        <DialogTitle>添加跟进记录</DialogTitle>
        <DialogDescription class="sr-only">记录本次跟进的详细信息</DialogDescription>
      </DialogHeader>

      <form class="space-y-4" @submit="onSubmit">
        <!-- Follow-up Method (RadioGroup) -->
        <div class="space-y-2">
          <Label class="text-sm font-medium">跟进方式 <span class="text-destructive">*</span></Label>
          <RadioGroup
            v-model="methodValue"
            class="flex flex-wrap gap-4"
          >
            <div
              v-for="option in methodOptions"
              :key="option.value"
              class="flex items-center space-x-2"
            >
              <RadioGroupItem :id="`method-${option.value}`" :value="option.value" />
              <Label :for="`method-${option.value}`" class="cursor-pointer">{{ option.label }}</Label>
            </div>
          </RadioGroup>
          <p v-if="methodError" class="text-sm text-destructive">{{ methodError }}</p>
        </div>

        <!-- Follow-up Content (Textarea, required) -->
        <FormField v-slot="{ componentField }" name="content">
          <FormItem>
            <FormLabel>跟进内容 *</FormLabel>
            <FormControl>
              <Textarea
                v-bind="componentField as any"
                :rows="4"
                placeholder="请输入跟进内容"
                class="resize-none"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Next Follow-up Time (Input type="date") -->
        <FormField v-slot="{ componentField }" name="next_follow_time">
          <FormItem>
            <FormLabel>下次跟进时间</FormLabel>
            <FormControl>
              <Input
                v-bind="componentField as any"
                type="date"
                class="h-11 sm:h-8"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Next Action (Textarea) -->
        <FormField v-slot="{ componentField }" name="next_action">
          <FormItem>
            <FormLabel>下一步动作</FormLabel>
            <FormControl>
              <Textarea
                v-bind="componentField as any"
                :rows="3"
                placeholder="请输入下一步动作（可选）"
                class="resize-none"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- DialogFooter -->
        <DialogFooter class="mt-6 pt-4 border-t">
          <Button variant="outline" type="button" @click="handleCancel">
            取消
          </Button>
          <Button type="submit" :loading="submitting">
            提交
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>

  <!-- Confirm discard changes dialog -->
  <AlertDialog v-model:open="showConfirmDialog">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>放弃更改？</AlertDialogTitle>
        <AlertDialogDescription>
          您有未保存的更改，确定要关闭吗？
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel @click="continueEditing">
          继续编辑
        </AlertDialogCancel>
        <AlertDialogAction @click="confirmCancel">
          放弃更改
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>