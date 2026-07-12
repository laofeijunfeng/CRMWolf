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
import contractApi, { type ContractCreate, type ContractUpdate, type ContractResponse, type LicenseType } from '@/api/contract'
import { opportunityApi, type OpportunityListResponse } from '@/api/opportunity'
import customerApi, { type ContactResponse } from '@/api/customer'

// Zod schema for form validation - use coerce for number fields
const schema = toTypedSchema(
  z.object({
    contract_name: z.string().min(1, '请输入合同名称').max(100, '合同名称不能超过100字'),
    opportunity_id: z.coerce.number().min(1, '请选择商机'),
    signing_contact_id: z.coerce.number().min(1, '请选择签署联系人'),
    user_count: z.coerce.number().int('用户数必须为整数').min(1, '用户数至少为1'),
    total_amount: z.coerce.number().min(0, '金额不能为负数'),
    license_type: z.enum(['SUBSCRIPTION', 'PERPETUAL'], { errorMap: () => ({ message: '请选择授权类型' }) }),
    subscription_years: z.coerce.number().int('订阅年限必须为整数').min(1, '订阅年限至少为1年').optional().nullable(),
    signing_date: z.string().optional().nullable(),
    effective_date: z.string().optional().nullable()
  })
)

interface Props {
  customerId: number
  open: boolean
  contract?: ContractResponse | null
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
    contract_name: '',
    user_count: 1,
    total_amount: 0,
    license_type: 'SUBSCRIPTION',
    subscription_years: 1
  }
})

// State
const submitting = ref(false)
const isDirty = ref(false)
const showConfirmDialog = ref(false)
const opportunities = ref<OpportunityListResponse[]>([])
const contacts = ref<ContactResponse[]>([])
const loadingOpportunities = ref(false)
const loadingContacts = ref(false)

// Computed property for edit mode
const isEdit = computed(() => !!props.contract)

// Computed property for dialog visibility
const visible = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val)
})

// License type options
const licenseTypeOptions = [
  { value: 'SUBSCRIPTION', label: '订阅制' },
  { value: 'PERPETUAL', label: '买断制' }
]

// Fetch available opportunities for this customer
async function fetchOpportunities(): Promise<void> {
  loadingOpportunities.value = true
  try {
    opportunities.value = await opportunityApi.getAvailableForContract(props.customerId)
  } catch (error) {
    handleApiError(error, '获取商机列表')
  } finally {
    loadingOpportunities.value = false
  }
}

// Fetch contacts for this customer
async function fetchContacts(): Promise<void> {
  loadingContacts.value = true
  try {
    contacts.value = await customerApi.getContacts(props.customerId)
  } catch (error) {
    handleApiError(error, '获取联系人列表')
  } finally {
    loadingContacts.value = false
  }
}

// Watch for form changes
watch(values, () => {
  isDirty.value = true
}, { deep: true })

// Reset or populate form when dialog opens
watch(() => props.open, (newOpen) => {
  if (newOpen) {
    if (props.contract) {
      // Edit mode: populate form with contract data
      setValues({
        contract_name: props.contract.contract_name,
        opportunity_id: props.contract.opportunity_id,
        signing_contact_id: props.contract.signing_contact_id,
        user_count: props.contract.user_count,
        total_amount: parseFloat(props.contract.total_amount),
        license_type: props.contract.license_type,
        subscription_years: props.contract.subscription_years ?? null,
        signing_date: props.contract.signing_date ?? null,
        effective_date: props.contract.effective_date ?? null
      })
    } else {
      // Create mode: reset form
      resetForm({
        values: {
          contract_name: '',
          user_count: 1,
          total_amount: 0,
          license_type: 'SUBSCRIPTION',
          subscription_years: 1
        }
      })
    }
    // Reset dirty state after form is populated/reset
    setTimeout(() => {
      isDirty.value = false
    }, 100)
  }
})

// Fetch data on mount
onMounted(() => {
  fetchOpportunities()
  fetchContacts()
})

