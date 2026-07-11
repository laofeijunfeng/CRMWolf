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
import { Switch } from '@/components/ui/switch'
import { handleApiError } from '@/utils/errorHandler'
import customerApi, { type ContactResponse, type ContactCreate, type ContactUpdate } from '@/api/customer'

// Zod schema for form validation
const schema = toTypedSchema(
  z.object({
    name: z.string().min(1, '请输入姓名').max(50, '姓名不能超过50字'),
    gender: z.enum(['男', '女']).optional(),
    position: z.string().max(50, '职位不能超过50字').optional(),
    is_decision_maker: z.boolean().optional(),
    mobile: z.string().min(1, '请输入手机号').regex(/^1[3-9]\d{9}$/, '请输入正确的手机号'),
    email: z.string().email('请输入正确的邮箱').optional().or(z.literal('')),
    wechat_id: z.string().max(50, '微信号不能超过50字').optional()
  })
)

interface Props {
  customerId: number
  open: boolean
  contact?: ContactResponse | null
}

interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// VeeValidate form setup
const { handleSubmit, resetForm, setValues, values } = useForm({
  validationSchema: schema,
  initialValues: {
    name: '',
    gender: undefined,
    position: '',
    is_decision_maker: false,
    mobile: '',
    email: '',
    wechat_id: ''
  }
})

// Use useField for RadioGroup and Switch to handle type compatibility
const { value: genderValue } = useField<string | undefined>('gender')
const { value: isDecisionMakerValue } = useField<boolean>('is_decision_maker')

// State
const submitting = ref(false)
const isDirty = ref(false)
const showConfirmDialog = ref(false)

// Computed property for edit mode
const isEdit = computed(() => !!props.contact)

// Computed property for dialog visibility
const visible = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val)
})

// Watch for form changes
watch(values, () => {
  isDirty.value = true
}, { deep: true })

// Reset or populate form when dialog opens
watch(() => props.open, (newOpen) => {
  if (newOpen) {
    if (props.contact) {
      // Edit mode: populate form with contact data
      setValues({
        name: props.contact.name,
        gender: props.contact.gender === 1 ? '男' : props.contact.gender === 0 ? '女' : undefined,
        position: props.contact.position ?? '',
        is_decision_maker: props.contact.is_decision_maker,
        mobile: props.contact.mobile,
        email: props.contact.email ?? '',
        wechat_id: props.contact.wechat_id ?? ''
      })
    } else {
      // Create mode: reset form
      resetForm({
        values: {
          name: '',
          gender: undefined,
          position: '',
          is_decision_maker: false,
          mobile: '',
          email: '',
          wechat_id: ''
        }
      })
    }
    // Reset dirty state after form is populated/reset
    setTimeout(() => {
      isDirty.value = false
    }, 100)
  }
})

// Form submission
const onSubmit = handleSubmit(async (formValues) => {
  submitting.value = true
  try {
    const data: ContactCreate | ContactUpdate = {
      name: formValues.name,
      gender: formValues.gender ?? null,
      position: formValues.position ?? null,
      is_decision_maker: formValues.is_decision_maker ?? false,
      mobile: formValues.mobile,
      email: formValues.email ?? null,
      wechat_id: formValues.wechat_id ?? null
    }

    if (isEdit.value && props.contact) {
      await customerApi.updateContact(props.contact.id, data)
      toast.success('联系人更新成功')
    } else {
      await customerApi.createContact(props.customerId, data as ContactCreate)
      toast.success('联系人创建成功')
    }

    isDirty.value = false
    visible.value = false
    emit('success')
  } catch (error) {
    handleApiError(error, isEdit.value ? '更新联系人' : '创建联系人')
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
        <DialogTitle>{{ isEdit ? '编辑联系人' : '新建联系人' }}</DialogTitle>
      </DialogHeader>

      <form class="space-y-4" @submit="onSubmit">
        <!-- Name (required) -->
        <FormField v-slot="{ componentField }" name="name">
          <FormItem>
            <FormLabel>姓名 <span class="text-destructive">*</span></FormLabel>
            <FormControl>
              <Input
                v-bind="componentField"
                placeholder="请输入姓名"
                class="h-11 sm:h-8"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Gender (RadioGroup) -->
        <div class="space-y-2">
          <Label class="text-sm font-medium">性别</Label>
          <RadioGroup
            v-model="genderValue"
            class="flex gap-4"
          >
            <div class="flex items-center space-x-2">
              <RadioGroupItem id="gender-male" value="男" />
              <Label for="gender-male" class="cursor-pointer">男</Label>
            </div>
            <div class="flex items-center space-x-2">
              <RadioGroupItem id="gender-female" value="女" />
              <Label for="gender-female" class="cursor-pointer">女</Label>
            </div>
          </RadioGroup>
        </div>

        <!-- Position -->
        <FormField v-slot="{ componentField }" name="position">
          <FormItem>
            <FormLabel>职位</FormLabel>
            <FormControl>
              <Input
                v-bind="componentField"
                placeholder="请输入职位"
                class="h-11 sm:h-8"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Is Decision Maker (Switch) -->
        <div class="flex items-center space-x-2">
          <Switch
            id="is_decision_maker"
            v-model:checked="isDecisionMakerValue"
          />
          <Label for="is_decision_maker" class="cursor-pointer">是否决策者</Label>
        </div>

        <!-- Mobile (required) -->
        <FormField v-slot="{ componentField }" name="mobile">
          <FormItem>
            <FormLabel>手机号 <span class="text-destructive">*</span></FormLabel>
            <FormControl>
              <Input
                v-bind="componentField"
                type="tel"
                autocomplete="tel"
                placeholder="请输入手机号"
                class="h-11 sm:h-8"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Email -->
        <FormField v-slot="{ componentField }" name="email">
          <FormItem>
            <FormLabel>邮箱</FormLabel>
            <FormControl>
              <Input
                v-bind="componentField"
                type="email"
                autocomplete="email"
                placeholder="请输入邮箱"
                class="h-11 sm:h-8"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- WeChat ID -->
        <FormField v-slot="{ componentField }" name="wechat_id">
          <FormItem>
            <FormLabel>微信号</FormLabel>
            <FormControl>
              <Input
                v-bind="componentField"
                placeholder="请输入微信号"
                class="h-11 sm:h-8"
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
            {{ submitting ? '提交中...' : '确定' }}
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