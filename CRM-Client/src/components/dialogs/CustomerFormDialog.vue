<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useForm } from 'vee-validate'
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
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
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
    default_procurement_method_id: undefined
  } as CustomerCreateForm
})

// State
const submitting = ref(false)
const loading = ref(false)
const procurementMethodsLoading = ref(false)
const procurementMethodOptions = ref<ProcurementMethodOption[]>([])
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

function normalizeCompanyScale(value: string | null): CustomerForm['company_scale'] {
  return companyScaleOptions.some(option => option.value === value)
    ? value as CustomerForm['company_scale']
    : undefined
}

function normalizeCustomerSource(value: string | null): CustomerForm['source'] {
  return customerSourceOptions.some(option => option.value === value)
    ? value as CustomerForm['source']
    : undefined
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
      })
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
        default_procurement_method_id: undefined
      } as CustomerCreateForm
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
        default_procurement_method_id: createData.default_procurement_method_id ?? null
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
    <DialogContent>
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
            <FormField v-slot="{ componentField }" name="account_name">
              <FormItem>
                <FormLabel>客户名称 <span class="text-destructive">*</span></FormLabel>
                <FormControl>
                  <Input
                    v-bind="componentField"
                    autocomplete="organization"
                    class="h-11 sm:h-8"
                    placeholder="请输入客户名称"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- City (required) -->
            <FormField v-slot="{ componentField }" name="city">
              <FormItem>
                <FormLabel>所在城市 <span class="text-destructive">*</span></FormLabel>
                <FormControl>
                  <Input
                    v-bind="componentField"
                    autocomplete="address-level2"
                    class="h-11 sm:h-8"
                    placeholder="请输入城市"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- Customer Source -->
            <FormField v-slot="{ componentField }" name="source">
              <FormItem>
                <FormLabel>客户来源</FormLabel>
                <Select v-bind="componentField">
                  <FormControl>
                    <SelectTrigger class="h-11 sm:h-8">
                      <SelectValue placeholder="请选择来源" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem
                      v-for="option in customerSourceOptions"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- Company Scale -->
            <FormField v-slot="{ componentField }" name="company_scale">
              <FormItem>
                <FormLabel>公司规模</FormLabel>
                <Select v-bind="componentField">
                  <FormControl>
                    <SelectTrigger class="h-11 sm:h-8">
                      <SelectValue placeholder="请选择规模" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem
                      v-for="option in companyScaleOptions"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- Default Procurement Method -->
            <FormField v-slot="{ componentField }" name="default_procurement_method_id">
              <FormItem>
                <FormLabel>采购方式</FormLabel>
                <Select v-bind="componentField" :disabled="procurementMethodsLoading">
                  <FormControl>
                    <SelectTrigger class="h-11 sm:h-8">
                      <SelectValue :placeholder="procurementMethodsLoading ? '采购方式加载中' : '请选择采购方式'" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem
                      v-for="option in procurementMethodOptions"
                      :key="option.id"
                      :value="option.id"
                    >
                      {{ option.name }}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            </FormField>
          </div>

          <!-- Address (full width) -->
          <FormField v-slot="{ componentField }" name="address">
            <FormItem>
              <FormLabel>详细地址</FormLabel>
              <FormControl>
                <Input
                  v-bind="componentField"
                  autocomplete="street-address"
                  class="h-11 sm:h-8"
                  placeholder="请输入详细地址"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          </FormField>
        </div>

        <!-- Profile Section (only in edit mode) -->
        <div v-if="mode === 'edit'" class="space-y-4 pt-4 border-t">
          <h3 class="text-sm font-medium text-muted-foreground">档案信息</h3>

          <!-- Company Background -->
          <FormField v-slot="{ componentField }" name="company_background">
            <FormItem>
              <FormLabel>公司背景</FormLabel>
              <FormControl>
                <Textarea
                  v-bind="componentField"
                  :rows="3"
                  placeholder="请输入公司背景信息"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          </FormField>

          <!-- Company Website -->
          <FormField v-slot="{ componentField }" name="company_website">
            <FormItem>
              <FormLabel>公司网站</FormLabel>
              <FormControl>
                <Input
                  v-bind="componentField"
                  type="url"
                  autocomplete="url"
                  class="h-11 sm:h-8"
                  placeholder="请输入公司网站URL"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          </FormField>

          <!-- Main Business -->
          <FormField v-slot="{ componentField }" name="main_business">
            <FormItem>
              <FormLabel>主营业务</FormLabel>
              <FormControl>
                <Textarea
                  v-bind="componentField"
                  :rows="3"
                  placeholder="请输入主营业务信息"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          </FormField>

          <!-- Project Background -->
          <FormField v-slot="{ componentField }" name="project_background">
            <FormItem>
              <FormLabel>项目背景</FormLabel>
              <FormControl>
                <Textarea
                  v-bind="componentField"
                  :rows="3"
                  placeholder="请输入项目背景信息"
                />
              </FormControl>
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
