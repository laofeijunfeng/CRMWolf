<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { toast } from 'vue-sonner'
import { handleApiError } from '@/utils/errorHandler'
import customerApi, { type CustomerCreate, type CustomerUpdate } from '@/api/customer'
import procurementApi, { type ProcurementMethodOption } from '@/api/procurement'
import { usePageTitle } from '@/composables/usePageTitle'
import { useHeaderStore } from '@/stores/header'
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
import { Badge } from '@/components/ui/badge'
import { customerFormSchema, customerSourceOptions, companyScaleOptions, type CustomerForm } from '@/schemas/customer-form'

usePageTitle()

const router = useRouter()
const route = useRoute()
const headerStore = useHeaderStore()

onMounted(() => {
  headerStore.setBack(true)
})

onUnmounted(() => {
  headerStore.clear()
})

const loading = ref(false)
const submitting = ref(false)
const procurementMethodOptions = ref<ProcurementMethodOption[]>([])

const customerId = computed(() => Number(route.params['id']))
const isEdit = computed(() => !!customerId.value)

// Profile status related
const profileStatus = ref<string | null>(null)
const hasProfile = computed(() => profileStatus.value === 'COMPLETED')

const profileStatusConfig = computed(() => {
  switch (profileStatus.value) {
    case 'COMPLETED': return { label: '已生成', variant: 'default' as const }
    case 'GENERATING': return { label: '生成中', variant: 'secondary' as const }
    case 'PENDING': return { label: '待生成', variant: 'outline' as const }
    case 'FAILED': return { label: '生成失败', variant: 'destructive' as const }
    default: return { label: '未生成', variant: 'outline' as const }
  }
})

// VeeValidate form setup
const { handleSubmit, setValues } = useForm({
  validationSchema: toTypedSchema(customerFormSchema),
  initialValues: {
    account_name: '',
    city: '',
    address: '',
    company_scale: undefined,
    source: undefined,
    default_procurement_method_id: undefined,
    company_background: '',
    company_website: '',
    main_business: '',
    project_background: ''
  }
})

const fetchCustomerDetail = async () => {
  if (!isEdit.value) return

  loading.value = true
  try {
    const res = await customerApi.getCustomerDetail(customerId.value)
    setValues({
      account_name: res.account_name || '',
      city: res.city || '',
      address: res.address || '',
      company_scale: (res.company_scale || undefined) as CustomerForm['company_scale'],
      source: (res.source || undefined) as CustomerForm['source'],
      default_procurement_method_id: res.default_procurement_method_id || undefined,
      company_background: res.company_background || '',
      company_website: res.company_website || '',
      main_business: res.main_business || '',
      project_background: res.project_background || ''
    })
    profileStatus.value = res.profile_status
  } catch (error: unknown) {
    handleApiError(error, '获取客户详情')
    router.back()
  } finally {
    loading.value = false
  }
}

const fetchOptions = async () => {
  try {
    const procurementRes = await procurementApi.getProcurementMethodOptions()
    procurementMethodOptions.value = procurementRes || []
  } catch (error) {
    console.error('获取选项失败:', error)
  }
}

// Form submission
const onSubmit = handleSubmit(async (formValues: CustomerForm) => {
  submitting.value = true
  try {
    if (isEdit.value) {
      const updateData = {
        account_name: formValues.account_name || null,
        city: formValues.city || null,
        address: formValues.address || null,
        company_scale: formValues.company_scale || null,
        source: formValues.source || null,
        default_procurement_method_id: formValues.default_procurement_method_id || null,
        company_background: formValues.company_background || null,
        company_website: formValues.company_website || null,
        main_business: formValues.main_business || null,
        project_background: formValues.project_background || null
      } as CustomerUpdate
      await customerApi.updateCustomer(customerId.value, updateData)
      toast.success('客户更新成功')
    } else {
      const createData = {
        account_name: formValues.account_name,
        city: formValues.city,
        address: formValues.address || null,
        company_scale: formValues.company_scale || null,
        source: formValues.source || null,
        default_procurement_method_id: formValues.default_procurement_method_id || null
      } as CustomerCreate
      await customerApi.createCustomer(createData)
      toast.success('客户创建成功')
    }
    router.back()
  } catch (error: unknown) {
    handleApiError(error, isEdit.value ? '更新客户' : '创建客户')
  } finally {
    submitting.value = false
  }
})

const handleGoBack = () => {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/customers')
  }
}

onMounted(async () => {
  await fetchOptions()
  if (isEdit.value) {
    await fetchCustomerDetail()
  }
})
</script>

