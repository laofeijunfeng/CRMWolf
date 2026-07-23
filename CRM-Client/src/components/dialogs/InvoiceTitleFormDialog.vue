<script setup lang="ts">
/**
 * InvoiceTitleFormDialog.vue - 发票抬头表单对话框
 *
 * 用于创建/编辑客户发票抬头
 * 使用 VeeValidate + Zod 进行表单验证
 *
 * 技术栈：shadcn-vue + variables-v2.scss
 */
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
  FormField,
  FormItem,
  FormMessage,
} from '@/components/ui/form'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import {
  InputField,
  SegmentedChoiceControl,
} from '@/components/crmwolf'
import { handleApiError } from '@/utils/errorHandler'
import invoiceApi, {
  type InvoiceTitleResponse,
  type InvoiceTitleCreate,
  type InvoiceTitleUpdate,
  type TitleType
} from '@/api/invoice'

// ==================== Zod Schema ====================
const schema = toTypedSchema(
  z.object({
    title_type: z.enum(['COMPANY', 'PERSONAL']).default('COMPANY'),
    title: z.string().min(1, '请输入发票抬头名称').max(100, '名称不能超过100字'),
    taxpayer_id: z.string().min(1, '请输入税号').max(30, '税号不能超过30字'),
    bank_name: z.string().max(50, '银行名称不能超过50字').optional().or(z.literal('')),
    bank_account: z.string().max(30, '账号不能超过30字').optional().or(z.literal('')),
    address: z.string().max(200, '地址不能超过200字').optional().or(z.literal('')),
    phone: z.string().max(20, '电话不能超过20字').optional().or(z.literal(''))
  })
)

// ==================== Props & Emits ====================
interface Props {
  customerId: number
  open: boolean
  invoiceTitle?: InvoiceTitleResponse | null
}

interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// ==================== VeeValidate Setup ====================
const { handleSubmit, resetForm, setValues, values } = useForm({
  validationSchema: schema,
  initialValues: {
    title_type: 'COMPANY' as TitleType,
    title: '',
    taxpayer_id: '',
    bank_name: '',
    bank_account: '',
    address: '',
    phone: ''
  }
})

// Use useField for RadioGroup to handle type compatibility
const { value: titleTypeValue } = useField<TitleType>('title_type')

// ==================== State ====================
const submitting = ref(false)
const isDirty = ref(false)
const showConfirmDialog = ref(false)

// ==================== Computed ====================
const isEdit = computed(() => !!props.invoiceTitle)

const visible = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val)
})

const titleTypeOptions = [
  { value: 'COMPANY', label: '企业', tone: 'primary' as const },
  { value: 'PERSONAL', label: '个人', tone: 'success' as const },
]

// ==================== Watchers ====================
watch(values, () => {
  isDirty.value = true
}, { deep: true })

watch(() => props.open, (newOpen) => {
  if (newOpen) {
    if (props.invoiceTitle) {
      // Edit mode: populate form
      setValues({
        title_type: props.invoiceTitle.title_type,
        title: props.invoiceTitle.title,
        taxpayer_id: props.invoiceTitle.taxpayer_id,
        bank_name: props.invoiceTitle.bank_name ?? '',
        bank_account: props.invoiceTitle.bank_account ?? '',
        address: props.invoiceTitle.address ?? '',
        phone: props.invoiceTitle.phone ?? ''
      })
    } else {
      // Create mode: reset form
      resetForm({
        values: {
          title_type: 'COMPANY',
          title: '',
          taxpayer_id: '',
          bank_name: '',
          bank_account: '',
          address: '',
          phone: ''
        }
      })
    }
    // Reset dirty state after form is populated/reset
    setTimeout(() => {
      isDirty.value = false
    }, 100)
  }
})

// ==================== Methods ====================
const onSubmit = handleSubmit(async (formValues) => {
  submitting.value = true
  try {
    const data: InvoiceTitleCreate | InvoiceTitleUpdate = {
      title_type: formValues.title_type,
      title: formValues.title,
      taxpayer_id: formValues.taxpayer_id,
      bank_name: formValues.bank_name ?? null,
      bank_account: formValues.bank_account ?? null,
      address: formValues.address ?? null,
      phone: formValues.phone ?? null
    }

    if (isEdit.value && props.invoiceTitle) {
      await invoiceApi.updateInvoiceTitle(props.invoiceTitle.id, data as InvoiceTitleUpdate)
      toast.success('发票抬头更新成功')
    } else {
      await invoiceApi.createInvoiceTitle(props.customerId, data as InvoiceTitleCreate)
      toast.success('发票抬头创建成功')
    }

    isDirty.value = false
    visible.value = false
    emit('success')
  } catch (error) {
    handleApiError(error, isEdit.value ? '更新发票抬头' : '创建发票抬头')
  } finally {
    submitting.value = false
  }
})

function handleCancel(): void {
  if (isDirty.value) {
    showConfirmDialog.value = true
  } else {
    visible.value = false
  }
}

function confirmCancel(): void {
  showConfirmDialog.value = false
  visible.value = false
}

function continueEditing(): void {
  showConfirmDialog.value = false
}
</script>

<template>
  <Dialog v-model:open="visible">
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{{ isEdit ? '编辑发票抬头' : '新建发票抬头' }}</DialogTitle>
      </DialogHeader>

      <form class="space-y-4" @submit="onSubmit">
        <!-- Title Type -->
        <div class="space-y-2">
          <Label id="invoice-title-type-label" class="text-sm font-medium">
            类型 <span class="text-destructive">*</span>
          </Label>
          <SegmentedChoiceControl
            v-model="titleTypeValue"
            :options="titleTypeOptions"
            labelled-by="invoice-title-type-label"
            id-prefix="invoice-title-type"
          />
        </div>

        <!-- Title Name (required) -->
        <FormField v-slot="{ value, handleChange }" name="title">
          <FormItem>
            <InputField
              id="invoice-title-name"
              :model-value="String(value ?? '')"
              label="发票抬头"
              required
              placeholder="请输入发票抬头名称"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Taxpayer ID (required) -->
        <FormField v-slot="{ value, handleChange }" name="taxpayer_id">
          <FormItem>
            <InputField
              id="invoice-title-taxpayer-id"
              :model-value="String(value ?? '')"
              label="税号"
              required
              placeholder="请输入纳税人识别号"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Bank Name -->
        <FormField v-slot="{ value, handleChange }" name="bank_name">
          <FormItem>
            <InputField
              id="invoice-title-bank-name"
              :model-value="String(value ?? '')"
              label="开户银行"
              placeholder="请输入开户银行名称"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Bank Account -->
        <FormField v-slot="{ value, handleChange }" name="bank_account">
          <FormItem>
            <InputField
              id="invoice-title-bank-account"
              :model-value="String(value ?? '')"
              label="银行账号"
              placeholder="请输入银行账号"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Address -->
        <FormField v-slot="{ value, handleChange }" name="address">
          <FormItem>
            <InputField
              id="invoice-title-address"
              :model-value="String(value ?? '')"
              label="地址"
              placeholder="请输入注册地址"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Phone -->
        <FormField v-slot="{ value, handleChange }" name="phone">
          <FormItem>
            <InputField
              id="invoice-title-phone"
              :model-value="String(value ?? '')"
              label="电话"
              placeholder="请输入电话号码"
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

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;
</style>
