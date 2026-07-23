<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useForm, useField } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
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
import { Button } from '@/components/ui/button'
import {
  InputField,
  SegmentedChoiceControl,
  SelectField,
  TextareaField,
} from '@/components/crmwolf'
import { handleApiError } from '@/utils/errorHandler'
import customerApi, { type CustomerCreate, type CustomerUpdate } from '@/api/customer'
import procurementApi, { type ProcurementMethodOption } from '@/api/procurement'
import {
  customerFormSchema,
  customerCreateSchema,
  customerSourceOptions,
  companyScaleOptions,
  type CustomerForm,
  type CustomerCreateForm
} from '@/schemas/customer-form'

interface Props {
  open: boolean
  mode: 'create' | 'edit'
  customerId?: number
}

interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// Use different schemas for create/edit modes
const schema = computed(() =>
  props.mode === 'create'
    ? toTypedSchema(customerCreateSchema)
    : toTypedSchema(customerFormSchema)
)

// VeeValidate form setup
const { handleSubmit, resetForm, setValues, values } = useForm<CustomerForm | CustomerCreateForm>({
  validationSchema: schema,
  initialValues: {
    account_name: '',
    city: '',
    address: '',
    company_scale: undefined,
    source: undefined,
    default_procurement_method_id: undefined,
    contact_name: '',
    contact_mobile: '',
    contact_position: '',
    contact_gender: undefined
  } as unknown as CustomerCreateForm
})
const { value: contactGenderValue, errorMessage: contactGenderError } = useField<string>('contact_gender')

const genderOptions = [
  { value: '男', label: '男', tone: 'primary' as const },
  { value: '女', label: '女', tone: 'success' as const },
]

// State
const submitting = ref(false)
const loading = ref(false)
const procurementMethodsLoading = ref(false)
const procurementMethodOptions = ref<ProcurementMethodOption[]>([])
const procurementMethodSelectOptions = computed(() =>
  procurementMethodOptions.value.map(option => ({
    value: option.id,
    label: option.name,
  }))
)
const isDirty = ref(false)
const showConfirmDialog = ref(false)

// Computed property for dialog visibility
const visible = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val)
})

// Watch for form changes
watch(values, () => {
  isDirty.value = true
}, { deep: true })

async function fetchProcurementMethodOptions(): Promise<void> {
  if (procurementMethodOptions.value.length > 0 || procurementMethodsLoading.value) return

  procurementMethodsLoading.value = true
  try {
    procurementMethodOptions.value = await procurementApi.getProcurementMethodOptions()
  } catch (error) {
    handleApiError(error, '获取采购方式')
  } finally {
    procurementMethodsLoading.value = false
  }
}

function normalizeCompanyScale(value: string | null): CustomerForm['company_scale'] | undefined {
  return companyScaleOptions.some(option => option.value === value)
    ? value as CustomerForm['company_scale']
    : undefined
}

function normalizeCustomerSource(value: string | null): CustomerForm['source'] | undefined {
  return customerSourceOptions.some(option => option.value === value)
    ? value as CustomerForm['source']
    : undefined
}

function mapContactGenderToApi(gender: string): '1' | '2' {
  return gender === '女' ? '2' : '1'
}

function handleProcurementMethodChange(value: string, handleChange: (value: number | undefined) => void): void {
  const procurementMethodId = Number(value)
  handleChange(Number.isFinite(procurementMethodId) && procurementMethodId > 0 ? procurementMethodId : undefined)
}

// Load customer detail in edit mode
watch([(): boolean => props.open, (): number | undefined => props.customerId], async ([open, customerId]): Promise<void> => {
  if (open) {
    void fetchProcurementMethodOptions()
  }

  if (open && props.mode === 'edit' && customerId !== undefined && customerId !== null) {
    loading.value = true
    try {
      const customer = await customerApi.getCustomerDetail(customerId)
      setValues({
        account_name: customer.account_name,
        city: customer.city,
        address: customer.address ?? '',
        company_scale: normalizeCompanyScale(customer.company_scale),
        source: normalizeCustomerSource(customer.source),
        default_procurement_method_id: customer.default_procurement_method_id ?? undefined,
        // Profile fields (only in edit mode)
        company_background: customer.company_background ?? '',
        company_website: customer.company_website ?? '',
        main_business: customer.main_business ?? '',
        project_background: customer.project_background ?? ''
      } as Partial<CustomerForm>)
      // Reset dirty state after loading
      isDirty.value = false
    } catch (error) {
      handleApiError(error, '加载客户详情')
      visible.value = false
    } finally {
      loading.value = false
    }
  } else if (open && props.mode === 'create') {
    // Reset form for create mode
    resetForm({
      values: {
        account_name: '',
        city: '',
        address: '',
        company_scale: undefined,
        source: undefined,
        default_procurement_method_id: undefined,
        contact_name: '',
        contact_mobile: '',
        contact_position: '',
        contact_gender: undefined
      } as unknown as CustomerCreateForm
    })
    isDirty.value = false
  }
}, { immediate: true })