<template>
  <div class="customer-edit-page">
    <!-- Loading State -->
    <div v-if="loading" class="loading-container">
      <div class="loading-spinner" />
    </div>

    <!-- Form Content -->
    <div v-else class="form-container">
      <!-- Basic Info Card -->
      <div class="form-card">
        <div class="card-title">基本信息</div>
        <form class="space-y-4" @submit="onSubmit">
          <div class="form-grid">
            <!-- Customer Name -->
            <FormField v-slot="{ componentField }" name="account_name">
              <FormItem>
                <FormLabel>客户名称 <span class="text-destructive">*</span></FormLabel>
                <FormControl>
                  <Input
                    v-bind="componentField as any"
                    placeholder="请输入客户公司名称"
                    class="h-11 sm:h-8"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- City -->
            <FormField v-slot="{ componentField }" name="city">
              <FormItem>
                <FormLabel>所在城市 <span class="text-destructive">*</span></FormLabel>
                <FormControl>
                  <Input
                    v-bind="componentField as any"
                    placeholder="请输入所在城市"
                    class="h-11 sm:h-8"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>
          </div>

          <div class="form-grid">
            <!-- Source -->
            <FormField v-slot="{ componentField }" name="source">
              <FormItem>
                <FormLabel>客户来源</FormLabel>
                <Select v-bind="componentField as any">
                  <FormControl>
                    <SelectTrigger class="h-11 sm:h-8">
                      <SelectValue placeholder="请选择客户来源" />
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
                <Select v-bind="componentField as any">
                  <FormControl>
                    <SelectTrigger class="h-11 sm:h-8">
                      <SelectValue placeholder="请选择公司规模" />
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
          </div>

          <div class="form-grid">
            <!-- Default Procurement Method -->
            <FormField v-slot="{ componentField }" name="default_procurement_method_id">
              <FormItem>
                <FormLabel>默认采购方式</FormLabel>
                <Select v-bind="componentField as any">
                  <FormControl>
                    <SelectTrigger class="h-11 sm:h-8">
                      <SelectValue placeholder="请选择默认采购方式" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem
                      v-for="option in procurementMethodOptions"
                      :key="option['id']"
                      :value="option['id']"
                    >
                      {{ option.name }}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- Address -->
            <FormField v-slot="{ componentField }" name="address">
              <FormItem>
                <FormLabel>公司地址</FormLabel>
                <FormControl>
                  <Input
                    v-bind="componentField as any"
                    placeholder="请输入公司地址"
                    class="h-11 sm:h-8"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>
          </div>
        </form>
      </div>

      <!-- Profile Card (Edit mode only) -->
      <div v-if="isEdit && hasProfile" class="form-card">
        <div class="card-title">
          <span>客户档案</span>
          <Badge :variant="profileStatusConfig.variant">
            {{ profileStatusConfig.label }}
          </Badge>
        </div>

        <form class="space-y-4">
          <div class="form-grid">
            <!-- Company Website -->
            <FormField v-slot="{ componentField }" name="company_website">
              <FormItem>
                <FormLabel>公司官网</FormLabel>
                <FormControl>
                  <Input
                    v-bind="componentField as any"
                    type="url"
                    placeholder="请输入公司官网地址"
                    class="h-11 sm:h-8"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>
          </div>

          <!-- Company Background -->
          <FormField v-slot="{ componentField }" name="company_background">
            <FormItem>
              <FormLabel>企业背景</FormLabel>
              <FormControl>
                <Textarea
                  v-bind="componentField as any"
                  :rows="4"
                  placeholder="请输入企业背景介绍"
                  class="resize-none"
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
                  v-bind="componentField as any"
                  :rows="4"
                  placeholder="请输入主营业务描述"
                  class="resize-none"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          </FormField>

          <!-- Project Background -->
          <FormField v-slot="{ componentField }" name="project_background">
            <FormItem>
              <FormLabel>项目需求背景</FormLabel>
              <FormControl>
                <Textarea
                  v-bind="componentField as any"
                  :rows="4"
                  placeholder="请输入项目需求背景"
                  class="resize-none"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          </FormField>
        </form>
      </div>

      <!-- Form Actions -->
      <div class="form-actions-card">
        <Button variant="outline" type="button" @click="handleGoBack">
          取消
        </Button>
        <Button type="submit" :loading="submitting" @click="onSubmit">
          {{ isEdit ? '保存' : '创建' }}
        </Button>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.customer-edit-page {
  padding: 0;
  background: $wolf-bg-page-v2;
  min-height: calc(100vh - 56px);
}

// Loading state
.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
  padding: $wolf-page-padding-v2;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid $wolf-border-default-v2;
  border-top-color: $wolf-primary-v2;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

// Form container (full width)
.form-container {
  padding: $wolf-page-padding-v2;
}

// Form card (full width)
.form-card {
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-lg-v2;
  padding: $wolf-card-padding-v2;
  margin-bottom: $wolf-space-lg-v2;
  box-shadow: $wolf-shadow-card-v2;
}

.card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
  margin-bottom: $wolf-space-lg-v2;
  padding-bottom: $wolf-space-sm-v2;
  border-bottom: 1px solid $wolf-border-light-v2;
}

// Form grid (two columns)
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: $wolf-form-item-gap-v2;
}

// Form actions card
.form-actions-card {
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-lg-v2;
  padding: $wolf-card-padding-v2;
  box-shadow: $wolf-shadow-card-v2;
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm-v2;
}

// Responsive
@media (max-width: 768px) {
  .form-container {
    padding: $wolf-page-padding-mobile-v2;
  }

  .form-card {
    padding: $wolf-card-padding-mobile-v2;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }

  .form-actions-card {
    flex-direction: column-reverse;
  }
}
</style>