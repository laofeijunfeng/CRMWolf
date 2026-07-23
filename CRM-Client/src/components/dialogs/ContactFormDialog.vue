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
  FormField,
  FormItem,
  FormMessage,
} from '@/components/ui/form'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import {
  InputField,
  SelectField,
  SegmentedChoiceControl,
  TextareaField,
} from '@/components/crmwolf'
import { handleApiError } from '@/utils/errorHandler'
import customerApi, { type ContactResponse, type ContactCreate, type ContactUpdate } from '@/api/customer'

// Zod schema for form validation
const schema = toTypedSchema(
  z.object({
    name: z.string().min(1, '请输入姓名').max(50, '姓名不能超过50字'),
    gender: z.enum(['男', '女'], {
      required_error: '请选择性别',
      invalid_type_error: '请选择性别'
    }),
    position: z.string().min(1, '请输入职位').max(50, '职位不能超过50字'),
    is_decision_maker: z.boolean().optional(),
    mobile: z.string().min(1, '请输入手机号').regex(/^1[3-9]\d{9}$/, '请输入正确的手机号'),
    email: z.string().email('请输入正确的邮箱').optional().or(z.literal('')),
    wechat_id: z.string().max(50, '微信号不能超过50字').optional(),
    remark: z.string().max(500, '备注不能超过500字').optional(),
    reports_to: z.string().optional().nullable().transform(val => val !== null && val !== undefined && val !== '' ? Number(val) : null)
  })
)

interface Props {
  customerId: number
  open: boolean
  contact?: ContactResponse | null
  availableContacts?: ContactResponse[] // For reports_to field
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
    position: '',
    is_decision_maker: false,
    mobile: '',
    email: '',
    wechat_id: '',
    remark: '',
    reports_to: null
  }
})

// Use useField for RadioGroup and Switch to handle type compatibility
const { value: genderValue, errorMessage: genderError } = useField<string | undefined>('gender')
const { value: isDecisionMakerValue } = useField<boolean>('is_decision_maker')
const genderRadioValue = computed({
  get: () => genderValue.value ?? '',
  set: (value: string) => {
    genderValue.value = value || undefined
  }
})

const genderOptions = [
  { value: '男', label: '男', tone: 'primary' as const },
  { value: '女', label: '女', tone: 'success' as const },
]
const reportsToOptions = computed(() =>
  (props.availableContacts ?? [])
    .filter(contact => contact.id !== props.contact?.id)
    .map(contact => ({
      value: contact.id,
      label: `${contact.name}${contact.position !== undefined && contact.position !== null && contact.position.trim().length > 0 ? ` (${contact.position})` : ''}`,
    }))
)

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

function mapContactGenderToForm(gender: number | null): '男' | '女' | undefined {
  if (gender === 1) return '男'
  if (gender === 2) return '女'
  return undefined
}

function mapContactGenderToApi(gender: string): '1' | '2' {
  if (gender === '男') return '1'
  if (gender === '女') return '2'
  return '1'
}

function normalizeOptionalText(value: string | null | undefined): string | null {
  const trimmed = value?.trim() ?? ''
  return trimmed === '' ? null : trimmed
}

// Watch for form changes
watch(values, () => {
  isDirty.value = true
}, { deep: true })

// Reset or populate form when dialog opens
watch(() => props.open, (newOpen) => {
  if (newOpen) {
    if (props.contact) {
      // Edit mode: populate form with contact data
      const formGender = mapContactGenderToForm(props.contact.gender)
      setValues({
        name: props.contact.name,
        ...(formGender ? { gender: formGender } : {}),
        position: props.contact.position ?? '',
        is_decision_maker: props.contact.is_decision_maker,
        mobile: props.contact.mobile,
        email: props.contact.email ?? '',
        wechat_id: props.contact.wechat_id ?? '',
        remark: props.contact.remark ?? '',
        reports_to: props.contact.reports_to?.toString() ?? null
      })
      genderValue.value = formGender
    } else {
      // Create mode: reset form
      resetForm({
        values: {
          name: '',
          position: '',
          is_decision_maker: false,
          mobile: '',
          email: '',
          wechat_id: '',
          remark: '',
          reports_to: null
        }
      })
      genderValue.value = undefined
    }
    // Reset dirty state immediately (no setTimeout)
    isDirty.value = false
  }
}, { immediate: true })