// Form submission
const onSubmit = handleSubmit(async (formValues) => {
  submitting.value = true
  try {
    if (isEdit.value && props.contract) {
      // Edit mode: use update
      const data: ContractUpdate = {
        contract_name: formValues['contract_name'] ?? null,
        signing_contact_id: formValues['signing_contact_id'] ?? null,
        user_count: formValues['user_count'] ?? null,
        total_amount: formValues['total_amount'] ?? null,
        license_type: formValues['license_type'] ?? null,
        subscription_years: formValues['license_type'] === 'SUBSCRIPTION' ? formValues['subscription_years'] ?? null : null,
        signing_date: formValues['signing_date'] ?? null,
        effective_date: formValues['effective_date'] ?? null
      }
      await contractApi.updateContract(props.contract.id, data)
      toast.success('合同更新成功')
    } else {
      // Create mode
      const data: ContractCreate = {
        contract_name: formValues['contract_name'],
        customer_id: props.customerId,
        opportunity_id: formValues['opportunity_id'],
        signing_contact_id: formValues['signing_contact_id'],
        user_count: formValues['user_count'],
        total_amount: formValues['total_amount'],
        license_type: formValues['license_type'] as LicenseType,
        subscription_years: formValues['license_type'] === 'SUBSCRIPTION' ? formValues['subscription_years'] ?? null : null,
        signing_date: formValues['signing_date'] ?? null,
        effective_date: formValues['effective_date'] ?? null
      }
      await contractApi.createContract(data)
      toast.success('合同创建成功')
    }

    isDirty.value = false
    visible.value = false
    emit('success')
  } catch (error) {
    handleApiError(error, isEdit.value ? '更新合同' : '创建合同')
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
        <DialogTitle>{{ isEdit ? '编辑合同' : '新建合同' }}</DialogTitle>
      </DialogHeader>

      <form class="space-y-4" @submit="onSubmit">
        <!-- Contract Name (required) -->
        <FormField v-slot="{ componentField }" name="contract_name">
          <FormItem>
            <FormLabel>合同名称 <span class="text-destructive">*</span></FormLabel>
            <FormControl>
              <Input
                v-bind="componentField as any"
                placeholder="请输入合同名称"
                class="h-11 sm:h-8"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Opportunity (required, only in create mode) -->
        <FormField v-if="!isEdit" v-slot="{ componentField }" name="opportunity_id">
          <FormItem>
            <FormLabel>关联商机 <span class="text-destructive">*</span></FormLabel>
            <Select v-bind="componentField as any">
              <FormControl>
                <SelectTrigger class="h-11 sm:h-8">
                  <SelectValue placeholder="请选择商机" />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                <SelectItem
                  v-for="opportunity in opportunities"
                  :key="opportunity.id"
                  :value="opportunity.id.toString()"
                >
                  {{ opportunity.opportunity_name }}
                </SelectItem>
              </SelectContent>
            </Select>
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Signing Contact (required) -->
        <FormField v-slot="{ componentField }" name="signing_contact_id">
          <FormItem>
            <FormLabel>签署联系人 <span class="text-destructive">*</span></FormLabel>
            <Select v-bind="componentField as any">
              <FormControl>
                <SelectTrigger class="h-11 sm:h-8">
                  <SelectValue placeholder="请选择签署联系人" />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                <SelectItem
                  v-for="contact in contacts"
                  :key="contact.id"
                  :value="contact.id.toString()"
                >
                  {{ contact.name }}{{ contact.position ? ` (${contact.position})` : '' }}
                </SelectItem>
              </SelectContent>
            </Select>
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
        <FormField v-if="values.license_type === 'SUBSCRIPTION'" v-slot="{ componentField }" name="subscription_years">
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

        <!-- Signing Date (optional) -->
        <FormField v-slot="{ componentField }" name="signing_date">
          <FormItem>
            <FormLabel>签署日期</FormLabel>
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

        <!-- Effective Date (optional) -->
        <FormField v-slot="{ componentField }" name="effective_date">
          <FormItem>
            <FormLabel>生效日期</FormLabel>
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