// Form submission
const onSubmit = handleSubmit(async (formValues): Promise<void> => {
  submitting.value = true
  try {
    if (props.mode === 'create') {
      // Cast to CustomerCreateForm since schema validates required fields
      const createData = formValues as CustomerCreateForm
      const data: CustomerCreate = {
        account_name: createData.account_name,
        city: createData.city,
        address: createData.address !== '' && createData.address !== undefined ? createData.address : null,
        company_scale: createData.company_scale ?? null,
        source: createData.source ?? null,
        default_procurement_method_id: createData.default_procurement_method_id ?? null,
        primary_contact: {
          name: createData.contact_name,
          mobile: createData.contact_mobile,
          position: createData.contact_position,
          gender: mapContactGenderToApi(createData.contact_gender),
          is_decision_maker: false
        }
      }
      await customerApi.createCustomer(data)
      toast.success('客户创建成功')
    } else if (props.customerId !== undefined) {
      // Cast to CustomerForm for edit mode with profile fields
      const editData = formValues as CustomerForm
      const data: CustomerUpdate = {
        account_name: editData.account_name,
        city: editData.city,
        address: editData.address !== '' && editData.address !== undefined ? editData.address : null,
        company_scale: editData.company_scale ?? null,
        source: editData.source ?? null,
        default_procurement_method_id: editData.default_procurement_method_id ?? null,
        // Profile fields (only in edit mode)
        company_background: editData.company_background !== '' && editData.company_background !== undefined ? editData.company_background : null,
        company_website: editData.company_website !== '' && editData.company_website !== undefined ? editData.company_website : null,
        main_business: editData.main_business !== '' && editData.main_business !== undefined ? editData.main_business : null,
        project_background: editData.project_background !== '' && editData.project_background !== undefined ? editData.project_background : null
      }
      await customerApi.updateCustomer(props.customerId, data)
      toast.success('客户更新成功')
    }

    isDirty.value = false
    visible.value = false
    emit('success')
  } catch (error) {
    handleApiError(error, props.mode === 'create' ? '创建客户' : '更新客户')
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
    <DialogContent class="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle>{{ mode === 'create' ? '新建客户' : '编辑客户' }}</DialogTitle>
        <DialogDescription class="sr-only">填写客户信息</DialogDescription>
      </DialogHeader>

      <div v-if="loading" class="flex justify-center py-8">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>

      <form v-else class="space-y-4" @submit="onSubmit">
        <!-- Basic Information Section -->
        <div class="space-y-4">
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <!-- Customer Name (required) -->
            <FormField v-slot="{ value, handleChange }" name="account_name">
              <FormItem>
                <InputField
                  id="customer-account-name"
                  :model-value="String(value ?? '')"
                  label="客户名称"
                  required
                  autocomplete="organization"
                  placeholder="请输入客户名称"
                  @update:model-value="handleChange"
                />
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- City (required) -->
            <FormField v-slot="{ value, handleChange }" name="city">
              <FormItem>
                <InputField
                  id="customer-city"
                  :model-value="String(value ?? '')"
                  label="所在城市"
                  required
                  autocomplete="address-level2"
                  placeholder="请输入城市"
                  @update:model-value="handleChange"
                />
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- Customer Source -->
            <FormField v-slot="{ value, handleChange }" name="source">
              <FormItem>
                <SelectField
                  id="customer-source"
                  :model-value="String(value ?? '')"
                  label="客户来源"
                  required
                  :options="customerSourceOptions"
                  placeholder="请选择来源"
                  @update:model-value="handleChange"
                />
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- Company Scale -->
            <FormField v-slot="{ value, handleChange }" name="company_scale">
              <FormItem>
                <SelectField
                  id="customer-company-scale"
                  :model-value="String(value ?? '')"
                  label="公司规模"
                  required
                  :options="companyScaleOptions"
                  placeholder="请选择规模"
                  @update:model-value="handleChange"
                />
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- Default Procurement Method -->
            <FormField v-slot="{ value, handleChange }" name="default_procurement_method_id">
              <FormItem>
                <SelectField
                  id="customer-procurement-method"
                  :model-value="String(value ?? '')"
                  label="采购方式"
                  required
                  :options="procurementMethodSelectOptions"
                  :placeholder="procurementMethodsLoading ? '采购方式加载中' : '请选择采购方式'"
                  :disabled="procurementMethodsLoading"
                  @update:model-value="(selectedValue) => handleProcurementMethodChange(selectedValue, handleChange)"
                />
                <FormMessage />
              </FormItem>
            </FormField>
          </div>

          <!-- Address (full width) -->
          <FormField v-slot="{ value, handleChange }" name="address">
            <FormItem>
              <InputField
                id="customer-address"
                :model-value="String(value ?? '')"
                label="详细地址"
                autocomplete="street-address"
                placeholder="请输入详细地址"
                @update:model-value="handleChange"
              />
              <FormMessage />
            </FormItem>
          </FormField>
        </div>

        <div v-if="mode === 'create'" class="space-y-4 pt-4 border-t">
          <h3 class="text-sm font-medium text-muted-foreground">联系人信息</h3>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <FormField v-slot="{ value, handleChange }" name="contact_name">
              <FormItem>
                <InputField
                  id="customer-contact-name"
                  :model-value="String(value ?? '')"
                  label="联系人姓名"
                  required
                  autocomplete="name"
                  placeholder="请输入联系人姓名"
                  @update:model-value="handleChange"
                />
                <FormMessage />
              </FormItem>
            </FormField>

            <FormField v-slot="{ value, handleChange }" name="contact_mobile">
              <FormItem>
                <InputField
                  id="customer-contact-mobile"
                  :model-value="String(value ?? '')"
                  label="联系电话"
                  required
                  type="tel"
                  autocomplete="tel"
                  placeholder="请输入联系电话"
                  @update:model-value="handleChange"
                />
                <FormMessage />
              </FormItem>
            </FormField>

            <FormField v-slot="{ value, handleChange }" name="contact_position">
              <FormItem>
                <InputField
                  id="customer-contact-position"
                  :model-value="String(value ?? '')"
                  label="职位"
                  required
                  placeholder="请输入职位"
                  @update:model-value="handleChange"
                />
                <FormMessage />
              </FormItem>
            </FormField>

            <div class="space-y-2">
              <div id="customer-contact-gender-label" class="text-sm font-medium">
                性别 <span class="text-destructive">*</span>
              </div>
              <SegmentedChoiceControl
                v-model="contactGenderValue"
                :options="genderOptions"
                labelled-by="customer-contact-gender-label"
                id-prefix="customer-contact-gender"
              />
              <p v-if="contactGenderError" class="text-sm font-medium text-destructive">
                {{ contactGenderError }}
              </p>
            </div>
          </div>
        </div>

        <!-- Profile Section (only in edit mode) -->
        <div v-if="mode === 'edit'" class="space-y-4 pt-4 border-t">
          <h3 class="text-sm font-medium text-muted-foreground">档案信息</h3>

          <!-- Company Background -->
          <FormField v-slot="{ value, handleChange }" name="company_background">
            <FormItem>
              <TextareaField
                id="customer-company-background"
                :model-value="String(value ?? '')"
                label="公司背景"
                :rows="3"
                placeholder="请输入公司背景信息"
                @update:model-value="handleChange"
              />
              <FormMessage />
            </FormItem>
          </FormField>

          <!-- Company Website -->
          <FormField v-slot="{ value, handleChange }" name="company_website">
            <FormItem>
              <InputField
                id="customer-company-website"
                :model-value="String(value ?? '')"
                label="公司网站"
                type="url"
                autocomplete="url"
                placeholder="请输入公司网站URL"
                @update:model-value="handleChange"
              />
              <FormMessage />
            </FormItem>
          </FormField>

          <!-- Main Business -->
          <FormField v-slot="{ value, handleChange }" name="main_business">
            <FormItem>
              <TextareaField
                id="customer-main-business"
                :model-value="String(value ?? '')"
                label="主营业务"
                :rows="3"
                placeholder="请输入主营业务信息"
                @update:model-value="handleChange"
              />
              <FormMessage />
            </FormItem>
          </FormField>

          <!-- Project Background -->
          <FormField v-slot="{ value, handleChange }" name="project_background">
            <FormItem>
              <TextareaField
                id="customer-project-background"
                :model-value="String(value ?? '')"
                label="项目背景"
                :rows="3"
                placeholder="请输入项目背景信息"
                @update:model-value="handleChange"
              />
              <FormMessage />
            </FormItem>
          </FormField>
        </div>

        <!-- DialogFooter -->
        <DialogFooter class="mt-6 pt-4 border-t">
          <Button variant="outline" type="button" @click="handleCancel">
            取消
          </Button>
          <Button type="submit" :loading="submitting">
            {{ submitting ? '提交中...' : (mode === 'create' ? '创建' : '保存') }}
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