// Form submission
const onSubmit = handleSubmit(async (formValues) => {
  submitting.value = true
  try {
    const data: ContactCreate | ContactUpdate = {
      name: formValues.name.trim(),
      gender: mapContactGenderToApi(formValues.gender),
      position: formValues.position.trim(),
      is_decision_maker: formValues.is_decision_maker ?? false,
      mobile: formValues.mobile.trim(),
      email: normalizeOptionalText(formValues.email),
      wechat_id: normalizeOptionalText(formValues.wechat_id),
      remark: normalizeOptionalText(formValues.remark),
      reports_to: formValues.reports_to ?? null
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
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{{ isEdit ? '编辑联系人' : '新建联系人' }}</DialogTitle>
        <DialogDescription class="sr-only">填写联系人信息</DialogDescription>
      </DialogHeader>

      <form class="space-y-4" @submit="onSubmit">
        <FormField v-slot="{ value, handleChange }" name="name">
          <FormItem>
            <InputField
              id="contact-name"
              :model-value="String(value ?? '')"
              label="姓名"
              required
              placeholder="请输入姓名"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Gender -->
        <div class="space-y-2">
          <div id="contact-gender-label" class="text-sm font-medium">
            性别 <span class="text-destructive">*</span>
          </div>
          <SegmentedChoiceControl
            v-model="genderRadioValue"
            :options="genderOptions"
            labelled-by="contact-gender-label"
            id-prefix="contact-gender"
          />
          <p v-if="genderError" class="text-sm font-medium text-destructive">
            {{ genderError }}
          </p>
        </div>

        <FormField v-slot="{ value, handleChange }" name="position">
          <FormItem>
            <InputField
              id="contact-position"
              :model-value="String(value ?? '')"
              label="职位"
              required
              placeholder="请输入职位"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Is Decision Maker (Switch) -->
        <div class="flex items-center space-x-2">
          <Switch
            id="is_decision_maker"
            :checked="isDecisionMakerValue"
            @update:checked="isDecisionMakerValue = $event"
          />
          <Label for="is_decision_maker" class="cursor-pointer">是否决策者</Label>
        </div>

        <FormField v-slot="{ value, handleChange }" name="mobile">
          <FormItem>
            <InputField
              id="contact-mobile"
              :model-value="String(value ?? '')"
              label="手机号"
              required
              type="tel"
              autocomplete="tel"
              placeholder="请输入手机号"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <FormField v-slot="{ value, handleChange }" name="email">
          <FormItem>
            <InputField
              id="contact-email"
              :model-value="String(value ?? '')"
              label="邮箱"
              type="email"
              autocomplete="email"
              placeholder="请输入邮箱"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <FormField v-slot="{ value, handleChange }" name="wechat_id">
          <FormItem>
            <InputField
              id="contact-wechat-id"
              :model-value="String(value ?? '')"
              label="微信号"
              placeholder="请输入微信号"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <FormField v-if="reportsToOptions.length > 0" v-slot="{ value, handleChange }" name="reports_to">
          <FormItem>
            <SelectField
              id="contact-reports-to"
              :model-value="String(value ?? '')"
              label="汇报对象"
              :options="reportsToOptions"
              placeholder="选择汇报对象"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <FormField v-slot="{ value, handleChange }" name="remark">
          <FormItem>
            <TextareaField
              id="contact-remark"
              :model-value="String(value ?? '')"
              label="备注"
              placeholder="请输入备注"
              control-class="min-h-20 resize-none"
              @update:model-value="handleChange"
            />
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
