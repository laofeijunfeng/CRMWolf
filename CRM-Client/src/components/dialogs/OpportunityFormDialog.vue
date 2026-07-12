<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useForm } from 'vee-validate'
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
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { handleApiError } from '@/utils/errorHandler'
import { opportunityApi, type OpportunityCreate, LicenseType, PurchaseType } from '@/api/opportunity'
import userApi, { type UserResponse, UserStatus } from '@/api/user'
import procurementApi, { type ProcurementMethodOption } from '@/api/procurement'

// Zod schema for form validation - use coerce for number fields
const schema = toTypedSchema(
  z.object({
    opportunity_name: z.string().min(1, '请输入商机名称').max(100, '商机名称不能超过100字'),
    total_amount: z.coerce.number().min(0, '金额不能为负数'),
    user_count: z.coerce.number().int('用户数必须为整数').min(1, '用户数至少为1'),
    license_type: z.nativeEnum(LicenseType, { errorMap: () => ({ message: '请选择授权类型' }) }),
    subscription_years: z.coerce.number().int('订阅年限必须为整数').min(1, '订阅年限至少为1年').optional().nullable(),
    purchase_type: z.nativeEnum(PurchaseType, { errorMap: () => ({ message: '请选择采购类型' }) }),
    expected_closing_date: z.string().min(1, '请选择预计成交日期'),
    procurement_method_id: z.coerce.number().optional().nullable(),
    owner_id: z.string().min(1, '请选择负责人'),
    decision_maker_count: z.coerce.number().int('决策人数必须为整数').min(0, '决策人数不能为负数').optional().nullable()
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

// Get default date (30 days from now)
function getDefaultDate(): string {
  const date = new Date()
  date.setDate(date.getDate() + 30)
  return date.toISOString().split('T')[0] ?? ''
}

// VeeValidate form setup
const { handleSubmit, resetForm, values } = useForm({
  validationSchema: schema,
  initialValues: {
    opportunity_name: '',
    total_amount: 0,
    user_count: 1,
    license_type: LicenseType.SUBSCRIPTION,
    subscription_years: 1,
    purchase_type: PurchaseType.NEW,
    expected_closing_date: getDefaultDate(),
    procurement_method_id: null,
    owner_id: '',
    decision_maker_count: null
  }
})

// State
const submitting = ref(false)
const isDirty = ref(false)
const showConfirmDialog = ref(false)
const users = ref<UserResponse[]>([])
const procurementMethods = ref<ProcurementMethodOption[]>([])
const loadingUsers = ref(false)
const loadingMethods = ref(false)

// Computed property for dialog visibility
const visible = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val)
})

// License type options
const licenseTypeOptions = [
  { value: LicenseType.SUBSCRIPTION, label: '订阅制' },
  { value: LicenseType.PERPETUAL, label: '买断制' }
]

// Purchase type options
const purchaseTypeOptions = [
  { value: PurchaseType.NEW, label: '新购' },
  { value: PurchaseType.RENEWAL, label: '续购' },
  { value: PurchaseType.EXPANSION, label: '增购' }
]

// Fetch users for owner selection
async function fetchUsers(): Promise<void> {
  loadingUsers.value = true
  try {
    users.value = await userApi.getUsers({ status: UserStatus.ACTIVE })
  } catch (error) {
    handleApiError(error, '获取用户列表')
  } finally {
    loadingUsers.value = false
  }
}

// Fetch procurement methods
async function fetchProcurementMethods(): Promise<void> {
  loadingMethods.value = true
  try {
    procurementMethods.value = await procurementApi.getProcurementMethodOptions()
  } catch (error) {
    handleApiError(error, '获取采购方式')
  } finally {
    loadingMethods.value = false
  }
}

// Watch for form changes
watch(values, () => {
  isDirty.value = true
}, { deep: true })

// Reset form when dialog opens
watch(() => props.open, (newOpen) => {
  if (newOpen) {
    resetForm({
      values: {
        opportunity_name: '',
        total_amount: 0,
        user_count: 1,
        license_type: LicenseType.SUBSCRIPTION,
        subscription_years: 1,
        purchase_type: PurchaseType.NEW,
        expected_closing_date: getDefaultDate(),
        procurement_method_id: null,
        owner_id: '',
        decision_maker_count: null
      }
    })
    isDirty.value = false
  }
})

// Fetch data on mount
onMounted(() => {
  fetchUsers()
  fetchProcurementMethods()
})

