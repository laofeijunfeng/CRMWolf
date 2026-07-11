<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
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
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import customerFollowUpApi from '@/api/customerFollowUp'

// Form values interface
interface FollowUpFormValues {
  method: string
  content: string
  next_follow_time: string
  next_action: string
}

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

// State
const submitting = ref(false)
const isDirty = ref(false)
const showConfirmDialog = ref(false)
const formValues = ref<FollowUpFormValues>({
  method: '',
  content: '',
  next_follow_time: getDefaultNextFollowTime(),
  next_action: ''
})

// Compute default date: 3 days from now
function getDefaultNextFollowTime(): string {
  const date = new Date()
  date.setDate(date.getDate() + 3)
  const parts = date.toISOString().split('T')
  return parts[0] ?? ''
}

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
watch(formValues, () => {
  isDirty.value = true
}, { deep: true })

// Reset form when dialog opens
watch(() => props.open, (newOpen) => {
  if (newOpen) {
    formValues.value = {
      method: '',
      content: '',
      next_follow_time: getDefaultNextFollowTime(),
      next_action: ''
    }
    isDirty.value = false
  }
})

// Form validation
const errors = ref<Record<string, string>>({})

function validateForm(): boolean {
  errors.value = {}

  if (!formValues.value.method) {
    errors.value['method'] = '请选择跟进方式'
  }

  if (!formValues.value.content) {
    errors.value['content'] = '请输入跟进内容'
  } else if (formValues.value.content.length > 500) {
    errors.value['content'] = '内容不能超过500字'
  }

  if (formValues.value.next_action && formValues.value.next_action.length > 200) {
    errors.value['next_action'] = '动作不能超过200字'
  }

  return Object.keys(errors.value).length === 0
}

// Form submission
async function handleSubmit(): Promise<void> {
  if (!validateForm()) {
    return
  }

  submitting.value = true
  try {
    await customerFollowUpApi.createFollowUp(props.customerId, {
      method: formValues.value.method,
      content: formValues.value.content,
      next_follow_time: formValues.value.next_follow_time || null,
      next_action: formValues.value.next_action || null
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
}

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
      </DialogHeader>

      <form class="space-y-4" @submit.prevent="handleSubmit">
        <!-- Follow-up Method (RadioGroup) -->
        <div class="space-y-2">
          <Label class="text-sm font-medium">跟进方式 <span class="text-destructive">*</span></Label>
          <RadioGroup
            v-model="formValues.method"
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
          <p v-if="errors['method']" class="text-sm text-destructive">{{ errors['method'] }}</p>
        </div>

        <!-- Follow-up Content (Textarea, required) -->
        <div class="space-y-2">
          <Label class="text-sm font-medium">跟进内容 <span class="text-destructive">*</span></Label>
          <Textarea
            v-model="formValues.content"
            :rows="4"
            placeholder="请输入跟进内容"
            class="resize-none"
          />
          <p v-if="errors['content']" class="text-sm text-destructive">{{ errors['content'] }}</p>
        </div>

        <!-- Next Follow-up Time (Input type="date") -->
        <div class="space-y-2">
          <Label class="text-sm font-medium">下次跟进时间</Label>
          <Input
            v-model="formValues.next_follow_time"
            type="date"
            class="h-11 sm:h-8"
          />
        </div>

        <!-- Next Action (Textarea) -->
        <div class="space-y-2">
          <Label class="text-sm font-medium">下一步动作</Label>
          <Textarea
            v-model="formValues.next_action"
            :rows="3"
            placeholder="请输入下一步动作（可选）"
            class="resize-none"
          />
          <p v-if="errors['next_action']" class="text-sm text-destructive">{{ errors['next_action'] }}</p>
        </div>

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