<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Field, useForm, useField } from 'vee-validate'
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
import { useDialogCloseGuard } from '@/composables/useDialogCloseGuard'
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
  elevated?: boolean
  customerId: string
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

// Computed property for edit mode
const isEdit = computed(() => !!props.contact)

// Computed property for dialog visibility
const visible = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val)
})

const closeGuard = useDialogCloseGuard({
  isDirty: isDirty,
  submitting,
  emitOpen: (open) => emit('update:open', open),
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
}, { deep: true, flush: 'sync' })

// Reset or populate form when dialog opens
watch(() => props.open, (newOpen) => {
  if (!newOpen) {
    if (closeGuard.handleParentClose()) return
    return
  }

  if (newOpen) {
    closeGuard.reset()
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
    closeGuard.approveClose()
    visible.value = false
    emit('success')
  } catch (error) {
    handleApiError(error, isEdit.value ? '更新联系人' : '创建联系人')
  } finally {
    submitting.value = false
  }
})

// Cancel operation
function handleOpenChange(open: boolean): void {
  closeGuard.handleOpenChange(open)
}

function handleCancel(): void {
  closeGuard.requestClose()
}
</script>

<template>
  <Dialog :open="props.open" @update:open="handleOpenChange">
    <DialogContent v-bind="elevated ? { elevated: true } : {}" class="contact-form-dialog">
      <DialogHeader>
        <DialogTitle>{{ isEdit ? '编辑联系人' : '新建联系人' }}</DialogTitle>
        <DialogDescription class="sr-only">填写联系人信息</DialogDescription>
      </DialogHeader>

      <div class="contact-form-dialog__body">

      <form id="contact-form" class="space-y-4" @submit="onSubmit">
        <Field v-slot="{ value, handleChange, errorMessage }" name="name">
          <InputField
            id="contact-name"
            :error="errorMessage ?? ''"
            :model-value="String(value ?? '')"
            label="姓名"
            required
            placeholder="请输入姓名"
            @update:model-value="handleChange"
          />
        </Field>

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

        <Field v-slot="{ value, handleChange, errorMessage }" name="position">
          <InputField
            id="contact-position"
            :error="errorMessage ?? ''"
            :model-value="String(value ?? '')"
            label="职位"
            required
            placeholder="请输入职位"
            @update:model-value="handleChange"
          />
        </Field>

        <!-- Is Decision Maker (Switch) -->
        <div class="flex items-center space-x-2">
          <Switch
            id="is_decision_maker"
            :checked="isDecisionMakerValue"
            @update:checked="isDecisionMakerValue = $event"
          />
          <Label for="is_decision_maker" class="cursor-pointer">是否决策者</Label>
        </div>

        <Field v-slot="{ value, handleChange, errorMessage }" name="mobile">
          <InputField
            id="contact-mobile"
            :error="errorMessage ?? ''"
            :model-value="String(value ?? '')"
            label="手机号"
            required
            type="tel"
            autocomplete="tel"
            placeholder="请输入手机号"
            @update:model-value="handleChange"
          />
        </Field>

        <Field v-slot="{ value, handleChange, errorMessage }" name="email">
          <InputField
            id="contact-email"
            :error="errorMessage ?? ''"
            :model-value="String(value ?? '')"
            label="邮箱"
            type="email"
            autocomplete="email"
            placeholder="请输入邮箱"
            @update:model-value="handleChange"
          />
        </Field>

        <Field v-slot="{ value, handleChange, errorMessage }" name="wechat_id">
          <InputField
            id="contact-wechat-id"
            :error="errorMessage ?? ''"
            :model-value="String(value ?? '')"
            label="微信号"
            placeholder="请输入微信号"
            @update:model-value="handleChange"
          />
        </Field>

        <Field v-if="reportsToOptions.length > 0" v-slot="{ value, handleChange, errorMessage }" name="reports_to">
          <SelectField
            id="contact-reports-to"
            :error="errorMessage ?? ''"
            :model-value="String(value ?? '')"
            label="汇报对象"
            :options="reportsToOptions"
            placeholder="选择汇报对象"
            @update:model-value="handleChange"
          />
        </Field>

        <Field v-slot="{ value, handleChange, errorMessage }" name="remark">
          <TextareaField
            id="contact-remark"
            :error="errorMessage ?? ''"
            :model-value="String(value ?? '')"
            label="备注"
            placeholder="请输入备注"
            control-class="min-h-20 resize-none"
            @update:model-value="handleChange"
          />
        </Field>

        <!-- DialogFooter -->
        </form>
      </div>

        <DialogFooter class="contact-form-dialog__footer">
          <Button variant="outline" type="button" :disabled="submitting" @click="handleCancel">
            取消
          </Button>
          <Button type="submit" form="contact-form" :loading="submitting">
            确定
          </Button>
        </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<style lang="scss">
@use '@/styles/tokens.scss' as *;

/* 非 scoped：DialogContent 经 Portal 渲染，scoped data 属性不随 class 传递 */
.contact-form-dialog {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  max-height: min(90vh, 90dvh);
  overflow: hidden;
}

.contact-form-dialog__body {
  display: flex;
  min-height: 0;
  flex-direction: column;
  gap: $space-4;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-inline: calc(2px + 2px);
  scroll-padding-bottom: calc($space-6 + var(--safe-bottom));
}

.contact-form-dialog__footer {
  gap: $space-2;
  padding-top: $space-4;
  border-top: 1px solid hsl(var(--border));
}
</style>