// Form submission
const onSubmit = handleSubmit(async (formValues) => {
  submitting.value = true
  try {
    const data: OpportunityCreate = {
      opportunity_name: formValues['opportunity_name'],
      customer_id: props.customerId,
      total_amount: formValues['total_amount'],
      user_count: formValues['user_count'],
      license_type: formValues['license_type'],
      subscription_years: formValues['license_type'] === LicenseType.SUBSCRIPTION ? formValues['subscription_years'] ?? null : null,
      purchase_type: formValues['purchase_type'],
      expected_closing_date: formValues['expected_closing_date'],
      procurement_method_id: formValues['procurement_method_id'] ?? null,
      owner_id: formValues['owner_id'],
      decision_maker_count: formValues['decision_maker_count'] ?? null
    }

    await opportunityApi.createOpportunity(data)
    toast.success('商机创建成功')

    isDirty.value = false
    visible.value = false
    emit('success')
  } catch (error) {
    handleApiError(error, '创建商机')
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
    <DialogContent class="sm:max-w-[500px] max-h-[90vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle>新建商机</DialogTitle>
      </DialogHeader>

      <form class="space-y-4" @submit="onSubmit">
        <!-- Opportunity Name (required) -->
        <FormField v-slot="{ componentField }" name="opportunity_name">
          <FormItem>
            <FormLabel>商机名称 <span class="text-destructive">*</span></FormLabel>
            <FormControl>
              <Input
                v-bind="componentField as any"
                placeholder="请输入商机名称"
                class="h-11 sm:h-8"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Total Amount (required) -->
        <FormField v-slot="{ componentField }" name="total_amount">
          <FormItem>
            <FormLabel>总金额 <span class="text-destructive">*</span></FormLabel>
            <FormControl>
              <Input
                v-bind="componentField as any"
                type="number"
                step="0.01"
                min="0"
                placeholder="请输入总金额"
                class="h-11 sm:h-8"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- User Count (required) -->
        <FormField v-slot="{ componentField }" name="user_count">
          <FormItem>
            <FormLabel>用户数 <span class="text-destructive">*</span></FormLabel>
            <FormControl>
              <Input
                v-bind="componentField as any"
                type="number"
                min="1"
                placeholder="请输入用户数"
                class="h-11 sm:h-8"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- License Type (Select) -->
        <FormField v-slot="{ componentField }" name="license_type">
          <FormItem>
            <FormLabel>授权类型 <span class="text-destructive">*</span></FormLabel>
            <Select v-bind="componentField as any">
              <FormControl>
                <SelectTrigger class="h-11 sm:h-8">
                  <SelectValue placeholder="请选择授权类型" />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                <SelectItem
                  v-for="option in licenseTypeOptions"
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

        <!-- Subscription Years (optional, only for SUBSCRIPTION) -->
        <FormField v-if="values.license_type === LicenseType.SUBSCRIPTION" v-slot="{ componentField }" name="subscription_years">
          <FormItem>
            <FormLabel>订阅年限</FormLabel>
            <FormControl>
              <Input
                v-bind="componentField as any"
                type="number"
                min="1"
                max="10"
                placeholder="请输入订阅年限"
                class="h-11 sm:h-8"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Purchase Type (Select) -->
        <FormField v-slot="{ componentField }" name="purchase_type">
          <FormItem>
            <FormLabel>采购类型 <span class="text-destructive">*</span></FormLabel>
            <Select v-bind="componentField as any">
              <FormControl>
                <SelectTrigger class="h-11 sm:h-8">
                  <SelectValue placeholder="请选择采购类型" />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                <SelectItem
                  v-for="option in purchaseTypeOptions"
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

        <!-- Expected Closing Date (required) -->
        <FormField v-slot="{ componentField }" name="expected_closing_date">
          <FormItem>
            <FormLabel>预计成交日期 <span class="text-destructive">*</span></FormLabel>
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

        <!-- Procurement Method (optional) -->
        <FormField v-slot="{ componentField }" name="procurement_method_id">
          <FormItem>
            <FormLabel>采购方式</FormLabel>
            <Select v-bind="componentField as any">
              <FormControl>
                <SelectTrigger class="h-11 sm:h-8">
                  <SelectValue placeholder="请选择采购方式" />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                <SelectItem
                  v-for="method in procurementMethods"
                  :key="method.id"
                  :value="method.id.toString()"
                >
                  {{ method.name }}
                </SelectItem>
              </SelectContent>
            </Select>
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Owner (required) -->
        <FormField v-slot="{ componentField }" name="owner_id">
          <FormItem>
            <FormLabel>负责人 <span class="text-destructive">*</span></FormLabel>
            <Select v-bind="componentField as any">
              <FormControl>
                <SelectTrigger class="h-11 sm:h-8">
                  <SelectValue placeholder="请选择负责人" />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                <SelectItem
                  v-for="user in users"
                  :key="user.id"
                  :value="user.id.toString()"
                >
                  {{ user.name }}
                </SelectItem>
              </SelectContent>
            </Select>
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Decision Maker Count (optional) -->
        <FormField v-slot="{ componentField }" name="decision_maker_count">
          <FormItem>
            <FormLabel>决策人数</FormLabel>
            <FormControl>
              <Input
                v-bind="componentField as any"
                type="number"
                min="0"
                placeholder="请输入决策人数"
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